import json
from pathlib import Path
from typing import Any

from agent_watch.api.github_client import JsonObject

REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[2]
VALID_FIXTURE_DIRECTORY: Path = REPOSITORY_ROOT / "documentation" / "fixtures" / "telemetry-v1" / "valid"
INVALID_FIXTURE_DIRECTORY: Path = REPOSITORY_ROOT / "documentation" / "fixtures" / "telemetry-v1" / "invalid"
TETRAGON_RAW_FIXTURE_DIRECTORY: Path = REPOSITORY_ROOT / "documentation" / "fixtures" / "tetragon" / "raw"
TETRAGON_EXPECTED_FIXTURE_DIRECTORY: Path = REPOSITORY_ROOT / "documentation" / "fixtures" / "tetragon" / "expected"


def load_json_object(json_path: Path) -> JsonObject:
    loaded_value: Any = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(loaded_value, dict):
        raise AssertionError(f"{json_path} must contain a JSON object")
    return loaded_value
