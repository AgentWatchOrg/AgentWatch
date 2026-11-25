from typing import Protocol

from agent_watch.api.github_client import JsonObject


class EventBuffer(Protocol):
    def add_events(self, events: list[JsonObject]) -> None: ...

    def unsent_events(self, maximum_event_count: int) -> list[JsonObject]: ...

    def remove_events(self, event_ids: set[str]) -> None: ...

    def unsent_event_count(self) -> int: ...


class InMemoryEventBuffer:
    def __init__(self) -> None:
        self._unsent_events_by_id: dict[str, JsonObject] = {}

    def add_events(self, events: list[JsonObject]) -> None:
        for event in events:
            self._unsent_events_by_id[event["event_id"]] = event

    def unsent_events(self, maximum_event_count: int) -> list[JsonObject]:
        return list(self._unsent_events_by_id.values())[:maximum_event_count]

    def remove_events(self, event_ids: set[str]) -> None:
        for event_id in event_ids:
            self._unsent_events_by_id.pop(event_id, None)

    def unsent_event_count(self) -> int:
        return len(self._unsent_events_by_id)
