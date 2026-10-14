import json
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from click.testing import CliRunner
from xmu_rollcall import cli


class RadarTests(unittest.TestCase):
    def invoke(self, args, rows=None, status=200, saved=True):
        config = {"current_account_id": 3, "accounts": [{"id": 3}, {"id": 4}]}
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = {"rollcalls": rows or []}
        session.put.return_value.status_code = status
        session.put.return_value.headers = {"Content-Type": "application/json"}
        session.put.return_value.json.return_value = {"status": "on_call_fine"}
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "setup_logging"))
            stack.enter_context(patch.object(cli, "load_config", return_value=config))
            load = stack.enter_context(patch.object(cli, "load_session", return_value=saved))
            stack.enter_context(patch.object(cli.requests, "Session", return_value=session))
            logger = stack.enter_context(patch.object(cli, "logger"))
            result = CliRunner().invoke(cli.cli, ["radar", *args])
        return result, session, load, logger

    def test_coordinate_forms_and_account_selection(self):
        for coordinates in (["24.1234", "118.5678"],
                            ["--latitude", "24.1234", "--longitude", "118.5678"]):
            for account in ([], ["--account-id", "4"]):
                with self.subTest(coordinates=coordinates, account=account):
                    result, session, load, _ = self.invoke([*coordinates, *account, "--rollcall-id", "42"])
                    self.assertEqual(result.exit_code, 0, result.output)
                    output = json.loads(result.output)
                    self.assertEqual((output["account_id"], output["rollcall_id"]), (4 if account else 3, 42))
                    self.assertEqual((output["latitude"], output["longitude"]), (24.1234, 118.5678))
                    load.assert_called_once_with(session, output["account_id"])
                    session.get.assert_not_called()

    def test_query_selects_only_pending_radar(self):
        rows = [{"rollcall_id": 1, "is_radar": False},
                {"rollcall_id": 2, "is_radar": True, "is_expired": True},
                {"rollcall_id": 3, "is_radar": True, "status": "on_call_fine"},
                {"rollcall_id": 42, "is_radar": True, "status": "absent"}]
        result, _, _, _ = self.invoke(["24", "118"], rows)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["rollcall_id"], 42)

    def test_no_or_ambiguous_rollcall_fails_without_submission_and_logs(self):
        for rows, message in [([], "No pending radar"),
                              ([{"is_radar": True, "rollcall_id": i} for i in (1, 2)], "Multiple pending")]:
            result, session, _, logger = self.invoke(["24", "118"], rows)
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn(message, result.output)
            session.put.assert_not_called()
            logger.exception.assert_called_once()

    def test_missing_invalid_or_conflicting_coordinates_do_not_submit(self):
        for args in ([], ["24"], ["nan", "118"], ["91", "118"], ["24", "181"],
                     ["--latitude", "24"], ["--latitude", "24", "--longitude", "118", "24", "118"]):
            with self.subTest(args=args):
                result, session, _, _ = self.invoke(args)
                self.assertNotEqual(result.exit_code, 0)
                session.put.assert_not_called()

    def test_missing_session_and_rejected_submission_fail(self):
        result, session, _, logger = self.invoke(["24", "118", "--rollcall-id", "42"], saved=False)
        self.assertNotEqual(result.exit_code, 0)
        session.put.assert_not_called()
        logger.exception.assert_called_once()
        result, _, _, logger = self.invoke(["24", "118", "--rollcall-id", "42"], status=403)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("HTTP 403", result.output)
        logger.exception.assert_called_once()
