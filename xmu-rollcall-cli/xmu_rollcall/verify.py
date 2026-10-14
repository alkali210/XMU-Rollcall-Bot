import uuid
import time
import builtins
import logging
from datetime import datetime, timedelta, timezone
import requests
from . import tui
from .network import REQUEST_TIMEOUT, is_retryable

logger = logging.getLogger(__name__)

base_url = "https://lnt.xmu.edu.cn"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://ids.xmu.edu.cn/authserver/login",
}


def log_and_print(*args, **kwargs):
    if not tui.rollcall_output_active():
        builtins.print(*args, **kwargs)
    sep = kwargs.get("sep", " ")
    message = sep.join(str(arg) for arg in args).strip()
    if message:
        logger.info(message)

def _api_headers(in_session=None):
    """Build JSON API headers while preserving cookies/auth from the session."""
    session_headers = getattr(in_session, "headers", {}) or {}
    return {
        **headers,
        **session_headers,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{base_url}/",
    }

def get_number_rollcall_info(in_session, rollcall_id):
    """Return (code, status, end_time, error) for this rollcall via the timetable API."""
    request_headers = _api_headers(in_session)
    try:
        detail_response = in_session.get(
            f"{base_url}/api/rollcall/{rollcall_id}",
            headers=request_headers, timeout=REQUEST_TIMEOUT,
        )
        detail_response.raise_for_status()
        detail = detail_response.json()
        if not isinstance(detail, dict) or not detail.get("course_id") or not detail.get("rollcall_time"):
            return None, None, None, "Failed to get rollcall course or time from API response."
        rollcall_date = datetime.fromisoformat(detail["rollcall_time"]).astimezone(
            timezone(timedelta(hours=8))
        ).date().isoformat()
        code_response = in_session.get(
            f"{base_url}/api/timetable_rollcalls",
            params={"course_ids": detail["course_id"], "rollcall_date": rollcall_date},
            headers=request_headers, timeout=REQUEST_TIMEOUT,
        )
        code_response.raise_for_status()
        code_data = code_response.json()
    except ValueError as e:
        return None, None, None, f"Failed to parse number code API response: {e}"
    except requests.RequestException as e:
        if is_retryable(e):
            raise
        return None, None, None, f"Failed to request number code API: {e}"

    rollcalls = code_data.get("rollcalls") if isinstance(code_data, dict) else None
    if not isinstance(rollcalls, list):
        return None, None, None, "Failed to get rollcalls from timetable API response."
    for rollcall in rollcalls:
        if not isinstance(rollcall, dict) or str(rollcall.get("id")) != str(rollcall_id):
            continue
        number_code = rollcall.get("number_code")
        status, end_time = rollcall.get("status"), rollcall.get("end_time")
        if number_code is None or str(number_code).strip() == "":
            return None, status, end_time, "Failed to get number code. 'number_code' not found in API response."
        return str(number_code), status, end_time, None
    return None, None, None, f"Rollcall {rollcall_id} not found in timetable API response."


def submit_number_code(in_session, rollcall_id, number_code, status=None, end_time=None, started_at=None):
    print = log_and_print
    answer_url = f"{base_url}/api/rollcall/{rollcall_id}/answer_number_rollcall"
    t00 = started_at or time.time()

    payload = {
        "deviceId": str(uuid.uuid4()),
        "numberCode": number_code
    }
    request_headers = _api_headers(in_session)
    try:
        response = in_session.put(answer_url, json=payload, headers=request_headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        if response.status_code == 200:
            print("Number code rollcall answered successfully.")
            tui.update_rollcall(state="success")
            time.sleep(5)
            t01 = time.time()
            print(f"Time: {t01 - t00:.2f} s.")
            return True
        t01 = time.time()
        print(f"Failed to submit number code. Status: {response.status_code}\nTime: {t01 - t00:.2f} s.")
        return False
    except requests.RequestException as e:
        if is_retryable(e):
            raise
        t01 = time.time()
        print(f"Failed to submit number code: {e}\nTime: {t01 - t00:.2f} s.")
        return False

def send_code(in_session, rollcall_id, before_submit=None):
    print = log_and_print
    print("Trying number code from API...")
    t00 = time.time()

    number_code, status, end_time, error = get_number_rollcall_info(in_session, rollcall_id)
    if error:
        t01 = time.time()
        print(f"{error}\nTime: {t01 - t00:.2f} s.")
        return False

    print("Number code obtained from API.")
    print("Number code: ", number_code)
    if status or end_time:
        logger.info(
            "Number rollcall API info: rollcall_id=%s status=%s end_time=%s",
            rollcall_id,
            status,
            end_time,
        )
    if before_submit is not None:
        before_submit(number_code, status, end_time)

    return submit_number_code(
        in_session,
        rollcall_id,
        number_code,
        status=status,
        end_time=end_time,
        started_at=t00,
    )

