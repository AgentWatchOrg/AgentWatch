from datetime import date

import click

from agent_watch_cli.project_board.project_board_client import (
    BACKLOG_STATUS, DONE_STATUS, SPRINT_LOG_ISSUE_TITLE, ProjectBoard, ProjectBoardClient, ProjectItem, SprintWeek)


def add_missing_open_issues_to_backlog(client: ProjectBoardClient, board: ProjectBoard,
                                       project_items: list[ProjectItem], is_dry_run: bool) -> None:
    issue_numbers_on_board: set[int] = {item.issue_number for item in project_items if item.issue_number}
    for issue in client.load_open_issues():
        if issue["number"] in issue_numbers_on_board or issue["title"] == SPRINT_LOG_ISSUE_TITLE:
            continue
        click.echo(f"Add #{issue['number']} {issue['title']} to {BACKLOG_STATUS}")
        if not is_dry_run:
            added_item_id: str = client.add_issue_to_project(board, issue["id"])
            client.set_item_status(board, added_item_id, BACKLOG_STATUS)


def synchronize_item(client: ProjectBoardClient, board: ProjectBoard, item: ProjectItem,
                     current_week: SprintWeek, is_dry_run: bool) -> None:
    item_label: str = item.summary_line()[2:]
    if item.is_closed and item.status != DONE_STATUS:
        click.echo(f"Mark {item_label} {DONE_STATUS} (issue closed)")
        if not is_dry_run:
            client.set_item_status(board, item.id, DONE_STATUS)
        if item.week_id is None:
            click.echo(f"Put {item_label} in {current_week.title}")
            if not is_dry_run:
                client.set_item_week(board, item.id, current_week)
    elif item.status is None:
        click.echo(f"Put {item_label} in {BACKLOG_STATUS}")
        if not is_dry_run:
            client.set_item_status(board, item.id, BACKLOG_STATUS)
            if item.week_id:
                client.clear_item_week(board, item.id)
    elif item.status == BACKLOG_STATUS and item.week_id:
        click.echo(f"Remove {item_label} from {item.week_title} (back in {BACKLOG_STATUS})")
        if not is_dry_run:
            client.clear_item_week(board, item.id)
    elif item.status != BACKLOG_STATUS and item.week_id is None:
        click.echo(f"Put {item_label} in {current_week.title} (status {item.status})")
        if not is_dry_run:
            client.set_item_week(board, item.id, current_week)


def synchronize_statuses_with_sprint_weeks(client: ProjectBoardClient, today: date, is_dry_run: bool) -> None:
    board: ProjectBoard = client.load_project_board()
    current_week: SprintWeek = board.current_or_next_week(today)
    click.echo(f"{board.title}: today is {today}, sprint {current_week.title}{' (dry run)' if is_dry_run else ''}")
    project_items: list[ProjectItem] = client.load_project_items(board)
    add_missing_open_issues_to_backlog(client, board, project_items, is_dry_run)
    for item in project_items:
        synchronize_item(client, board, item, current_week, is_dry_run)
