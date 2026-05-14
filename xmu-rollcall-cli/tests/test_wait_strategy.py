from xmu_rollcall import rollcall_handler


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, timeout=None):
        return FakeResponse(self.payload)


def test_updated_at_alone_does_not_count_as_signed():
    assert rollcall_handler._is_signed_student({"updated_at": "2026-05-14T06:00:00Z", "status": "absent"}) is False
    assert rollcall_handler._is_signed_student({"updated_at": "2026-05-14T06:00:00Z"}) is False


def test_explicit_signed_status_or_answer_time_counts_as_signed():
    assert rollcall_handler._is_signed_student({"status": "on_call_fine"}) is True
    assert rollcall_handler._is_signed_student({"status": "attended"}) is True
    assert rollcall_handler._is_signed_student({"answered_at": "2026-05-14T06:00:00Z"}) is True


def test_fetch_signed_count_ignores_records_when_every_row_only_has_updated_at():
    payload = {
        "student_rollcalls": [
            {"status": "absent", "updated_at": "2026-05-14T06:00:00Z"},
            {"status": "absent", "updated_at": "2026-05-14T06:00:01Z"},
        ]
    }

    assert rollcall_handler._fetch_signed_count(FakeSession(payload), 123) == 0


def test_fetch_signed_count_uses_sparse_updated_at_like_reference_project():
    payload = {
        "student_rollcalls": [
            {"status": "absent", "updated_at": "2026-05-14T06:00:00Z"},
            {"status": "absent"},
            {"status": "absent", "updated_at": "2026-05-14T06:00:02Z"},
        ]
    }

    assert rollcall_handler._fetch_signed_count(FakeSession(payload), 123) == 2


def test_fetch_signed_count_uses_updated_at_changed_from_created_at():
    payload = {
        "student_rollcalls": [
            {
                "status": "absent",
                "created_at": "2026-05-14T06:00:00Z",
                "updated_at": "2026-05-14T06:00:00Z",
            },
            {
                "status": "absent",
                "created_at": "2026-05-14T06:00:00Z",
                "updated_at": "2026-05-14T06:00:15Z",
            },
            {
                "status": "absent",
                "created_at": "2026-05-14T06:00:00Z",
                "updated_at": "2026-05-14T06:00:20Z",
            },
        ]
    }

    assert rollcall_handler._fetch_signed_count(FakeSession(payload), 123) == 2


def test_fetch_signed_count_uses_updated_at_after_wait_start():
    payload = {
        "student_rollcalls": [
            {"status": "absent", "updated_at": "2026-05-14T06:00:00Z"},
            {"status": "absent", "updated_at": "2026-05-14T06:00:12Z"},
            {"status": "absent", "updated_at": "2026-05-14T06:00:15Z"},
        ]
    }
    wait_started_at = rollcall_handler._parse_api_time("2026-05-14T06:00:10Z")

    assert rollcall_handler._fetch_signed_count(
        FakeSession(payload),
        123,
        updated_after=wait_started_at,
    ) == 2
