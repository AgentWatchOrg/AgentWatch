from dataclasses import dataclass
from typing import Protocol

from agent_watch.api.github_client import JsonObject

MAXIMUM_EVENTS_PER_INGESTION_BATCH: int = 1000


class EventValidator(Protocol):
    def validation_errors(self, event: JsonObject) -> list[str]: ...


@dataclass(frozen=True)
class RejectedEvent:
    index: int
    event_id: str | None
    reason: str


@dataclass(frozen=True)
class IngestionBatchResult:
    accepted_count: int
    rejected_events: list[RejectedEvent]
    duplicate_events: list[RejectedEvent]


@dataclass(frozen=True)
class PlannedIngestion:
    accepted_events: list[tuple[str, JsonObject]]
    rejected_events: list[RejectedEvent]
    duplicate_events: list[RejectedEvent]
