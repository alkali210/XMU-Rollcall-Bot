import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from xmu_rollcall.cli import INSTALL_URL, cli, detect_install_method


UV_ARGV = ["uv", "tool", "install", "--upgrade", "--force", INSTALL_URL]
PIP_ARGV = ["pip", "install", "--upgrade", INSTALL_URL]
UV_PACKAGE = (
    "/home/user/.local/share/uv/tools/xmu-rollcall-cli"
    "/lib/python3.12/site-packages/xmu_rollcall/cli.py"
)
UV_PREFIX = "/home/user/.local/share/uv/tools/xmu-rollcall-cli"
PIP_PACKAGE = "/home/user/proj/.venv/lib/python3.12/site-packages/xmu_rollcall/cli.py"
SOURCE_PACKAGE = "/home/user/src/xmu-rollcall-cli/xmu_rollcall/cli.py"


class InstallDetectionTests(unittest.TestCase):
    def detect(self, package, executable="/usr/bin/python3", prefix="/usr", frozen=False):
        with patch("shutil.which", return_value="/usr/bin/uv") as which:
            method = detect_install_method(
                package=package, executable=executable, prefix=prefix, frozen=frozen,
            )
        which.assert_not_called()
        return method

    def test_agreeing_uv_tool_paths_guess_uv(self):
        self.assertEqual(self.detect(UV_PACKAGE, prefix=UV_PREFIX), "uv")

    def test_windows_uv_tool_paths_guess_uv_without_resolving_the_interpreter(self):
        package = (
            r"C:\Users\me\AppData\Roaming\uv\tools\xmu-rollcall-cli"
            r"\Lib\site-packages\xmu_rollcall\cli.py"
        )
        prefix = r"C:\Users\me\AppData\Roaming\uv\tools\xmu-rollcall-cli"
        # uv's tool Python is often a symlink to a base interpreter outside the tool env.
        self.assertEqual(
            self.detect(package, executable=r"C:\Users\me\AppData\Roaming\uv\python\python.exe",
                        prefix=prefix),
            "uv",
        )

    def test_uv_receipt_guesses_uv_without_a_uv_tools_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom-tools" / "xmu-rollcall-cli"
            package = root / "lib" / "python3.12" / "site-packages" / "xmu_rollcall" / "cli.py"
            package.parent.mkdir(parents=True)
            package.write_text("", encoding="utf-8")
            (root / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
            (root / "uv-receipt.toml").write_text("[tool]\n", encoding="utf-8")
            self.assertEqual(
                self.detect(package, executable="/usr/bin/python3", prefix=root),
                "uv",
            )

    def test_pip_site_packages_stay_pip_when_uv_is_on_path(self):
        self.assertEqual(self.detect(PIP_PACKAGE), "pip")

    def test_plain_checkout_is_unknown_when_uv_is_on_path(self):
        self.assertIsNone(self.detect(SOURCE_PACKAGE))

    def test_conflicting_uv_and_pip_signals_are_unknown(self):
        self.assertIsNone(self.detect(
            PIP_PACKAGE,
            executable="/home/user/.local/share/uv/tools/xmu-rollcall-cli/bin/python",
            prefix="/usr",
        ))
        self.assertIsNone(self.detect(UV_PACKAGE, executable="/usr/bin/python3", prefix="/usr"))

    def test_frozen_executable_is_unknown(self):
        self.assertIsNone(self.detect(UV_PACKAGE, prefix=UV_PREFIX, frozen=True))

    def test_which_uv_is_not_consulted(self):
        with patch("shutil.which", side_effect=AssertionError("PATH must not be consulted")):
            self.assertEqual(
                detect_install_method(package=PIP_PACKAGE, executable="/usr/bin/python3",
                                      prefix="/usr", frozen=False),
                "pip",
            )


class UpdateCommandTests(unittest.TestCase):
    def invoke(self, args, *, input=None, detect="uv", interactive=False):
        with patch("xmu_rollcall.cli.setup_logging") as setup_logging, patch(
            "xmu_rollcall.cli.load_config", return_value={}
        ) as load_config, patch("xmu_rollcall.cli.save_config") as save_config, patch(
            "xmu_rollcall.cli.detect_install_method", return_value=detect
        ) as detect_mock, patch(
            "xmu_rollcall.cli._stdin_is_interactive", return_value=interactive
        ), patch("shutil.which", return_value="/usr/bin/uv"), patch(
            "xmu_rollcall.cli.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            result = CliRunner().invoke(cli, args, input=input)
        return result, setup_logging, load_config, save_config, run, detect_mock

    def test_guessed_uv_installs_only_after_confirmation(self):
        result, setup_logging, load_config, save_config, run, _detect = self.invoke(
            ["update"], input="y\n", interactive=True,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Guessed install method: uv.", result.output)
        self.assertIn("where the program is running", result.output)
        self.assertIn("uv is on", result.output)
        self.assertIn("Command: uv tool install --upgrade --force", result.output)
        run.assert_called_once_with(UV_ARGV)
        setup_logging.assert_not_called()
        load_config.assert_not_called()
        save_config.assert_not_called()

    def test_declining_the_guess_does_not_install(self):
        result, _setup, _load, _save, run, _detect = self.invoke(
            ["upgrade"], input="n\n", detect="pip", interactive=True,
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Guessed install method: pip.", result.output)
        self.assertIn("Update cancelled.", result.output)
        run.assert_not_called()

    def test_uv_on_path_does_not_install_when_detection_is_unknown(self):
        result, setup_logging, load_config, save_config, run, _detect = self.invoke(
            ["update"], detect=None, interactive=False,
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Could not tell how this copy was installed", result.output)
        self.assertIn("--uv", result.output)
        self.assertIn("--pip", result.output)
        run.assert_not_called()
        setup_logging.assert_not_called()
        load_config.assert_not_called()
        save_config.assert_not_called()

    def test_yes_without_an_explicit_method_does_not_install(self):
        result, _setup, _load, _save, run, _detect = self.invoke(
            ["update", "--yes"], detect="uv", interactive=False,
        )
        self.assertNotEqual(result.exit_code, 0, result.output)
        self.assertIn("Refusing to install without a prompt", result.output)
        run.assert_not_called()

    def test_explicit_uv_and_yes_skips_detection_and_the_prompt(self):
        result, _setup, _load, _save, run, detect_mock = self.invoke(
            ["update", "--uv", "--yes"], detect=None, interactive=False,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Install method: uv (--uv).", result.output)
        run.assert_called_once_with(UV_ARGV)
        detect_mock.assert_not_called()

    def test_explicit_pip_overrides_a_uv_guess(self):
        result, _setup, _load, _save, run, detect_mock = self.invoke(
            ["upgrade", "--pip", "--yes"], detect="uv", interactive=False,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        run.assert_called_once_with(PIP_ARGV)
        detect_mock.assert_not_called()

    def test_explicit_method_without_yes_refuses_when_noninteractive(self):
        result, _setup, _load, _save, run, _detect = self.invoke(
            ["update", "--pip"], interactive=False,
        )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Install method: pip (--pip).", result.output)
        self.assertIn("Command: pip install --upgrade", result.output)
        self.assertIn("Refusing to install without a prompt", result.output)
        run.assert_not_called()

    def test_explicit_method_still_confirms_interactively_without_yes(self):
        result, _setup, _load, _save, run, detect_mock = self.invoke(
            ["update", "--uv"], input="y\n", detect="pip", interactive=True,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        run.assert_called_once_with(UV_ARGV)
        detect_mock.assert_not_called()

    def test_both_install_flags_are_rejected(self):
        result, _setup, _load, _save, run, detect_mock = self.invoke(
            ["update", "--uv", "--pip", "--yes"],
        )
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Pass only one of --uv or --pip.", result.output)
        run.assert_not_called()
        detect_mock.assert_not_called()

    def test_unknown_interactive_choice_then_confirms(self):
        result, _setup, _load, _save, run, _detect = self.invoke(
            ["update"], input="pip\ny\n", detect=None, interactive=True,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Could not tell how this copy was installed", result.output)
        self.assertIn("Install method: pip.", result.output)
        run.assert_called_once_with(PIP_ARGV)

    def test_missing_installer_is_reported(self):
        with patch("xmu_rollcall.cli.setup_logging"), patch(
            "xmu_rollcall.cli._stdin_is_interactive", return_value=False
        ), patch("xmu_rollcall.cli.subprocess.run", side_effect=FileNotFoundError):
            result = CliRunner().invoke(cli, ["update", "--uv", "--yes"])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Could not run uv", result.output)

    def test_menu_update_confirms_and_returns_to_the_menu(self):
        result, _setup, _load, _save, run, _detect = self.invoke(
            [], input="6\ny\n", interactive=True,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        run.assert_called_once_with(UV_ARGV)
        self.assertIn("Goodbye", result.output)
        self.assertEqual(result.output.count("Welcome back"), 2)

    def test_menu_upgrade_alias_can_cancel_and_return(self):
        result, _setup, _load, _save, run, _detect = self.invoke(
            [], input="upgrade\nn\n", detect="pip", interactive=True,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        run.assert_not_called()
        self.assertIn("Update cancelled.", result.output)
        self.assertIn("Goodbye", result.output)
        self.assertEqual(result.output.count("Welcome back"), 2)


if __name__ == "__main__":
    unittest.main()
