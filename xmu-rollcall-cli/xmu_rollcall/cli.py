import click
import logging
import sys
from xmulogin import xmulogin
from . import __version__
from .config import (
    load_config, save_config, is_config_complete, get_cookies_path,
    add_account, get_all_accounts, get_current_account, set_current_account,
    get_account_by_id, CONFIG_FILE, delete_account, perform_account_deletion,
    get_rollcall_settings, set_rollcall_settings
)
from .logging_config import setup_logging
from .monitor import start_monitor, base_url, headers

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
    command_name = ctx.invoked_subcommand or "help"
    logger.info("CLI invoked: %s", command_name)
    if ctx.invoked_subcommand is None:
        click.echo(f"{Colors.OKCYAN}{Colors.BOLD}XMU Rollcall Bot CLI v{__version__}{Colors.ENDC}")
        click.echo(f"\nUsage:")
        click.echo(f"  xmurollcall-cli config    Configure credentials and settings")
        click.echo(f"  xmurollcall-cli switch    Switch between accounts")
        click.echo(f"  xmurollcall-cli start     Start monitoring rollcalls")
        click.echo(f"  xmurollcall-cli refresh   Refresh the login status")
        click.echo(f"  xmurollcall-cli --help    Show this message")

@cli.command()
def config():
    """Configure accounts and rollcall settings."""
    click.echo(f"\n{Colors.BOLD}{Colors.OKCYAN}=== XMU Rollcall Configuration ==={Colors.ENDC}\n")

    current_config = load_config()

    def show_accounts():
        accounts = get_all_accounts(current_config)
        if accounts:
            click.echo(f"{Colors.BOLD}Existing accounts:{Colors.ENDC}")
            current_account = get_current_account(current_config)
            for acc in accounts:
                current_marker = f" {Colors.OKGREEN}(current){Colors.ENDC}" if current_account and acc.get("id") == current_account.get("id") else ""
                settings = get_rollcall_settings(acc)
                wait_value = settings.get("wait_before_answer")
                wait_text = "no wait" if wait_value is False else f"wait {wait_value} classmates"
                click.echo(f"  {acc.get('id')}: {acc.get('name') or acc.get('username')}{current_marker} [{wait_text}]")
            click.echo()
        else:
            click.echo(f"{Colors.GRAY}No accounts configured.{Colors.ENDC}\n")

    def add_new_account():
        click.echo(f"{Colors.BOLD}Adding a new account...{Colors.ENDC}\n")
        username = click.prompt(f"{Colors.BOLD}Username{Colors.ENDC}")
        password = click.prompt(f"{Colors.BOLD}Password{Colors.ENDC}", hide_input=False)

        click.echo(f"\n{Colors.OKCYAN}Validating credentials...{Colors.ENDC}")
        try:
            session = xmulogin(type=3, username=username, password=password)
            if not session:
                click.echo(f"{Colors.FAIL}Login failed. Please check your credentials.{Colors.ENDC}")
                return

            logger.info("Credential validation succeeded for username=%s", username)
            click.echo(f"{Colors.OKGREEN}Login successful!{Colors.ENDC}")

            click.echo(f"{Colors.OKCYAN}Fetching user profile...{Colors.ENDC}")
            try:
                profile = session.get(f"{base_url}/api/profile", headers=headers).json()
                name = profile.get("name", "")
                click.echo(f"{Colors.OKGREEN}Welcome, {name}!{Colors.ENDC}")
            except Exception:
                click.echo(f"{Colors.WARNING}Could not fetch profile, using username as name{Colors.ENDC}")
                name = username

            try:
                account_id = add_account(current_config, username, password, name)
                save_config(current_config)
                click.echo(f"{Colors.OKGREEN}Account added successfully! (ID: {account_id}){Colors.ENDC}")
                click.echo(f"{Colors.GRAY}Configuration file: {CONFIG_FILE}{Colors.ENDC}\n")
            except RuntimeError as e:
                click.echo(f"{Colors.FAIL}Failed to save configuration: {str(e)}{Colors.ENDC}")
                click.echo(f"{Colors.WARNING}Tip: set XMU_ROLLCALL_CONFIG_DIR to choose a writable config directory.{Colors.ENDC}")
        except Exception as e:
            click.echo(f"{Colors.FAIL}Error during login validation: {str(e)}{Colors.ENDC}")

    def delete_existing_account():
        accounts = get_all_accounts(current_config)
        if not accounts:
            click.echo(f"{Colors.WARNING}No accounts to delete.{Colors.ENDC}\n")
            return

        show_accounts()
        valid_ids = [str(acc.get("id")) for acc in accounts]
        selected_id = click.prompt(
            f"{Colors.BOLD}Enter account ID to delete{Colors.ENDC}",
            type=click.Choice(valid_ids, case_sensitive=False),
        )
        selected_id = int(selected_id)
        selected_account = get_account_by_id(current_config, selected_id)
        if not selected_account:
            click.echo(f"{Colors.FAIL}Account not found.{Colors.ENDC}\n")
            return

        confirm = click.prompt(
            f"{Colors.WARNING}Are you sure you want to delete account '{selected_account.get('name') or selected_account.get('username')}' (ID: {selected_id})?{Colors.ENDC}",
            type=click.Choice(['y', 'n'], case_sensitive=False),
            default='n',
        )
        if confirm.lower() != 'y':
            click.echo(f"{Colors.GRAY}Deletion cancelled.{Colors.ENDC}\n")
            return

        success, cookies_to_delete, cookies_to_rename = delete_account(current_config, selected_id)
        if success:
            save_config(current_config)
            perform_account_deletion(cookies_to_delete, cookies_to_rename)
            click.echo(f"{Colors.OKGREEN}Account deleted successfully!{Colors.ENDC}")
            if cookies_to_rename:
                click.echo(f"{Colors.GRAY}Note: Account IDs have been re-assigned.{Colors.ENDC}")
            click.echo()
        else:
            click.echo(f"{Colors.FAIL}Failed to delete account.{Colors.ENDC}\n")

    def edit_account_settings():
        accounts = get_all_accounts(current_config)
        if not accounts:
            click.echo(f"{Colors.WARNING}No accounts to configure.{Colors.ENDC}\n")
            return

        show_accounts()
        valid_ids = [str(acc.get("id")) for acc in accounts]
        selected_id = click.prompt(
            f"{Colors.BOLD}Enter account ID to edit settings{Colors.ENDC}",
            type=click.Choice(valid_ids, case_sensitive=False),
        )
        selected_account = get_account_by_id(current_config, int(selected_id))
        if not selected_account:
            click.echo(f"{Colors.FAIL}Account not found.{Colors.ENDC}\n")
            return

        settings = get_rollcall_settings(selected_account)
        current_wait = settings.get("wait_before_answer", False)
        current_wait_text = "false" if current_wait is False else str(current_wait)

        click.echo()
        click.echo(f"{Colors.BOLD}Rollcall settings for {selected_account.get('name') or selected_account.get('username')}:{Colors.ENDC}")
        click.echo(f"  wait_before_answer: {Colors.OKCYAN}{current_wait_text}{Colors.ENDC}")
        click.echo()
        click.echo("Set wait_before_answer:")
        click.echo("  false  - do not wait after getting the number code")
        click.echo("  number - wait until that many classmates have signed")

        raw_value = click.prompt(
            f"{Colors.BOLD}wait_before_answer{Colors.ENDC}",
            default=current_wait_text,
            show_default=True,
        ).strip().lower()

        if raw_value in ("false", "f", "no", "n", "0", "off", ""):
            wait_before_answer = False
        else:
            try:
                wait_before_answer = int(raw_value)
            except ValueError:
                click.echo(f"{Colors.FAIL}Invalid value. Use false or a positive number.{Colors.ENDC}\n")
                return
            if wait_before_answer <= 0:
                wait_before_answer = False

        set_rollcall_settings(selected_account, {"wait_before_answer": wait_before_answer})
        save_config(current_config)
        saved = get_rollcall_settings(selected_account).get("wait_before_answer")
        saved_text = "false" if saved is False else str(saved)
        click.echo(f"{Colors.OKGREEN}Settings saved. wait_before_answer = {saved_text}{Colors.ENDC}\n")

    while True:
        show_accounts()
        click.echo(f"{Colors.BOLD}Choose an action:{Colors.ENDC}")
        click.echo(f"  {Colors.OKCYAN}n{Colors.ENDC} - Add new account")
        click.echo(f"  {Colors.OKCYAN}d{Colors.ENDC} - Delete account")
        click.echo(f"  {Colors.OKCYAN}s{Colors.ENDC} - Edit rollcall settings")
        click.echo(f"  {Colors.OKCYAN}q{Colors.ENDC} - Quit")

        action = click.prompt(
            f"\n{Colors.BOLD}Action{Colors.ENDC}",
            type=click.Choice(['n', 'd', 's', 'q'], case_sensitive=False),
            default='q',
        )
        click.echo()

        if action.lower() == 'n':
            add_new_account()
        elif action.lower() == 'd':
            delete_existing_account()
        elif action.lower() == 's':
            edit_account_settings()
        elif action.lower() == 'q':
            accounts = get_all_accounts(current_config)
            if accounts:
                click.echo(f"{Colors.BOLD}Final account list:{Colors.ENDC}")
                current_account = get_current_account(current_config)
                for acc in accounts:
                    current_marker = f" {Colors.OKGREEN}(current){Colors.ENDC}" if current_account and acc.get("id") == current_account.get("id") else ""
                    settings = get_rollcall_settings(acc)
                    wait_value = settings.get("wait_before_answer")
                    wait_text = "no wait" if wait_value is False else f"wait {wait_value} classmates"
                    click.echo(f"  {acc.get('id')}: {acc.get('name') or acc.get('username')}{current_marker} [{wait_text}]")
                click.echo(f"\n{Colors.GRAY}You can run: {Colors.BOLD}xmurollcall-cli switch{Colors.ENDC} to switch between accounts")
                click.echo(f"{Colors.GRAY}You can run: {Colors.BOLD}xmurollcall-cli start{Colors.ENDC} to start monitoring")
            break

@cli.command()
def start():
    """启动签到监控"""
    # 加载配置
    logger.info("Start command selected")
    config_data = load_config()

    # 检查配置是否完整
    if not is_config_complete(config_data):
        click.echo(f"{Colors.FAIL}✗ Configuration incomplete!{Colors.ENDC}")
        click.echo(f"Please run: {Colors.BOLD}xmurollcall-cli config{Colors.ENDC}")
        sys.exit(1)

    # 获取当前账号
    current_account = get_current_account(config_data)
    click.echo(f"{Colors.OKCYAN}Using account: {current_account.get('name') or current_account.get('username')} (ID: {current_account.get('id')}){Colors.ENDC}")
    logger.info("Using account id=%s name=%s", current_account.get('id'), current_account.get('name') or current_account.get('username'))

    # 启动监控
    try:
        start_monitor(current_account)
    except KeyboardInterrupt:
        logger.info("Start command interrupted by user")
        click.echo(f"\n{Colors.WARNING}Shutting down...{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        logger.exception("Start command failed")
        click.echo(f"\n{Colors.FAIL}Error: {str(e)}{Colors.ENDC}")
        sys.exit(1)

@cli.command()
def refresh():
    """清除当前账号的登录缓存"""
    config_data = load_config()
    current_account = get_current_account(config_data)

    if not current_account:
        click.echo(f"{Colors.FAIL}✗ No account configured!{Colors.ENDC}")
        click.echo(f"Please run: {Colors.BOLD}xmurollcall-cli config{Colors.ENDC}")
        sys.exit(1)

    account_id = current_account.get("id")
    cookies_path = get_cookies_path(account_id)
    try:
        click.echo(f"\n{Colors.WARNING}Deleting cookies for account {account_id} ({current_account.get('name')})...{Colors.ENDC}")
        # delete cookies file
        import os
        if os.path.exists(cookies_path):
            os.remove(cookies_path)
            click.echo(f"{Colors.OKGREEN}✓ Cookies deleted successfully.{Colors.ENDC}")
        else:
            click.echo(f"{Colors.GRAY}No cookies file found to delete.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        click.echo(f"{Colors.FAIL}✗ Failed to delete cookies: {str(e)}{Colors.ENDC}")
        sys.exit(1)


@cli.command()
def switch():
    """切换当前使用的账号"""
    click.echo(f"\n{Colors.BOLD}{Colors.OKCYAN}=== Switch Account ==={Colors.ENDC}\n")

    config_data = load_config()
    accounts = get_all_accounts(config_data)

    if not accounts:
        click.echo(f"{Colors.FAIL}✗ No accounts configured!{Colors.ENDC}")
        click.echo(f"Please run: {Colors.BOLD}xmurollcall-cli config{Colors.ENDC}")
        sys.exit(1)

    current_account = get_current_account(config_data)
    current_id = current_account.get("id") if current_account else None

    # 显示账号列表
    click.echo(f"{Colors.BOLD}Available accounts:{Colors.ENDC}")
    for acc in accounts:
        current_marker = f" {Colors.OKGREEN}(current){Colors.ENDC}" if acc.get("id") == current_id else ""
        click.echo(f"  {acc.get('id')}: {acc.get('name') or acc.get('username')}{current_marker}")

    click.echo()

    # 让用户选择账号
    valid_ids = [str(acc.get("id")) for acc in accounts]
    selected_id = click.prompt(
        f"{Colors.BOLD}Enter account ID to switch to{Colors.ENDC}",
        type=click.Choice(valid_ids, case_sensitive=False)
    )

    selected_id = int(selected_id)
    selected_account = get_account_by_id(config_data, selected_id)

    if selected_account:
        set_current_account(config_data, selected_id)
        save_config(config_data)
        click.echo(f"\n{Colors.OKGREEN}✓ Switched to account: {selected_account.get('name') or selected_account.get('username')} (ID: {selected_id}){Colors.ENDC}")
        click.echo(f"{Colors.GRAY}You can now run: {Colors.BOLD}xmurollcall-cli start{Colors.ENDC}")
    else:
        click.echo(f"{Colors.FAIL}✗ Account not found!{Colors.ENDC}")
        sys.exit(1)


if __name__ == '__main__':
    cli()
