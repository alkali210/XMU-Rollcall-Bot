from xmu_rollcall import verify
from xmu_rollcall import rollcall_handler
from xmu_rollcall.config import get_rollcall_settings


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.get_calls = []
        self.put_calls = []

    def get(self, url, headers=None, timeout=None):
        self.get_calls.append({"url": url, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)

    def put(self, url, json=None, headers=None):
        self.put_calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(200, {"ok": True})


def _student_payload(signed_count):
    return {
        "student_rollcalls": [
            {"updated_at": "2026-05-12T10:00:00+08:00"} for _ in range(signed_count)
        ]
    }


def test_send_code_can_wait_after_fetching_code_before_submit(monkeypatch):
    monkeypatch.setattr(verify.time, "sleep", lambda _seconds: None)
    session = FakeSession([FakeResponse(200, {"number_code": "1357"})])
    events = []

    def before_submit(number_code, status, end_time):
        events.append(("wait", number_code, len(session.put_calls)))

    assert verify.send_code(session, 99, before_submit=before_submit) is True

    assert events == [("wait", "1357", 0)]
    assert session.get_calls[0]["url"].endswith("/api/rollcall/99/student_rollcalls")
    assert session.put_calls[0]["url"].endswith("/api/rollcall/99/answer_number_rollcall")
    assert session.put_calls[0]["json"]["numberCode"] == "1357"


def test_wait_for_classmates_polls_until_target_count(monkeypatch):
    sleeps = []
    monkeypatch.setattr(rollcall_handler.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(rollcall_handler, "WAIT_POLL_INTERVAL", 1)
    session = FakeSession([
        FakeResponse(200, _student_payload(1)),
        FakeResponse(200, _student_payload(3)),
    ])
    settings = get_rollcall_settings({
        "rollcall_settings": {
            "wait_before_answer": 3,
        }
    })

    rollcall_handler.wait_for_classmates(session, 42, settings)

    assert len(session.get_calls) == 2
    assert session.get_calls[0]["url"].endswith("/api/rollcall/42/student_rollcalls")
    assert sleeps == [1]


def test_wait_strategy_disabled_by_default():
    assert get_rollcall_settings({})["wait_before_answer"] is False
    assert rollcall_handler._choose_wait_target(get_rollcall_settings({})) == 0


def test_wait_strategy_accepts_only_false_or_positive_number():
    assert get_rollcall_settings({"rollcall_settings": {"wait_before_answer": False}})["wait_before_answer"] is False
    assert get_rollcall_settings({"rollcall_settings": {"wait_before_answer": 5}})["wait_before_answer"] == 5
    assert get_rollcall_settings({"rollcall_settings": {"wait_before_answer": 0}})["wait_before_answer"] is False
