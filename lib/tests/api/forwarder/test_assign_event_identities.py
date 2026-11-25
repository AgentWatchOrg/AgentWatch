import pytest

from agent_watch.api.forwarder.assign_event_identities import (
    EventIdentityAssigner, canonical_event_text, compute_event_id)
from agent_watch.api.github_client import JsonObject


@pytest.fixture
def normalized_event() -> JsonObject:
    return {"schema_version": "1.0", "timestamp": "2026-11-18T12:00:00Z", "host": "agentwatch-test-01",
            "source": "tetragon", "activity_type": "process_exec", "process": {"pid": 2450},
            "agent": {"attribution_status": "unknown", "session_id": None}, "target": "/usr/bin/curl",
            "outcome": "success", "details": {"cwd": "/home/agent"}}


def test_assign_identity_numbers_events_from_one(
        identity_assigner: EventIdentityAssigner, normalized_event: JsonObject) -> None:
    first_event: JsonObject = identity_assigner.assign_identity(normalized_event)
    second_event: JsonObject = identity_assigner.assign_identity({**normalized_event, "target": "/usr/bin/wget"})

    assert [first_event["forwarder_seq"], second_event["forwarder_seq"]] == [1, 2]
    assert first_event["event_id"] == compute_event_id(normalized_event)


def test_assign_identity_gives_identical_events_different_ids(
        identity_assigner: EventIdentityAssigner, normalized_event: JsonObject) -> None:
    first_event: JsonObject = identity_assigner.assign_identity(normalized_event)
    repeated_event: JsonObject = identity_assigner.assign_identity(normalized_event)

    assert first_event["event_id"] != repeated_event["event_id"]
    assert repeated_event["event_id"] == compute_event_id(normalized_event, distinguishing_forwarder_seq=2)


def test_assign_identity_forgets_ids_beyond_the_remembered_count(normalized_event: JsonObject) -> None:
    identity_assigner_remembering_one: EventIdentityAssigner = EventIdentityAssigner(remembered_event_id_count=1)
    identity_assigner_remembering_one.assign_identity(normalized_event)
    identity_assigner_remembering_one.assign_identity({**normalized_event, "target": "/usr/bin/wget"})

    event_after_eviction: JsonObject = identity_assigner_remembering_one.assign_identity(normalized_event)

    assert event_after_eviction["event_id"] == compute_event_id(normalized_event)


def test_remember_event_id_drops_the_oldest_id_first() -> None:
    identity_assigner_remembering_two: EventIdentityAssigner = EventIdentityAssigner(remembered_event_id_count=2)

    for event_id in ["sha256:a", "sha256:b", "sha256:c"]:
        identity_assigner_remembering_two.remember_event_id(event_id)

    assert list(identity_assigner_remembering_two._recent_event_ids) == ["sha256:b", "sha256:c"]


def test_canonical_event_text_ignores_key_order_and_non_identity_fields(normalized_event: JsonObject) -> None:
    reordered_event: JsonObject = dict(reversed(list(normalized_event.items())))

    assert canonical_event_text(reordered_event) == canonical_event_text({**normalized_event, "outcome": "denied"})


def test_canonical_event_text_includes_a_distinguishing_forwarder_seq(normalized_event: JsonObject) -> None:
    assert '"forwarder_seq":7' in canonical_event_text(normalized_event, distinguishing_forwarder_seq=7)


def test_compute_event_id_is_a_prefixed_sha256_digest(normalized_event: JsonObject) -> None:
    event_id: str = compute_event_id(normalized_event)

    assert event_id.startswith("sha256:")
    assert len(event_id) == len("sha256:") + 64
