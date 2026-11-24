from pathlib import Path

from telemetry_fixture_paths import REPOSITORY_ROOT

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.schema_validator import (
    PACKAGED_SCHEMA_PATH, SchemaValidator, load_telemetry_schema_validator)

CANONICAL_SCHEMA_PATH: Path = REPOSITORY_ROOT / "documentation" / "schemas" / "agent-watch-v1.schema.json"


def test_packaged_schema_matches_the_canonical_schema() -> None:
    assert PACKAGED_SCHEMA_PATH.read_text(encoding="utf-8") == CANONICAL_SCHEMA_PATH.read_text(encoding="utf-8")


def test_load_telemetry_schema_validator_accepts_a_valid_event(
        telemetry_schema_validator: SchemaValidator, valid_process_exec_event: JsonObject) -> None:
    assert telemetry_schema_validator.validation_errors(valid_process_exec_event) == []


def test_load_telemetry_schema_validator_rejects_an_invalid_event(
        telemetry_schema_validator: SchemaValidator, invalid_missing_event_id_event: JsonObject) -> None:
    validation_errors: list[str] = telemetry_schema_validator.validation_errors(invalid_missing_event_id_event)

    assert any("event_id" in validation_error for validation_error in validation_errors)


def test_load_telemetry_schema_validator_is_cached() -> None:
    assert load_telemetry_schema_validator() is load_telemetry_schema_validator()
