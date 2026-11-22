import pytest
from telemetry_fixture_paths import INVALID_FIXTURE_DIRECTORY, VALID_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.ingestion.schema_validator import SchemaValidator, load_telemetry_schema_validator


@pytest.fixture
def telemetry_schema_validator() -> SchemaValidator:
    return load_telemetry_schema_validator()


@pytest.fixture
def event_store() -> InMemoryEventStore:
    return InMemoryEventStore()


@pytest.fixture
def valid_process_exec_event() -> JsonObject:
    return load_json_object(VALID_FIXTURE_DIRECTORY / "process-exec.json")


@pytest.fixture
def valid_file_access_event() -> JsonObject:
    return load_json_object(VALID_FIXTURE_DIRECTORY / "file-access.json")


@pytest.fixture
def invalid_missing_event_id_event() -> JsonObject:
    return load_json_object(INVALID_FIXTURE_DIRECTORY / "missing-event-id.json")
