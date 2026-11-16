from datetime import date

import pytest
from fastapi import HTTPException

from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch_web_server import dependencies
from agent_watch_web_server.dependencies import get_project_board_client


def test_project_board_client_is_unavailable_without_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJECT_BOARD_TOKEN", raising=False)

    with pytest.raises(HTTPException) as raised_exception:
        get_project_board_client()

    assert raised_exception.value.status_code == 503


def test_project_board_client_uses_the_configured_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECT_BOARD_TOKEN", "token")
    monkeypatch.setenv("PROJECT_REPOSITORY", "AgentWatchOrg/Other")

    client: ProjectBoardClient = get_project_board_client()

    assert client.github_client.github_token == "token"
    assert client.repository == "AgentWatchOrg/Other"
    assert client.project_owner == "AgentWatchOrg"


def test_today_is_the_project_calendar_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependencies, "today_in_project_time_zone", lambda: date(2026, 11, 24))

    assert dependencies.get_today() == date(2026, 11, 24)
