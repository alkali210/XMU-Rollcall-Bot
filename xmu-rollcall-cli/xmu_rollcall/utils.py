import os
import json
import requests
from . import secure_store
from .config import get_cookies_path

base_url = "https://lnt.xmu.edu.cn"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def clear_screen():
    """清屏"""
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')

def _is_account_id(value):
    return isinstance(value, int) or (isinstance(value, str) and value.isdigit())

def save_session(sess: requests.Session, path: str):
    """保存session到加密SQLite；传入文件路径时兼容旧版JSON行为"""
    try:
        cj_dict = requests.utils.dict_from_cookiejar(sess.cookies)
        if _is_account_id(path):
            secure_store.save_session(int(path), cj_dict)
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cj_dict, f)
    except Exception:
        pass

def load_session(sess: requests.Session, path: str):
    """从加密SQLite加载session；必要时兼容迁移旧版JSON cookies"""
    try:
        if _is_account_id(path):
            account_id = int(path)
            cj_dict = secure_store.load_session(account_id)
            if cj_dict is None:
                legacy_path = get_cookies_path(account_id)
                with open(legacy_path, "r", encoding="utf-8") as f:
                    cj_dict = json.load(f)
                secure_store.save_session(account_id, cj_dict)
                try:
                    os.remove(legacy_path)
                except OSError:
                    pass
            sess.cookies = requests.utils.cookiejar_from_dict(cj_dict)
            return True

        with open(path, "r", encoding="utf-8") as f:
            cj_dict = json.load(f)
        sess.cookies = requests.utils.cookiejar_from_dict(cj_dict)
        return True
    except Exception:
        return False

def verify_session(sess: requests.Session) -> dict:
    """验证session是否有效"""
    try:
        resp = sess.get(f"{base_url}/api/profile", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "name" in data:
                return data
    except Exception:
        pass
    return {}
