import io
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import requests
from rich.console import Console

from xmu_rollcall import monitor, network, utils, verify, rollcall_handler


def response(data=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = data or {"rollcalls": []}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(response=result)
    return result


class NetworkTests(unittest.TestCase):
    def run_monitor(self, outcomes, process=None, interrupt_delay=None):
        session = Mock()
        session.get.side_effect = outcomes
        clock = [1000.0]
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if seconds == interrupt_delay:
                raise KeyboardInterrupt
            clock[0] += max(seconds, 1)

        with ExitStack() as stack:
            for name, value in {
                "setup_logging": None, "_load_monitor_settings": 10,
                "has_saved_session": True, "load_session": True,
                "verify_session": {"name": "Test"}, "clear_screen": None,
            }.items():
                stack.enter_context(patch.object(monitor, name, return_value=value))
            stack.enter_context(patch.object(monitor.requests, "Session", return_value=session))
            stack.enter_context(patch.object(monitor.time, "time", side_effect=lambda: clock[0]))
            stack.enter_context(patch.object(monitor.time, "sleep", side_effect=sleep))
            live = stack.enter_context(patch.object(monitor, "Live")).return_value
            output = io.StringIO()
            stack.enter_context(patch.object(monitor.tui, "console", Console(file=output)))
            handler = stack.enter_context(patch.object(monitor, "process_rollcalls", side_effect=process))
            with self.assertRaises(SystemExit) as stopped:
                monitor.start_monitor({"id": 1, "username": "test", "password": "unused"})
        live.stop.assert_called()
        return stopped.exception.code, sleeps, session, handler, output.getvalue()

    def test_disconnect_backoff_cap_recovery_and_reset(self):
        code, sleeps, session, _, output = self.run_monitor(
            [requests.ConnectionError() for _ in range(7)] +
            [response(), requests.Timeout(), response(), KeyboardInterrupt()])
        self.assertEqual(code, 0)
        self.assertEqual([s for s in sleeps if s >= 5], [5, 10, 20, 40, 60, 60, 60, 5])
        self.assertEqual(session.get.call_count, 11)
        self.assertIn("Network recovered", output)
        for call in session.get.call_args_list:
            self.assertEqual(call.kwargs["timeout"], network.REQUEST_TIMEOUT)

    def test_monitor_stops_after_ten_retries(self):
        code, sleeps, session, _, output = self.run_monitor(
            [requests.ConnectionError() for _ in range(11)])
        self.assertEqual(code, 1)
        self.assertEqual(session.get.call_count, 11)
        self.assertEqual([s for s in sleeps if s >= 5], [5, 10, 20, 40] + [60] * 6)
        self.assertIn("retry limit reached (10 retries)", output)

    def test_last_retry_can_recover_and_reset_count(self):
        code, sleeps, session, _, _ = self.run_monitor(
            [requests.Timeout() for _ in range(10)] + [response()] +
            [requests.Timeout() for _ in range(10)] + [response(), KeyboardInterrupt()])
        self.assertEqual(code, 0)
        self.assertEqual(session.get.call_count, 23)
        self.assertEqual([s for s in sleeps if s >= 5], ([5, 10, 20, 40] + [60] * 6) * 2)

    def test_initialization_stops_after_ten_retries(self):
        error = requests.Timeout()
        operation = Mock(side_effect=error)
        with patch.object(monitor.time, "sleep") as sleep, patch.object(monitor.tui, "echo"):
            with self.assertRaises(requests.Timeout) as raised:
                monitor._retry_initialization(operation)
        self.assertIs(raised.exception, error)
        self.assertEqual(operation.call_count, 11)
        self.assertEqual(sleep.call_count, 10)

    def test_initialization_last_retry_can_succeed(self):
        operation = Mock(side_effect=[requests.Timeout() for _ in range(10)] + ["ok"])
        with patch.object(monitor.time, "sleep") as sleep, patch.object(monitor.tui, "echo"):
            self.assertEqual(monitor._retry_initialization(operation), "ok")
        self.assertEqual(operation.call_count, 11)
        self.assertEqual(sleep.call_count, 10)

    def test_transient_http_and_truncated_response_recover(self):
        code, sleeps, _, _, _ = self.run_monitor([
            response(status=503), requests.exceptions.ChunkedEncodingError(),
            response(), KeyboardInterrupt()])
        self.assertEqual(code, 0)
        self.assertEqual([s for s in sleeps if s >= 5], [5, 10])

    def test_interrupted_processing_is_not_cached_as_handled(self):
        data = {"rollcalls": [{"id": 123}]}
        code, _, _, handler, _ = self.run_monitor(
            [response(data), response(data), KeyboardInterrupt()],
            process=[requests.Timeout(), {"rollcalls": []}])
        self.assertEqual(code, 0)
        self.assertEqual(handler.call_count, 2)

    def test_interrupt_during_backoff_exits_cleanly(self):
        code, _, session, _, _ = self.run_monitor([requests.ConnectionError()], interrupt_delay=5)
        self.assertEqual(code, 0)
        self.assertEqual(session.get.call_count, 1)

    def test_permanent_errors_are_not_retried(self):
        for error in (ValueError("bad JSON"), requests.exceptions.SSLError(),
                      response(status=401), response(status=403)):
            with self.subTest(error=error):
                code, sleeps, session, _, _ = self.run_monitor([error])
                self.assertEqual(code, 1)
                self.assertEqual(session.get.call_count, 1)
                self.assertNotIn(5, sleeps)

    def test_initialization_retries_transport_errors_only(self):
        operation = Mock(side_effect=[requests.ConnectionError(), requests.Timeout(), "ok"])
        with patch.object(monitor.time, "sleep") as sleep, patch.object(monitor, "_report_retry"):
            self.assertEqual(monitor._retry_initialization(operation), "ok")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10])
        self.assertIsNone(monitor._retry_initialization(lambda: None))

    def test_cached_session_network_failure_is_not_expiration(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()
        with self.assertRaises(requests.Timeout):
            utils.verify_session(session)
        session.get.side_effect = None
        session.get.return_value = response(status=401)
        self.assertEqual(utils.verify_session(session), {})

    def test_api_failures_reach_monitor_without_replaying_submission(self):
        for operation in (
            lambda s: verify.get_number_rollcall_info(s, 42),
            lambda s: verify.submit_number_code(s, 42, "1234"),
            lambda s: verify.send_radar(s, 42),
            lambda s: rollcall_handler._fetch_attendance(s, 42),
        ):
            with self.subTest(operation=operation):
                session = Mock()
                session.headers = {}
                session.get.side_effect = requests.Timeout()
                session.put.side_effect = requests.Timeout()
                with self.assertRaises(requests.Timeout):
                    operation(session)
                self.assertEqual(session.get.call_count + session.put.call_count, 1)
