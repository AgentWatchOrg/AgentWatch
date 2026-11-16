from dataclasses import dataclass
from datetime import date, timedelta

from agent_watch.api.project_board.models import (
    SPRINT_LOG_ISSUE_TITLE, NewSprintWeek, ProjectBoard, ProjectItem, SprintWeek)
from agent_watch.api.project_board.project_board_client import ProjectBoardClient

WEEK_LENGTH_DAYS: int = 7
SPRINT_LOG_ISSUE_BODY: str = "Weekly sprint summaries, posted every Monday by `.github/workflows/weekly-sprint-rollover.yml`."


@dataclass(frozen=True)
class SprintRolloverPlan:
    target_week: SprintWeek
    previous_week: SprintWeek | None
    carried_over_items: list[ProjectItem]
    finished_items: list[ProjectItem]
    this_week_items: list[ProjectItem]
    new_weeks: list[NewSprintWeek]


@dataclass(frozen=True)
class SprintRolloverResult:
    plan: SprintRolloverPlan
    summary: str | None
    sprint_log_issue_number: int | None


def plan_sprint_rollover(board: ProjectBoard, items: list[ProjectItem], today: date,
                         minimum_future_weeks: int) -> SprintRolloverPlan:
    target_week: SprintWeek = board.current_or_next_week(today)
    earlier_weeks: list[SprintWeek] = sorted(
        (week for week in board.weeks if week.start_date < target_week.start_date), key=lambda week: week.start_date)
    previous_week: SprintWeek | None = earlier_weeks[-1] if earlier_weeks else None
    carried_over_items: list[ProjectItem] = [
        item for item in items
        if item.week_start_date and item.week_start_date < target_week.start_date and not item.is_finished]
    return SprintRolloverPlan(
        target_week=target_week,
        previous_week=previous_week,
        carried_over_items=carried_over_items,
        finished_items=[item for item in items
                        if previous_week and item.week_id == previous_week.id and item.is_finished],
        this_week_items=[item for item in items if item.week_id == target_week.id] + carried_over_items,
        new_weeks=plan_new_weeks(board.weeks, today, minimum_future_weeks),
    )


def plan_new_weeks(weeks: list[SprintWeek], today: date, minimum_future_weeks: int) -> list[NewSprintWeek]:
    future_week_count: int = sum(1 for week in weeks if week.start_date > today)
    missing_week_count: int = max(0, minimum_future_weeks - future_week_count)
    next_start_date: date = max(week.end_date for week in weeks)
    new_weeks: list[NewSprintWeek] = []
    for week_number in range(len(weeks) + 1, len(weeks) + 1 + missing_week_count):
        new_weeks.append(NewSprintWeek(title=f"Week {week_number} ({next_start_date.strftime('%b')} {next_start_date.day})",
                                       start_date=next_start_date, duration_days=WEEK_LENGTH_DAYS))
        next_start_date += timedelta(days=WEEK_LENGTH_DAYS)
    return new_weeks


def apply_sprint_rollover(client: ProjectBoardClient, board: ProjectBoard, plan: SprintRolloverPlan) -> None:
    for item in plan.carried_over_items:
        client.set_item_week(board, item.id, plan.target_week)
    if plan.new_weeks:
        client.add_weeks(board, plan.new_weeks, WEEK_LENGTH_DAYS)


def format_item_as_markdown(item: ProjectItem) -> str:
    assignees: str = ", ".join(f"@{login}" for login in item.assignee_logins) or "_unassigned_"
    reference: str = f"[#{item.issue_number}]({item.issue_url})" if item.issue_number else "(draft)"
    return f"- {reference} {item.title} ({assignees})"


def build_sprint_summary(plan: SprintRolloverPlan, collaborator_logins: set[str]) -> str:
    logins_with_work: set[str] = {login for item in plan.this_week_items for login in item.assignee_logins}
    logins_without_work: list[str] = sorted(collaborator_logins - logins_with_work, key=str.lower)
    summary_lines: list[str] = [f"## {plan.target_week.title} has started", ""]
    if plan.previous_week:
        summary_lines += [f"**Finished in {plan.previous_week.title}** ({len(plan.finished_items)})"]
        summary_lines += [format_item_as_markdown(item) for item in plan.finished_items] or ["- nothing marked Done"]
        summary_lines += [""]
    summary_lines += [f"**Carried over into {plan.target_week.title}** ({len(plan.carried_over_items)})"]
    summary_lines += [format_item_as_markdown(item) for item in plan.carried_over_items] or ["- nothing to carry over"]
    summary_lines += ["", "**No cards this week:** " + (
        ", ".join(f"@{login}" for login in logins_without_work) if logins_without_work else "everyone has work 🎉")]
    return "\n".join(summary_lines)


def roll_over_sprint(client: ProjectBoardClient, today: date, minimum_future_weeks: int,
                     should_post_summary: bool, is_dry_run: bool) -> SprintRolloverResult:
    board: ProjectBoard = client.load_board()
    plan: SprintRolloverPlan = plan_sprint_rollover(board, client.load_items(board), today, minimum_future_weeks)
    if not is_dry_run:
        apply_sprint_rollover(client, board, plan)
    if not should_post_summary:
        return SprintRolloverResult(plan=plan, summary=None, sprint_log_issue_number=None)
    summary: str = build_sprint_summary(plan, client.repository_collaborator_logins())
    if is_dry_run:
        return SprintRolloverResult(plan=plan, summary=summary, sprint_log_issue_number=None)
    sprint_log_issue_number: int = client.find_or_create_issue(SPRINT_LOG_ISSUE_TITLE, SPRINT_LOG_ISSUE_BODY)
    client.comment_on_issue(sprint_log_issue_number, summary)
    return SprintRolloverResult(plan=plan, summary=summary, sprint_log_issue_number=sprint_log_issue_number)
