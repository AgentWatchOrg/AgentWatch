import urllib.request
from typing import Iterator

import pytest
from doubles.forwarder_test_doubles import (
    IngestionApplicationUnderTest, IngestionApplicationUrlopen, RecordingEventBatchSender, TetragonRecordLoader)
from fastapi.testclient import TestClient
from telemetry_fixture_paths import TETRAGON_RAW_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.forwarder.assign_event_identities import EventIdentityAssigner
from agent_watch.api.forwarder.event_buffer import InMemoryEventBuffer
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.rest_api.application import application
from agent_watch.rest_api.routers.ingestion_router import get_ingestion_event_store
from agent_watch.rest_api.settings import INGESTION_API_KEY_ENVIRONMENT_VARIABLE

TEST_INGESTION_API_KEY: str = "test-ingestion-key"
TEST_INGESTION_URL: str = "http://ingestion.test"


@pytest.fixture
def load_tetragon_record() -> TetragonRecordLoader:
    def load_raw_tetragon_fixture(fixture_name: str) -> JsonObject:
        return load_json_object(TETRAGON_RAW_FIXTURE_DIRECTORY / f"{fixture_name}.json")
    return load_raw_tetragon_fixture


@pytest.fixture
def identity_assigner() -> EventIdentityAssigner:
    return EventIdentityAssigner()


@pytest.fixture
def event_buffer() -> InMemoryEventBuffer:
    return InMemoryEventBuffer()


@pytest.fixture
def recording_sender() -> RecordingEventBatchSender:
    return RecordingEventBatchSender()


@pytest.fixture
def sender_rejecting_event_c() -> RecordingEventBatchSender:
    return RecordingEventBatchSender(rejected_event_ids=frozenset({"c"}))


@pytest.fixture
def ingestion_application(
        monkeypatch: pytest.MonkeyPatch, event_store: InMemoryEventStore) -> Iterator[IngestionApplicationUnderTest]:
    monkeypatch.setenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, TEST_INGESTION_API_KEY)
    application.dependency_overrides[get_ingestion_event_store] = lambda: event_store
    application_urlopen: IngestionApplicationUrlopen = IngestionApplicationUrlopen(TestClient(application))
    monkeypatch.setattr(urllib.request, "urlopen", application_urlopen)
    yield IngestionApplicationUnderTest(url=TEST_INGESTION_URL, api_key=TEST_INGESTION_API_KEY,
                                        event_store=event_store, urlopen=application_urlopen)
    del application.dependency_overrides[get_ingestion_event_store]
