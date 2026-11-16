from datetime import date

from fastapi import HTTPException, status

from agent_watch.api.github_client import GitHubClient
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_calendar import today_in_project_time_zone
from agent_watch_web_server.web_server_settings import WebServerSettings, load_web_server_settings


def get_project_board_client() -> ProjectBoardClient:
    settings: WebServerSettings = load_web_server_settings()
    if settings.github_token is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PROJECT_BOARD_TOKEN is not configured.")
    return ProjectBoardClient(GitHubClient(settings.github_token), settings.project_owner, settings.project_number,
                              settings.repository)


def get_today() -> date:
    return today_in_project_time_zone()
