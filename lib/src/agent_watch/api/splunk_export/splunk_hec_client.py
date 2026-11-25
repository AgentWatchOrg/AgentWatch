import http.client
import json
import logging
import ssl
import urllib.error
import urllib.request

from agent_watch.api.github_client import JsonObject
from agent_watch.api.splunk_export.models import HEC_EVENT_PATH, SplunkExportError, SplunkHecSettings

DEFAULT_REQUEST_TIMEOUT_SECONDS: float = 10.0
MAXIMUM_ERROR_BODY_LENGTH: int = 500
BAD_REQUEST_STATUS_CODE: int = 400
CONTENT_TOO_LARGE_STATUS_CODE: int = 413
PERMANENT_REJECTION_HEC_CODES: frozenset[int] = frozenset({5, 6, 12, 13, 15})

logger: logging.Logger = logging.getLogger(__name__)


class SplunkHecClient:
    def __init__(self, hec_settings: SplunkHecSettings,
                 request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS) -> None:
        self.events_url: str = f"{hec_settings.hec_url.rstrip('/')}{HEC_EVENT_PATH}"
        self._hec_token: str = hec_settings.hec_token
        self._request_timeout_seconds: float = request_timeout_seconds
        self._tls_context: ssl.SSLContext = ssl.create_default_context()
        if not hec_settings.should_verify_tls:
            self._tls_context.check_hostname = False
            self._tls_context.verify_mode = ssl.CERT_NONE

    def send_hec_events(self, hec_events: list[JsonObject]) -> None:
        logger.debug("POST %s with %d event(s)", self.events_url, len(hec_events))
        request_body: bytes = "".join(json.dumps(hec_event) for hec_event in hec_events).encode("utf-8")
        http_request: urllib.request.Request = urllib.request.Request(
            self.events_url, method="POST", data=request_body,
            headers={"Authorization": f"Splunk {self._hec_token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(http_request, timeout=self._request_timeout_seconds,
                                        context=self._tls_context) as http_response:
                http_response.read()
        except urllib.error.HTTPError as http_error:
            error_body: str = http_error.read().decode("utf-8", errors="replace")
            raise SplunkExportError(
                f"Splunk HEC at {self.events_url} returned HTTP {http_error.code}: "
                f"{error_body[:MAXIMUM_ERROR_BODY_LENGTH]}",
                is_retryable=not is_permanent_rejection(http_error.code, error_body)) from http_error
        except (urllib.error.URLError, http.client.HTTPException, OSError) as connection_error:
            raise SplunkExportError(
                f"Could not reach Splunk HEC at {self.events_url}: {connection_error}") from connection_error


def is_permanent_rejection(status_code: int, response_body: str) -> bool:
    if status_code == CONTENT_TOO_LARGE_STATUS_CODE:
        return True
    if status_code != BAD_REQUEST_STATUS_CODE:
        return False
    try:
        parsed_body: object = json.loads(response_body)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed_body, dict) and parsed_body.get("code") in PERMANENT_REJECTION_HEC_CODES
