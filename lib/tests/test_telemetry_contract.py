import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[2]
SCHEMA_PATH: Path = REPOSITORY_ROOT / "documentation" / "schemas" / "agent-watch-v1.schema.json"
VALID_FIXTURE_DIRECTORY: Path = REPOSITORY_ROOT / "documentation" / "fixtures" / "telemetry-v1" / "valid"
INVALID_FIXTURE_DIRECTORY: Path = REPOSITORY_ROOT / "documentation" / "fixtures" / "telemetry-v1" / "invalid"
EXPECTED_REASON_BY_INVALID_FIXTURE: dict[str, str] = {
    "missing-event-id": "'event_id' is a required property",
    "wrong-forwarder-sequence-type": "'1' is not of type 'integer'",
    "mismatched-network-details": "should not be valid under",
    "invalid-timestamp": "'not-a-date' is not a 'date-time'",
}


def load_json_file(json_path: Path) -> dict[str, Any]:
    with json_path.open("r", encoding="utf-8") as json_file:
        loaded_value: Any = json.load(json_file)
    if not isinstance(loaded_value, dict):
        raise AssertionError(f"{json_path} must contain a JSON object")
    return loaded_value


def telemetry_schema_validator() -> Draft202012Validator:
    telemetry_schema: dict[str, Any] = load_json_file(SCHEMA_PATH)
    Draft202012Validator.check_schema(telemetry_schema)
    return Draft202012Validator(telemetry_schema, format_checker=FormatChecker())


@pytest.mark.parametrize(
    "fixture_path",
    sorted(VALID_FIXTURE_DIRECTORY.glob("*.json")),
    ids=lambda fixture_path: fixture_path.stem,
)
def test_valid_telemetry_fixtures(fixture_path: Path) -> None:
    fixture: dict[str, Any] = load_json_file(fixture_path)
    validator: Draft202012Validator = telemetry_schema_validator()

    assert validator.is_valid(fixture), list(validator.iter_errors(fixture))


@pytest.mark.parametrize(
    "fixture_path",
    sorted(INVALID_FIXTURE_DIRECTORY.glob("*.json")),
    ids=lambda fixture_path: fixture_path.stem,
)
def test_invalid_telemetry_fixtures(fixture_path: Path) -> None:
    assert fixture_path.stem in EXPECTED_REASON_BY_INVALID_FIXTURE, (
        f"Add the expected rejection reason for {fixture_path.name} to EXPECTED_REASON_BY_INVALID_FIXTURE")
    expected_reason: str = EXPECTED_REASON_BY_INVALID_FIXTURE[fixture_path.stem]
    fixture: dict[str, Any] = load_json_file(fixture_path)
    validator: Draft202012Validator = telemetry_schema_validator()

    errors: list[ValidationError] = list(validator.iter_errors(fixture))

    assert errors
    assert any(expected_reason in error.message for error in errors)
