from datetime import date

import pytest
from doubles.github_test_doubles import ScriptedGitHubClient
from doubles.project_board_test_doubles import (
    FakeProjectBoardClient, FakeProjectBoardClientFactory, ProjectItemFactory)
from doubles.pull_request_review_test_doubles import ExistingReviewThreadFactory, ReviewFindingFactory
from telemetry_fixture_paths import INVALID_FIXTURE_DIRECTORY, VALID_FIXTURE_DIRECTORY, load_json_object

from agent_watch.api.github_client import JsonObject
from agent_watch.api.ingestion.event_store import InMemoryEventStore
from agent_watch.api.ingestion.schema_validator import SchemaValidator, load_telemetry_schema_validator
from agent_watch.api.project_board.models import OpenIssue, ProjectBoard, ProjectItem, SprintWeek
from agent_watch.api.pull_request_review.models import (
    ChangedFile, ExistingReviewThread, PullRequest, ReviewFinding, ReviewFindingCategory, ReviewSeverity)

STATUS_NAMES: list[str] = ["Backlog", "Ready", "In Progress", "Blocked", "Done"]
CHANGED_FILE_PATH: str = "lib/src/agent_watch/api/example.py"


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


@pytest.fixture
def pull_request() -> PullRequest:
    return PullRequest(number=7, title="Add HEC export retry", body="Closes #6", author_login="Ernesto-B",
                       base_branch="main", base_sha="base1234567", head_sha="head7654321", is_draft=False,
                       changed_files=[ChangedFile(path=CHANGED_FILE_PATH,
                                                  commentable_line_numbers=frozenset(range(8, 16)))])


@pytest.fixture
def make_finding() -> ReviewFindingFactory:
    def build_review_finding(path: str = CHANGED_FILE_PATH, start_line: int = 10, end_line: int | None = None,
                             severity: ReviewSeverity = ReviewSeverity.HIGH,
                             category: ReviewFindingCategory = ReviewFindingCategory.CORRECTNESS,
                             title: str = "Off-by-one drops the last page",
                             violated_skill_name: str | None = None) -> ReviewFinding:
        return ReviewFinding(path=path, start_line=start_line, end_line=end_line or start_line, severity=severity,
                             category=category, title=title, explanation="The loop stops one page early.",
                             failure_scenario="A repository with exactly 101 issues loses issue 101.",
                             suggested_fix="Loop until a page has fewer than 100 items.",
                             violated_skill_name=violated_skill_name)
    return build_review_finding


@pytest.fixture
def make_thread() -> ExistingReviewThreadFactory:
    def build_existing_review_thread(path: str = CHANGED_FILE_PATH, line: int | None = 10,
                                     finding_fingerprint: str | None = None,
                                     finding_category: ReviewFindingCategory | None = None, is_resolved: bool = False,
                                     is_outdated: bool = False,
                                     author_login: str = "github-actions") -> ExistingReviewThread:
        return ExistingReviewThread(path=path, start_line=None, line=line, is_resolved=is_resolved,
                                    is_outdated=is_outdated, author_login=author_login, body="Earlier comment",
                                    finding_fingerprint=finding_fingerprint, finding_category=finding_category)
    return build_existing_review_thread


@pytest.fixture
def telemetry_schema_validator() -> SchemaValidator:
    return load_telemetry_schema_validator()


@pytest.fixture
def event_store() -> InMemoryEventStore:
    return InMemoryEventStore()


@pytest.fixture
def valid_process_exec_event() -> JsonObject:
    return load_json_object(VALID_FIXTURE_DIRECTORY / "process-exec.json")


@pytest.fixture
def valid_file_access_event() -> JsonObject:
    return load_json_object(VALID_FIXTURE_DIRECTORY / "file-access.json")


@pytest.fixture
def invalid_missing_event_id_event() -> JsonObject:
    return load_json_object(INVALID_FIXTURE_DIRECTORY / "missing-event-id.json")
