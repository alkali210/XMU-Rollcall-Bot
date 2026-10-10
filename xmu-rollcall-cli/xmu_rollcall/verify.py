import uuid
import time
import math
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

def send_radar(in_session, rollcall_id):
    print = log_and_print
    url = f"{base_url}/api/rollcall/{rollcall_id}/answer"

    lat_1, lat_2 = 24.3, 24.6
    lon_1, lon_2 = 118.0, 118.2

    def payload(lat, lon):
        return {
            "accuracy": 35,
            "altitude": 0,
            "altitudeAccuracy": None,
            "deviceId": str(uuid.uuid4()),
            "heading": None,
            "latitude": lat,
            "longitude": lon,
            "speed": None
        }

    res_1 = in_session.put(url, json=payload(lat_1, lon_1), headers=headers, timeout=REQUEST_TIMEOUT)
    if res_1.status_code in (408, 429, 500, 502, 503, 504):
        res_1.raise_for_status()
    data_1 = res_1.json()

    if res_1.status_code == 200:
        return True

    res_2 = in_session.put(url, json=payload(lat_2, lon_2), headers=headers, timeout=REQUEST_TIMEOUT)
    if res_2.status_code in (408, 429, 500, 502, 503, 504):
        res_2.raise_for_status()
    data_2 = res_2.json()

    if res_2.status_code == 200:
        return True

    distance_1 = data_1.get("distance")
    distance_2 = data_2.get("distance")

    def latlon_to_xy(lat, lon, lat0, lon0):
        R = 6371000
        x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
        y = math.radians(lat - lat0) * R
        return x, y

    def xy_to_latlon(x, y, lat0, lon0):
        R = 6371000
        lat = lat0 + math.degrees(y / R)
        lon = lon0 + math.degrees(x / (R * math.cos(math.radians(lat0))))
        return lat, lon

    def circle_intersections(x1, y1, d1, x2, y2, d2):
        D = math.hypot(x2 - x1, y2 - y1)

        if D > d1 + d2 or D < abs(d1 - d2):
            return None

        a = (d1**2 - d2**2 + D**2) / (2 * D)
        h = math.sqrt(d1**2 - a**2)

        xm = x1 + a * (x2 - x1) / D
        ym = y1 + a * (y2 - y1) / D

        rx = -(y2 - y1) * (h / D)
        ry = (x2 - x1) * (h / D)

        p1 = (xm + rx, ym + ry)
        p2 = (xm - rx, ym - ry)
        return p1, p2

    def solve_two_points(lat1, lon1, lat2, lon2, d1, d2):
        lat0 = (lat1 + lat2) / 2
        lon0 = (lon1 + lon2) / 2
        x1, y1 = latlon_to_xy(lat1, lon1, lat0, lon0)
        x2, y2 = latlon_to_xy(lat2, lon2, lat0, lon0)

        sols = circle_intersections(x1, y1, d1, x2, y2, d2)
        if sols is None:
            return None

        p1 = xy_to_latlon(sols[0][0], sols[0][1], lat0, lon0)
        p2 = xy_to_latlon(sols[1][0], sols[1][1], lat0, lon0)
        return p1, p2

    resolutions = solve_two_points(lat_1, lon_1, lat_2, lon_2, distance_1, distance_2)
    if resolutions:
        ((sol_x_1, sol_y_1), (sol_x_2, sol_y_2)) = resolutions
    else:
        return False

    payload_1 = payload(sol_x_1, sol_y_1)
    payload_2 = payload(sol_x_2, sol_y_2)

    res_3 = in_session.put(url, json=payload_1, headers=headers, timeout=REQUEST_TIMEOUT)
    if res_3.status_code in (408, 429, 500, 502, 503, 504):
        res_3.raise_for_status()
    if res_3.status_code == 200:
        return True
    else:
        print(res_3.json())
        res_4 = in_session.put(url, json=payload_2, headers=headers, timeout=REQUEST_TIMEOUT)
        if res_4.status_code in (408, 429, 500, 502, 503, 504):
            res_4.raise_for_status()
        if res_4.status_code == 200:
            return True

    return False
