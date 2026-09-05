import time
import os
import sys
import requests
import logging
from xmulogin import xmulogin
from . import tui
from rich.live import Live
from .logging_config import setup_logging
from .utils import save_session, load_session, verify_session
from .rollcall_handler import process_rollcalls
from .config import get_cookies_path, load_config, has_saved_session, get_interval, DEFAULT_INTERVAL

logger = logging.getLogger(__name__)

base_url = "https://lnt.xmu.edu.cn"
interval = DEFAULT_INTERVAL
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

# ANSI Color codes
class Colors:
    __slots__ = ()
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    BG_BLUE = '\033[44m'
    BG_GREEN = '\033[42m'
    BG_CYAN = '\033[46m'

BOLD_LABEL = f"{Colors.BOLD}"
CYAN_TEXT = f"{Colors.OKCYAN}"
GREEN_TEXT = f"{Colors.OKGREEN}"
YELLOW_TEXT = f"{Colors.WARNING}"
END = Colors.ENDC

def _load_monitor_settings():
    """Load monitor polling interval from config."""
    config = load_config()
    return get_interval(config)

def clear_screen():
    if tui.console.is_terminal:
        tui.console.clear()


def center_text(text, width=None):
    width = tui.console.width if width is None else width
    return "\n".join(
        " " * max(0, (width - tui.Text.from_ansi(line).cell_len) // 2) + line
        for line in text.split("\n")
    )


def print_banner():
    tui.console.print(tui.frame(tui.Text("Preparing your account and saved session."), "Initialization"))


def print_separator(char="─"):
    tui.console.rule(style="bright_black")


def format_time(seconds):
    """格式化时间显示"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def monitor_dashboard(name, start_time, query_count):
    return tui.dashboard(name, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
                         format_time(int(time.time() - start_time)), query_count, interval)


def print_login_status(message, is_success=True):
    """打印登录状态"""
    if is_success:
        tui.echo(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {message}")
        logger.info(f"[SUCCESS] {message}")
    else:
        tui.echo(f"{Colors.FAIL}[FAILED]{Colors.ENDC} {message}")
        logger.warning(f"[FAILED] {message}")

def start_monitor(account):
    """启动监控程序"""
    log_file = setup_logging()
    global interval
    interval = _load_monitor_settings()
    USERNAME = account['username']
    PASSWORD = account['password']
    ACCOUNT_ID = account.get('id', 1)
    ACCOUNT_NAME = account.get('name', '')
    # LATITUDE = account.get('latitude', 0)
    # LONGITUDE = account.get('longitude', 0)

    # 设置全局位置信息
    # set_location(LATITUDE, LONGITUDE)

    legacy_cookies_path = get_cookies_path(ACCOUNT_ID)
    rollcalls_url = f"{base_url}/api/radar/rollcalls"
    session = None
    logger.info("Starting monitor for account id=%s name=%s", ACCOUNT_ID, ACCOUNT_NAME or USERNAME)
    logger.info("Log file: %s", log_file)

    # 初始化
    clear_screen()
    print_banner()
    tui.echo(f"\n{Colors.BOLD}Initializing XMU Rollcall Bot...{Colors.ENDC}\n")
    print_separator()

    tui.echo(f"\n{Colors.OKCYAN}[Step 1/3]{Colors.ENDC} Checking credentials...")

    if has_saved_session(ACCOUNT_ID) or os.path.exists(legacy_cookies_path):
        tui.echo(f"{Colors.OKCYAN}[Step 2/3]{Colors.ENDC} Found cached session, attempting to restore...")
        session_candidate = requests.Session()
        if load_session(session_candidate, ACCOUNT_ID):
            profile = verify_session(session_candidate)
            if profile:
                session = session_candidate
                print_login_status("Session restored successfully", True)
            else:
                print_login_status("Session expired, will re-login", False)
        else:
            print_login_status("Failed to load session", False)

    if not session:
        tui.echo(f"{Colors.OKCYAN}[Step 2/3]{Colors.ENDC} Logging in with credentials...")
        time.sleep(2)
        session = xmulogin(type=3, username=USERNAME, password=PASSWORD)
        if session:
            save_session(session, ACCOUNT_ID)
            print_login_status("Login successful", True)
        else:
            print_login_status("Login failed. Please check your credentials", False)
            time.sleep(5)
            sys.exit(1)

    tui.echo(f"{Colors.OKCYAN}[Step 3/3]{Colors.ENDC} Fetching user profile...")
    # profile = session.get(f"{base_url}/api/profile", headers=headers).json()
    # name = profile["name"]
    tui.echo(f"Welcome, {ACCOUNT_NAME}")

    tui.echo(f"\n{Colors.OKGREEN}{Colors.BOLD}Initialization complete{Colors.ENDC}")
    tui.echo(f"\n{Colors.GRAY}Starting monitor in 3 seconds...{Colors.ENDC}")
    time.sleep(3)

    # 主循环
    temp_data = {'rollcalls': []}
    query_count = 0
    start_time = time.time()

    clear_screen()
    live = Live(monitor_dashboard(ACCOUNT_NAME, start_time, query_count),
                console=tui.console, auto_refresh=False)
    live.start(refresh=True)
    last_display_second = -1
    _last_query_time = -interval # 进入循环时立即查询一次

    try:
        while True:
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                raise

            try:
                current_time = time.time()

                elapsed = int(current_time - start_time)
                if elapsed != last_display_second:
                    last_display_second = elapsed
                    live.update(monitor_dashboard(ACCOUNT_NAME, start_time, query_count), refresh=True)

                if elapsed > _last_query_time + interval - 1:
                    _last_query_time = elapsed
                    data = session.get(rollcalls_url, headers=headers).json()
                    query_count += 1

                    live.update(monitor_dashboard(ACCOUNT_NAME, start_time, query_count), refresh=True)

                    if temp_data != data:
                        temp_data = data
                        if len(temp_data['rollcalls']) > 0:
                            logger.info("New rollcall detected: count=%s", len(temp_data['rollcalls']))
                            live.stop()
                            clear_screen()
                            tui.console.print(tui.frame(tui.Text("Processing new rollcalls…", style="yellow"), "New rollcall detected"))

                            temp_data = process_rollcalls(temp_data, session, account)
                            print_separator("=")
                            tui.echo(f"\n{center_text(f'{Colors.GRAY}Press Ctrl+C to exit, continuing monitor...{Colors.ENDC}')}\n")
                            try:
                                time.sleep(3)
                            except KeyboardInterrupt:
                                raise
                            clear_screen()
                            live.update(monitor_dashboard(ACCOUNT_NAME, start_time, query_count))
                            live.start(refresh=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                live.stop()
                logger.exception("Monitor exited because of an error: %s", str(e))
                clear_screen()
                tui.echo(f"\n{center_text(f'{Colors.FAIL}{Colors.BOLD}Error occurred:{Colors.ENDC} {str(e)}')}")
                tui.echo(f"{center_text(f'{Colors.GRAY}Exiting...{Colors.ENDC}')}\n")
                sys.exit(1)
    except KeyboardInterrupt:
        live.stop()
        logger.info(
            "Monitor stopped by user. queries=%s running_time=%s",
            query_count,
            format_time(int(time.time() - start_time)),
        )
        clear_screen()
        tui.echo(f"\n{center_text(f'{Colors.WARNING}Shutting down gracefully...{Colors.ENDC}')}")
        tui.echo(f"{center_text(f'{Colors.GRAY}Total queries performed: {query_count}{Colors.ENDC}')}")
        tui.echo(f"{center_text(f'{Colors.GRAY}Total running time: {format_time(int(time.time() - start_time))}{Colors.ENDC}')}")
        tui.echo(f"\n{center_text(f'{Colors.OKGREEN}Goodbye{Colors.ENDC}')}\n")
        sys.exit(0)

    finally:
        live.stop()
