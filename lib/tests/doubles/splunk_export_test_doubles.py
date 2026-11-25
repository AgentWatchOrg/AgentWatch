import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Protocol

from agent_watch.api.github_client import JsonObject
from agent_watch.api.splunk_export.models import SplunkExportError, SplunkHecSettings

TEST_HEC_TOKEN: str = "test-hec-token-do-not-log"


class SplunkHecSettingsFactory(Protocol):
    def __call__(self, hec_url: str, index: str | None = None) -> SplunkHecSettings: ...


@dataclass
class ReceivedHecRequest:
    path: str
    authorization: str
    body: str


@dataclass
class FakeSplunkHecServer:
    url: str
    received_requests: list[ReceivedHecRequest] = field(default_factory=list)
    response_status: int = 200
    response_body: str = '{"text":"Success","code":0}'


class RecordingHecEventSender:
    def __init__(self, failing_request_numbers: frozenset[int] = frozenset()) -> None:
        self.sent_batches: list[list[JsonObject]] = []
        self._failing_request_numbers: frozenset[int] = failing_request_numbers
        self._request_count: int = 0

    def send_hec_events(self, hec_events: list[JsonObject]) -> None:
        self._request_count += 1
        if self._request_count in self._failing_request_numbers:
            raise SplunkExportError("Could not reach Splunk HEC at https://splunk.invalid/services/collector/event")
        self.sent_batches.append(hec_events)

    def sent_events(self) -> list[JsonObject]:
        return [hec_event["event"] for sent_batch in self.sent_batches for hec_event in sent_batch]


def start_fake_splunk_hec_server() -> tuple[FakeSplunkHecServer, HTTPServer]:
    fake_server_state: FakeSplunkHecServer = FakeSplunkHecServer(url="")

    class FakeHecRequestHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            request_body: str = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            fake_server_state.received_requests.append(
                ReceivedHecRequest(path=self.path, authorization=self.headers.get("Authorization", ""),
                                   body=request_body))
            self.send_response(fake_server_state.response_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(fake_server_state.response_body.encode("utf-8"))

        def log_message(self, format: str, *arguments: object) -> None:
            pass

    http_server: HTTPServer = HTTPServer(("127.0.0.1", 0), FakeHecRequestHandler)
    fake_server_state.url = f"http://127.0.0.1:{http_server.server_address[1]}"
    threading.Thread(target=http_server.serve_forever, daemon=True).start()
    return fake_server_state, http_server


def parse_concatenated_hec_events(request_body: str) -> list[JsonObject]:
    json_decoder: json.JSONDecoder = json.JSONDecoder()
    hec_events: list[JsonObject] = []
    position: int = 0
    while position < len(request_body):
        hec_event, position = json_decoder.raw_decode(request_body, position)
        hec_events.append(hec_event)
    return hec_events
