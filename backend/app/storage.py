"""
In-memory event store for the Sprint 1 ingestion spike.

Deliberately not persistent — a real datastore (and whether we need one at
all before the Sprint 2 detection engine exists) is an explicit open question
in spike #7, not something to decide inside the prototype.
"""

from __future__ import annotations

from typing import Dict, List

from app.schemas import TelemetryEvent


class InMemoryEventStore:
    def __init__(self) -> None:
        self._events: Dict[str, TelemetryEvent] = {}

    def contains(self, event_id: str) -> bool:
        return event_id in self._events

    def add(self, event: TelemetryEvent) -> None:
        self._events[event.event_id] = event

    def all(self) -> List[TelemetryEvent]:
        return list(self._events.values())

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()


store = InMemoryEventStore()
