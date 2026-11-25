from threading import Lock
from typing import Protocol

from agent_watch.api.github_client import JsonObject


class EventStore(Protocol):
    lock: Lock

    def contains(self, event_id: str) -> bool: ...

    def add(self, event_id: str, event: JsonObject) -> None: ...

    def pop_unexported_events(self) -> list[JsonObject]: ...

    def requeue_unexported_events(self, events: list[JsonObject]) -> None: ...


class InMemoryEventStore:
    def __init__(self) -> None:
        self.lock: Lock = Lock()
        self._seen_event_ids: set[str] = set()
        self._unexported_events: list[JsonObject] = []

    def contains(self, event_id: str) -> bool:
        return event_id in self._seen_event_ids

    def add(self, event_id: str, event: JsonObject) -> None:
        self._seen_event_ids.add(event_id)
        self._unexported_events.append(event)

    def pop_unexported_events(self) -> list[JsonObject]:
        with self.lock:
            unexported_events: list[JsonObject] = self._unexported_events
            self._unexported_events = []
            return unexported_events

    def requeue_unexported_events(self, events: list[JsonObject]) -> None:
        with self.lock:
            self._unexported_events = events + self._unexported_events
