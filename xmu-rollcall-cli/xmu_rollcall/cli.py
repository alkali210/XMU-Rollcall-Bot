import click
import logging
import math
from decimal import Decimal, InvalidOperation
import sys
import json
import uuid
import requests
from .network import REQUEST_TIMEOUT
from .utils import load_session
from . import tui
from xmulogin import xmulogin
from .config import (
    load_config, save_config, is_config_complete, get_cookies_path,
    add_account, get_all_accounts, get_current_account, set_current_account,
    get_account_by_id, CONFIG_FILE, delete_account, perform_account_deletion,
    delete_saved_session, get_rollcall_settings, set_rollcall_settings, get_interval,
    get_disable_monitor_retry
)
from .logging_config import setup_logging
from .monitor import start_monitor, base_url, headers
from . import __version__
from .updates import check_updates

logger = logging.getLogger(__name__)

# ANSI Color codes
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    GRAY = '\033[90m'

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    log_file = setup_logging()
    ctx.ensure_object(dict)
    ctx.obj["log_file"] = log_file
    command_name = ctx.invoked_subcommand or "interactive"
    logger.info("CLI invoked: %s", command_name)
    if ctx.invoked_subcommand is None:
        interactive_menu(ctx)


def interactive_menu(ctx):
    if tui.console.is_terminal:
        tui.console.clear()
    aliases = {"1": "config", "2": "switch", "3": "start", "4": "refresh", "5": "check"}
    while True:
        data = load_config()
        tui.home(get_current_account(data), len(get_all_accounts(data)))
        try:
            action = tui.prompt("Command", type=click.Choice(
                ["1", "2", "3", "4", "5", "config", "switch", "start", "refresh", "check"],
                case_sensitive=False)).lower()
            command = cli.commands[aliases.get(action, action)]
            try:
                ctx.invoke(command)
            except SystemExit as exc:
                # Stopping monitoring ends the application; failed setup can be retried.
                logger.info("Interactive command %s exited: %s", command.name, exc.code)
                if command.name == "start" and exc.code in (None, 0):
                    return
            except click.Abort:
                if command.name == "start":
                    return
                tui.echo("Operation cancelled. Returning to commands.")
            except KeyboardInterrupt:
                if command.name == "start":
                    return
                tui.echo("Operation cancelled. Returning to commands.")
        except (click.Abort, KeyboardInterrupt):
            tui.echo("Goodbye!")
            return

@cli.command()
def check():
    """检查更新"""
    tui.echo(f"{Colors.BOLD}Checking for updates...{Colors.ENDC}")
    try:
        info = check_updates(__version__)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    tui.echo(f"Current version: {__version__} ({info.current_commit})")
    tui.echo(f"{info.commits_since_release} commits to main since this release")
    if info.update_available:
        tui.echo(f"{Colors.OKGREEN}Update available!{Colors.ENDC}")
        tui.echo(f"New version: {info.latest_version} ({info.latest_commit})")
        tui.echo(f"Release: {info.release_url}")
    else:
        tui.echo("Up to date.")


@cli.command()
def config():
    """配置账号和签到设置"""
    current_config = load_config()

    def show_accounts():
        accounts = get_all_accounts(current_config)
        tui.console.print(tui.accounts_panel(
            accounts, get_current_account(current_config), get_rollcall_settings))

    def add_new_account():
        tui.echo(f"{Colors.BOLD}Adding a new account...{Colors.ENDC}\n")
        username = tui.prompt(f"{Colors.BOLD}Username{Colors.ENDC}")
        password = tui.prompt(f"{Colors.BOLD}Password{Colors.ENDC}", hide_input=True)

        tui.echo(f"\n{Colors.OKCYAN}Validating credentials...{Colors.ENDC}")
        try:
            session = xmulogin(type=3, username=username, password=password)
            if not session:
                tui.echo(f"{Colors.FAIL}Login failed. Please check your credentials.{Colors.ENDC}")
                return

            logger.info("Credential validation succeeded for username=%s", username)
            tui.echo(f"{Colors.OKGREEN}Login successful!{Colors.ENDC}")

            tui.echo(f"{Colors.OKCYAN}Fetching user profile...{Colors.ENDC}")
            try:
                profile = session.get(f"{base_url}/api/profile", headers=headers).json()
                name = profile.get("name", "")
                tui.echo(f"{Colors.OKGREEN}Welcome, {name}!{Colors.ENDC}")
            except Exception:
                tui.echo(f"{Colors.WARNING}Could not fetch profile, using username as name{Colors.ENDC}")
                name = username

            try:
                account_id = add_account(current_config, username, password, name)
                save_config(current_config)
                tui.echo(f"{Colors.OKGREEN}Account added successfully! (ID: {account_id}){Colors.ENDC}")
                tui.echo(f"{Colors.GRAY}Configuration file: {CONFIG_FILE}{Colors.ENDC}\n")
            except RuntimeError as e:
                tui.echo(f"{Colors.FAIL}Failed to save configuration: {str(e)}{Colors.ENDC}")
                tui.echo(f"{Colors.WARNING}Tip: set XMU_ROLLCALL_CONFIG_DIR to choose a writable config directory.{Colors.ENDC}")
        except Exception as e:
            tui.echo(f"{Colors.FAIL}Error during login validation: {str(e)}{Colors.ENDC}")

    def delete_existing_account():
        accounts = get_all_accounts(current_config)
        if not accounts:
            tui.echo(f"{Colors.WARNING}No accounts to delete.{Colors.ENDC}\n")
            return

        show_accounts()
        valid_ids = [str(acc.get("id")) for acc in accounts]
        selected_id = tui.prompt(
            f"{Colors.BOLD}Enter account ID to delete{Colors.ENDC}",
            type=click.Choice(valid_ids, case_sensitive=False),
        )
        selected_id = int(selected_id)
        selected_account = get_account_by_id(current_config, selected_id)
        if not selected_account:
            tui.echo(f"{Colors.FAIL}Account not found.{Colors.ENDC}\n")
            return

        confirm = tui.prompt(
            f"{Colors.WARNING}Are you sure you want to delete account '{selected_account.get('name') or selected_account.get('username')}' (ID: {selected_id})?{Colors.ENDC}",
            type=click.Choice(['y', 'n'], case_sensitive=False),
            default='n',
        )
        if confirm.lower() != 'y':
            tui.echo(f"{Colors.GRAY}Deletion cancelled.{Colors.ENDC}\n")
            return

        success, cookies_to_delete, cookies_to_rename = delete_account(current_config, selected_id)
        if success:
            save_config(current_config)
            perform_account_deletion(cookies_to_delete, cookies_to_rename)
            tui.echo(f"{Colors.OKGREEN}Account deleted successfully!{Colors.ENDC}")
            if cookies_to_rename:
                tui.echo(f"{Colors.GRAY}Note: Account IDs have been re-assigned.{Colors.ENDC}")
            tui.echo()
        else:
            tui.echo(f"{Colors.FAIL}Failed to delete account.{Colors.ENDC}\n")

    def edit_account_settings():
        accounts = get_all_accounts(current_config)
        if not accounts:
            tui.echo(f"{Colors.WARNING}No accounts to configure.{Colors.ENDC}\n")
            return

        show_accounts()
        valid_ids = [str(acc.get("id")) for acc in accounts]
        selected_id = tui.prompt(
            f"{Colors.BOLD}Enter account ID to edit settings{Colors.ENDC}",
            type=click.Choice(valid_ids, case_sensitive=False),
        )
        selected_account = get_account_by_id(current_config, int(selected_id))
        if not selected_account:
            tui.echo(f"{Colors.FAIL}Account not found.{Colors.ENDC}\n")
            return

        settings = get_rollcall_settings(selected_account)
        current_wait = settings.get("wait_before_answer", False)
        current_wait_text = "false" if current_wait is False else str(current_wait)

        tui.echo()
        tui.echo(f"{Colors.BOLD}Rollcall settings for {selected_account.get('name') or selected_account.get('username')}:{Colors.ENDC}")
        tui.echo(f"  wait_before_answer: {Colors.OKCYAN}{current_wait_text}{Colors.ENDC}")
        tui.echo()
        tui.echo("Set wait_before_answer:")
        tui.echo("  false  - do not wait after getting the number code")
        tui.echo("  number - wait until that many classmates have signed")
        tui.echo("  20%    - wait until that percentage of students has signed")

        raw_value = tui.prompt(
            f"{Colors.BOLD}wait_before_answer{Colors.ENDC}",
            default=current_wait_text,
            show_default=True,
        ).strip().lower()

        if raw_value in ("false", "f", "no", "n", "0", "off", ""):
            wait_before_answer = False
        elif raw_value.endswith("%"):
            try:
                percentage = Decimal(raw_value[:-1])
                if not percentage.is_finite() or not 0 < percentage <= 100:
                    raise ValueError
            except (InvalidOperation, ValueError):
                tui.echo("Invalid percentage. Use a value greater than 0% and at most 100%.")
                return
            wait_before_answer = raw_value
        else:
            try:
                wait_before_answer = int(raw_value)
            except ValueError:
                tui.echo(f"{Colors.FAIL}Invalid value. Use false, a positive integer, or 20%.{Colors.ENDC}\n")
                return
            if wait_before_answer <= 0:
                wait_before_answer = False

        set_rollcall_settings(selected_account, {"wait_before_answer": wait_before_answer})
        save_config(current_config)
        saved = get_rollcall_settings(selected_account).get("wait_before_answer")
        saved_text = "false" if saved is False else str(saved)
        tui.echo(f"{Colors.OKGREEN}Settings saved. wait_before_answer = {saved_text}{Colors.ENDC}\n")

    def edit_interval():
        while True:
            value = tui.prompt("Polling interval (seconds)", type=float,
                               default=get_interval(current_config))
            if math.isfinite(value) and value > 0:
                break
            tui.echo("Invalid interval. Enter a finite number greater than zero.")
        current_config["interval"] = value
        save_config(current_config)
        tui.echo(f"Polling interval saved: {value:g}s (all accounts).")

    def edit_monitor_retry():
        current_config["disable_monitor_retry"] = not get_disable_monitor_retry(current_config)
        save_config(current_config)
        value = str(get_disable_monitor_retry(current_config)).lower()
        tui.echo(f"Disable monitor retries: {value} (saved for all accounts; applies on next start).")

    try:
        while True:
            tui.console.print(tui.frame(tui.Group(tui.sections(
                tui.accounts_panel(get_all_accounts(current_config),
                                   get_current_account(current_config), get_rollcall_settings),
                tui.panel(tui.menu_rows([
                    ("n", "Add new account"), ("d", "Delete account"),
                    ("s", "Edit rollcall settings"),
                    ("i", f"Polling interval: {get_interval(current_config):g}s (all accounts)"),
                    ("r", f"Disable monitor retries: {str(get_disable_monitor_retry(current_config)).lower()} (all accounts)")]),
                    "Actions", "blue")),
                tui.Text(f"Configuration file: {CONFIG_FILE.resolve()}", style="dim")),
                "Configuration", subtitle="Ctrl+C to return"))

            action = tui.prompt(
                f"{Colors.BOLD}Action{Colors.ENDC}",
                type=click.Choice(['n', 'd', 's', 'i', 'r'], case_sensitive=False),
            )

            if action.lower() == 'n':
                add_new_account()
            elif action.lower() == 'd':
                delete_existing_account()
            elif action.lower() == 's':
                edit_account_settings()
            elif action.lower() == 'i':
                edit_interval()
            elif action.lower() == 'r':
                edit_monitor_retry()
    except (click.Abort, KeyboardInterrupt):
        tui.echo("Configuration closed.")
        return

@cli.command()
@click.option("--account-id", type=click.IntRange(min=1), help="默认使用当前选中的账号。")
@click.option("--rollcall-id", type=click.IntRange(min=1), help="默认查询该账号未完成的雷达签到。")
@click.option("--latitude", type=click.FloatRange(-90, 90), help="纬度；也可作为第一个位置参数。")
@click.option("--longitude", type=click.FloatRange(-180, 180), help="经度；也可作为第二个位置参数。")
@click.argument("coordinates", nargs=-1, type=float)
def radar(account_id, rollcall_id, latitude, longitude, coordinates):
    """使用已知经纬度提交雷达签到，不计算位置"""
    try:
        if coordinates:
            if len(coordinates) != 2 or latitude is not None or longitude is not None:
                raise click.UsageError("Provide either LATITUDE LONGITUDE or --latitude and --longitude, not both.")
            latitude, longitude = coordinates
        if latitude is None or longitude is None:
            raise click.UsageError("Both latitude and longitude values are required.")
        if (not math.isfinite(latitude) or not -90 <= latitude <= 90
                or not math.isfinite(longitude) or not -180 <= longitude <= 180):
            raise click.UsageError("Latitude must be in [-90, 90]; longitude in [-180, 180].")

        data = load_config()
        account = get_current_account(data) if account_id is None else get_account_by_id(data, account_id)
        if not account:
            raise RuntimeError("No selected account or account not found; run xmu-rollcall config.")
        account_id = account["id"]
        logger.info("Radar submission using account id=%s", account_id)
        with requests.Session() as session:
            if not load_session(session, account_id):
                raise RuntimeError("No saved session for this account; log in with xmu-rollcall start first.")
            if rollcall_id is None:
                response = session.get(
                    f"{base_url}/api/radar/rollcalls", headers=headers,
                    timeout=REQUEST_TIMEOUT, allow_redirects=False,
                )
                if response.status_code != 200:
                    raise RuntimeError(f"Radar rollcall query failed: HTTP {response.status_code}")
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("rollcalls"), list):
                    raise RuntimeError("Radar rollcall query returned an invalid response.")
                ids = {
                    row["rollcall_id"] for row in data["rollcalls"]
                    if isinstance(row, dict) and row.get("is_radar")
                    and not row.get("is_expired") and row.get("status") != "on_call_fine"
                    and isinstance(row.get("rollcall_id"), int) and row["rollcall_id"] > 0
                }
                if not ids:
                    raise RuntimeError("No pending radar rollcall found for this account.")
                if len(ids) != 1:
                    raise RuntimeError(f"Multiple pending radar rollcalls found: {sorted(ids)}; specify --rollcall-id.")
                rollcall_id = ids.pop()
            logger.info("Submitting radar rollcall id=%s latitude=%s longitude=%s",
                        rollcall_id, latitude, longitude)
            response = session.put(
                f"{base_url}/api/rollcall/{rollcall_id}/answer",
                json={
                    "accuracy": 35, "altitude": 0, "altitudeAccuracy": None,
                    "deviceId": str(uuid.uuid4()), "heading": None,
                    "latitude": latitude, "longitude": longitude, "speed": None,
                },
                headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=False,
            )
            try:
                body = response.json()
            except ValueError:
                body = response.text
            result = json.dumps({
                "account_id": account_id, "rollcall_id": rollcall_id,
                "latitude": latitude, "longitude": longitude,
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type"), "response": body,
            }, ensure_ascii=False)
            click.echo(result)
            logger.info("Radar submission result: %s", result)
            if response.status_code != 200:
                raise RuntimeError(f"Radar submission failed: HTTP {response.status_code}")
    except click.ClickException:
        logger.exception("Invalid radar command")
        raise
    except Exception as exc:
        logger.exception("Radar command failed")
        raise click.ClickException(str(exc)) from exc


@cli.command()
def start():
    """启动签到监控"""
    # 加载配置
    logger.info("Start command selected")
    config_data = load_config()

    # 检查配置是否完整
    if not is_config_complete(config_data):
        tui.echo(f"{Colors.FAIL}✗ Configuration incomplete!{Colors.ENDC}")
        tui.echo(f"Please run: {Colors.BOLD}xmu-rollcall config{Colors.ENDC}")
        sys.exit(1)

    # 获取当前账号
    current_account = get_current_account(config_data)
    tui.echo(f"{Colors.OKCYAN}Using account: {current_account.get('name') or current_account.get('username')} (ID: {current_account.get('id')}){Colors.ENDC}")
    logger.info("Using account id=%s name=%s", current_account.get('id'), current_account.get('name') or current_account.get('username'))

    # 启动监控
    try:
        start_monitor(current_account)
    except KeyboardInterrupt:
        logger.info("Start command interrupted by user")
        tui.echo(f"\n{Colors.WARNING}Shutting down...{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        logger.exception("Start command failed")
        tui.echo(f"\n{Colors.FAIL}Error: {str(e)}{Colors.ENDC}")
        sys.exit(1)

@cli.command()
def refresh():
    """刷新登录状态"""
    config_data = load_config()
    current_account = get_current_account(config_data)

    if not current_account:
        tui.echo(f"{Colors.FAIL}No account configured!{Colors.ENDC}")
        tui.echo(f"Please run: {Colors.BOLD}xmu-rollcall config{Colors.ENDC}")
        sys.exit(1)

    account_id = current_account.get("id")
    cookies_path = get_cookies_path(account_id)
    try:
        tui.echo(f"\n{Colors.WARNING}Deleting saved session for account {account_id} ({current_account.get('name')})...{Colors.ENDC}")
        delete_saved_session(account_id)
        # delete legacy cookies file if present
        import os
        if os.path.exists(cookies_path):
            os.remove(cookies_path)
            tui.echo(f"{Colors.OKGREEN}Saved session deleted successfully. Legacy cookies file removed too.{Colors.ENDC}")
        else:
            tui.echo(f"{Colors.OKGREEN}Saved session deleted successfully.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        tui.echo(f"{Colors.FAIL}Failed to delete saved session: {str(e)}{Colors.ENDC}")
        sys.exit(1)


@cli.command()
def switch():
    """切换当前使用的账号"""
    config_data = load_config()
    accounts = get_all_accounts(config_data)

    if not accounts:
        tui.echo(f"{Colors.FAIL}✗ No accounts configured!{Colors.ENDC}")
        tui.echo(f"Please run: {Colors.BOLD}xmu-rollcall config{Colors.ENDC}")
        sys.exit(1)

    tui.console.print(tui.frame(tui.accounts_panel(
        accounts, get_current_account(config_data), get_rollcall_settings), "Switch account"))

    # 让用户选择账号
    valid_ids = [str(acc.get("id")) for acc in accounts]
    selected_id = tui.prompt(
        f"{Colors.BOLD}Enter account ID to switch to{Colors.ENDC}",
        type=click.Choice(valid_ids, case_sensitive=False)
    )

    selected_id = int(selected_id)
    selected_account = get_account_by_id(config_data, selected_id)

    if selected_account:
        set_current_account(config_data, selected_id)
        save_config(config_data)
        tui.echo(f"\n{Colors.OKGREEN}✓ Switched to account: {selected_account.get('name') or selected_account.get('username')} (ID: {selected_id}){Colors.ENDC}")
        tui.echo(f"{Colors.GRAY}You can now run: {Colors.BOLD}xmu-rollcall start{Colors.ENDC}")
    else:
        tui.echo(f"{Colors.FAIL}✗ Account not found!{Colors.ENDC}")
        sys.exit(1)


if __name__ == '__main__':
    cli()

