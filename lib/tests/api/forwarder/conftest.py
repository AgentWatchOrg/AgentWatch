import socket
import threading
from typing import Iterator

import pytest
import uvicorn
from doubles.forwarder_test_doubles import LiveIngestionServer, RecordingEventBatchSender, TetragonRecordLoader
from telemetry_fixture_paths import TETRAGON_RAW_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.forwarder.assign_event_identities import EventIdentityAssigner
from agent_watch.api.forwarder.event_buffer import InMemoryEventBuffer
from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.rest_api.application import application
from agent_watch.rest_api.routers.ingestion_router import get_ingestion_event_store
from agent_watch.rest_api.settings import INGESTION_API_KEY_ENVIRONMENT_VARIABLE

LIVE_INGESTION_API_KEY: str = "live-test-ingestion-key"


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
def unused_local_url() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unused_socket:
        unused_socket.bind(("127.0.0.1", 0))
        unused_port: int = unused_socket.getsockname()[1]
    return f"http://127.0.0.1:{unused_port}"


@pytest.fixture
def live_ingestion_server(
        monkeypatch: pytest.MonkeyPatch, event_store: InMemoryEventStore) -> Iterator[LiveIngestionServer]:
    monkeypatch.setenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, LIVE_INGESTION_API_KEY)
    application.dependency_overrides[get_ingestion_event_store] = lambda: event_store
    server: uvicorn.Server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=0, log_level="error"))
    server_thread: threading.Thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    while not server.started and server_thread.is_alive():
        server_thread.join(0.01)
    assert server.started, "The live ingestion server did not start"
    bound_port: int = server.servers[0].sockets[0].getsockname()[1]
    yield LiveIngestionServer(url=f"http://127.0.0.1:{bound_port}", api_key=LIVE_INGESTION_API_KEY,
                              event_store=event_store)
    server.should_exit = True
    server_thread.join()
    del application.dependency_overrides[get_ingestion_event_store]
