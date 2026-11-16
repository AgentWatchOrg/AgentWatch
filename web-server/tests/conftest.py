from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent_watch.api.github_client import GitHubClient
from agent_watch.api.project_board.models import SprintWeek
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch_web_server.application import application
from agent_watch_web_server.dependencies import get_project_board_client, get_today

FIXED_TODAY: date = date(2026, 11, 24)


@pytest.fixture
def unused_project_board_client() -> ProjectBoardClient:
    return ProjectBoardClient(GitHubClient("unused-token"), "AgentWatchOrg", 1, "AgentWatchOrg/AgentWatch")


@pytest.fixture
def week_two() -> SprintWeek:
    return SprintWeek(id="week-2", title="Week 2 (Nov 23)", start_date=date(2026, 11, 23), duration_days=7)


@pytest.fixture
def api_client(unused_project_board_client: ProjectBoardClient) -> Iterator[TestClient]:
    application.dependency_overrides[get_project_board_client] = lambda: unused_project_board_client
    application.dependency_overrides[get_today] = lambda: FIXED_TODAY
    yield TestClient(application)
    application.dependency_overrides.clear()
