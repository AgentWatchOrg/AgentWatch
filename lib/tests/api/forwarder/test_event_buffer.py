import pytest

from agent_watch.api.forwarder.event_buffer import InMemoryEventBuffer
from agent_watch.api.github_client import JsonObject


@pytest.fixture
def three_identified_events() -> list[JsonObject]:
    return [{"event_id": "a"}, {"event_id": "b"}, {"event_id": "c"}]


def test_add_events_keeps_each_event_id_once(
        event_buffer: InMemoryEventBuffer, three_identified_events: list[JsonObject]) -> None:
    event_buffer.add_events(three_identified_events + three_identified_events[:1])

    assert event_buffer.unsent_event_count() == 3


def test_unsent_events_returns_at_most_the_requested_count_in_order(
        event_buffer: InMemoryEventBuffer, three_identified_events: list[JsonObject]) -> None:
    event_buffer.add_events(three_identified_events)

    assert event_buffer.unsent_events(2) == three_identified_events[:2]


def test_remove_events_ignores_unknown_ids(
        event_buffer: InMemoryEventBuffer, three_identified_events: list[JsonObject]) -> None:
    event_buffer.add_events(three_identified_events)

    event_buffer.remove_events({"a", "missing"})

    assert event_buffer.unsent_events(10) == three_identified_events[1:]


def test_unsent_event_count_starts_at_zero(event_buffer: InMemoryEventBuffer) -> None:
    assert event_buffer.unsent_event_count() == 0
