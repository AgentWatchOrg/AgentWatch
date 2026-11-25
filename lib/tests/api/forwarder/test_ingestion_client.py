import pytest
from doubles.forwarder_test_doubles import LiveIngestionServer

from agent_watch.api.forwarder.ingestion_client import (
    IngestionClient, parse_ingestion_batch_result, parse_rejected_events)
from agent_watch.api.forwarder.models import IngestionRequestError
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.models import IngestionBatchResult, RejectedEvent


def test_send_event_batch_delivers_an_authenticated_batch(
        live_ingestion_server: LiveIngestionServer, valid_process_exec_event: JsonObject) -> None:
    ingestion_client: IngestionClient = IngestionClient(live_ingestion_server.url, live_ingestion_server.api_key)

    batch_result: IngestionBatchResult = ingestion_client.send_event_batch([valid_process_exec_event])

    assert batch_result == IngestionBatchResult(accepted_count=1, rejected_events=[], duplicate_events=[])
    assert live_ingestion_server.event_store.contains(valid_process_exec_event["event_id"])


def test_send_event_batch_reports_a_rejected_api_key_without_revealing_it(
        live_ingestion_server: LiveIngestionServer, valid_process_exec_event: JsonObject) -> None:
    ingestion_client: IngestionClient = IngestionClient(live_ingestion_server.url, "wrong-secret-key")

    with pytest.raises(IngestionRequestError, match="HTTP 401") as raised_error:
        ingestion_client.send_event_batch([valid_process_exec_event])

    assert "wrong-secret-key" not in str(raised_error.value)


def test_send_event_batch_reports_an_unreachable_endpoint(
        unused_local_url: str, valid_process_exec_event: JsonObject) -> None:
    ingestion_client: IngestionClient = IngestionClient(unused_local_url, "key", request_timeout_seconds=2)

    with pytest.raises(IngestionRequestError, match="Could not reach"):
        ingestion_client.send_event_batch([valid_process_exec_event])


def test_ingestion_client_builds_the_events_url_from_a_base_url_with_a_trailing_slash() -> None:
    assert IngestionClient("http://127.0.0.1:8000/", "key").events_url == "http://127.0.0.1:8000/v1/events"


def test_parse_rejected_events_reads_each_rejection() -> None:
    assert parse_rejected_events([{"index": 0, "event_id": None, "reason": "bad"}]) == [
        RejectedEvent(index=0, event_id=None, reason="bad")]


def test_parse_ingestion_batch_result_rejects_an_incomplete_response() -> None:
    with pytest.raises(IngestionRequestError, match="accepted_count"):
        parse_ingestion_batch_result({"rejected_events": [], "duplicate_events": []})
