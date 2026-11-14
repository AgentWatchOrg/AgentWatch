"""
Demonstrates accept/reject/duplicate behavior for the ingestion prototype
using a handful of representative events (process_exec, file_access,
network_connect), one malformed event, and one duplicate submission.

Run: pytest backend/tests/test_ingestion.py -v
"""

import os

os.environ["AGENTWATCH_API_KEY"] = "dev-local-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.storage import store  # noqa: E402

HEADERS = {"X-API-Key": "dev-local-key"}


def setup_function() -> None:
    store.clear()


def valid_events() -> list[dict]:
    return [
        {
            "event_id": "evt-1",
            "timestamp": "2026-11-13T10:00:00Z",
            "host": "test-host-01",
            "agent_session_id": "session-abc",
            "source": "tetragon",
            "process": {"pid": 1001, "ppid": 1, "exec_id": "exec-1", "binary_path": "/usr/bin/claude"},
            "activity_type": "process_exec",
            "details": {"activity_type": "process_exec", "binary": "/usr/bin/curl", "args": ["curl", "-s", "http://example.com"]},
            "outcome": "success",
        },
        {
            "event_id": "evt-2",
            "timestamp": "2026-11-13T10:00:01Z",
            "host": "test-host-01",
            "agent_session_id": "session-abc",
            "source": "tetragon",
            "process": {"pid": 1001, "ppid": 1, "exec_id": "exec-1"},
            "activity_type": "file_access",
            "details": {"activity_type": "file_access", "path": "/etc/secrets/credentials.txt", "access_mode": "read"},
            "outcome": "success",
        },
        {
            "event_id": "evt-3",
            "timestamp": "2026-11-13T10:00:02Z",
            "host": "test-host-01",
            "agent_session_id": "session-abc",
            "source": "tetragon",
            "process": {"pid": 1002, "ppid": 1001, "exec_id": "exec-2"},
            "activity_type": "network_connect",
            "details": {"activity_type": "network_connect", "dest_ip": "203.0.113.5", "dest_port": 4444, "protocol": "tcp"},
            "outcome": "success",
        },
    ]


def test_accepts_valid_events():
    client = TestClient(app)
    resp = client.post("/v1/events", json={"events": valid_events()}, headers=HEADERS)
    assert resp.status_code == 200
    result = resp.json()
    assert result["accepted"] == 3
    assert result["rejected"] == []
    assert result["duplicate"] == []


def test_rejects_malformed_event_without_crashing():
    client = TestClient(app)
    malformed = {
        "event_id": "evt-bad-1",
        "timestamp": "2026-11-13T10:00:03Z",
        "host": "test-host-01",
        "agent_session_id": "session-abc",
        "source": "tetragon",
        "process": {"pid": "not-an-int"},  # wrong type
        "activity_type": "file_access",
        "details": {"activity_type": "file_access", "path": "/etc/passwd"},  # missing access_mode
    }
    resp = client.post("/v1/events/raw", json={"events": [malformed]}, headers=HEADERS)
    assert resp.status_code == 200  # service stays up; rejection is data, not an error
    result = resp.json()
    assert result["accepted"] == 0
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["event_id"] == "evt-bad-1"


def test_mismatched_activity_type_is_rejected_as_coherence_error():
    client = TestClient(app)
    bad = valid_events()[0]
    bad["activity_type"] = "network_connect"  # mismatches details.activity_type == "process_exec"
    resp = client.post("/v1/events", json={"events": [bad]}, headers=HEADERS)
    assert resp.status_code == 200  # service stays up; mismatch is reported as a rejection, not an error
    result = resp.json()
    assert result["accepted"] == 0
    assert len(result["rejected"]) == 1
    assert "does not match" in result["rejected"][0]["reason"]


def test_duplicate_event_id_is_reported_separately_from_rejected():
    client = TestClient(app)
    events = valid_events()[:1]
    first = client.post("/v1/events", json={"events": events}, headers=HEADERS)
    assert first.json()["accepted"] == 1

    second = client.post("/v1/events", json={"events": events}, headers=HEADERS)
    result = second.json()
    assert result["accepted"] == 0
    assert result["rejected"] == []
    assert len(result["duplicate"]) == 1
    assert result["duplicate"][0]["event_id"] == "evt-1"


def test_missing_api_key_is_rejected():
    client = TestClient(app)
    resp = client.post("/v1/events", json={"events": valid_events()})
    assert resp.status_code == 401
