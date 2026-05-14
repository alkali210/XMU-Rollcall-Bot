import time
import builtins
import logging
from datetime import datetime, timezone, timedelta
from .verify import send_code, send_radar, base_url
from .config import get_rollcall_settings

logger = logging.getLogger(__name__)
WAIT_POLL_INTERVAL = 3
SIGNED_STATUSES = {
    "present",
    "signed",
    "success",
    "on_call_fine",
    "attended",
    "late",
    "已签到",
    "签到成功",
}
SIGNED_TIME_FIELDS = (
    "answered_at",
    "submitted_at",
    "submit_time",
    "signed_at",
    "answer_time",
    "checkin_time",
)

def log_and_print(*args, **kwargs):
    builtins.print(*args, **kwargs)
    sep = kwargs.get("sep", " ")
    message = sep.join(str(arg) for arg in args).strip()
    if message:
        logger.info(message)

def _extract_student_rollcalls(payload):
    if isinstance(payload, dict):
        students = payload.get("student_rollcalls")
        if isinstance(students, list):
            return students
        nested_data = payload.get("data")
        if isinstance(nested_data, dict):
            return _extract_student_rollcalls(nested_data)
    return []

def _parse_api_time(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Tronclass is a China campus system; if it ever returns a timestamp
        # without an offset, treat it as Beijing time rather than UTC.
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed.astimezone(timezone.utc)

def _is_signed_student(student):
    """Return True for explicit signed signals only.

    Tronclass also exposes ``updated_at`` on ``student_rollcalls``, but in
    practice that field may be populated for every roster row as soon as the
    rollcall is created.  Counting a bare ``updated_at`` therefore causes the
    "68/10 immediately" false positive seen in the log.  Raw ``updated_at`` is
    handled separately with safeguards in ``_count_signed_students``.
    """
    if not isinstance(student, dict):
        return False
    if any(student.get(field) for field in SIGNED_TIME_FIELDS):
        return True
    status = str(student.get("status") or "").lower()
    return status in SIGNED_STATUSES

def _updated_at_changed_from_creation(student):
    updated_at = student.get("updated_at")
    created_at = student.get("created_at")
    if not updated_at or not created_at:
        return False

    updated_dt = _parse_api_time(updated_at)
    created_dt = _parse_api_time(created_at)
    if updated_dt and created_dt:
        return updated_dt > created_dt
    return str(updated_at) != str(created_at)

def _updated_at_after(student, threshold):
    if threshold is None or not student.get("updated_at"):
        return False
    updated_dt = _parse_api_time(student.get("updated_at"))
    if updated_dt is None:
        return False
    return updated_dt > threshold

def _count_signed_students(students, updated_after=None):
    """Count classmates who have likely signed.

    The reference project simply counts non-empty ``updated_at`` values.  That
    fixes Tronclass payloads where signing only changes ``updated_at``, but it
    overcounts when Tronclass pre-populates ``updated_at`` for every roster row.
    This implementation keeps the useful part of that strategy while avoiding
    the unsafe "all rows are already signed" interpretation:

    * explicit signed status/time fields always count;
    * ``updated_at > created_at`` counts when both fields are present;
    * while actively waiting, ``updated_at`` after the wait start counts;
    * as a compatibility fallback, sparse ``updated_at`` values count when not
      every row has one.
    """
    valid_students = [student for student in students if isinstance(student, dict)]
    total = len(valid_students)
    if total == 0:
        return 0

    explicit_count = sum(1 for student in valid_students if _is_signed_student(student))
    changed_count = sum(1 for student in valid_students if _updated_at_changed_from_creation(student))
    after_wait_count = sum(1 for student in valid_students if _updated_at_after(student, updated_after))
    raw_updated_count = sum(1 for student in valid_students if student.get("updated_at"))

    if after_wait_count:
        count = max(explicit_count, changed_count, after_wait_count)
    elif changed_count:
        count = max(explicit_count, changed_count)
    elif explicit_count:
        count = explicit_count
    elif 0 < raw_updated_count < total:
        count = raw_updated_count
    else:
        count = 0

    logger.debug(
        "Signed count signals: count=%s total=%s explicit=%s changed_updated_at=%s "
        "after_wait_updated_at=%s raw_updated_at=%s",
        count,
        total,
        explicit_count,
        changed_count,
        after_wait_count,
        raw_updated_count,
    )
    return count

def _fetch_signed_count(session, rollcall_id, updated_after=None):
    """Query current number of students who have already signed."""
    try:
        resp = session.get(
            f"{base_url}/api/rollcall/{rollcall_id}/student_rollcalls",
            timeout=10,
        )
        if resp.status_code == 200:
            students = _extract_student_rollcalls(resp.json())
            return _count_signed_students(students, updated_after=updated_after)
    except Exception as exc:
        logger.debug("Failed to fetch signed count for rollcall_id=%s: %s", rollcall_id, exc)
    return None

def _choose_wait_target(settings):
    wait_value = settings.get("wait_before_answer", False)
    if wait_value is False:
        return 0
    try:
        wait_count = int(wait_value)
    except (TypeError, ValueError):
        return 0
    return wait_count if wait_count > 0 else 0

def wait_for_classmates(session, rollcall_id, settings):
    """Wait until enough classmates have signed before answering."""
    print = log_and_print
    target = _choose_wait_target(settings)
    if target <= 0:
        return

    wait_started_at = datetime.now(timezone.utc)
    print(f"Waiting for {target} classmate(s) to answer before signing...")
    while True:
        count = _fetch_signed_count(session, rollcall_id, updated_after=wait_started_at)
        if count is not None:
            print(f"\r  Signed: {count}/{target}", end="", flush=True)
            if count >= target:
                print()
                return
        else:
            print("\r  Signed: unknown, retrying...", end="", flush=True)

        time.sleep(WAIT_POLL_INTERVAL)

def process_rollcalls(data, session, account=None):
    """处理签到数据"""
    data_empty = {'rollcalls': []}
    result = handle_rollcalls(data, session, account)
    if False in result:
        return data_empty
    else:
        return data

def extract_rollcalls(data):
    """提取签到信息"""
    rollcalls = data['rollcalls']
    result = []
    if rollcalls:
        rollcall_count = len(rollcalls)
        for rollcall in rollcalls:
            result.append({
                'course_title': rollcall['course_title'],
                'created_by_name': rollcall['created_by_name'],
                'department_name': rollcall['department_name'],
                'is_expired': rollcall['is_expired'],
                'is_number': rollcall['is_number'],
                'is_radar': rollcall['is_radar'],
                'rollcall_id': rollcall['rollcall_id'],
                'rollcall_status': rollcall['rollcall_status'],
                'scored': rollcall['scored'],
                'status': rollcall['status']
            })
    else:
        rollcall_count = 0
    return rollcall_count, result

def handle_rollcalls(data, session, account=None):
    """处理签到流程"""
    print = log_and_print
    count, rollcalls = extract_rollcalls(data)
    answer_status = [False for _ in range(count)]
    settings = get_rollcall_settings(account or {})

    if count:
        print(time.strftime("%H:%M:%S", time.localtime()), f"New rollcall(s) found!\n")
        for i in range(count):
            print(f"{i+1} of {count}:")
            print(f"Course name: {rollcalls[i]['course_title']}, rollcall created by {rollcalls[i]['department_name']} {rollcalls[i]['created_by_name']}.")

            if rollcalls[i]['is_radar']:
                temp_str = "Radar rollcall"
            elif rollcalls[i]['is_number']:
                temp_str = "Number rollcall"
            else:
                temp_str = "QRcode rollcall"
            print(f"Rollcall type: {temp_str}\n")

            if (rollcalls[i]['status'] == 'absent') & (rollcalls[i]['is_number']) & (not rollcalls[i]['is_radar']):
                def before_submit(_number_code, _status, _end_time, rollcall_id=rollcalls[i]['rollcall_id']):
                    wait_for_classmates(session, rollcall_id, settings)

                if send_code(session, rollcalls[i]['rollcall_id'], before_submit=before_submit):
                    answer_status[i] = True
                else:
                    print("Answering failed.")
            elif rollcalls[i]['status'] == 'on_call_fine':
                print("Already answered.")
                answer_status[i] = True
            elif rollcalls[i]['is_radar']:
                wait_for_classmates(session, rollcalls[i]['rollcall_id'], settings)
                if send_radar(session, rollcalls[i]['rollcall_id']):
                    answer_status[i] = True
                else:
                    print("Answering failed.")
            else:
                # TODO: qrcode rollcall
                print("Answering failed. QRcode rollcall not supported yet.")
                print("Waiting for 5 minutes before next attempt...")
                time.sleep(300)

    return answer_status
