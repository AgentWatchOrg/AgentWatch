import pytest

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore


@pytest.fixture
def first_event() -> JsonObject:
    return {"event_id": "event-1"}


@pytest.fixture
def second_event() -> JsonObject:
    return {"event_id": "event-2"}


def test_in_memory_event_store_does_not_contain_an_unadded_event_id(event_store: InMemoryEventStore) -> None:
    assert event_store.contains("event-1") is False


def test_in_memory_event_store_contains_an_added_event_id(
        event_store: InMemoryEventStore, first_event: JsonObject) -> None:
    event_store.add("event-1", first_event)

    assert event_store.contains("event-1") is True


def test_in_memory_event_store_pop_unexported_events_returns_added_events_in_order(
        event_store: InMemoryEventStore, first_event: JsonObject, second_event: JsonObject) -> None:
    event_store.add("event-1", first_event)
    event_store.add("event-2", second_event)

    assert event_store.pop_unexported_events() == [first_event, second_event]


def test_in_memory_event_store_pop_unexported_events_clears_the_unexported_queue(
        event_store: InMemoryEventStore, first_event: JsonObject) -> None:
    event_store.add("event-1", first_event)
    event_store.pop_unexported_events()

    assert event_store.pop_unexported_events() == []


def test_in_memory_event_store_pop_unexported_events_does_not_remove_events_from_the_store(
        event_store: InMemoryEventStore, first_event: JsonObject) -> None:
    event_store.add("event-1", first_event)
    event_store.pop_unexported_events()

    assert event_store.contains("event-1") is True


def test_in_memory_event_store_requeue_unexported_events_puts_them_back_first(
        event_store: InMemoryEventStore, first_event: JsonObject, second_event: JsonObject) -> None:
    event_store.add("event-2", second_event)

    event_store.requeue_unexported_events([first_event])

    assert event_store.pop_unexported_events() == [first_event, second_event]
