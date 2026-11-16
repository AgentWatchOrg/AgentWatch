from datetime import date

import pytest
from click.testing import CliRunner, Result
from project_board_test_doubles import WEEK_TWO, make_item

from agent_watch.api.project_board.models import NewSprintWeek
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_board.roll_over_sprint import SprintRolloverPlan, SprintRolloverResult
from agent_watch.api.project_board.synchronize_statuses import BoardChange, BoardChangeKind
from agent_watch.cli import project_board_commands
from agent_watch.cli.main import agent_watch


def test_version_option_prints_the_package_version() -> None:
    result: Result = CliRunner().invoke(agent_watch, ["--version"])

    assert result.exit_code == 0
    assert result.output.startswith("agent-watch, version ")


def test_project_board_requires_a_token() -> None:
    result: Result = CliRunner().invoke(agent_watch, ["project-board", "synchronize-statuses"],
                                        env={"PROJECT_BOARD_TOKEN": None})

    assert result.exit_code != 0
    assert "--github-token" in result.output


def test_synchronize_statuses_prints_each_change(monkeypatch: pytest.MonkeyPatch) -> None:
    received_arguments: list[tuple[date, bool]] = []

    def fake_synchronize_statuses(client: ProjectBoardClient, today: date, is_dry_run: bool) -> list[BoardChange]:
        received_arguments.append((today, is_dry_run))
        return [BoardChange(BoardChangeKind.PUT_IN_SPRINT, "item-1", "Add HEC export", WEEK_TWO)]

    monkeypatch.setattr(project_board_commands, "synchronize_statuses", fake_synchronize_statuses)

    result: Result = CliRunner().invoke(
        agent_watch, ["project-board", "--simulated-today", "2026-11-24", "synchronize-statuses"],
        env={"PROJECT_BOARD_TOKEN": "token", "IS_DRY_RUN": "true"})

    assert result.exit_code == 0, result.output
    assert received_arguments == [(date(2026, 11, 24), True)]
    assert "put in sprint: Add HEC export (Week 2 (Nov 23))" in result.output
    assert "1 change(s) planned (dry run)" in result.output


def test_roll_over_sprint_prints_the_plan_and_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    plan: SprintRolloverPlan = SprintRolloverPlan(
        target_week=WEEK_TWO, previous_week=None, carried_over_items=[make_item("unfinished")],
        finished_items=[], this_week_items=[],
        new_weeks=[NewSprintWeek(title="Week 20 (Apr 19)", start_date=date(2027, 4, 19), duration_days=7)])

    def fake_roll_over_sprint(client: ProjectBoardClient, today: date, minimum_future_weeks: int,
                              should_post_summary: bool, is_dry_run: bool) -> SprintRolloverResult:
        return SprintRolloverResult(plan=plan, summary="## Week 2 (Nov 23) has started", sprint_log_issue_number=31)

    monkeypatch.setattr(project_board_commands, "roll_over_sprint", fake_roll_over_sprint)

    result: Result = CliRunner().invoke(agent_watch, ["project-board", "roll-over-sprint"],
                                        env={"PROJECT_BOARD_TOKEN": "token"})

    assert result.exit_code == 0, result.output
    assert "Target week: Week 2 (Nov 23)" in result.output
    assert "Carry over: Title of unfinished" in result.output
    assert "Add week: Week 20 (Apr 19)" in result.output
    assert "Posted on AgentWatchOrg/AgentWatch#31" in result.output
