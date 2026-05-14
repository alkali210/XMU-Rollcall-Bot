import time
import builtins
import logging
from .verify import send_code, send_radar, base_url
from .config import get_rollcall_settings

logger = logging.getLogger(__name__)
WAIT_POLL_INTERVAL = 3

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

def _is_signed_student(student):
    if not isinstance(student, dict):
        return False
    if student.get("updated_at") or student.get("answered_at") or student.get("submitted_at"):
        return True
    status = str(student.get("status") or "").lower()
    return status in {"present", "signed", "success", "on_call_fine", "attended"}

def _fetch_signed_count(session, rollcall_id):
    """Query current number of students who have already signed."""
    try:
        resp = session.get(
            f"{base_url}/api/rollcall/{rollcall_id}/student_rollcalls",
            timeout=10,
        )
        if resp.status_code == 200:
            students = _extract_student_rollcalls(resp.json())
            return sum(1 for student in students if _is_signed_student(student))
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

    print(f"Waiting for {target} classmate(s) to answer before signing...")
    while True:
        count = _fetch_signed_count(session, rollcall_id)
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
