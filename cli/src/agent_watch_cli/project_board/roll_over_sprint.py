from datetime import date, timedelta

import click

from agent_watch_cli.project_board.project_board_client import (
    SPRINT_LOG_ISSUE_TITLE, JsonObject, ProjectBoard, ProjectBoardClient, ProjectItem, SprintWeek)

WEEK_LENGTH_DAYS: int = 7


def add_weeks_if_running_low(client: ProjectBoardClient, board: ProjectBoard, today: date,
                             minimum_future_weeks: int, is_dry_run: bool) -> list[str]:
    future_week_count: int = sum(1 for week in board.weeks if week.start_date > today)
    if future_week_count >= minimum_future_weeks:
        return []
    weeks_by_start: list[SprintWeek] = sorted(board.weeks, key=lambda week: week.start_date)
    next_start_date: date = weeks_by_start[-1].end_date
    new_weeks: list[JsonObject] = []
    for week_number in range(len(weeks_by_start) + 1, len(weeks_by_start) + 1 + minimum_future_weeks - future_week_count):
        new_weeks.append({"startDate": next_start_date.isoformat(), "duration": WEEK_LENGTH_DAYS,
                          "title": f"Week {week_number} ({next_start_date.strftime('%b')} {next_start_date.day})"})
        next_start_date += timedelta(days=WEEK_LENGTH_DAYS)
    if not is_dry_run:
        # The API replaces the whole week list; resending existing weeks with their ids keeps cards attached.
        existing_weeks: list[JsonObject] = [
            {"id": week.id, "title": week.title, "startDate": week.start_date.isoformat(), "duration": week.duration_days}
            for week in weeks_by_start]
        client.replace_weeks(board, existing_weeks + new_weeks, WEEK_LENGTH_DAYS)
    return [new_week["title"] for new_week in new_weeks]


def build_sprint_summary(collaborator_logins: set[str], target_week: SprintWeek, previous_week: SprintWeek | None,
                         finished_items: list[ProjectItem], carried_over_items: list[ProjectItem],
                         this_week_items: list[ProjectItem]) -> str:
    logins_with_work: set[str] = {login for item in this_week_items for login in item.assignee_logins}
    logins_without_work: list[str] = sorted(collaborator_logins - logins_with_work, key=str.lower)
    summary_lines: list[str] = [f"## {target_week.title} has started", ""]
    if previous_week:
        summary_lines += [f"**Finished in {previous_week.title}** ({len(finished_items)})"]
        summary_lines += [item.summary_line() for item in finished_items] or ["- nothing marked Done"]
        summary_lines += [""]
    summary_lines += [f"**Carried over into {target_week.title}** ({len(carried_over_items)})"]
    summary_lines += [item.summary_line() for item in carried_over_items] or ["- nothing to carry over"]
    summary_lines += ["", "**No cards this week:** " + (
        ", ".join(f"@{login}" for login in logins_without_work) if logins_without_work else "everyone has work 🎉")]
    return "\n".join(summary_lines)


def roll_over_sprint(client: ProjectBoardClient, today: date, minimum_future_weeks: int,
                     should_post_summary: bool, is_dry_run: bool) -> None:
    board: ProjectBoard = client.load_project_board()
    click.echo(f"{board.title}: today is {today}{' (dry run)' if is_dry_run else ''}")

    target_week: SprintWeek = board.current_or_next_week(today)
    earlier_weeks: list[SprintWeek] = sorted((week for week in board.weeks if week.start_date < target_week.start_date),
                                             key=lambda week: week.start_date)
    previous_week: SprintWeek | None = earlier_weeks[-1] if earlier_weeks else None
    click.echo(f"Target week: {target_week.title}")

    project_items: list[ProjectItem] = client.load_project_items(board)
    carried_over_items: list[ProjectItem] = [
        item for item in project_items
        if item.week_start_date and item.week_start_date < target_week.start_date and not item.is_finished]
    for item in carried_over_items:
        click.echo(f"Move {item.summary_line()[2:]}: {item.week_title} -> {target_week.title}")
        if not is_dry_run:
            client.set_item_week(board, item.id, target_week)
    click.echo(f"Carried over {len(carried_over_items)} card(s)")

    for added_week_title in add_weeks_if_running_low(client, board, today, minimum_future_weeks, is_dry_run):
        click.echo(f"Added {added_week_title}")

    if not should_post_summary:
        return
    finished_items: list[ProjectItem] = [
        item for item in project_items
        if previous_week and item.week_id == previous_week.id and item.is_finished]
    this_week_items: list[ProjectItem] = [
        item for item in project_items if item.week_id == target_week.id] + carried_over_items
    summary: str = build_sprint_summary(client.repository_collaborator_logins(), target_week, previous_week,
                                        finished_items, carried_over_items, this_week_items)
    if is_dry_run:
        click.echo("\n--- summary (not posted, dry run) ---\n" + summary)
        return
    sprint_log_issue_number: int = client.find_or_create_issue_number(
        SPRINT_LOG_ISSUE_TITLE,
        "Weekly sprint summaries, posted every Monday by `.github/workflows/weekly-sprint-rollover.yml`.")
    client.comment_on_issue(sprint_log_issue_number, summary)
    click.echo(f"Posted summary on {client.repository}#{sprint_log_issue_number}")
