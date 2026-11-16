from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import click

from agent_watch_cli.project_board.project_board_client import ProjectBoardClient
from agent_watch_cli.project_board.roll_over_sprint import roll_over_sprint
from agent_watch_cli.project_board.synchronize_statuses_with_sprint_weeks import synchronize_statuses_with_sprint_weeks

PROJECT_TIME_ZONE: ZoneInfo = ZoneInfo("America/Edmonton")


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
        client=ProjectBoardClient(github_token, project_owner, project_number, repository),
        today=simulated_today.date() if simulated_today else datetime.now(PROJECT_TIME_ZONE).date(),
        is_dry_run=is_dry_run,
    )


@project_board.command("synchronize-statuses", help="Add new issues to Backlog and match each card's sprint week to its status.")
@click.pass_obj
def synchronize_statuses_command(settings: ProjectBoardCommandSettings) -> None:
    synchronize_statuses_with_sprint_weeks(settings.client, settings.today, settings.is_dry_run)


@project_board.command("roll-over-sprint", help="Move unfinished cards into the current sprint, add future weeks, post the Sprint Log summary.")
@click.option("--minimum-future-weeks", envvar="MINIMUM_FUTURE_WEEKS", default=4, show_default=True)
@click.option("--post-summary/--no-post-summary", "should_post_summary", envvar="SHOULD_POST_SUMMARY",
              default=True, show_default=True)
@click.pass_obj
def roll_over_sprint_command(settings: ProjectBoardCommandSettings, minimum_future_weeks: int,
                             should_post_summary: bool) -> None:
    roll_over_sprint(settings.client, settings.today, minimum_future_weeks, should_post_summary, settings.is_dry_run)
