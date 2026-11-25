from dataclasses import dataclass
from typing import Protocol

from agent_watch.api.forwarder.models import IngestionRequestError
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.ingestion.models import IngestionBatchResult, RejectedEvent

FAKE_SECRET_VALUES: list[str] = [
    "fake-bearer-token-0001", "fake-password-0002", "fake-user", "fake-url-password-0003", "fake-query-token-0004",
    "sk-fakeapikey00000000000005"]


class TetragonRecordLoader(Protocol):
    def __call__(self, fixture_name: str) -> JsonObject: ...


@dataclass(frozen=True)
class LiveIngestionServer:
    url: str
    api_key: str
    event_store: InMemoryEventStore


class RecordingEventBatchSender:
    def __init__(self, failing_attempt_count: int = 0, rejected_event_ids: frozenset[str] = frozenset()) -> None:
        self.sent_batches: list[list[JsonObject]] = []
        self._remaining_failing_attempt_count: int = failing_attempt_count
        self._rejected_event_ids: frozenset[str] = rejected_event_ids

    def send_event_batch(self, events: list[JsonObject]) -> IngestionBatchResult:
        self.sent_batches.append(events)
        if self._remaining_failing_attempt_count:
            self._remaining_failing_attempt_count -= 1
            raise IngestionRequestError("Could not reach http://ingestion.invalid/v1/events")
        rejected_events: list[RejectedEvent] = [
            RejectedEvent(index=index, event_id=event["event_id"], reason="rejected for the test")
            for index, event in enumerate(events) if event["event_id"] in self._rejected_event_ids]
        return IngestionBatchResult(
            accepted_count=len(events) - len(rejected_events), rejected_events=rejected_events, duplicate_events=[])
