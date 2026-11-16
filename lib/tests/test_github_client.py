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


def install_fake_urlopen(monkeypatch: pytest.MonkeyPatch, response_body: Any) -> list[urllib.request.Request]:
    sent_requests: list[urllib.request.Request] = []

    def fake_urlopen(http_request: urllib.request.Request) -> FakeHttpResponse:
        sent_requests.append(http_request)
        return FakeHttpResponse(response_body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return sent_requests


def test_request_sends_token_and_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_requests: list[urllib.request.Request] = install_fake_urlopen(monkeypatch, {"ok": True})

    response: Any = GitHubClient("secret-token").request("POST", "/repos/owner/name/issues", {"title": "Bug"})

    assert response == {"ok": True}
    assert sent_requests[0].full_url == "https://api.github.com/repos/owner/name/issues"
    assert sent_requests[0].get_header("Authorization") == "Bearer secret-token"
    assert sent_requests[0].data == b'{"title": "Bug"}'


def test_run_graphql_returns_data(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_urlopen(monkeypatch, {"data": {"viewer": {"login": "joshuajipp"}}})

    assert GitHubClient("token").run_graphql("{viewer{login}}") == {"viewer": {"login": "joshuajipp"}}


def test_run_graphql_raises_on_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_urlopen(monkeypatch, {"errors": [{"message": "Bad credentials"}]})

    with pytest.raises(GitHubApiError, match="Bad credentials"):
        GitHubClient("token").run_graphql("{viewer{login}}")
