import unittest
from unittest.mock import Mock, patch

from xmu_rollcall import rollcall_handler as handler, verify, tui
from test_rollcall_activity import rollcall


class WaitTimeoutTests(unittest.TestCase):
    def test_timeout_returns_to_monitor_without_submission(self):
        for attendance in ((1, 20), None):
            with self.subTest(attendance=attendance):
                now = [1000.0]
                sleeps = []

                def sleep(seconds):
                    sleeps.append(seconds)
                    if len(sleeps) > 60:
                        raise AssertionError('Still waiting after five minutes')
                    now[0] += seconds

                session = Mock()
                with patch.object(handler, 'get_rollcall_settings', return_value={'wait_before_answer': 10}), patch.object(
                    verify, 'get_number_rollcall_info', return_value=('0026', 'ongoing', None, None)
                ), patch.object(handler, '_fetch_attendance', return_value=attendance) as fetch, patch.object(
                    handler.time, 'monotonic', side_effect=lambda: now[0]
                ), patch.object(handler.time, 'sleep', side_effect=sleep), patch.object(
                    tui, 'log_and_print'
                ) as output, patch.object(tui, 'update_rollcall') as update:
                    result = handler.process_rollcalls({'rollcalls': [rollcall()]}, session)
                self.assertEqual(result, {'rollcalls': []})
                self.assertEqual(now[0], 1300)
                self.assertEqual(sleeps, [5] * 60)
                self.assertEqual(fetch.call_count, 60)
                session.put.assert_not_called()
                update.assert_called_with(state='timeout')
                self.assertFalse(any('Answering failed.' in str(call) for call in output.call_args_list))

    def test_timeout_during_attendance_request_overrides_reached_target(self):
        now = [1000.0]

        def fetch(*args):
            now[0] += 300
            return (20, 20)

        with patch.object(handler.time, 'monotonic', side_effect=lambda: now[0]), patch.object(
            handler, '_fetch_attendance', side_effect=fetch
        ), patch.object(handler.time, 'sleep') as sleep:
            self.assertFalse(handler.wait_for_classmates(Mock(), 42, {'wait_before_answer': '50%'}))
        sleep.assert_not_called()

    def test_final_sleep_is_limited_to_remaining_time(self):
        now = [1000.0]

        def fetch(*args):
            now[0] += 299
            return (0, 20)

        def sleep(seconds):
            now[0] += seconds

        with patch.object(handler.time, 'monotonic', side_effect=lambda: now[0]), patch.object(
            handler, '_fetch_attendance', side_effect=fetch
        ) as attendance, patch.object(handler.time, 'sleep', side_effect=sleep) as pause:
            self.assertFalse(handler.wait_for_classmates(Mock(), 42, {'wait_before_answer': 10}))
        attendance.assert_called_once()
        pause.assert_called_once_with(1)

    def test_disabled_wait_proceeds_without_starting_a_timer(self):
        with patch.object(handler.time, 'monotonic') as clock, patch.object(
            handler, '_fetch_attendance'
        ) as fetch, patch.object(handler.time, 'sleep') as sleep:
            self.assertTrue(handler.wait_for_classmates(Mock(), 42, {'wait_before_answer': False}))
        clock.assert_not_called()
        fetch.assert_not_called()
        sleep.assert_not_called()

    def test_api_end_time_does_not_affect_wait_or_submission(self):
        for end_time in (None, 'invalid-date', '2000-01-01T00:00:00Z'):
            with self.subTest(end_time=end_time):
                session = Mock()
                session.headers = {}
                session.put.return_value.status_code = 200
                with patch.object(handler, 'get_rollcall_settings', return_value={'wait_before_answer': 10}), patch.object(
                    verify, 'get_number_rollcall_info', return_value=('0026', 'ongoing', end_time, None)
                ), patch.object(handler, '_fetch_attendance', side_effect=[None, (9, 20), (10, 20)]), patch.object(
                    handler.time, 'monotonic', return_value=1000
                ), patch.object(handler.time, 'sleep'):
                    data = {'rollcalls': [rollcall()]}
                    self.assertEqual(handler.process_rollcalls(data, session), data)
                session.put.assert_called_once()
                self.assertEqual(session.put.call_args.kwargs['json']['numberCode'], '0026')
