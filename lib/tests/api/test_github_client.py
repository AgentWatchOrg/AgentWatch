import json
import urllib.request
from types import TracebackType
from typing import Any

import pytest

from agent_watch.api.github_client import GitHubApiError, GitHubClient


class FakeHttpResponse:
    def __init__(self, body: Any) -> None:
        self.body: bytes = json.dumps(body).encode()

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None,
                 traceback: TracebackType | None) -> None:
        pass


class RecordingUrlopen:
    def __init__(self) -> None:
        self.response_body: Any = None
        self.sent_requests: list[urllib.request.Request] = []

    def __call__(self, http_request: urllib.request.Request) -> FakeHttpResponse:
        self.sent_requests.append(http_request)
        return FakeHttpResponse(self.response_body)


@pytest.fixture
def recording_urlopen(monkeypatch: pytest.MonkeyPatch) -> RecordingUrlopen:
    fake_urlopen: RecordingUrlopen = RecordingUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return fake_urlopen


def test_request_sends_token_and_json_body(recording_urlopen: RecordingUrlopen) -> None:
    recording_urlopen.response_body = {"ok": True}

    response: Any = GitHubClient("secret-token").request("POST", "/repos/owner/name/issues", {"title": "Bug"})

    assert response == {"ok": True}
    assert recording_urlopen.sent_requests[0].full_url == "https://api.github.com/repos/owner/name/issues"
    assert recording_urlopen.sent_requests[0].get_header("Authorization") == "Bearer secret-token"
    assert recording_urlopen.sent_requests[0].data == b'{"title": "Bug"}'


def test_run_graphql_returns_data(recording_urlopen: RecordingUrlopen) -> None:
    recording_urlopen.response_body = {"data": {"viewer": {"login": "joshuajipp"}}}

    assert GitHubClient("token").run_graphql("{viewer{login}}") == {"viewer": {"login": "joshuajipp"}}


def test_run_graphql_raises_on_errors(recording_urlopen: RecordingUrlopen) -> None:
    recording_urlopen.response_body = {"errors": [{"message": "Bad credentials"}]}

    with pytest.raises(GitHubApiError, match="Bad credentials"):
        GitHubClient("token").run_graphql("{viewer{login}}")
