from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from agent_watch.api.project_board.models import (
    BACKLOG_STATUS, DONE_STATUS, SPRINT_LOG_ISSUE_TITLE, OpenIssue, ProjectBoard, ProjectItem, SprintWeek)
from agent_watch.api.project_board.project_board_client import ProjectBoardClient


class BoardChangeKind(StrEnum):
    ADD_ISSUE_TO_BACKLOG = "add issue to backlog"
    MARK_DONE = "mark done"
    MOVE_TO_BACKLOG = "move to backlog"
    PUT_IN_SPRINT = "put in sprint"
    REMOVE_FROM_SPRINT = "remove from sprint"


@dataclass(frozen=True)
class BoardChange:
    kind: BoardChangeKind
    target_id: str
    target_title: str
    sprint_week: SprintWeek | None = None


def plan_status_synchronization(board: ProjectBoard, items: list[ProjectItem], open_issues: list[OpenIssue],
                                today: date) -> list[BoardChange]:
    current_week: SprintWeek = board.current_or_next_week(today)
    issue_numbers_on_board: set[int] = {item.issue_number for item in items if item.issue_number}
    changes: list[BoardChange] = [
        BoardChange(BoardChangeKind.ADD_ISSUE_TO_BACKLOG, issue.id, issue.title)
        for issue in open_issues
        if issue.number not in issue_numbers_on_board and issue.title != SPRINT_LOG_ISSUE_TITLE]
    for item in items:
        changes += plan_item_changes(item, current_week)
    return changes


def plan_item_changes(item: ProjectItem, current_week: SprintWeek) -> list[BoardChange]:
    if item.is_closed and item.status != DONE_STATUS:
        closed_item_changes: list[BoardChange] = [BoardChange(BoardChangeKind.MARK_DONE, item.id, item.title)]
        if item.week_id is None:
            closed_item_changes.append(BoardChange(BoardChangeKind.PUT_IN_SPRINT, item.id, item.title, current_week))
        return closed_item_changes
    if item.status is None:
        unsorted_item_changes: list[BoardChange] = [BoardChange(BoardChangeKind.MOVE_TO_BACKLOG, item.id, item.title)]
        if item.week_id:
            unsorted_item_changes.append(BoardChange(BoardChangeKind.REMOVE_FROM_SPRINT, item.id, item.title))
        return unsorted_item_changes
    if item.status == BACKLOG_STATUS and item.week_id:
        return [BoardChange(BoardChangeKind.REMOVE_FROM_SPRINT, item.id, item.title)]
    if item.status != BACKLOG_STATUS and item.week_id is None:
        return [BoardChange(BoardChangeKind.PUT_IN_SPRINT, item.id, item.title, current_week)]
    return []


def apply_board_changes(client: ProjectBoardClient, board: ProjectBoard, changes: list[BoardChange]) -> None:
    for change in changes:
        if change.kind is BoardChangeKind.ADD_ISSUE_TO_BACKLOG:
            client.set_item_status(board, client.add_issue(board, change.target_id), BACKLOG_STATUS)
        elif change.kind is BoardChangeKind.MARK_DONE:
            client.set_item_status(board, change.target_id, DONE_STATUS)
        elif change.kind is BoardChangeKind.MOVE_TO_BACKLOG:
            client.set_item_status(board, change.target_id, BACKLOG_STATUS)
        elif change.kind is BoardChangeKind.PUT_IN_SPRINT and change.sprint_week:
            client.set_item_week(board, change.target_id, change.sprint_week)
        elif change.kind is BoardChangeKind.REMOVE_FROM_SPRINT:
            client.clear_item_week(board, change.target_id)


def synchronize_statuses(client: ProjectBoardClient, today: date, is_dry_run: bool) -> list[BoardChange]:
    board: ProjectBoard = client.load_board()
    changes: list[BoardChange] = plan_status_synchronization(
        board, client.load_items(board), client.load_open_issues(), today)
    if not is_dry_run:
        apply_board_changes(client, board, changes)
    return changes
