from datetime import date

from agent_watch.api.github_client import GitHubClient
from agent_watch.api.project_board.models import NewSprintWeek, OpenIssue, ProjectBoard, ProjectItem, SprintWeek
from agent_watch.api.project_board.project_board_client import ProjectBoardClient

WEEK_ONE: SprintWeek = SprintWeek(id="week-1", title="Week 1 (Nov 16)", start_date=date(2026, 11, 16), duration_days=7)
WEEK_TWO: SprintWeek = SprintWeek(id="week-2", title="Week 2 (Nov 23)", start_date=date(2026, 11, 23), duration_days=7)
WEEK_THREE: SprintWeek = SprintWeek(id="week-3", title="Week 3 (Jan 4)", start_date=date(2027, 1, 4), duration_days=7)
STATUS_NAMES: list[str] = ["Backlog", "Ready", "In Progress", "Blocked", "Done"]


class FakeProjectBoardClient(ProjectBoardClient):
    def __init__(self, board: ProjectBoard, items: list[ProjectItem], open_issues: list[OpenIssue],
                 collaborator_logins: set[str] | None = None) -> None:
        super().__init__(GitHubClient("unused-token"), "AgentWatchOrg", 1, "AgentWatchOrg/AgentWatch")
        self.board: ProjectBoard = board
        self.items: list[ProjectItem] = items
        self.open_issues: list[OpenIssue] = open_issues
        self.collaborator_logins: set[str] = collaborator_logins or set()
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


def make_board(weeks: list[SprintWeek] | None = None) -> ProjectBoard:
    return ProjectBoard(id="board-1", title="AgentWatch Board", week_field_id="week-field",
                        weeks=weeks if weeks is not None else [WEEK_ONE, WEEK_TWO, WEEK_THREE],
                        status_field_id="status-field",
                        status_option_ids_by_name={name: f"option-{name}" for name in STATUS_NAMES})


def make_item(item_id: str, status: str | None = "Ready", week: SprintWeek | None = None,
              issue_state: str | None = "OPEN", assignee_logins: list[str] | None = None,
              issue_number: int | None = 1) -> ProjectItem:
    return ProjectItem(id=item_id, title=f"Title of {item_id}", status=status,
                       week_id=week.id if week else None, week_title=week.title if week else None,
                       week_start_date=week.start_date if week else None, issue_number=issue_number,
                       issue_url=f"https://github.com/AgentWatchOrg/AgentWatch/issues/{issue_number}",
                       issue_state=issue_state, assignee_logins=assignee_logins or [])
