import unittest
from unittest.mock import Mock, patch

import requests

from xmu_rollcall import verify


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result.url = "https://lnt.xmu.edu.cn/api/timetable_rollcalls"
    result.json = Mock(return_value=payload)
    return result


class NumberRollcallTests(unittest.TestCase):
    def session(self, rows, rollcall_time="2026-10-10T01:57:40Z"):
        session = Mock()
        session.headers = {}
        session.get.side_effect = [
            response({"course_id": 113897, "rollcall_time": rollcall_time}),
            response({"rollcalls": rows}),
        ]
        return session

    def test_selects_requested_rollcall_and_preserves_leading_zero(self):
        session = self.session([
            {"id": 446054, "number_code": "9999", "status": "finished"},
            {"id": 446055, "number_code": "0026", "status": "ongoing",
             "end_time": "2026-10-10T02:42:40Z"},
        ])
        self.assertEqual(verify.get_number_rollcall_info(session, 446055),
                         ("0026", "ongoing", "2026-10-10T02:42:40Z", None))

    def test_campus_date_crosses_utc_midnight(self):
        session = self.session([{"id": 446055, "number_code": "4407"}],
                               rollcall_time="2026-10-09T16:05:00Z")
        self.assertEqual(verify.get_number_rollcall_info(session, 446055)[0], "4407")
        self.assertEqual(session.get.call_args.kwargs["params"],
                         {"course_ids": 113897, "rollcall_date": "2026-10-10"})

    def test_missing_rollcall_or_code_never_submits_another_code(self):
        for rows in ([{"id": 446054, "number_code": "9999"}],
                     [{"id": 446055, "number_code": None},
                      {"id": 446056, "number_code": "9999"}],
                     [{"id": 446055, "number_code": ""}], []):
            with self.subTest(rows=rows), patch.object(verify, "log_and_print"):
                session = self.session(rows)
                self.assertFalse(verify.send_code(session, 446055))
                session.put.assert_not_called()

    def test_timetable_network_errors_reach_monitor(self):
        for status in (429, 503):
            with self.subTest(status=status):
                session = self.session([])
                session.get.side_effect = [
                    response({"course_id": 113897, "rollcall_time": "2026-10-10T01:57:40Z"}),
                    response({}, status),
                ]
                with self.assertRaises(requests.HTTPError):
                    verify.get_number_rollcall_info(session, 446055)

    def test_unauthorized_or_malformed_response_does_not_submit(self):
        for result in (response({}, 401), response({"rollcalls": None})):
            with self.subTest(status=result.status_code), patch.object(verify, "log_and_print"):
                session = self.session([])
                session.get.side_effect = [
                    response({"course_id": 113897, "rollcall_time": "2026-10-10T01:57:40Z"}),
                    result,
                ]
                self.assertFalse(verify.send_code(session, 446055))
                session.put.assert_not_called()
