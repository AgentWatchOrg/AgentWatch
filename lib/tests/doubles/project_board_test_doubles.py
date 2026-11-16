from typing import Protocol

from agent_watch.api.github_client import GitHubClient
from agent_watch.api.project_board.models import NewSprintWeek, OpenIssue, ProjectBoard, ProjectItem, SprintWeek
from agent_watch.api.project_board.project_board_client import ProjectBoardClient


class ProjectItemFactory(Protocol):
    def __call__(self, item_id: str, status: str | None = "Ready", week: SprintWeek | None = None,
                 issue_state: str | None = "OPEN", assignee_logins: list[str] | None = None,
                 issue_number: int | None = 1) -> ProjectItem: ...


class FakeProjectBoardClient(ProjectBoardClient):
    def __init__(self, board: ProjectBoard, items: list[ProjectItem], open_issues: list[OpenIssue],
                 collaborator_logins: set[str]) -> None:
        super().__init__(GitHubClient("unused-token"), "AgentWatchOrg", 1, "AgentWatchOrg/AgentWatch")
        self.board: ProjectBoard = board
        self.items: list[ProjectItem] = items
        self.open_issues: list[OpenIssue] = open_issues
        self.collaborator_logins: set[str] = collaborator_logins
        self.recorded_calls: list[tuple[str, ...]] = []

    def load_board(self) -> ProjectBoard:
        return self.board

    def load_items(self, board: ProjectBoard) -> list[ProjectItem]:
        return self.items

    def load_open_issues(self) -> list[OpenIssue]:
        return self.open_issues

    def set_item_week(self, board: ProjectBoard, item_id: str, week: SprintWeek) -> None:
        self.recorded_calls.append(("set_item_week", item_id, week.id))

    def clear_item_week(self, board: ProjectBoard, item_id: str) -> None:
        self.recorded_calls.append(("clear_item_week", item_id))

    def set_item_status(self, board: ProjectBoard, item_id: str, status_name: str) -> None:
        self.recorded_calls.append(("set_item_status", item_id, status_name))

    def add_issue(self, board: ProjectBoard, issue_id: str) -> str:
        self.recorded_calls.append(("add_issue", issue_id))
        return f"item-for-{issue_id}"

    def add_weeks(self, board: ProjectBoard, new_weeks: list[NewSprintWeek], default_week_length_days: int) -> None:
        self.recorded_calls.append(("add_weeks", *[week.title for week in new_weeks]))

    def repository_collaborator_logins(self) -> set[str]:
        return self.collaborator_logins

    def find_or_create_issue(self, title: str, body: str) -> int:
        self.recorded_calls.append(("find_or_create_issue", title))
        return 99

    def comment_on_issue(self, issue_number: int, body: str) -> None:
        self.recorded_calls.append(("comment_on_issue", str(issue_number)))


class FakeProjectBoardClientFactory(Protocol):
    def __call__(self, items: list[ProjectItem] | None = None, open_issues: list[OpenIssue] | None = None,
                 collaborator_logins: set[str] | None = None) -> FakeProjectBoardClient: ...
