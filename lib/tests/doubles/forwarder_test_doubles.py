from typing import Protocol

from agent_watch.api.github_client import JsonObject


class TetragonRecordLoader(Protocol):
    def __call__(self, fixture_name: str) -> JsonObject: ...
