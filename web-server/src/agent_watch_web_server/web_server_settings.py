import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WebServerSettings:
    github_token: str | None
    project_owner: str
    project_number: int
    repository: str


def load_web_server_settings() -> WebServerSettings:
    return WebServerSettings(
        github_token=os.environ.get("PROJECT_BOARD_TOKEN") or None,
        project_owner=os.environ.get("PROJECT_OWNER", "AgentWatchOrg"),
        project_number=int(os.environ.get("PROJECT_NUMBER", "1")),
        repository=os.environ.get("PROJECT_REPOSITORY", "AgentWatchOrg/AgentWatch"),
    )
