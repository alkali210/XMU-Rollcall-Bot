import io
import unittest
from unittest.mock import Mock, patch

from click.testing import CliRunner
from rich.console import Console

from xmu_rollcall import tui
from xmu_rollcall.cli import cli
from xmu_rollcall import monitor


class TerminalTests(unittest.TestCase):
    def invoke(self, args=(), input=""):
        with patch("xmu_rollcall.cli.setup_logging"), patch(
            "xmu_rollcall.cli.load_config", return_value={}
        ):
            return CliRunner().invoke(cli, args, input=input)

    def test_menu_retries_invalid_choice_and_exits_on_eof(self):
        result = self.invoke(input="invalid\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("is not one of", result.output)
        self.assertIn("Goodbye", result.output)

    def test_all_menu_commands_return_after_system_exit(self):
        for choice, command in [("1", "config"), ("switch", "switch"),
                                ("3", "start"), ("refresh", "refresh")]:
            with self.subTest(command=command), patch.object(
                cli.commands[command], "callback", side_effect=SystemExit(1)
            ) as callback:
                result = self.invoke(input=f"{choice}\n")
                self.assertEqual(result.exit_code, 0, result.output)
                callback.assert_called_once()
                self.assertEqual(result.output.count("Welcome back"), 2)

    def test_config_returns_to_launcher(self):
        result = self.invoke(input="config\nq\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Configuration", result.output)
        self.assertEqual(result.output.count("Welcome back"), 2)

    def test_direct_command_keeps_failure_exit_code(self):
        result = self.invoke(["start"])
        self.assertEqual(result.exit_code, 1)
        self.assertNotIn("Welcome back", result.output)

    def test_stopping_monitor_exits_launcher(self):
        for interruption in (SystemExit(0), KeyboardInterrupt()):
            with self.subTest(interruption=interruption), patch(
                "xmu_rollcall.cli.is_config_complete", return_value=True
            ), patch("xmu_rollcall.cli.get_current_account", return_value={"name": "Test"}), patch(
                "xmu_rollcall.cli.start_monitor", side_effect=interruption
            ):
                result = self.invoke(input="start\n")
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(result.output.count("Welcome back"), 1)
                self.assertNotIn("q / exit", result.output)

    def test_monitor_greeting_uses_local_time(self):
        for hour, greeting in [(4, "Good evening"), (5, "Good morning"),
                               (11, "Good morning"), (12, "Good afternoon"),
                               (17, "Good afternoon"), (18, "Good evening")]:
            with self.subTest(hour=hour), patch.object(tui.time, "localtime", return_value=Mock(tm_hour=hour)):
                output = io.StringIO()
                console = Console(file=output, width=100)
                with patch.object(tui, "console", console):
                    console.print(tui.dashboard("Test", "12:00", "1m", 1, 10))
                self.assertIn(f"{greeting}, Test!", output.getvalue())

    def test_help_does_not_open_menu(self):
        result = self.invoke(["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("Welcome back", result.output)

    def test_layout_width_and_literal_account_names(self):
        for width in (40, 80, 120):
            output = io.StringIO()
            console = Console(file=output, width=width, color_system=None)
            with patch.object(tui, "console", console):
                tui.home({"name": "同学[red]"}, 1)
                console.print(tui.dashboard("同学[red]", "2026-09-05 12:00:00", "1m", 6, 10))
            text = output.getvalue()
            self.assertIn("╭", text)
            self.assertIn("╯", text)
            self.assertIn("同学[red]", text)
            from rich.cells import cell_len
            self.assertTrue(all(cell_len(line) <= width for line in text.splitlines()))

    def test_monitor_preserves_polling_and_restores_terminal(self):
        account = {"id": 1, "username": "test", "password": "unused", "name": "Test"}
        session = Mock()
        session.get.return_value.json.return_value = {"rollcalls": [{"id": 123}]}
        # Initialization, first poll, post-rollcall delay, then user interruption.
        with patch.object(monitor, "setup_logging"), patch.object(
            monitor, "_load_monitor_settings", return_value=10
        ), patch.object(monitor, "has_saved_session", return_value=True), patch.object(
            monitor.requests, "Session", return_value=session
        ), patch.object(monitor, "load_session", return_value=True), patch.object(
            monitor, "verify_session", return_value={"name": "Test"}
        ), patch.object(monitor.time, "sleep", side_effect=[None, None, None, KeyboardInterrupt]), patch.object(
            monitor, "process_rollcalls", return_value={"rollcalls": []}
        ) as process, patch.object(monitor, "Live") as live, patch.object(
            tui, "console", Console(file=io.StringIO())
        ):
            with self.assertRaises(SystemExit) as stopped:
                monitor.start_monitor(account)
            self.assertEqual(stopped.exception.code, 0)
            session.get.assert_called_once_with(
                f"{monitor.base_url}/api/radar/rollcalls", headers=monitor.headers)
            process.assert_called_once_with({"rollcalls": [{"id": 123}]}, session, account)
            self.assertEqual(live.return_value.start.call_count, 2)
            live.return_value.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
