from pathlib import Path

import pytest
from telemetry_fixture_paths import INVALID_FIXTURE_DIRECTORY, VALID_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.schema_validator import SchemaValidator, load_telemetry_schema_validator

EXPECTED_REASON_BY_INVALID_FIXTURE: dict[str, str] = {
    "missing-event-id": "'event_id' is a required property",
    "wrong-forwarder-sequence-type": "'1' is not of type 'integer'",
    "mismatched-network-details": "should not be valid under",
    "invalid-timestamp": "'not-a-date' is not a 'date-time'",
    "unknown-attribution-missing-session-id": "'session_id' is a required property",
}


@pytest.mark.parametrize(
    "fixture_path",
    sorted(VALID_FIXTURE_DIRECTORY.glob("*.json")),
    ids=lambda fixture_path: fixture_path.stem,
)
def test_valid_telemetry_fixtures(fixture_path: Path) -> None:
    telemetry_schema_validator: SchemaValidator = load_telemetry_schema_validator()
    fixture: JsonObject = load_json_object(fixture_path)

    assert telemetry_schema_validator.validation_errors(fixture) == []


@pytest.mark.parametrize(
    "fixture_path",
    sorted(INVALID_FIXTURE_DIRECTORY.glob("*.json")),
    ids=lambda fixture_path: fixture_path.stem,
)
def test_invalid_telemetry_fixtures(fixture_path: Path) -> None:
    assert fixture_path.stem in EXPECTED_REASON_BY_INVALID_FIXTURE, (
        f"Add the expected rejection reason for {fixture_path.name} to EXPECTED_REASON_BY_INVALID_FIXTURE")
    expected_reason: str = EXPECTED_REASON_BY_INVALID_FIXTURE[fixture_path.stem]
    telemetry_schema_validator: SchemaValidator = load_telemetry_schema_validator()
    fixture: JsonObject = load_json_object(fixture_path)

    validation_errors: list[str] = telemetry_schema_validator.validation_errors(fixture)

    assert validation_errors
    assert any(expected_reason in validation_error for validation_error in validation_errors)
