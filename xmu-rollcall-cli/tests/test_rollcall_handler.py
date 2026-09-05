import unittest
from unittest.mock import Mock, patch

from xmu_rollcall import rollcall_handler as handler
from xmu_rollcall.config import normalize_rollcall_settings


class WaitingTests(unittest.TestCase):
    def test_real_response_shape_and_percentage_boundaries(self):
        # Sanitized distribution from the supplied response; no personal fields.
        payload = {
            "status": "finished", "is_number": True, "is_radar": False,
            "student_rollcalls": [
                {"status": "on_call", "rollcall_status": "on_call_fine"}
                for _ in range(55)
            ] + [{"status": "absent", "rollcall_status": "absent"} for _ in range(4)],
        }
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = payload
        self.assertEqual(handler._fetch_attendance(session, 42), (55, 59))
        # This tests attendance thresholds only, not submission of a finished rollcall.
        for percentage, reached, target in [("20%", True, 12), ("93%", True, 55),
                                             ("94%", False, 56), ("100%", False, 59)]:
            with self.subTest(percentage=percentage), patch.object(
                handler.time, "sleep", side_effect=InterruptedError("still waiting")
            ) as sleep, patch.object(handler, "log_and_print") as output:
                if reached:
                    handler.wait_for_classmates(session, 42, {"wait_before_answer": percentage})
                    sleep.assert_not_called()
                else:
                    with self.assertRaises(InterruptedError):
                        handler.wait_for_classmates(session, 42, {"wait_before_answer": percentage})
                self.assertTrue(any(f"({target} students)" in str(call) for call in output.call_args_list))

    def test_percentage_rounds_up_and_keeps_waiting(self):
        with patch.object(handler, "_fetch_attendance", side_effect=[(1, 6), (2, 6)]) as fetch, patch.object(
            handler.time, "sleep"
        ) as sleep, patch.object(handler, "log_and_print"):
            handler.wait_for_classmates(Mock(), 42, {"wait_before_answer": "20%"})
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(handler.WAIT_POLL_INTERVAL)

    def test_exact_percentage_boundary(self):
        with patch.object(handler, "_fetch_attendance", return_value=(7, 100)), patch.object(
            handler.time, "sleep", side_effect=AssertionError("Should submit at exactly 7%")
        ), patch.object(handler, "log_and_print"):
            handler.wait_for_classmates(Mock(), 42, {"wait_before_answer": "7%"})

    def test_unavailable_attendance_waits(self):
        with patch.object(handler, "_fetch_attendance", side_effect=[None, (5, 10)]), patch.object(
            handler.time, "sleep"
        ) as sleep, patch.object(handler, "log_and_print"):
            handler.wait_for_classmates(Mock(), 42, {"wait_before_answer": "50%"})
        sleep.assert_called_once()

    def test_count_and_disabled_modes(self):
        with patch.object(handler, "_fetch_attendance", side_effect=[(2, 100), (3, 100)]) as fetch, patch.object(
            handler.time, "sleep"
        ), patch.object(handler, "log_and_print"):
            handler.wait_for_classmates(Mock(), 42, {"wait_before_answer": False})
            fetch.assert_not_called()
            handler.wait_for_classmates(Mock(), 42, {"wait_before_answer": 3})
            self.assertEqual(fetch.call_count, 2)

    def test_only_confirmed_rollcall_status_counts(self):
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = {"data": {"student_rollcalls": [
            {"rollcall_status": "on_call_fine", "status": "on_call"},
            {"status": "on_call"}, {"rollcall_status": "absent"}]}}
        self.assertEqual(handler._fetch_attendance(session, 42), (1, 3))

    def test_invalid_lists_fail_closed(self):
        session = Mock()
        session.get.return_value.status_code = 200
        for payload in ({}, {"student_rollcalls": []}, {"student_rollcalls": [None]},
                        {"student_rollcalls": "invalid"}):
            session.get.return_value.json.return_value = payload
            self.assertIsNone(handler._fetch_attendance(session, 42))

    def test_percentage_normalization(self):
        for value in ("20%", " 12.5% ", "100%"):
            self.assertTrue(normalize_rollcall_settings({"wait_before_answer": value})[
                "wait_before_answer"].endswith("%"))
        for value in ("0%", "-1%", "101%", "nan%", "inf%", "invalid%"):
            self.assertIs(normalize_rollcall_settings({"wait_before_answer": value})[
                "wait_before_answer"], False)
