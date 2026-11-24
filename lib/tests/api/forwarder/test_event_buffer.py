from agent_watch.api.forwarder.event_buffer import InMemoryEventBuffer


def test_add_events_keeps_each_event_id_once(event_buffer: InMemoryEventBuffer) -> None:
    event_buffer.add_events([{"event_id": "a"}, {"event_id": "a"}, {"event_id": "b"}])

    assert event_buffer.unsent_event_count() == 2


def test_unsent_events_returns_at_most_the_requested_count_in_order(event_buffer: InMemoryEventBuffer) -> None:
    event_buffer.add_events([{"event_id": "a"}, {"event_id": "b"}, {"event_id": "c"}])

    assert event_buffer.unsent_events(2) == [{"event_id": "a"}, {"event_id": "b"}]


def test_remove_events_ignores_unknown_ids(event_buffer: InMemoryEventBuffer) -> None:
    event_buffer.add_events([{"event_id": "a"}, {"event_id": "b"}])

    event_buffer.remove_events({"a", "missing"})

    assert event_buffer.unsent_events(10) == [{"event_id": "b"}]


def test_unsent_event_count_starts_at_zero(event_buffer: InMemoryEventBuffer) -> None:
    assert event_buffer.unsent_event_count() == 0
