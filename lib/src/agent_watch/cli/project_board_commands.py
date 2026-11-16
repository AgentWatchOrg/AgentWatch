import logging
from dataclasses import dataclass
from datetime import date, datetime

import click

from agent_watch.api.github_client import GitHubClient
from agent_watch.api.project_calendar import today_in_project_time_zone
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_board.roll_over_sprint import SprintRolloverResult, roll_over_sprint
from agent_watch.api.project_board.synchronize_statuses import BoardChange, synchronize_statuses

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectBoardCommandSettings:
    client: ProjectBoardClient
    today: date
    is_dry_run: bool


@click.group("project-board", help="Manage the AgentWatch project board and its weekly sprints.")
@click.option("--github-token", envvar="PROJECT_BOARD_TOKEN", required=True,
              help="Token with project and repo scopes. Env: PROJECT_BOARD_TOKEN")
@click.option("--project-owner", envvar="PROJECT_OWNER", default="AgentWatchOrg", show_default=True)
@click.option("--project-number", envvar="PROJECT_NUMBER", default=1, show_default=True)
@click.option("--repository", envvar="PROJECT_REPOSITORY", default="AgentWatchOrg/AgentWatch", show_default=True)
@click.option("--simulated-today", envvar="SIMULATED_TODAY", type=click.DateTime(["%Y-%m-%d"]),
              help="Pretend today is this date. Env: SIMULATED_TODAY")
@click.option("--dry-run/--no-dry-run", "is_dry_run", envvar="IS_DRY_RUN", default=False,
              help="Print changes without making them. Env: IS_DRY_RUN")
@click.pass_context
def project_board(context: click.Context, github_token: str, project_owner: str, project_number: int,
                  repository: str, simulated_today: datetime | None, is_dry_run: bool) -> None:
    context.obj = ProjectBoardCommandSettings(
        client=ProjectBoardClient(GitHubClient(github_token), project_owner, project_number, repository),
        today=simulated_today.date() if simulated_today else today_in_project_time_zone(),
        is_dry_run=is_dry_run,
    )


@project_board.command("synchronize-statuses",
                       help="Add new issues to Backlog and match each card's sprint week to its status.")
@click.pass_obj
def synchronize_statuses_command(settings: ProjectBoardCommandSettings) -> None:
    changes: list[BoardChange] = synchronize_statuses(settings.client, settings.today, settings.is_dry_run)
    for change in changes:
        sprint_week_suffix: str = f" ({change.sprint_week.title})" if change.sprint_week else ""
        logger.info(f"{change.kind}: {change.target_title}{sprint_week_suffix}")
    logger.info(f"{len(changes)} change(s){' planned (dry run)' if settings.is_dry_run else ' applied'}")


@project_board.command("roll-over-sprint",
                       help="Move unfinished cards into the current sprint, add future weeks, post the Sprint Log summary.")
@click.option("--minimum-future-weeks", envvar="MINIMUM_FUTURE_WEEKS", default=4, show_default=True)
@click.option("--post-summary/--no-post-summary", "should_post_summary", envvar="SHOULD_POST_SUMMARY",
              default=True, show_default=True)
@click.pass_obj
def roll_over_sprint_command(settings: ProjectBoardCommandSettings, minimum_future_weeks: int,
                             should_post_summary: bool) -> None:
    result: SprintRolloverResult = roll_over_sprint(
        settings.client, settings.today, minimum_future_weeks, should_post_summary, settings.is_dry_run)
    logger.info(f"Target week: {result.plan.target_week.title}{' (dry run)' if settings.is_dry_run else ''}")
    for item in result.plan.carried_over_items:
        logger.info(f"Carry over: {item.title} ({item.week_title} -> {result.plan.target_week.title})")
    for new_week in result.plan.new_weeks:
        logger.info(f"Add week: {new_week.title}")
    if result.summary:
        logger.info("%s", result.summary)
    if result.sprint_log_issue_number:
        logger.info(f"Posted on {settings.client.repository}#{result.sprint_log_issue_number}")
