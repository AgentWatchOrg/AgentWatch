from datetime import date

from doubles.project_board_test_doubles import WEEK_ONE, FakeProjectBoardClient, make_board, make_item

from agent_watch.api.project_board.models import OpenIssue, ProjectItem
from agent_watch.api.project_board.synchronize_statuses import (
    BoardChange, BoardChangeKind, apply_board_changes, plan_item_changes, plan_status_synchronization,
    synchronize_statuses)

DAY_IN_WEEK_ONE: date = date(2026, 11, 18)


def change_kinds(item: ProjectItem) -> list[BoardChangeKind]:
    return [change.kind for change in plan_item_changes(item, WEEK_ONE)]


def test_closed_issue_is_marked_done_and_put_in_the_sprint() -> None:
    assert change_kinds(make_item("closed", status="Ready", issue_state="CLOSED")) == [
        BoardChangeKind.MARK_DONE, BoardChangeKind.PUT_IN_SPRINT]


def test_closed_issue_already_in_a_sprint_is_only_marked_done() -> None:
    assert change_kinds(make_item("closed", status="Ready", week=WEEK_ONE, issue_state="CLOSED")) == [
        BoardChangeKind.MARK_DONE]


def test_item_without_status_moves_to_backlog_and_leaves_its_sprint() -> None:
    assert change_kinds(make_item("unsorted", status=None, week=WEEK_ONE)) == [
        BoardChangeKind.MOVE_TO_BACKLOG, BoardChangeKind.REMOVE_FROM_SPRINT]


def test_backlog_item_with_a_week_leaves_the_sprint() -> None:
    assert change_kinds(make_item("backlog", status="Backlog", week=WEEK_ONE)) == [
        BoardChangeKind.REMOVE_FROM_SPRINT]


def test_ready_item_without_a_week_joins_the_current_sprint() -> None:
    changes: list[BoardChange] = plan_item_changes(make_item("ready", status="Ready"), WEEK_ONE)

    assert changes == [BoardChange(BoardChangeKind.PUT_IN_SPRINT, "ready", "Title of ready", WEEK_ONE)]


def test_items_already_in_the_right_place_need_no_changes() -> None:
    assert change_kinds(make_item("backlog", status="Backlog")) == []
    assert change_kinds(make_item("ready", status="Ready", week=WEEK_ONE)) == []
    assert change_kinds(make_item("done", status="Done", week=WEEK_ONE, issue_state="CLOSED")) == []


def test_open_issues_missing_from_the_board_are_added_except_the_sprint_log() -> None:
    open_issues: list[OpenIssue] = [OpenIssue("on-board", 1, "On board"), OpenIssue("missing", 2, "Missing"),
                                    OpenIssue("log", 3, "Sprint Log")]

    changes: list[BoardChange] = plan_status_synchronization(
        make_board(), [make_item("item-1", week=WEEK_ONE, issue_number=1)], open_issues, DAY_IN_WEEK_ONE)

    assert changes == [BoardChange(BoardChangeKind.ADD_ISSUE_TO_BACKLOG, "missing", "Missing")]


def test_apply_board_changes_calls_the_matching_client_methods() -> None:
    client: FakeProjectBoardClient = FakeProjectBoardClient(make_board(), [], [])

    apply_board_changes(client, make_board(), [
        BoardChange(BoardChangeKind.ADD_ISSUE_TO_BACKLOG, "issue-node", "New"),
        BoardChange(BoardChangeKind.MARK_DONE, "item-1", "Closed"),
        BoardChange(BoardChangeKind.MOVE_TO_BACKLOG, "item-2", "Unsorted"),
        BoardChange(BoardChangeKind.PUT_IN_SPRINT, "item-3", "Ready", WEEK_ONE),
        BoardChange(BoardChangeKind.REMOVE_FROM_SPRINT, "item-4", "Backlog"),
    ])

    assert client.recorded_calls == [
        ("add_issue", "issue-node"), ("set_item_status", "item-for-issue-node", "Backlog"),
        ("set_item_status", "item-1", "Done"),
        ("set_item_status", "item-2", "Backlog"),
        ("set_item_week", "item-3", "week-1"),
        ("clear_item_week", "item-4"),
    ]


def test_dry_run_returns_changes_without_applying_them() -> None:
    client: FakeProjectBoardClient = FakeProjectBoardClient(make_board(), [make_item("ready")], [])

    changes: list[BoardChange] = synchronize_statuses(client, DAY_IN_WEEK_ONE, is_dry_run=True)

    assert [change.kind for change in changes] == [BoardChangeKind.PUT_IN_SPRINT]
    assert client.recorded_calls == []


def test_real_run_applies_the_planned_changes() -> None:
    client: FakeProjectBoardClient = FakeProjectBoardClient(make_board(), [make_item("ready")], [])

    synchronize_statuses(client, DAY_IN_WEEK_ONE, is_dry_run=False)

    assert client.recorded_calls == [("set_item_week", "ready", "week-1")]
