import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RestApiSettings:
    github_webhook_secret: str | None
    project_board_token: str | None
    project_owner: str
    project_number: int
    repository: str


def load_rest_api_settings() -> RestApiSettings:
    return RestApiSettings(
        github_webhook_secret=os.environ.get("GITHUB_WEBHOOK_SECRET") or None,
        project_board_token=os.environ.get("PROJECT_BOARD_TOKEN") or None,
        project_owner=os.environ.get("PROJECT_OWNER", "AgentWatchOrg"),
        project_number=int(os.environ.get("PROJECT_NUMBER", "1")),
        repository=os.environ.get("PROJECT_REPOSITORY", "AgentWatchOrg/AgentWatch"),
    )
