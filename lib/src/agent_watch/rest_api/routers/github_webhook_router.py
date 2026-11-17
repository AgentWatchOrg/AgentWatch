import json
import threading
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status

from agent_watch.api.github_client import JsonObject
from agent_watch.api.project_board.handle_board_webhook import (
    BoardWebhookOutcome, classify_board_webhook, is_change_to_synchronized_board, synchronize_board,
    verify_webhook_signature)
from agent_watch.api.project_board.models import WebhookSignatureError
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.rest_api.dependencies import BoardWebhookConfiguration, get_board_webhook_configuration, get_today

github_webhook_router: APIRouter = APIRouter(tags=["github"])
board_synchronization_lock: threading.Lock = threading.Lock()
waiting_synchronization_lock: threading.Lock = threading.Lock()


@dataclass(frozen=True)
class GitHubWebhookResponse:
    outcome: BoardWebhookOutcome


@github_webhook_router.post("/github/webhooks", status_code=status.HTTP_202_ACCEPTED)
async def receive_github_webhook(
        request: Request, background_tasks: BackgroundTasks,
        configuration: Annotated[BoardWebhookConfiguration, Depends(get_board_webhook_configuration)],
        today: Annotated[date, Depends(get_today)],
        x_github_event: Annotated[str, Header()],
        x_hub_signature_256: Annotated[str | None, Header()] = None) -> GitHubWebhookResponse:
    request_body: bytes = await request.body()
    try:
        verify_webhook_signature(configuration.webhook_secret, request_body, x_hub_signature_256)
    except WebhookSignatureError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    payload: JsonObject = json.loads(request_body or b"{}")
    outcome: BoardWebhookOutcome = classify_board_webhook(
        x_github_event, payload, configuration.project_board_client.repository)
    if outcome is BoardWebhookOutcome.SYNCHRONIZATION_STARTED:
        # GitHub abandons a delivery after 10 seconds, so the sync runs after the response is sent.
        background_tasks.add_task(synchronize_board_one_at_a_time, configuration.project_board_client,
                                  x_github_event, payload, today)
    return GitHubWebhookResponse(outcome=outcome)


def synchronize_board_one_at_a_time(client: ProjectBoardClient, event_name: str, payload: JsonObject,
                                    today: date) -> None:
    if not is_change_to_synchronized_board(client, event_name, payload):
        return
    # At most one sync runs and one waits; a sync that starts later reads every change made before it.
    if not waiting_synchronization_lock.acquire(blocking=False):
        return
    with board_synchronization_lock:
        waiting_synchronization_lock.release()
        synchronize_board(client, today)
