from typing import Protocol

from agent_watch.api.github_client import JsonObject

FAKE_SECRET_VALUES: list[str] = [
    "fake-bearer-token-0001", "fake-password-0002", "fake-user", "fake-url-password-0003", "fake-query-token-0004",
    "sk-fakeapikey00000000000005"]


class TetragonRecordLoader(Protocol):
    def __call__(self, fixture_name: str) -> JsonObject: ...
