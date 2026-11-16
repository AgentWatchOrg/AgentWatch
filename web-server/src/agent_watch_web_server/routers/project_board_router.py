from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_board.roll_over_sprint import SprintRolloverResult, roll_over_sprint
from agent_watch.api.project_board.synchronize_statuses import BoardChange, synchronize_statuses
from agent_watch_web_server.dependencies import get_project_board_client, get_today

MINIMUM_FUTURE_WEEKS: int = 4

project_board_router: APIRouter = APIRouter(prefix="/project-board", tags=["project board"])


@project_board_router.get("/status-synchronization-plan")
def get_status_synchronization_plan(
        client: Annotated[ProjectBoardClient, Depends(get_project_board_client)],
        today: Annotated[date, Depends(get_today)]) -> list[BoardChange]:
    return synchronize_statuses(client, today, is_dry_run=True)


@project_board_router.get("/sprint-rollover-plan")
def get_sprint_rollover_plan(
        client: Annotated[ProjectBoardClient, Depends(get_project_board_client)],
        today: Annotated[date, Depends(get_today)]) -> SprintRolloverResult:
    return roll_over_sprint(client, today, MINIMUM_FUTURE_WEEKS, should_post_summary=True, is_dry_run=True)
