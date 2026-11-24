from typing import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx2 import Response

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.rest_api.application import application
from agent_watch.rest_api.routers.ingestion_router import (
    MAXIMUM_EVENTS_PER_BATCH, get_ingestion_event_store, require_ingestion_api_key)
from agent_watch.rest_api.settings import INGESTION_API_KEY_ENVIRONMENT_VARIABLE

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
