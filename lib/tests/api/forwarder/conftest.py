import pytest
from doubles.forwarder_test_doubles import TetragonRecordLoader
from telemetry_fixture_paths import TETRAGON_RAW_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.github_client import JsonObject


@pytest.fixture
def load_tetragon_record() -> TetragonRecordLoader:
    def load_raw_tetragon_fixture(fixture_name: str) -> JsonObject:
        return load_json_object(TETRAGON_RAW_FIXTURE_DIRECTORY / f"{fixture_name}.json")
    return load_raw_tetragon_fixture
