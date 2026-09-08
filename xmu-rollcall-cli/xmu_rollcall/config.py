import os
import json
import math
from pathlib import Path
from . import secure_store

def get_config_dir():
    """
    获取配置目录路径，支持沙盒环境（如 a-Shell）
    优先级：
    1. 环境变量 XMU_ROLLCALL_CONFIG_DIR
    2. 用户主目录下的 .xmu_rollcall（如果可访问）
    3. 当前工作目录下的 .xmu_rollcall（沙盒环境备用方案）
    """
    # 优先使用环境变量指定的路径
    if env_path := os.environ.get("XMU_ROLLCALL_CONFIG_DIR"):
        return Path(env_path)

    # 尝试使用用户主目录
    try:
        home_config_dir = Path.home() / ".xmu_rollcall"
        # 测试是否可以创建目录（检测沙盒权限）
        home_config_dir.mkdir(parents=True, exist_ok=True)
        # 测试是否可以写入文件
        test_file = home_config_dir / ".test_write"
        try:
            test_file.touch()
            test_file.unlink()
            return home_config_dir
        except (OSError, PermissionError):
            pass
    except (OSError, PermissionError, RuntimeError):
        pass

    # 降级到当前工作目录（适用于沙盒环境）
    return Path.cwd() / ".xmu_rollcall"

CONFIG_DIR = get_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
secure_store.configure(CONFIG_DIR)

DEFAULT_CONFIG = {
    "accounts": [],
    "current_account_id": None,
    "interval": 10,
}

DEFAULT_INTERVAL = 10


def get_interval(config):
    value = config.get("interval", DEFAULT_INTERVAL)
    try:
        interval = float(value)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
    if isinstance(value, bool) or not math.isfinite(interval) or interval <= 0:
        return DEFAULT_INTERVAL
    return interval

DEFAULT_ACCOUNT = {
    "id": 0,
    "name": "",
    "username": "",
    "password": "",
    "rollcall_settings": {
        "wait_before_answer": "10%",
    },
}

DEFAULT_ROLLCALL_SETTINGS = DEFAULT_ACCOUNT["rollcall_settings"].copy()


def normalize_rollcall_settings(settings):
    """Normalize disabled, count, or percentage-based waiting."""
    merged = DEFAULT_ROLLCALL_SETTINGS.copy()
    if not isinstance(settings, dict):
        return merged

    if "wait_before_answer" not in settings:
        return merged

    wait_value = settings.get("wait_before_answer")
    if isinstance(wait_value, str) and wait_value.strip().endswith("%"):
        try:
            percentage = float(wait_value.strip()[:-1])
        except ValueError:
            percentage = 0
        if math.isfinite(percentage) and 0 < percentage <= 100:
            merged["wait_before_answer"] = f"{percentage}%"
        else:
            merged["wait_before_answer"] = False
        return merged
    if wait_value is False or wait_value is None:
        merged["wait_before_answer"] = False
        return merged

    try:
        wait_count = int(wait_value)
    except (TypeError, ValueError, OverflowError):
        wait_count = 0

    merged["wait_before_answer"] = wait_count if wait_count > 0 else False
    return merged


def normalize_account(account):
    """Return an account with rollcall settings defaults filled in."""
    account = (account or {}).copy()
    account["rollcall_settings"] = normalize_rollcall_settings(
        account.get("rollcall_settings")
    )
    return account


def _with_stored_accounts(config, accounts):
    """Attach decrypted accounts from SQLite to an in-memory config."""
    config = (config or DEFAULT_CONFIG).copy()
    public_accounts = {item["id"]: item for item in config.get("accounts", [])
                       if isinstance(item, dict) and "id" in item}
    config["accounts"] = [normalize_account({
        **account,
        "rollcall_settings": public_accounts.get(account["id"], {}).get(
            "rollcall_settings", account.get("rollcall_settings", {})),
    }) for account in accounts]
    config["interval"] = get_interval(config)
    if config.get("current_account_id") is None and accounts:
        config["current_account_id"] = accounts[0].get("id")
    return config

def ensure_config_dir():
    """确保配置目录存在"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        raise RuntimeError(f"无法创建配置目录 {CONFIG_DIR}: {e}\n提示：可以设置环境变量 XMU_ROLLCALL_CONFIG_DIR 指定配置目录位置")

def load_config():
    """加载配置文件"""
    ensure_config_dir()
    stored_accounts = secure_store.list_accounts()
    config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Cannot read configuration {CONFIG_FILE}: {exc}") from exc
        if not isinstance(config, dict) or not isinstance(config.get("accounts", []), list):
            raise RuntimeError(f"Invalid configuration format: {CONFIG_FILE}")
        # Migrate legacy plaintext credentials without discarding public settings.
        if "accounts" not in config and config.get("username") and config.get("password"):
            config["accounts"] = [{"id": 1, "name": "",
                                   "username": config["username"],
                                   "password": config["password"]}]
            config["current_account_id"] = 1
        legacy_accounts = config.get("accounts", [])
        if any(isinstance(acc, dict) and (acc.get("username") or acc.get("password"))
               for acc in legacy_accounts):
            save_config(config)
            return config
    merged = _with_stored_accounts(config, stored_accounts)
    if (any(account.get("rollcall_settings") for account in stored_accounts)
            or "accounts" not in config or "interval" not in config):
        save_config(merged)
    return merged

def save_config(config):
    """保存配置文件"""
    ensure_config_dir()
    accounts = [normalize_account(account) for account in config.get("accounts", [])]
    if "accounts" in config:
        config["accounts"] = accounts
        secure_store.replace_accounts(accounts)
    safe_config = {
        key: value
        for key, value in config.items()
        if key != "accounts" and key not in {"username", "password", "delay"}
    }
    safe_config["interval"] = get_interval(config)
    safe_config["accounts"] = [
        {"id": account["id"], "rollcall_settings": account["rollcall_settings"]}
        for account in accounts
    ]
    temporary = CONFIG_FILE.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(safe_config, f, indent=2, ensure_ascii=False)
    os.replace(temporary, CONFIG_FILE)
    secure_store.clear_legacy_rollcall_settings()

def get_next_account_id(config):
    """获取下一个可用的账号ID"""
    accounts = config.get("accounts", [])
    if not accounts:
        return 1
    return max(acc.get("id", 0) for acc in accounts) + 1

def add_account(config, username, password, name):
    """添加新账号"""
    account_id = get_next_account_id(config)
    new_account = {
        "id": account_id,
        "name": name,
        "username": username,
        "password": password,
        "rollcall_settings": DEFAULT_ROLLCALL_SETTINGS.copy()
    }
    if "accounts" not in config:
        config["accounts"] = []
    config["accounts"].append(new_account)
    # 如果是第一个账号，设为当前账号
    if config.get("current_account_id") is None:
        config["current_account_id"] = account_id
    return account_id

def get_account_by_id(config, account_id):
    """通过ID获取账号"""
    for acc in config.get("accounts", []):
        if acc.get("id") == account_id:
            return acc
    return None

def get_current_account(config):
    """获取当前选中的账号"""
    current_id = config.get("current_account_id")
    if current_id is None:
        return None
    return get_account_by_id(config, current_id)

def set_current_account(config, account_id):
    """设置当前账号"""
    config["current_account_id"] = account_id

def get_rollcall_settings(account):
    """Return rollcall settings with defaults filled in."""
    return normalize_rollcall_settings((account or {}).get("rollcall_settings") or {})


def set_rollcall_settings(account, settings):
    """Persist normalized rollcall settings on an account."""
    account["rollcall_settings"] = normalize_rollcall_settings(settings or {})


def get_all_accounts(config):
    """获取所有账号"""
    return config.get("accounts", [])

def is_config_complete(config):
    """检查配置是否完整（至少有一个账号且已选择当前账号）"""
    current_account = get_current_account(config)
    if current_account is None:
        return False
    required_fields = ["username", "password"]
    return all(current_account.get(field) for field in required_fields)

def get_cookies_path(account_id=None):
    """获取旧版cookies文件路径，仅用于兼容迁移"""
    ensure_config_dir()
    if account_id is None:
        config = load_config()
        account_id = config.get("current_account_id", 1)
    return str(CONFIG_DIR / f"{account_id}.json")

def has_saved_session(account_id):
    """检查SQLite中是否有加密session"""
    return secure_store.has_session(account_id)

def delete_saved_session(account_id):
    """删除SQLite中的加密session"""
    secure_store.delete_session(account_id)

def delete_account(config, account_id):
    """
    删除账号并重新编号
    返回: (成功删除, 被删除账号的旧cookies路径列表, 需要重命名的cookies映射)
    """
    import os

    accounts = config.get("accounts", [])

    # 找到要删除的账号
    account_to_delete = None
    delete_index = -1
    for i, acc in enumerate(accounts):
        if acc.get("id") == account_id:
            account_to_delete = acc
            delete_index = i
            break

    if account_to_delete is None:
        return False, [], {}

    # 记录需要删除的cookies文件
    cookies_to_delete = get_cookies_path(account_id)

    # 记录需要重命名的cookies文件 (旧ID -> 新ID)
    cookies_to_rename = {}

    # 删除账号
    accounts.pop(delete_index)

    # 重新编号：所有ID大于被删除ID的账号需要向前移动
    for acc in accounts:
        old_id = acc.get("id")
        if old_id > account_id:
            new_id = old_id - 1
            old_cookies = get_cookies_path(old_id)
            new_cookies = get_cookies_path(new_id)
            if os.path.exists(old_cookies):
                cookies_to_rename[old_cookies] = new_cookies
            acc["id"] = new_id

    # 更新当前账号ID
    current_id = config.get("current_account_id")
    if current_id == account_id:
        # 删除的是当前账号，切换到第一个账号
        if accounts:
            config["current_account_id"] = accounts[0].get("id")
        else:
            config["current_account_id"] = None
    elif current_id is not None and current_id > account_id:
        # 当前账号ID需要减1
        config["current_account_id"] = current_id - 1

    config["accounts"] = accounts

    return True, cookies_to_delete, cookies_to_rename

def perform_account_deletion(cookies_to_delete, cookies_to_rename):
    """执行cookies文件的删除和重命名操作"""
    import os

    # 删除被删除账号的cookies
    if os.path.exists(cookies_to_delete):
        os.remove(cookies_to_delete)

    # 重命名其他账号的cookies文件（按顺序处理，避免覆盖）
    # 先按旧ID从小到大排序
    sorted_renames = sorted(cookies_to_rename.items(), key=lambda x: x[0])
    for old_path, new_path in sorted_renames:
        if os.path.exists(old_path):
            # 如果目标文件已存在，先删除
            if os.path.exists(new_path):
                os.remove(new_path)
            os.rename(old_path, new_path)

