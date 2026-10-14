import os
import requests
from . import secure_store
from .network import REQUEST_TIMEOUT

base_url = "https://lnt.xmu.edu.cn"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    )
}

def clear_screen():
    """清屏"""
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')


def save_session(sess: requests.Session, account_id: int):
    """保存会话 Cookie 到加密 SQLite。"""
    try:
        cj_dict = requests.utils.dict_from_cookiejar(sess.cookies)
        secure_store.save_session(account_id, cj_dict)
    except Exception:
        pass

def load_session(sess: requests.Session, account_id: int):
    """从加密 SQLite 加载会话 Cookie。"""
    try:
        cj_dict = secure_store.load_session(account_id)
        if cj_dict is None:
            return False
        sess.cookies = requests.utils.cookiejar_from_dict(cj_dict)
        return True
    except Exception:
        return False

def verify_session(sess: requests.Session) -> dict:
    """验证session是否有效"""
    try:
        resp = sess.get(f"{base_url}/api/profile", headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code not in (401, 403):
            resp.raise_for_status()
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "name" in data:
                return data
    except ValueError:
        # Requests JSONDecodeError is also a RequestException: an invalid
        # profile must allow credential login, not propagate as a network error.
        pass
    except requests.exceptions.SSLError:
        # SSL error may occur when start the monitor, even if the connection is stable.
        # Let it be handled by the caller, and retry with password.
        pass
    except requests.RequestException:
        raise
    return {}
