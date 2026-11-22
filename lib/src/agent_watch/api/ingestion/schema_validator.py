import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from agent_watch.api.github_client import JsonObject

PACKAGED_SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema" / "agent-watch-v1.schema.json"


class SchemaValidator:
    def __init__(self, validator: Draft202012Validator) -> None:
        self._validator: Draft202012Validator = validator

    def validation_errors(self, event: JsonObject) -> list[str]:
        return [f"{error.json_path}: {error.message}" for error in self._validator.iter_errors(event)]


@lru_cache(maxsize=1)
def load_telemetry_schema_validator() -> SchemaValidator:
    schema: dict[str, Any] = json.loads(PACKAGED_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return SchemaValidator(Draft202012Validator(schema, format_checker=FormatChecker()))
