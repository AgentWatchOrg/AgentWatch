import io
import json
import ssl
import urllib.error
import urllib.request
from email.message import Message
from types import TracebackType
from typing import Protocol

from agent_watch.api.github_client import JsonObject
from agent_watch.api.splunk_export.models import SplunkExportError, SplunkHecSettings

TEST_HEC_TOKEN: str = "test-hec-token-do-not-log"
FAKE_HEC_EVENT_URL: str = "https://splunk.invalid:8088/services/collector/event"


class SplunkHecSettingsFactory(Protocol):
    def __call__(self, hec_url: str = "https://splunk.invalid:8088", index: str | None = None,
                 should_verify_tls: bool = True) -> SplunkHecSettings: ...


class FakeHecResponse:
    def read(self) -> bytes:
        return b'{"text":"Success","code":0}'

    def __enter__(self) -> "FakeHecResponse":
        return self

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None,
                 traceback: TracebackType | None) -> None:
        pass


class ScriptedHecUrlopen:
    def __init__(self) -> None:
        self.sent_requests: list[urllib.request.Request] = []
        self.failure: Exception | None = None

    def __call__(self, http_request: urllib.request.Request, timeout: float,
                 context: ssl.SSLContext) -> FakeHecResponse:
        self.sent_requests.append(http_request)
        if self.failure is not None:
            raise self.failure
        return FakeHecResponse()


class RecordingHecEventSender:
    def __init__(self, failing_request_numbers: frozenset[int] = frozenset(),
                 failure: Exception = SplunkExportError(
                     "Could not reach Splunk HEC at https://splunk.invalid/services/collector/event")) -> None:
        self.sent_batches: list[list[JsonObject]] = []
        self._failing_request_numbers: frozenset[int] = failing_request_numbers
        self._failure: Exception = failure
        self._request_count: int = 0

    def send_hec_events(self, hec_events: list[JsonObject]) -> None:
        self._request_count += 1
        if self._request_count in self._failing_request_numbers:
            raise self._failure
        self.sent_batches.append(hec_events)

    def sent_events(self) -> list[JsonObject]:
        return [hec_event["event"] for sent_batch in self.sent_batches for hec_event in sent_batch]


def build_hec_http_error(status_code: int, response_body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(FAKE_HEC_EVENT_URL, status_code, "HEC error", Message(),
                                  io.BytesIO(response_body.encode("utf-8")))


def parse_concatenated_hec_events(request_body: bytes) -> list[JsonObject]:
    json_decoder: json.JSONDecoder = json.JSONDecoder()
    request_text: str = request_body.decode("utf-8")
    hec_events: list[JsonObject] = []
    position: int = 0
    while position < len(request_text):
        hec_event, position = json_decoder.raw_decode(request_text, position)
        hec_events.append(hec_event)
    return hec_events
