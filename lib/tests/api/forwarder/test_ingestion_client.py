import http.client
import io
import urllib.error

import pytest
from doubles.forwarder_test_doubles import (
    BodyThatBreaksWhileRead, IngestionApplicationUnderTest, build_ingestion_http_error)

from agent_watch.api.forwarder.ingestion_client import (
    MAXIMUM_ERROR_BODY_LENGTH, UNREADABLE_ERROR_BODY, IngestionClient, parse_ingestion_batch_result,
    parse_rejected_events, read_error_body)
from agent_watch.api.forwarder.models import IngestionRequestError
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.models import IngestionBatchResult, RejectedEvent


def test_send_event_batch_delivers_an_authenticated_batch(
        ingestion_application: IngestionApplicationUnderTest, valid_process_exec_event: JsonObject) -> None:
    ingestion_client: IngestionClient = IngestionClient(ingestion_application.url, ingestion_application.api_key)

    batch_result: IngestionBatchResult = ingestion_client.send_event_batch([valid_process_exec_event])

    assert batch_result == IngestionBatchResult(accepted_count=1, rejected_events=[], duplicate_events=[])
    assert ingestion_application.event_store.contains(valid_process_exec_event["event_id"])


def test_send_event_batch_reports_a_rejected_api_key_without_revealing_it(
        ingestion_application: IngestionApplicationUnderTest, valid_process_exec_event: JsonObject) -> None:
    ingestion_client: IngestionClient = IngestionClient(ingestion_application.url, "wrong-secret-key")

    with pytest.raises(IngestionRequestError, match="HTTP 401") as raised_error:
        ingestion_client.send_event_batch([valid_process_exec_event])

    assert "wrong-secret-key" not in str(raised_error.value)


@pytest.mark.parametrize("connection_failure", [
    urllib.error.URLError("[Errno 111] Connection refused"),
    http.client.RemoteDisconnected("Remote end closed connection without response"),
    TimeoutError("timed out"),
], ids=["unreachable", "dropped-before-response", "timeout"])
def test_send_event_batch_reports_a_connection_failure(
        connection_failure: Exception, ingestion_application: IngestionApplicationUnderTest,
        valid_process_exec_event: JsonObject) -> None:
    ingestion_application.urlopen.failure = connection_failure
    ingestion_client: IngestionClient = IngestionClient(ingestion_application.url, ingestion_application.api_key)

    with pytest.raises(IngestionRequestError, match="Could not reach") as raised_error:
        ingestion_client.send_event_batch([valid_process_exec_event])

    assert ingestion_application.api_key not in str(raised_error.value)


def test_send_event_batch_reports_a_successful_response_that_is_not_json_text(
        ingestion_application: IngestionApplicationUnderTest, valid_process_exec_event: JsonObject) -> None:
    ingestion_application.urlopen.successful_response_body = "<html>Café Wi-Fi login</html>".encode("latin-1")
    ingestion_client: IngestionClient = IngestionClient(ingestion_application.url, ingestion_application.api_key)

    with pytest.raises(IngestionRequestError, match="not JSON"):
        ingestion_client.send_event_batch([valid_process_exec_event])


@pytest.mark.parametrize(("error_body", "expected_text"), [
    (io.BytesIO(b"\xff" + b"x" * 1000), "\ufffd" + "x" * (MAXIMUM_ERROR_BODY_LENGTH - 1)),
    (BodyThatBreaksWhileRead(), UNREADABLE_ERROR_BODY),
], ids=["truncated-and-undecodable", "breaks-while-read"])
def test_read_error_body(error_body: io.BytesIO, expected_text: str) -> None:
    assert read_error_body(build_ingestion_http_error(error_body)) == expected_text


def test_ingestion_client_builds_the_events_url_from_a_base_url_with_a_trailing_slash() -> None:
    assert IngestionClient("http://127.0.0.1:8000/", "key").events_url == "http://127.0.0.1:8000/v1/events"


def test_parse_rejected_events_reads_each_rejection() -> None:
    assert parse_rejected_events([{"index": 0, "event_id": None, "reason": "bad"}]) == [
        RejectedEvent(index=0, event_id=None, reason="bad")]


def test_parse_ingestion_batch_result_rejects_an_incomplete_response() -> None:
    with pytest.raises(IngestionRequestError, match="accepted_count"):
        parse_ingestion_batch_result({"rejected_events": [], "duplicate_events": []})
