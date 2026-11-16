from datetime import date
from typing import Any

import pytest

from agent_watch.api.github_client import GitHubClient, JsonObject
from agent_watch.api.project_board.models import NewSprintWeek, OpenIssue, ProjectBoard, ProjectItem, SprintWeek
from agent_watch.api.project_board.project_board_client import ProjectBoardClient


class ScriptedGitHubClient(GitHubClient):
    def __init__(self) -> None:
        super().__init__("unused-token")
        self.graphql_responses: list[JsonObject] = []
        self.rest_responses: list[Any] = []
        self.graphql_calls: list[tuple[str, dict[str, object]]] = []
        self.rest_calls: list[tuple[str, str, JsonObject | None]] = []

    def run_graphql(self, query: str, **variables: object) -> JsonObject:
        self.graphql_calls.append((query, variables))
        return self.graphql_responses.pop(0) if self.graphql_responses else {}

    def request(self, method: str, path: str, body: JsonObject | None = None) -> Any:
        self.rest_calls.append((method, path, body))
        return self.rest_responses.pop(0) if self.rest_responses else None


@pytest.fixture
def github_client() -> ScriptedGitHubClient:
    return ScriptedGitHubClient()


@pytest.fixture
def board_client(github_client: ScriptedGitHubClient) -> ProjectBoardClient:
    return ProjectBoardClient(github_client, "AgentWatchOrg", 1, "AgentWatchOrg/AgentWatch")


def test_load_board_parses_weeks_and_status_options(github_client: ScriptedGitHubClient,
                                                    board_client: ProjectBoardClient) -> None:
    github_client.graphql_responses = [{"repositoryOwner": {"projectV2": {
        "id": "board-1", "title": "AgentWatch Board",
        "week": {"id": "week-field", "configuration": {
            "iterations": [{"id": "week-2", "title": "Week 2", "startDate": "2026-11-23", "duration": 7}],
            "completedIterations": [{"id": "week-1", "title": "Week 1", "startDate": "2026-11-15", "duration": 8}]}},
        "status": {"id": "status-field", "options": [{"id": "option-1", "name": "Backlog"}]}}}}]

    board: ProjectBoard = board_client.load_board()

    assert [week.id for week in board.weeks] == ["week-2", "week-1"]
    assert board.weeks[1].start_date == date(2026, 11, 15)
    assert board.status_option_ids_by_name == {"Backlog": "option-1"}


def test_load_items_follows_pages_and_skips_archived_items(github_client: ScriptedGitHubClient,
                                                           board_client: ProjectBoardClient,
                                                           project_board: ProjectBoard) -> None:
    github_client.graphql_responses = [
        {"node": {"items": {"pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"}, "nodes": [
            {"id": "item-1", "isArchived": False, "status": {"name": "Ready"},
             "week": {"iterationId": "week-1", "title": "Week 1", "startDate": "2026-11-16"},
             "content": {"title": "Spike", "number": 4, "url": "url-4", "state": "OPEN",
                         "assignees": {"nodes": [{"login": "Ernesto-B"}]}}},
            {"id": "item-archived", "isArchived": True, "status": None, "week": None, "content": None}]}}},
        {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [
            {"id": "item-2", "isArchived": False, "status": None, "week": None, "content": {"title": "Draft"}}]}}},
    ]

    items: list[ProjectItem] = board_client.load_items(project_board)

    assert [item.id for item in items] == ["item-1", "item-2"]
    assert items[0].assignee_logins == ["Ernesto-B"]
    assert items[0].week_start_date == date(2026, 11, 16)
    assert items[1].status is None and items[1].issue_number is None
    assert github_client.graphql_calls[1][1]["after"] == "cursor-1"


def test_load_open_issues_reads_the_configured_repository(github_client: ScriptedGitHubClient,
                                                          board_client: ProjectBoardClient) -> None:
    github_client.graphql_responses = [{"repository": {"issues": {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [{"id": "issue-node-1", "number": 1, "title": "First"}]}}}]

    open_issues: list[OpenIssue] = board_client.load_open_issues()

    assert open_issues == [OpenIssue(id="issue-node-1", number=1, title="First")]
    assert github_client.graphql_calls[0][1]["owner"] == "AgentWatchOrg"
    assert github_client.graphql_calls[0][1]["name"] == "AgentWatch"


def test_field_mutations_send_the_right_values(github_client: ScriptedGitHubClient, board_client: ProjectBoardClient,
                                               project_board: ProjectBoard, week_two: SprintWeek) -> None:
    board_client.set_item_week(project_board, "item-1", week_two)
    board_client.set_item_status(project_board, "item-1", "Done")
    board_client.clear_item_week(project_board, "item-1")

    assert github_client.graphql_calls[0][1]["value"] == {"iterationId": "week-2"}
    assert github_client.graphql_calls[1][1]["value"] == {"singleSelectOptionId": "option-Done"}
    assert github_client.graphql_calls[2][1]["fieldId"] == "week-field"


def test_add_issue_returns_the_new_item_id(github_client: ScriptedGitHubClient, board_client: ProjectBoardClient,
                                           project_board: ProjectBoard) -> None:
    github_client.graphql_responses = [{"addProjectV2ItemById": {"item": {"id": "new-item"}}}]

    assert board_client.add_issue(project_board, "issue-node-1") == "new-item"


def test_add_weeks_resends_existing_weeks_with_ids_before_new_weeks(
        github_client: ScriptedGitHubClient, board_client: ProjectBoardClient, project_board: ProjectBoard) -> None:
    new_week: NewSprintWeek = NewSprintWeek(title="Week 4", start_date=date(2027, 1, 11), duration_days=7)
    board_with_unsorted_weeks: ProjectBoard = ProjectBoard(
        **{**project_board.__dict__, "weeks": list(reversed(project_board.weeks))})

    board_client.add_weeks(board_with_unsorted_weeks, [new_week], 7)

    configuration: Any = github_client.graphql_calls[0][1]["configuration"]
    assert configuration["startDate"] == "2026-11-16"
    assert [week.get("id") for week in configuration["iterations"]] == ["week-1", "week-2", "week-3", None]
    assert configuration["iterations"][3]["title"] == "Week 4"


def test_repository_collaborator_logins_ignores_bots(github_client: ScriptedGitHubClient,
                                                     board_client: ProjectBoardClient) -> None:
    github_client.rest_responses = [[{"login": "joshuajipp", "type": "User"}, {"login": "dependabot", "type": "Bot"}]]

    assert board_client.repository_collaborator_logins() == {"joshuajipp"}


def test_find_or_create_issue_reuses_an_exact_title_match(github_client: ScriptedGitHubClient,
                                                          board_client: ProjectBoardClient) -> None:
    github_client.graphql_responses = [{"search": {"nodes": [
        {"number": 5, "title": "Sprint Log (old)"}, {"number": 7, "title": "Sprint Log"}]}}]

    assert board_client.find_or_create_issue("Sprint Log", "body") == 7
    assert github_client.rest_calls == []


def test_find_or_create_issue_creates_when_missing(github_client: ScriptedGitHubClient,
                                                  board_client: ProjectBoardClient) -> None:
    github_client.graphql_responses = [{"search": {"nodes": []}}]
    github_client.rest_responses = [{"number": 30}]

    assert board_client.find_or_create_issue("Sprint Log", "body") == 30
    assert github_client.rest_calls[0] == ("POST", "/repos/AgentWatchOrg/AgentWatch/issues",
                                          {"title": "Sprint Log", "body": "body"})


def test_comment_on_issue_posts_to_the_issue(github_client: ScriptedGitHubClient,
                                             board_client: ProjectBoardClient) -> None:
    board_client.comment_on_issue(30, "hello")

    assert github_client.rest_calls[0] == ("POST", "/repos/AgentWatchOrg/AgentWatch/issues/30/comments",
                                          {"body": "hello"})
