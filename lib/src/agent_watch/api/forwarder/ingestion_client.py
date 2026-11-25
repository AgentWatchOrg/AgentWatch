import http.client
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from agent_watch.api.forwarder.models import IngestionRequestError
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.models import IngestionBatchResult, RejectedEvent

EVENTS_ENDPOINT_PATH: str = "/v1/events"
API_KEY_HEADER_NAME: str = "X-Api-Key"
DEFAULT_REQUEST_TIMEOUT_SECONDS: float = 10.0
MAXIMUM_ERROR_BODY_LENGTH: int = 500
UNREADABLE_ERROR_BODY: str = "<unreadable body>"

logger: logging.Logger = logging.getLogger(__name__)


class IngestionClient:
    def __init__(self, ingestion_url: str, ingestion_api_key: str,
                 request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS) -> None:
        self.events_url: str = f"{ingestion_url.rstrip('/')}{EVENTS_ENDPOINT_PATH}"
        self._ingestion_api_key: str = ingestion_api_key
        self._request_timeout_seconds: float = request_timeout_seconds

    def send_event_batch(self, events: list[JsonObject]) -> IngestionBatchResult:
        logger.debug("POST %s with %d event(s)", self.events_url, len(events))
        http_request: urllib.request.Request = urllib.request.Request(
            self.events_url, method="POST", data=json.dumps({"events": events}).encode("utf-8"),
            headers={API_KEY_HEADER_NAME: self._ingestion_api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(http_request, timeout=self._request_timeout_seconds) as http_response:
                response_body: Any = json.loads(http_response.read())
        except urllib.error.HTTPError as http_error:
            error_body: str = read_error_body(http_error)
            raise IngestionRequestError(
                f"POST {self.events_url} returned HTTP {http_error.code}: {error_body}") from http_error
        except (urllib.error.URLError, http.client.HTTPException, OSError) as connection_error:
            raise IngestionRequestError(f"Could not reach {self.events_url}: {connection_error}") from connection_error
        except ValueError as decode_error:
            raise IngestionRequestError(f"POST {self.events_url} returned a body that is not JSON") from decode_error
        return parse_ingestion_batch_result(response_body)


def read_error_body(http_error: urllib.error.HTTPError) -> str:
    try:
        return http_error.read().decode("utf-8", errors="replace")[:MAXIMUM_ERROR_BODY_LENGTH]
    except (http.client.HTTPException, OSError):
        return UNREADABLE_ERROR_BODY


def parse_rejected_events(raw_rejected_events: list[JsonObject]) -> list[RejectedEvent]:
    return [RejectedEvent(index=raw_event["index"], event_id=raw_event.get("event_id"), reason=raw_event["reason"])
            for raw_event in raw_rejected_events]


def parse_ingestion_batch_result(response_body: Any) -> IngestionBatchResult:
    try:
        return IngestionBatchResult(
            accepted_count=response_body["accepted_count"],
            rejected_events=parse_rejected_events(response_body["rejected_events"]),
            duplicate_events=parse_rejected_events(response_body["duplicate_events"]))
    except (KeyError, TypeError) as parse_error:
        raise IngestionRequestError(f"Ingestion response is missing {parse_error}") from parse_error
