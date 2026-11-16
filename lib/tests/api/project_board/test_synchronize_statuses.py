from datetime import date

import pytest
from doubles.project_board_test_doubles import (
    FakeProjectBoardClient, FakeProjectBoardClientFactory, ProjectItemFactory)

from agent_watch.api.project_board.models import OpenIssue, ProjectBoard, ProjectItem, SprintWeek
from agent_watch.api.project_board.synchronize_statuses import (
    BoardChange, BoardChangeKind, apply_board_changes, plan_item_changes, plan_status_synchronization,
    synchronize_statuses)

DAY_IN_WEEK_ONE: date = date(2026, 11, 18)


@pytest.mark.parametrize(("status", "is_in_sprint", "issue_state", "expected_kinds"), [
    ("Ready", False, "CLOSED", [BoardChangeKind.MARK_DONE, BoardChangeKind.PUT_IN_SPRINT]),
    ("Ready", True, "CLOSED", [BoardChangeKind.MARK_DONE]),
    (None, True, "OPEN", [BoardChangeKind.MOVE_TO_BACKLOG, BoardChangeKind.REMOVE_FROM_SPRINT]),
    (None, False, "OPEN", [BoardChangeKind.MOVE_TO_BACKLOG]),
    ("Backlog", True, "OPEN", [BoardChangeKind.REMOVE_FROM_SPRINT]),
    ("Ready", False, "OPEN", [BoardChangeKind.PUT_IN_SPRINT]),
    ("Blocked", False, "OPEN", [BoardChangeKind.PUT_IN_SPRINT]),
    ("Backlog", False, "OPEN", []),
    ("Ready", True, "OPEN", []),
    ("Done", True, "CLOSED", []),
], ids=["closed outside sprint", "closed in sprint", "no status in sprint", "no status outside sprint",
        "backlog in sprint", "ready outside sprint", "blocked outside sprint", "backlog outside sprint",
        "ready in sprint", "done in sprint"])
def test_plan_item_changes(make_item: ProjectItemFactory, week_one: SprintWeek, status: str | None,
                           is_in_sprint: bool, issue_state: str, expected_kinds: list[BoardChangeKind]) -> None:
    item: ProjectItem = make_item("item", status=status, week=week_one if is_in_sprint else None,
                                  issue_state=issue_state)

    assert [change.kind for change in plan_item_changes(item, week_one)] == expected_kinds


def test_put_in_sprint_change_carries_the_current_week(make_item: ProjectItemFactory, week_one: SprintWeek) -> None:
    assert plan_item_changes(make_item("ready"), week_one) == [
        BoardChange(BoardChangeKind.PUT_IN_SPRINT, "ready", "Title of ready", week_one)]


def test_open_issues_missing_from_the_board_are_added_except_the_sprint_log(
        project_board: ProjectBoard, make_item: ProjectItemFactory, week_one: SprintWeek) -> None:
    open_issues: list[OpenIssue] = [OpenIssue("on-board", 1, "On board"), OpenIssue("missing", 2, "Missing"),
                                    OpenIssue("log", 3, "Sprint Log")]

    changes: list[BoardChange] = plan_status_synchronization(
        project_board, [make_item("item-1", week=week_one, issue_number=1)], open_issues, DAY_IN_WEEK_ONE)

    assert changes == [BoardChange(BoardChangeKind.ADD_ISSUE_TO_BACKLOG, "missing", "Missing")]


def test_apply_board_changes_calls_the_matching_client_methods(
        make_fake_client: FakeProjectBoardClientFactory, project_board: ProjectBoard, week_one: SprintWeek) -> None:
    client: FakeProjectBoardClient = make_fake_client()

    apply_board_changes(client, project_board, [
        BoardChange(BoardChangeKind.ADD_ISSUE_TO_BACKLOG, "issue-node", "New"),
        BoardChange(BoardChangeKind.MARK_DONE, "item-1", "Closed"),
        BoardChange(BoardChangeKind.MOVE_TO_BACKLOG, "item-2", "Unsorted"),
        BoardChange(BoardChangeKind.PUT_IN_SPRINT, "item-3", "Ready", week_one),
        BoardChange(BoardChangeKind.REMOVE_FROM_SPRINT, "item-4", "Backlog"),
    ])

    assert client.recorded_calls == [
        ("add_issue", "issue-node"), ("set_item_status", "item-for-issue-node", "Backlog"),
        ("set_item_status", "item-1", "Done"),
        ("set_item_status", "item-2", "Backlog"),
        ("set_item_week", "item-3", "week-1"),
        ("clear_item_week", "item-4"),
    ]


@pytest.mark.parametrize(("is_dry_run", "expected_calls"), [
    (True, []),
    (False, [("set_item_week", "ready", "week-1")]),
], ids=["dry run", "real run"])
def test_synchronize_statuses_applies_changes_only_outside_dry_run(
        make_fake_client: FakeProjectBoardClientFactory, make_item: ProjectItemFactory, is_dry_run: bool,
        expected_calls: list[tuple[str, ...]]) -> None:
    client: FakeProjectBoardClient = make_fake_client(items=[make_item("ready")])

    changes: list[BoardChange] = synchronize_statuses(client, DAY_IN_WEEK_ONE, is_dry_run=is_dry_run)

    assert [change.kind for change in changes] == [BoardChangeKind.PUT_IN_SPRINT]
    assert client.recorded_calls == expected_calls
