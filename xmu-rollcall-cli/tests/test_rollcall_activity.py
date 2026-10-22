import io
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

import requests
from rich.cells import cell_len
from rich.console import Console

from xmu_rollcall import rollcall_handler as handler, tui, verify
from xmu_rollcall import config


def rollcall(**changes):
    value = dict(course_title="高等数学[red]", created_by_name="陈老师",
                 department_name="数学学院", is_expired=False, is_number=True,
                 is_radar=False, rollcall_id=42, rollcall_status="absent",
                 scored=False, status="absent")
    value.update(changes)
    return value


class RollcallActivityTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.console_patch = patch.object(tui, "console", Console(file=self.output, width=100))
        self.console_patch.start()
        self.addCleanup(self.console_patch.stop)

    def test_number_wait_and_confirmation_use_real_data_without_plain_output(self):
        session = Mock()
        session.headers = {}
        session.put.return_value.status_code = 200
        snapshots = []
        with tui.rollcall_activity("同学", "1m", 12, 10) as view:
            update = view.update

            def capture(**changes):
                update(**changes)
                snapshots.append(dict(view.data))

            with patch.object(view, "update", side_effect=capture), patch.object(
                handler, "get_rollcall_settings", return_value={"wait_before_answer": "30%"}
            ), patch.object(handler, "_fetch_attendance", side_effect=[None, (7, 60), (18, 60)]), patch.object(
                verify, "get_number_rollcall_info", return_value=("0026", "ongoing", "2099-01-01T00:00:00Z", None)
            ), patch.object(handler.time, "sleep"), patch("builtins.print") as plain:
                result = handler.process_rollcalls({"rollcalls": [rollcall()]}, session)
                plain.assert_not_called()
        self.assertEqual(len(result["rollcalls"]), 1)
        self.assertEqual(session.put.call_args.kwargs["json"]["numberCode"], "0026")
        self.assertTrue(any(s["state"] == "waiting" and s["signed"] is None for s in snapshots))
        self.assertTrue(any(s["signed"] == 7 and s["target"] == 18 for s in snapshots))
        self.assertTrue(any(s["state"] == "submitting" for s in snapshots))
        self.assertEqual(snapshots[-1]["state"], "success")
        self.assertIn("0026", self.output.getvalue())
        self.assertFalse(tui.rollcall_output_active())

    def test_batch_results_and_branch_outcomes(self):
        calls = [rollcall(status="on_call_fine"),
                 rollcall(is_radar=True), rollcall(is_number=False)]
        session = Mock()
        with tui.rollcall_activity("同学", "1m", 12, 10) as view, patch.object(
            handler, "get_rollcall_settings", return_value={"wait_before_answer": False}
        ), patch.object(
            handler.time, "sleep"
        ) as sleep, patch.object(handler, "answer_radar", return_value=True):
            result = handler.process_rollcalls({"rollcalls": calls}, session)
            self.assertEqual(view.data["state"], "unsupported")
            self.assertEqual(len(view.results), 2)
            self.assertIn("already", view.results[0].plain)
            self.assertIn("success", view.results[1].plain)
            self.assertIsNone(view.data["number_code"])
        session.get.assert_not_called()
        session.put.assert_not_called()
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(300)])
        self.assertEqual(result, {"rollcalls": []})

    def test_radar_waits_once_before_list_and_manual_submissions(self):
        for wait_setting in (3, "30%"):
            with self.subTest(wait_setting=wait_setting):
                events = []
                session = Mock()

                def attendance(*args, **kwargs):
                    signed = len(events) + 1
                    events.append(f"attendance:{signed}")
                    return Mock(status_code=200, json=lambda: {"student_rollcalls": [
                        {"rollcall_status": "on_call_fine" if n < signed else "absent"}
                        for n in range(10)
                    ]})

                def submit(*args, **kwargs):
                    events.append(f"submit:{kwargs['json']['latitude']}")
                    return Mock(status_code=200 if kwargs["json"]["latitude"] == 26 else 400)

                session.get.side_effect = attendance
                session.put.side_effect = submit
                locations = [{"latitude": n, "longitude": 118, "remark": ""} for n in (24, 25)]
                with tui.rollcall_activity("同学", "1m", 12, 10) as view, patch.object(
                    config, "load_radar_locations", return_value=locations
                ), patch.object(tui, "submission_shortcut", return_value=nullcontext(lambda seconds: False)), patch.object(
                    tui, "prompt", return_value="26 118"
                ):
                    result = handler.process_rollcalls(
                        {"rollcalls": [rollcall(is_radar=True, is_number=False)]}, session,
                        {"rollcall_settings": {"wait_before_answer": wait_setting}},
                    )
                    self.assertEqual(view.data["state"], "success")
                    self.assertIsNone(view.data["number_code"])
                self.assertEqual(events, ["attendance:1", "attendance:2", "attendance:3",
                                          "submit:24", "submit:25", "submit:26.0"])
                self.assertEqual(len(result["rollcalls"]), 1)

    def test_radar_wait_timeout_does_not_submit_or_prompt(self):
        session = Mock()
        with tui.rollcall_activity("同学", "1m", 12, 10) as view, patch.object(
            handler, "WAIT_TIMEOUT", 0
        ), patch.object(tui, "prompt") as prompt:
            result = handler.process_rollcalls(
                {"rollcalls": [rollcall(is_radar=True)]}, session,
                {"rollcall_settings": {"wait_before_answer": 3}},
            )
            self.assertEqual(view.data["state"], "timeout")
        self.assertEqual(result, {"rollcalls": []})
        session.put.assert_not_called()
        prompt.assert_not_called()

    def test_radar_skip_wait_and_disabled_wait_submit_without_threshold(self):
        for wait_setting in (False, 3):
            with self.subTest(wait_setting=wait_setting):
                session = Mock()
                session.get.return_value.status_code = 200
                session.get.return_value.json.return_value = {"student_rollcalls": [
                    {"rollcall_status": "absent"} for _ in range(10)
                ]}
                session.put.return_value.status_code = 200
                with tui.rollcall_activity("同学", "1m", 12, 10) as view, patch.object(
                    config, "load_radar_locations",
                    return_value=[{"latitude": 24, "longitude": 118, "remark": ""}],
                ), patch.object(tui, "submission_shortcut", return_value=nullcontext(lambda seconds: True)):
                    handler.process_rollcalls(
                        {"rollcalls": [rollcall(is_radar=True)]}, session,
                        {"rollcall_settings": {"wait_before_answer": wait_setting}},
                    )
                    self.assertEqual(view.data["state"], "success")
                session.put.assert_called_once()
                self.assertEqual(session.get.call_count, 0 if wait_setting is False else 1)


    def test_error_and_interrupt_restore_output_and_propagate(self):
        for error, state in [(requests.Timeout("offline"), "failed"),
                             (KeyboardInterrupt(), "interrupted")]:
            with self.subTest(state=state):
                with self.assertRaises(type(error)):
                    with tui.rollcall_activity("同学", "1m", 12, 10) as view:
                        view.update(rollcall=rollcall(), index=1, count=1)
                        raise error
                self.assertEqual(view.data["state"], state)
                self.assertFalse(tui.rollcall_output_active())
        with patch("builtins.print") as plain:
            tui.log_and_print("Restored")
            plain.assert_called_once_with("Restored")

    def test_layout_and_literal_names_at_multiple_widths(self):
        for width in (40, 60, 80, 100, 120):
            for state in ("detected", "waiting", "timeout", "submitting", "success", "failed", "already", "unsupported"):
                with self.subTest(width=width, state=state):
                    output = io.StringIO()
                    console = Console(file=output, width=width, color_system=None)
                    with patch.object(tui, "console", console):
                        view = tui.RollcallView("同学[red]", "1m", 12, 10)
                        view.live = Mock()
                        view.update(rollcall=rollcall(), index=1, count=1)
                        view.update(state=state, number_code="0026", signed=7,
                                    total=60, target=18, target_label="30% (18 students)")
                        console.print(view.render())
                    text = output.getvalue()
                    self.assertIn("高等数学[red]", text)
                    self.assertTrue(all(cell_len(line) <= width for line in text.splitlines()))


if __name__ == "__main__":
    unittest.main()
