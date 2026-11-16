from datetime import date

import pytest
from doubles.github_test_doubles import ScriptedGitHubClient
from doubles.project_board_test_doubles import (
    FakeProjectBoardClient, FakeProjectBoardClientFactory, ProjectItemFactory)

from agent_watch.api.project_board.models import OpenIssue, ProjectBoard, ProjectItem, SprintWeek

STATUS_NAMES: list[str] = ["Backlog", "Ready", "In Progress", "Blocked", "Done"]


@pytest.fixture
def week_one() -> SprintWeek:
    return SprintWeek(id="week-1", title="Week 1 (Nov 16)", start_date=date(2026, 11, 16), duration_days=7)


@pytest.fixture
def week_two() -> SprintWeek:
    return SprintWeek(id="week-2", title="Week 2 (Nov 23)", start_date=date(2026, 11, 23), duration_days=7)


@pytest.fixture
def week_after_winter_break() -> SprintWeek:
    return SprintWeek(id="week-3", title="Week 3 (Jan 4)", start_date=date(2027, 1, 4), duration_days=7)


@pytest.fixture
def project_board(week_one: SprintWeek, week_two: SprintWeek, week_after_winter_break: SprintWeek) -> ProjectBoard:
    return ProjectBoard(id="board-1", title="AgentWatch Board", week_field_id="week-field",
                        weeks=[week_one, week_two, week_after_winter_break], status_field_id="status-field",
                        status_option_ids_by_name={name: f"option-{name}" for name in STATUS_NAMES})


@pytest.fixture
def make_item() -> ProjectItemFactory:
    def build_project_item(item_id: str, status: str | None = "Ready", week: SprintWeek | None = None,
                           issue_state: str | None = "OPEN", assignee_logins: list[str] | None = None,
                           issue_number: int | None = 1) -> ProjectItem:
        return ProjectItem(id=item_id, title=f"Title of {item_id}", status=status,
                           week_id=week.id if week else None, week_title=week.title if week else None,
                           week_start_date=week.start_date if week else None, issue_number=issue_number,
                           issue_url=f"https://github.com/AgentWatchOrg/AgentWatch/issues/{issue_number}",
                           issue_state=issue_state, assignee_logins=assignee_logins or [])
    return build_project_item


@pytest.fixture
def make_fake_client(project_board: ProjectBoard) -> FakeProjectBoardClientFactory:
    def build_fake_client(items: list[ProjectItem] | None = None, open_issues: list[OpenIssue] | None = None,
                          collaborator_logins: set[str] | None = None) -> FakeProjectBoardClient:
        return FakeProjectBoardClient(project_board, items or [], open_issues or [], collaborator_logins or set())
    return build_fake_client


@pytest.fixture
def github_client() -> ScriptedGitHubClient:
    return ScriptedGitHubClient()
