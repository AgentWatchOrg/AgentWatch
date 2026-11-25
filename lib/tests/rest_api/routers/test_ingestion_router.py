import logging
import urllib.error
import urllib.request
from typing import Iterator

import pytest
from doubles.splunk_export_test_doubles import TEST_HEC_TOKEN, RecordingHecEventSender, ScriptedHecUrlopen
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx2 import Response
from telemetry_fixture_paths import VALID_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.splunk_export.models import SplunkHecSettings
from agent_watch.api.splunk_export.export_events import SplunkExporter
from agent_watch.rest_api.application import application
from agent_watch.rest_api.routers.ingestion_router import (
    MAXIMUM_EVENTS_PER_BATCH, build_splunk_exporter, get_ingestion_event_store, get_splunk_exporter,
    get_splunk_hec_settings, require_ingestion_api_key)
from agent_watch.rest_api.settings import INGESTION_API_KEY_ENVIRONMENT_VARIABLE, SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE

API_KEY_HEADER_NAME: str = "X-Api-Key"
CONFIGURED_API_KEY: str = "test-ingestion-key"


@pytest.fixture
def configured_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, CONFIGURED_API_KEY)
    return CONFIGURED_API_KEY


@pytest.fixture
def authorized_headers(configured_api_key: str) -> dict[str, str]:
    return {API_KEY_HEADER_NAME: configured_api_key}


@pytest.fixture
def wrong_api_key_headers(configured_api_key: str) -> dict[str, str]:
    return {API_KEY_HEADER_NAME: "wrong-key"}


@pytest.fixture
def isolated_event_store(event_store: InMemoryEventStore) -> Iterator[InMemoryEventStore]:
    application.dependency_overrides[get_ingestion_event_store] = lambda: event_store
    yield event_store
    del application.dependency_overrides[get_ingestion_event_store]


def test_post_events_rejects_a_request_when_no_api_key_is_configured(
        api_client: TestClient, monkeypatch: pytest.MonkeyPatch, valid_process_exec_event: JsonObject) -> None:
    monkeypatch.delenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, raising=False)

    response: Response = api_client.post("/v1/events", json={"events": [valid_process_exec_event]})

    assert response.status_code == 500


def test_post_events_rejects_a_request_with_the_wrong_api_key(
        api_client: TestClient, wrong_api_key_headers: dict[str, str], valid_process_exec_event: JsonObject) -> None:
    response: Response = api_client.post(
        "/v1/events", json={"events": [valid_process_exec_event]}, headers=wrong_api_key_headers)

    assert response.status_code == 401


def test_post_events_rejects_a_request_without_an_api_key_header(
        api_client: TestClient, configured_api_key: str, valid_process_exec_event: JsonObject) -> None:
    response: Response = api_client.post("/v1/events", json={"events": [valid_process_exec_event]})

    assert response.status_code == 401


def test_require_ingestion_api_key_rejects_a_non_ascii_api_key_without_raising(configured_api_key: str) -> None:
    with pytest.raises(HTTPException) as raised_exception:
        require_ingestion_api_key(x_api_key="wrong-ké")

    assert raised_exception.value.status_code == 401


def test_post_events_rejects_an_invalid_envelope(
        api_client: TestClient, authorized_headers: dict[str, str]) -> None:
    response: Response = api_client.post("/v1/events", json={"not_events": []}, headers=authorized_headers)

    assert response.status_code == 422


def test_post_events_rejects_a_batch_larger_than_the_maximum(
        api_client: TestClient, authorized_headers: dict[str, str]) -> None:
    oversized_batch: list[JsonObject] = [{"event_id": str(index)} for index in range(MAXIMUM_EVENTS_PER_BATCH + 1)]

    response: Response = api_client.post("/v1/events", json={"events": oversized_batch}, headers=authorized_headers)

    assert response.status_code == 422


def test_post_events_accepts_a_mixed_batch_and_reports_each_outcome(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject, invalid_missing_event_id_event: JsonObject) -> None:
    response: Response = api_client.post(
        "/v1/events", json={"events": [valid_process_exec_event, invalid_missing_event_id_event]},
        headers=authorized_headers)

    response_body: JsonObject = response.json()
    assert response.status_code == 200
    assert response_body["accepted_count"] == 1
    assert len(response_body["rejected_events"]) == 1
    assert response_body["duplicate_events"] == []


def test_post_events_accepts_a_batch_mixing_a_valid_event_with_a_non_object_item(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject) -> None:
    response: Response = api_client.post(
        "/v1/events", json={"events": [valid_process_exec_event, "not-an-object"]}, headers=authorized_headers)

    response_body: JsonObject = response.json()
    assert response.status_code == 200
    assert response_body["accepted_count"] == 1
    assert len(response_body["rejected_events"]) == 1


def test_post_events_reports_a_replayed_event_as_a_duplicate(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject) -> None:
    api_client.post("/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    response: Response = api_client.post(
        "/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    response_body: JsonObject = response.json()
    assert response_body["accepted_count"] == 0
    assert len(response_body["duplicate_events"]) == 1


def test_post_events_continues_to_accept_valid_traffic_after_a_malformed_request(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        invalid_missing_event_id_event: JsonObject, valid_process_exec_event: JsonObject) -> None:
    api_client.post("/v1/events", json={"events": [invalid_missing_event_id_event]}, headers=authorized_headers)

    response: Response = api_client.post(
        "/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    assert response.status_code == 200
    assert response.json()["accepted_count"] == 1


def test_post_events_makes_newly_accepted_events_available_for_export(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        valid_process_exec_event: JsonObject) -> None:
    api_client.post("/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    assert isolated_event_store.pop_unexported_events() == [valid_process_exec_event]


@pytest.fixture
def splunk_hec_settings() -> SplunkHecSettings:
    return SplunkHecSettings(hec_url="https://splunk.invalid:8088", hec_token=TEST_HEC_TOKEN, index=None,
                             should_verify_tls=True)


@pytest.fixture
def unreachable_splunk(
        monkeypatch: pytest.MonkeyPatch, splunk_hec_settings: SplunkHecSettings) -> Iterator[ScriptedHecUrlopen]:
    unreachable_urlopen: ScriptedHecUrlopen = ScriptedHecUrlopen()
    unreachable_urlopen.failure = urllib.error.URLError("[Errno 111] Connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", unreachable_urlopen)
    application.dependency_overrides[get_splunk_hec_settings] = lambda: splunk_hec_settings
    yield unreachable_urlopen
    del application.dependency_overrides[get_splunk_hec_settings]


@pytest.fixture
def recording_splunk_export() -> Iterator[RecordingHecEventSender]:
    recording_sender: RecordingHecEventSender = RecordingHecEventSender()
    application.dependency_overrides[get_splunk_exporter] = lambda: SplunkExporter(recording_sender, index=None)
    yield recording_sender
    del application.dependency_overrides[get_splunk_exporter]


@pytest.fixture
def splunk_export_failing_once() -> Iterator[RecordingHecEventSender]:
    sender_failing_first_request: RecordingHecEventSender = RecordingHecEventSender(frozenset({1}))
    application.dependency_overrides[get_splunk_exporter] = lambda: SplunkExporter(
        sender_failing_first_request, index=None)
    yield sender_failing_first_request
    del application.dependency_overrides[get_splunk_exporter]


@pytest.fixture
def valid_network_connect_event() -> JsonObject:
    return load_json_object(VALID_FIXTURE_DIRECTORY / "network-connect.json")


def test_post_events_exports_each_accepted_event_type_to_splunk(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        recording_splunk_export: RecordingHecEventSender, valid_process_exec_event: JsonObject,
        valid_file_access_event: JsonObject, valid_network_connect_event: JsonObject) -> None:
    events: list[JsonObject] = [valid_process_exec_event, valid_file_access_event, valid_network_connect_event]

    api_client.post("/v1/events", json={"events": events}, headers=authorized_headers)

    assert recording_splunk_export.sent_events() == events
    assert isolated_event_store.pop_unexported_events() == []


def test_post_events_does_not_export_rejected_or_duplicate_events(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        recording_splunk_export: RecordingHecEventSender, valid_process_exec_event: JsonObject,
        valid_file_access_event: JsonObject, invalid_missing_event_id_event: JsonObject) -> None:
    api_client.post("/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    api_client.post("/v1/events", headers=authorized_headers, json={
        "events": [invalid_missing_event_id_event, valid_process_exec_event, valid_file_access_event]})

    assert recording_splunk_export.sent_events() == [valid_process_exec_event, valid_file_access_event]


def test_post_events_keeps_accepting_and_logs_an_error_when_splunk_is_unreachable(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        unreachable_splunk: ScriptedHecUrlopen, valid_process_exec_event: JsonObject,
        caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging.getLogger("agent_watch"), "propagate", True)

    with caplog.at_level(logging.ERROR, logger="agent_watch"):
        response: Response = api_client.post(
            "/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    assert response.json()["accepted_count"] == 1
    assert "Splunk export failed: Could not reach Splunk HEC" in caplog.text
    assert TEST_HEC_TOKEN not in caplog.text
    assert len(unreachable_splunk.sent_requests) == 1
    assert isolated_event_store.pop_unexported_events() == [valid_process_exec_event]


def test_post_events_retries_held_events_even_when_a_batch_has_only_duplicates(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        splunk_export_failing_once: RecordingHecEventSender, valid_process_exec_event: JsonObject) -> None:
    api_client.post("/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    response: Response = api_client.post(
        "/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    assert len(response.json()["duplicate_events"]) == 1
    assert splunk_export_failing_once.sent_events() == [valid_process_exec_event]


def test_post_events_does_not_export_when_splunk_is_not_configured(
        api_client: TestClient, authorized_headers: dict[str, str], isolated_event_store: InMemoryEventStore,
        monkeypatch: pytest.MonkeyPatch, valid_process_exec_event: JsonObject) -> None:
    monkeypatch.delenv(SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE, raising=False)

    api_client.post("/v1/events", json={"events": [valid_process_exec_event]}, headers=authorized_headers)

    assert isolated_event_store.pop_unexported_events() == [valid_process_exec_event]


def test_get_splunk_exporter_builds_an_exporter_only_when_splunk_is_configured(
        splunk_hec_settings: SplunkHecSettings) -> None:
    assert isinstance(get_splunk_exporter(splunk_hec_settings), SplunkExporter)
    assert get_splunk_exporter(None) is None


def test_build_splunk_exporter_reuses_one_exporter_per_configuration(splunk_hec_settings: SplunkHecSettings) -> None:
    assert build_splunk_exporter(splunk_hec_settings) is build_splunk_exporter(splunk_hec_settings)


def test_get_splunk_hec_settings_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE, raising=False)

    assert get_splunk_hec_settings() is None
