import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from xmu_rollcall import config, secure_store
from xmu_rollcall.cli import cli


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.old_paths = secure_store._paths()
        self.patches = [patch.object(config, "CONFIG_DIR", self.directory),
                        patch.object(config, "CONFIG_FILE", self.directory / "config.json")]
        for item in self.patches:
            item.start()
        secure_store.configure(self.directory)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for item in self.patches:
            item.stop()
        secure_store.configure(self.old_paths[0])
        self.temp.cleanup()

    def seed(self, legacy=False):
        secure_store.upsert_account({"id": 1, "name": "Test", "username": "student",
                                     "password": "secret"})
        secure_store.save_session(1, {"token": "session-secret"})
        if legacy:
            with secure_store._connect() as conn:
                conn.execute("ALTER TABLE accounts ADD COLUMN rollcall_settings TEXT NOT NULL DEFAULT '{}'")
                conn.execute('UPDATE accounts SET rollcall_settings = ?',
                             (json.dumps({"wait_before_answer": 7}),))

    def test_migration_preserves_secrets_and_session(self):
        self.seed(legacy=True)
        loaded = config.load_config()
        self.assertEqual(loaded["accounts"][0]["rollcall_settings"]["wait_before_answer"], 7)
        public = json.loads(config.CONFIG_FILE.read_text())
        self.assertEqual(public["accounts"], [{"id": 1, "rollcall_settings": {"wait_before_answer": 7}}])
        self.assertNotIn("secret", config.CONFIG_FILE.read_text())
        self.assertEqual(secure_store.list_accounts()[0]["rollcall_settings"], {})
        self.assertEqual(secure_store.load_session(1), {"token": "session-secret"})
        self.assertEqual(config.load_config(), loaded)

    def test_manual_settings_override_database(self):
        self.seed(legacy=True)
        config.CONFIG_FILE.write_text(json.dumps({"interval": 15, "current_account_id": 1,
            "accounts": [{"id": 1, "rollcall_settings": {"wait_before_answer": False}}]}))
        loaded = config.load_config()
        self.assertIs(loaded["accounts"][0]["rollcall_settings"]["wait_before_answer"], False)
        self.assertEqual(config.get_interval(loaded), 15)

    def test_failed_json_write_keeps_legacy_settings(self):
        self.seed(legacy=True)
        with patch.object(config.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                config.load_config()
        self.assertEqual(secure_store.list_accounts()[0]["rollcall_settings"]["wait_before_answer"], 7)

    def test_broken_json_is_not_overwritten(self):
        self.seed(legacy=True)
        config.CONFIG_FILE.write_text("{broken")
        with self.assertRaises(RuntimeError):
            config.load_config()
        self.assertEqual(config.CONFIG_FILE.read_text(), "{broken")

    def test_settings_follow_account_after_deletion(self):
        self.seed()
        loaded = config.load_config()
        config.add_account(loaded, "second", "password2", "Second")
        config.set_rollcall_settings(loaded["accounts"][1], {"wait_before_answer": 9})
        config.save_config(loaded)
        config.delete_account(loaded, 1)
        config.save_config(loaded)
        reloaded = config.load_config()
        self.assertEqual(reloaded["accounts"][0]["username"], "second")
        self.assertEqual(reloaded["accounts"][0]["rollcall_settings"]["wait_before_answer"], 9)
        self.assertEqual(len(json.loads(config.CONFIG_FILE.read_text())["accounts"]), 1)

    def test_interval_menu_validates_and_persists(self):
        with patch("xmu_rollcall.cli.setup_logging"):
            result = CliRunner().invoke(cli, ["config"], input="i\n0\n-2\nnan\ninf\n2.5\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(config.load_config()["interval"], 2.5)

    def test_wait_menu_saves_only_public_settings(self):
        self.seed()
        with patch("xmu_rollcall.cli.setup_logging"):
            result = CliRunner().invoke(cli, ["config"], input="s\n1\n4\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(config.load_config()["accounts"][0]["rollcall_settings"]["wait_before_answer"], 4)
        self.assertEqual(secure_store.list_accounts()[0]["rollcall_settings"], {})
        self.assertEqual(secure_store.load_session(1), {"token": "session-secret"})

    def test_invalid_intervals_use_default(self):
        for value in (None, True, 0, -1, "bad", "nan", "inf"):
            self.assertEqual(config.get_interval({"interval": value}), 10)

    def test_percentage_menu_round_trip(self):
        self.seed()
        with patch("xmu_rollcall.cli.setup_logging"):
            result = CliRunner().invoke(cli, ["config"], input="s\n1\n20%\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(config.load_config()["accounts"][0]["rollcall_settings"]["wait_before_answer"], "20.0%")
        self.assertIn("20.0% of students", result.output)


if __name__ == "__main__":
    unittest.main()
