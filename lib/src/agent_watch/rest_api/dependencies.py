from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status

from agent_watch.api.github_client import GitHubClient
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_calendar import today_in_project_time_zone
from agent_watch.rest_api.rest_api_settings import RestApiSettings, load_rest_api_settings


@dataclass(frozen=True)
class BoardWebhookConfiguration:
    project_board_client: ProjectBoardClient
    webhook_secret: str


def get_board_webhook_configuration() -> BoardWebhookConfiguration:
    settings: RestApiSettings = load_rest_api_settings()
    if settings.github_webhook_secret is None or settings.project_board_token is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "GITHUB_WEBHOOK_SECRET and PROJECT_BOARD_TOKEN are not configured.")
    return BoardWebhookConfiguration(
        project_board_client=ProjectBoardClient(GitHubClient(settings.project_board_token), settings.project_owner,
                                                settings.project_number, settings.repository),
        webhook_secret=settings.github_webhook_secret)


def get_today() -> date:
    return today_in_project_time_zone()
