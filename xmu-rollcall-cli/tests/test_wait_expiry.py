import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from xmu_rollcall import rollcall_handler as handler, verify
from test_rollcall_activity import rollcall


class WaitExpiryTests(unittest.TestCase):
    def test_expiry_stops_wait_and_never_submits(self):
        deadline = datetime.fromisoformat('2030-01-01T00:00:00+00:00').timestamp()
        now = [deadline - 1]
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) > 2:
                raise AssertionError('Still waiting after end_time')
            now[0] += seconds

        session = Mock()
        with patch.object(handler, 'get_rollcall_settings', return_value={'wait_before_answer': 10}), patch.object(
            verify, 'get_number_rollcall_info', return_value=('0026', 'ongoing', '2030-01-01T00:00:00Z', None)
        ), patch.object(handler, '_fetch_attendance', return_value=(1, 20)), patch.object(
            handler.time, 'time', side_effect=lambda: now[0]
        ), patch.object(handler.time, 'sleep', side_effect=sleep), patch.object(handler.tui, 'log_and_print'):
            result = handler.process_rollcalls({'rollcalls': [rollcall(is_number=True)]}, session)
        self.assertEqual(result, {'rollcalls': []})
        self.assertEqual(sleeps, [1])
        session.put.assert_not_called()

    def test_already_expired_never_fetches_even_when_wait_disabled(self):
        deadline = datetime.fromisoformat('2030-01-01T00:00:00+00:00').timestamp()
        with patch.object(handler.time, 'time', return_value=deadline), patch.object(
            handler, '_fetch_attendance'
        ) as fetch, patch.object(handler.time, 'sleep') as sleep:
            self.assertFalse(handler.wait_for_classmates(
                Mock(), 42, {'wait_before_answer': False}, end_time='2030-01-01T08:00:00+08:00'
            ))
        fetch.assert_not_called()
        sleep.assert_not_called()

    def test_expiry_during_attendance_request_overrides_reached_target(self):
        deadline = datetime.fromisoformat('2030-01-01T00:00:00+00:00').timestamp()
        now = [deadline - 1]

        def fetch(*args):
            now[0] = deadline
            return (20, 20)

        with patch.object(handler.time, 'time', side_effect=lambda: now[0]), patch.object(
            handler, '_fetch_attendance', side_effect=fetch
        ), patch.object(handler.time, 'sleep') as sleep:
            self.assertFalse(handler.wait_for_classmates(
                Mock(), 42, {'wait_before_answer': '50%'}, end_time='2030-01-01T00:00:00Z'
            ))
        sleep.assert_not_called()

    def test_unavailable_attendance_also_stops_at_deadline(self):
        deadline = datetime.fromisoformat('2030-01-01T00:00:00+00:00').timestamp()
        now = [deadline - 1]

        def sleep(seconds):
            now[0] += seconds

        with patch.object(handler.time, 'time', side_effect=lambda: now[0]), patch.object(
            handler, '_fetch_attendance', return_value=None
        ), patch.object(handler.time, 'sleep', side_effect=sleep):
            self.assertFalse(handler.wait_for_classmates(
                Mock(), 42, {'wait_before_answer': '50%'}, end_time='2030-01-01T00:00:00Z'
            ))
        self.assertEqual(now[0], deadline)

    def test_missing_or_invalid_deadline_waits_for_target_then_submits(self):
        for end_time in (None, '', 'invalid-date', '2026-02-30T00:00:00Z', 123, [], {}):
            with self.subTest(end_time=end_time):
                self.assert_waits_for_target_then_submits(end_time)

    def assert_waits_for_target_then_submits(self, end_time):
        session = Mock()
        session.headers = {}
        session.put.return_value.status_code = 200
        with patch.object(handler, 'get_rollcall_settings', return_value={'wait_before_answer': 10}), patch.object(
            verify, 'get_number_rollcall_info', return_value=('0026', 'ongoing', end_time, None)
        ), patch.object(handler, '_fetch_attendance', side_effect=[None, (9, 20), (10, 20)]), patch.object(
            handler.time, 'sleep'
        ) as sleep:
            data = {'rollcalls': [rollcall(is_number=True)]}
            self.assertEqual(handler.process_rollcalls(data, session), data)
        self.assertEqual([call.args[0] for call in sleep.call_args_list],
                         [handler.WAIT_POLL_INTERVAL, handler.WAIT_POLL_INTERVAL, 5])
        session.put.assert_called_once()
        self.assertEqual(session.put.call_args.kwargs['json']['numberCode'], '0026')

    def test_invalid_deadline_with_wait_disabled_proceeds_immediately(self):
        with patch.object(handler, '_fetch_attendance') as fetch, patch.object(handler.time, 'sleep') as sleep:
            self.assertTrue(handler.wait_for_classmates(
                Mock(), 42, {'wait_before_answer': False}, end_time='invalid-date'
            ))
        fetch.assert_not_called()
        sleep.assert_not_called()

    def test_target_reached_before_deadline_still_submits(self):
        deadline = datetime.fromisoformat('2030-01-01T00:00:00+00:00').timestamp()
        session = Mock()
        session.headers = {}
        session.put.return_value.status_code = 200
        with patch.object(handler, 'get_rollcall_settings', return_value={'wait_before_answer': 10}), patch.object(
            verify, 'get_number_rollcall_info', return_value=('0026', 'ongoing', '2030-01-01T00:00:00Z', None)
        ), patch.object(handler, '_fetch_attendance', return_value=(10, 20)), patch.object(
            handler.time, 'time', return_value=deadline - 1
        ), patch.object(handler.time, 'sleep'):
            data = {'rollcalls': [rollcall(is_number=True)]}
            self.assertEqual(handler.process_rollcalls(data, session), data)
        session.put.assert_called_once()
        self.assertEqual(session.put.call_args.kwargs['json']['numberCode'], '0026')
