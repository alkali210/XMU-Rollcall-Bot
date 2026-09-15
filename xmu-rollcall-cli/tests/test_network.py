import io
import ssl
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import requests
from rich.console import Console
from urllib3.exceptions import MaxRetryError, SSLError as UrllibSSLError

from xmu_rollcall import monitor, network, utils, verify, rollcall_handler


def response(data=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = data or {"rollcalls": []}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(response=result)
    return result


class NetworkTests(unittest.TestCase):
    def test_disabled_monitor_retries_exit_on_first_error(self):
        for error in (requests.Timeout("Read timed out"),
                      requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING"),
                      response(status=503)):
            with self.subTest(error=error):
                code, sleeps, session, _, output = self.run_monitor([error], disable_retry=True)
                self.assertEqual(code, 1)
                self.assertEqual(session.get.call_count, 1)
                self.assertFalse(any(s >= 5 for s in sleeps))
                self.assertNotIn("Retry 1/10", output)

    def test_monitor_loads_retry_setting(self):
        with patch.object(monitor, "load_config", return_value={"disable_monitor_retry": True}):
            self.assertEqual(monitor._load_monitor_settings(), (10, True))

    def test_retry_reports_original_error_in_red(self):
        error = requests.ConnectionError("Connection reset [details]\nOriginal server error")
        with patch.object(monitor.tui.console, "print") as output, patch.object(monitor.logger, "warning") as log:
            monitor._report_retry(error, 5, 1)
        rendered = output.call_args.args[0]
        self.assertEqual(rendered.style, "red")
        self.assertIn(str(error), rendered.plain)
        self.assertIn("ConnectionError:", rendered.plain)
        self.assertIn("Retry 1/10 in 5s", rendered.plain)
        log.assert_called_once_with(rendered.plain)

    def test_retry_limit_reports_last_error_in_red(self):
        error = requests.Timeout("Read timed out")
        with patch.object(monitor.tui.console, "print") as output, patch.object(monitor.logger, "error") as log:
            monitor._report_retry_limit(error)
        rendered = output.call_args.args[0]
        self.assertEqual(rendered.style, "red")
        self.assertIn("Timeout: Read timed out", rendered.plain)
        self.assertIn("retry limit reached (10 retries)", rendered.plain)
        log.assert_called_once_with(rendered.plain)

    def run_monitor(self, outcomes, process=None, interrupt_delay=None, disable_retry=False):
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
                "setup_logging": None, "_load_monitor_settings": (10, disable_retry),
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

    def test_startup_network_errors_fail_without_retry(self):
        for cached in (True, False):
            with self.subTest(cached=cached), ExitStack() as stack:
                for name, value in {
                    "setup_logging": None, "_load_monitor_settings": (10, False),
                    "has_saved_session": cached, "load_session": True,
                    "clear_screen": None,
                }.items():
                    stack.enter_context(patch.object(monitor, name, return_value=value))
                stack.enter_context(patch.object(monitor.os.path, "exists", return_value=False))
                stack.enter_context(patch.object(monitor.tui, "console", Console(file=io.StringIO())))
                sleep = stack.enter_context(patch.object(monitor.time, "sleep"))
                retry = stack.enter_context(patch.object(monitor, "_report_retry"))
                error = requests.Timeout("startup failure")
                operation = stack.enter_context(patch.object(
                    monitor, "verify_session" if cached else "xmulogin", side_effect=error))
                with self.assertRaises(requests.Timeout) as raised:
                    monitor.start_monitor({"id": 1, "username": "test", "password": "unused"})
                self.assertIs(raised.exception, error)
                operation.assert_called_once()
                retry.assert_not_called()
                self.assertFalse(any(call.args[0] >= 5 for call in sleep.call_args_list))

    def test_ssl_eof_recovers_with_backoff(self):
        eof = ssl.SSLEOFError(8, "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
        wrapped = requests.exceptions.SSLError(MaxRetryError(
            None, "/api/radar/rollcalls", reason=UrllibSSLError(eof)))
        for error in (wrapped, requests.exceptions.SSLError(str(wrapped)),
                      requests.exceptions.SSLError(ssl.SSLEOFError(8, "EOF"))):
            with self.subTest(error=error):
                code, sleeps, _, _, output = self.run_monitor([error, response(), KeyboardInterrupt()])
                self.assertEqual(code, 0)
                self.assertEqual([s for s in sleeps if s >= 5], [5])
                self.assertIn("Network recovered", output)

    def test_certificate_and_other_ssl_errors_are_not_retryable(self):
        for error in (ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"),
                      ssl.SSLError(1, "WRONG_VERSION_NUMBER")):
            wrapped = requests.exceptions.SSLError(MaxRetryError(None, "/", reason=UrllibSSLError(error)))
            self.assertFalse(network.is_retryable(wrapped))

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
