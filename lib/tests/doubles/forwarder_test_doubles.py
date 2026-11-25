import io
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.message import Message
from types import TracebackType
from typing import Protocol

from fastapi.testclient import TestClient
from httpx2 import Response

from agent_watch.api.forwarder.models import IngestionRequestError
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.ingestion.models import IngestionBatchResult, RejectedEvent

FAKE_SECRET_VALUES: list[str] = [
    "fake-bearer-token-0001", "fake-password-0002", "fake-user", "fake-url-password-0003", "fake-query-token-0004",
    "sk-fakeapikey00000000000005"]


class TetragonRecordLoader(Protocol):
    def __call__(self, fixture_name: str) -> JsonObject: ...


class FakeIngestionResponse:
    def __init__(self, response_body: bytes) -> None:
        self._response_body: bytes = response_body

    def read(self) -> bytes:
        return self._response_body

    def __enter__(self) -> "FakeIngestionResponse":
        return self

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None,
                 traceback: TracebackType | None) -> None:
        pass


class IngestionApplicationUrlopen:
    def __init__(self, api_client: TestClient) -> None:
        self.failure: Exception | None = None
        self.successful_response_body: bytes | None = None
        self._api_client: TestClient = api_client

    def __call__(self, http_request: urllib.request.Request, timeout: float) -> FakeIngestionResponse:
        if self.failure is not None:
            raise self.failure
        if self.successful_response_body is not None:
            return FakeIngestionResponse(self.successful_response_body)
        request_body: bytes = http_request.data if isinstance(http_request.data, bytes) else b""
        response: Response = self._api_client.request(
            http_request.get_method(), urllib.parse.urlsplit(http_request.full_url).path,
            content=request_body, headers=dict(http_request.header_items()))
        if response.status_code >= 400:
            raise urllib.error.HTTPError(http_request.full_url, response.status_code, response.reason_phrase,
                                         Message(), io.BytesIO(response.content))
        return FakeIngestionResponse(response.content)


@dataclass
class IngestionApplicationUnderTest:
    url: str
    api_key: str
    event_store: InMemoryEventStore
    urlopen: IngestionApplicationUrlopen = field(repr=False)


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
