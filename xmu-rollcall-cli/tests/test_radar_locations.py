import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from xmu_rollcall import config, radar


class RadarLocationTests(unittest.TestCase):
    def test_coordinate_separators_and_invalid_values(self):
        for text in ("24.1234 118.1234", "24.1234,118.1234", " 24.1234 , 118.1234 "):
            self.assertEqual(radar.parse_coordinates(text), (24.1234, 118.1234))
        for text in ("24", "24 118 3", "nan 118", "24 inf", "91 118", "24 181", "24,,118", "24，118"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                radar.parse_coordinates(text)

    def test_jsonl_roundtrip_preserves_order_and_notes(self):
        rows = [{"latitude": 24.1, "longitude": 118.1, "remark": "教室 A"},
                {"latitude": 24.2, "longitude": 118.2, "remark": "教室 B"}]
        with tempfile.TemporaryDirectory() as directory, patch.object(config, "CONFIG_DIR", Path(directory)):
            self.assertEqual(config.load_radar_locations(), [])
            config.save_radar_locations(rows)
            self.assertEqual(config.load_radar_locations(), rows)
            lines = (Path(directory) / "radar_locations.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line) for line in lines], rows)

    def test_bad_jsonl_rows_do_not_hide_valid_locations(self):
        row = {"latitude": 24, "longitude": 118, "remark": "valid"}
        invalid_rows = ["{broken", '{"latitude": 91, "longitude": 118, "remark": ""}',
                        '{"latitude": 24, "longitude": 118}', "[]"]
        with tempfile.TemporaryDirectory() as directory, patch.object(config, "CONFIG_DIR", Path(directory)):
            path = Path(directory) / "radar_locations.jsonl"
            path.write_text("\n".join([json.dumps(row), *invalid_rows, "", json.dumps(row)]), encoding="utf-8")
            with self.assertLogs("xmu_rollcall.config", level="WARNING") as logs:
                self.assertEqual(config.load_radar_locations(), [row, row])
            self.assertEqual(len(logs.output), 4)
            self.assertIn("line 2", logs.output[0])

    def test_saved_locations_stop_at_first_success(self):
        rows = [{"latitude": n, "longitude": 118, "remark": str(n)} for n in (24, 25, 26)]
        session = Mock()
        session.put.side_effect = [Mock(status_code=400), Mock(status_code=200)]
        with patch.object(config, "load_radar_locations", return_value=rows), patch.object(radar.tui, "prompt") as prompt:
            self.assertTrue(radar.answer_radar(session, 42))
        self.assertEqual([call.kwargs["json"]["latitude"] for call in session.put.call_args_list], [24, 25])
        prompt.assert_not_called()

    def test_all_failed_then_invalid_input_then_manual_submission(self):
        session = Mock()
        session.put.side_effect = [Mock(status_code=400), Mock(status_code=403), Mock(status_code=200)]
        rows = [{"latitude": n, "longitude": 118, "remark": ""} for n in (24, 25)]
        with patch.object(config, "load_radar_locations", return_value=rows), patch.object(
            radar.tui, "prompt", side_effect=["nan 118", "24.1234,118.1234"]
        ):
            self.assertTrue(radar.answer_radar(session, 42))
        self.assertEqual([call.kwargs["json"]["latitude"] for call in session.put.call_args_list], [24, 25, 24.1234])
        self.assertEqual(session.put.call_args.kwargs["json"]["longitude"], 118.1234)

    def test_empty_list_manual_failure_and_skip(self):
        for text, expected_calls in (("24 118", 1), ("", 0)):
            session = Mock()
            session.put.return_value.status_code = 400
            with patch.object(config, "load_radar_locations", return_value=[]), patch.object(radar.tui, "prompt", return_value=text):
                self.assertFalse(radar.answer_radar(session, 42))
            self.assertEqual(session.put.call_count, expected_calls)

    def test_retryable_failures_stop_location_fallback_and_propagate(self):
        failures = [requests.Timeout("offline"), requests.ConnectionError("disconnected"),
                    requests.exceptions.ChunkedEncodingError("incomplete response")]
        for status in (408, 429, 500, 502, 503, 504):
            response = requests.Response()
            response.status_code = status
            failures.append(response)
        rows = [{"latitude": n, "longitude": 118, "remark": ""} for n in (24, 25)]
        for failure in failures:
            with self.subTest(failure=failure):
                session = Mock()
                session.put.side_effect = [failure]
                expected = type(failure) if isinstance(failure, Exception) else requests.HTTPError
                with patch.object(config, "load_radar_locations", return_value=rows), patch.object(
                    radar.tui, "prompt"
                ) as prompt, self.assertRaises(expected):
                    radar.answer_radar(session, 42)
                session.put.assert_called_once()
                prompt.assert_not_called()

    def test_manual_submission_propagates_retryable_http_failure(self):
        response = requests.Response()
        response.status_code = 503
        session = Mock()
        session.put.return_value = response
        with patch.object(config, "load_radar_locations", return_value=[]), patch.object(
            radar.tui, "prompt", return_value="24 118"
        ) as prompt, self.assertRaises(requests.HTTPError) as raised:
            radar.answer_radar(session, 42)
        self.assertIs(raised.exception.response, response)
        session.put.assert_called_once()
        prompt.assert_called_once()

    def test_http_rejection_advances_to_next_saved_location(self):
        responses = []
        for status in (400, 403, 200):
            response = requests.Response()
            response.status_code = status
            response._content = b"{}"
            responses.append(response)
        session = Mock()
        session.put.side_effect = responses
        rows = [{"latitude": n, "longitude": 118, "remark": ""} for n in (24, 25, 26)]
        with patch.object(config, "load_radar_locations", return_value=rows), patch.object(
            radar.tui, "prompt"
        ) as prompt:
            self.assertTrue(radar.answer_radar(session, 42))
        self.assertEqual([call.kwargs["json"]["latitude"] for call in session.put.call_args_list], [24, 25, 26])
        prompt.assert_not_called()
