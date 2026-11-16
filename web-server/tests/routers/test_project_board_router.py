from datetime import date

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from agent_watch.api.project_board.models import SprintWeek
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_board.roll_over_sprint import SprintRolloverPlan, SprintRolloverResult
from agent_watch.api.project_board.synchronize_statuses import BoardChange, BoardChangeKind
from agent_watch_web_server.routers import project_board_router


def test_status_synchronization_plan_is_a_dry_run_for_today(api_client: TestClient, monkeypatch: pytest.MonkeyPatch,
                                                            week_two: SprintWeek) -> None:
    received_arguments: list[tuple[date, bool]] = []

    def fake_synchronize_statuses(client: ProjectBoardClient, today: date, is_dry_run: bool) -> list[BoardChange]:
        received_arguments.append((today, is_dry_run))
        return [BoardChange(BoardChangeKind.PUT_IN_SPRINT, "item-1", "Add HEC export", week_two)]

    monkeypatch.setattr(project_board_router, "synchronize_statuses", fake_synchronize_statuses)

    response: Response = api_client.get("/project-board/status-synchronization-plan")

    assert response.status_code == 200
    assert received_arguments == [(date(2026, 11, 24), True)]
    assert response.json() == [{"kind": "put in sprint", "target_id": "item-1", "target_title": "Add HEC export",
                                "sprint_week": {"id": "week-2", "title": "Week 2 (Nov 23)",
                                                "start_date": "2026-11-23", "duration_days": 7}}]


def test_sprint_rollover_plan_is_a_dry_run_with_summary(api_client: TestClient, monkeypatch: pytest.MonkeyPatch,
                                                        week_two: SprintWeek) -> None:
    received_flags: list[tuple[bool, bool]] = []

    def fake_roll_over_sprint(client: ProjectBoardClient, today: date, minimum_future_weeks: int,
                              should_post_summary: bool, is_dry_run: bool) -> SprintRolloverResult:
        received_flags.append((should_post_summary, is_dry_run))
        plan: SprintRolloverPlan = SprintRolloverPlan(target_week=week_two, previous_week=None, carried_over_items=[],
                                                      finished_items=[], this_week_items=[], new_weeks=[])
        return SprintRolloverResult(plan=plan, summary="## Week 2 (Nov 23) has started", sprint_log_issue_number=None)

    monkeypatch.setattr(project_board_router, "roll_over_sprint", fake_roll_over_sprint)

    response: Response = api_client.get("/project-board/sprint-rollover-plan")

    assert response.status_code == 200
    assert received_flags == [(True, True)]
    assert response.json()["plan"]["target_week"]["title"] == "Week 2 (Nov 23)"
    assert response.json()["summary"] == "## Week 2 (Nov 23) has started"
