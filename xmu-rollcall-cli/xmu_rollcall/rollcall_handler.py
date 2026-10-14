import time
import logging
from . import network, tui
from .network import is_retryable
from decimal import Decimal, ROUND_CEILING
from datetime import datetime
from .verify import send_code
from .config import get_rollcall_settings, normalize_rollcall_settings

logger = logging.getLogger(__name__)
WAIT_POLL_INTERVAL = 5
SIGNED_ROLLCALL_STATUS = "on_call_fine"


def _extract_student_rollcalls(payload):
    if isinstance(payload, dict):
        students = payload.get("student_rollcalls")
        if isinstance(students, list):
            return students
        nested_data = payload.get("data")
        if isinstance(nested_data, dict):
            return _extract_student_rollcalls(nested_data)
    return []

def _is_signed_student(student):
    """Return True when Tronclass marks this student as already signed.

    The student_rollcalls API returns every classmate with explicit state
    fields.  In observed payloads, signed rows look like:
    ``{"rollcall_status": "on_call_fine", "status": "on_call"}``, while
    students who have not signed yet during an active rollcall do not need to
    be inferred from any negative status.  Therefore the wait strategy counts
    only the positive ``rollcall_status == "on_call_fine"`` signal and must not
    infer signed state from ``updated_at`` or from ``status``.
    """
    if not isinstance(student, dict):
        return False
    rollcall_status = str(student.get("rollcall_status") or "").lower()
    return rollcall_status == SIGNED_ROLLCALL_STATUS

def _count_signed_students(students):
    """Count classmates who have already signed according to API statuses."""
    valid_students = [student for student in students if isinstance(student, dict)]
    count = sum(1 for student in valid_students if _is_signed_student(student))
    logger.debug(
        "Signed count by API status: count=%s total=%s",
        count,
        len(valid_students),
    )
    return count

def _fetch_attendance(session, rollcall_id):
    """Return signed and total students, or None for unavailable data."""
    try:
        resp = session.get(
            f"{network.BASE_URL}/api/rollcall/{rollcall_id}/student_rollcalls",
            timeout=10,
        )
        resp.raise_for_status()
        if resp.status_code == 200:
            students = _extract_student_rollcalls(resp.json())
            if not students or any(not isinstance(student, dict) for student in students):
                return None
            return _count_signed_students(students), len(students)
    except Exception as exc:
        if is_retryable(exc):
            raise
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

def _wait_status_line(count_text, target, number_code=None):
    code_text = f" | Number code: {number_code}" if number_code else ""
    return f"\r  Signed: {count_text}/{target}{code_text}"

def wait_for_classmates(session, rollcall_id, settings, number_code=None, *, end_time):
    """Return whether submission may proceed; stop waiting at the API deadline."""
    print = tui.log_and_print
    try:
        deadline = datetime.fromisoformat(end_time).timestamp() if end_time else None
    except (TypeError, ValueError, OverflowError, OSError):
        deadline = None
        logger.warning("Invalid end_time for rollcall_id=%s: %r; waiting without a deadline", rollcall_id, end_time)

    def expired():
        if deadline is not None and time.time() >= deadline:
            print(f"\nRollcall {rollcall_id} expired at {end_time}; stop waiting without submitting.")
            return True
        return False

    if expired():
        return False
    settings = normalize_rollcall_settings(settings)
    wait_value = settings["wait_before_answer"]
    percentage = (Decimal(wait_value[:-1])
                  if isinstance(wait_value, str) and wait_value.endswith("%") else None)
    target = _choose_wait_target(settings)
    if percentage is None and target <= 0:
        return True

    target_label = f"{percentage}% of students" if percentage is not None else f"{target} classmate(s)"
    tui.update_rollcall(state="waiting", target_label=target_label, number_code=number_code)
    print(f"Waiting for {target_label} to answer before signing...")
    if number_code:
        print(f"Number code: {number_code}")
    while True:
        if expired():
            return False
        attendance = _fetch_attendance(session, rollcall_id)
        if expired():
            return False
        count = attendance[0] if attendance is not None else None
        if count is not None:
            if percentage is not None:
                total = attendance[1]
                target = int((percentage * total / 100).to_integral_value(rounding=ROUND_CEILING))
                display_target = f"{total} | Target: {percentage}% ({target} students)"
            else:
                display_target = target
            tui.update_rollcall(signed=count, total=attendance[1], target=target,
                                target_label=f"{target_label} ({target} students)" if percentage is not None else target_label)
            print(_wait_status_line(count, display_target, number_code), end="", flush=True)
            if count >= target:
                print()
                return True
        else:
            tui.update_rollcall(signed=None, total=None)
            code_text = f" | Number code: {number_code}" if number_code else ""
            print(f"\r  Signed: unknown | Target: {target_label}, retrying...{code_text}", end="", flush=True)

        sleep_seconds = WAIT_POLL_INTERVAL
        if deadline is not None:
            sleep_seconds = min(sleep_seconds, max(0, deadline - time.time()))
        time.sleep(sleep_seconds)

def process_rollcalls(data, session, account=None):
    """处理签到数据"""
    result = handle_rollcalls(data, session, account)
    return {'rollcalls': []} if False in result else data

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
    print = tui.log_and_print
    count, rollcalls = extract_rollcalls(data)
    answer_status = [False for _ in range(count)]
    settings = get_rollcall_settings(account or {})

    if count:
        print(time.strftime("%H:%M:%S", time.localtime()), f"New rollcall(s) found!\n")
        for i in range(count):
            tui.update_rollcall(rollcall=rollcalls[i], index=i + 1, count=count)
            print(f"{i+1} of {count}:")
            print(f"Course name: {rollcalls[i]['course_title']}, rollcall created by {rollcalls[i]['department_name']} {rollcalls[i]['created_by_name']}.")

            if rollcalls[i]['is_radar']:
                logger.info("Radar rollcall detected: rollcall_id=%s", rollcalls[i]['rollcall_id'])
                temp_str = "Radar rollcall"
            elif rollcalls[i]['is_number']:
                temp_str = "Number rollcall"
            else:
                temp_str = "QRcode rollcall"
            print(f"Rollcall type: {temp_str}\n")

            if (rollcalls[i]['status'] == 'absent') & (rollcalls[i]['is_number']) & (not rollcalls[i]['is_radar']):
                def before_submit(_number_code, _status, _end_time, rollcall_id=rollcalls[i]['rollcall_id']):
                    tui.update_rollcall(number_code=_number_code)
                    if not wait_for_classmates(
                        session, rollcall_id, settings, number_code=_number_code, end_time=_end_time
                    ):
                        return False
                    tui.update_rollcall(state="submitting")
                    return True

                if send_code(session, rollcalls[i]['rollcall_id'], before_submit=before_submit):
                    answer_status[i] = True
                else:
                    print("Answering failed.")
                tui.update_rollcall(state="success" if answer_status[i] else "failed")
            elif rollcalls[i]['status'] == 'on_call_fine':
                print("Already answered.")
                answer_status[i] = True
                tui.update_rollcall(state="already")
            else:
                print(f"Answering failed. {temp_str} not supported yet.")
                print("Waiting for 5 minutes before next attempt...")
                tui.update_rollcall(state="unsupported")
                time.sleep(300)

    return answer_status
