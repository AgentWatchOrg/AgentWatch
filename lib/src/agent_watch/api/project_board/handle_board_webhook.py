import hashlib
import hmac
import logging
from datetime import date
from enum import StrEnum

from agent_watch.api.github_client import JsonObject
from agent_watch.api.project_board.models import ProjectBoard, WebhookSignatureError
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_board.synchronize_statuses import BoardChange, synchronize_statuses

PING_EVENT_NAME: str = "ping"
ISSUES_EVENT_NAME: str = "issues"
PROJECT_ITEM_EVENT_NAME: str = "projects_v2_item"
SYNCHRONIZING_ISSUE_ACTIONS: frozenset[str] = frozenset({"opened", "reopened", "closed"})
SYNCHRONIZING_PROJECT_ITEM_ACTIONS: frozenset[str] = frozenset({"created", "edited", "restored", "converted"})

logger: logging.Logger = logging.getLogger(__name__)


class BoardWebhookOutcome(StrEnum):
    PONG = "pong"
    SYNCHRONIZATION_STARTED = "synchronization started"
    IGNORED = "ignored"


def verify_webhook_signature(webhook_secret: str, request_body: bytes, signature_header: str | None) -> None:
    expected_signature: str = "sha256=" + hmac.new(webhook_secret.encode(), request_body, hashlib.sha256).hexdigest()
    if signature_header is None or not hmac.compare_digest(expected_signature, signature_header):
        raise WebhookSignatureError("The X-Hub-Signature-256 header does not match the webhook secret.")


def classify_board_webhook(event_name: str, payload: JsonObject, repository: str) -> BoardWebhookOutcome:
    if event_name == PING_EVENT_NAME:
        return BoardWebhookOutcome.PONG
    is_issue_change: bool = (event_name == ISSUES_EVENT_NAME and payload.get("action") in SYNCHRONIZING_ISSUE_ACTIONS
                             and (payload.get("repository") or {}).get("full_name") == repository)
    is_card_change: bool = (event_name == PROJECT_ITEM_EVENT_NAME
                            and payload.get("action") in SYNCHRONIZING_PROJECT_ITEM_ACTIONS)
    if is_issue_change or is_card_change:
        return BoardWebhookOutcome.SYNCHRONIZATION_STARTED
    return BoardWebhookOutcome.IGNORED


def is_change_to_synchronized_board(client: ProjectBoardClient, event_name: str, payload: JsonObject) -> bool:
    if event_name != PROJECT_ITEM_EVENT_NAME:
        return True
    board: ProjectBoard = client.load_board()
    changed_project_node_id: str | None = (payload.get("projects_v2_item") or {}).get("project_node_id")
    if changed_project_node_id != board.id:
        logger.info("Ignored a card change in project %s; this server syncs %s (%s)", changed_project_node_id,
                    board.title, board.id)
        return False
    return True


def synchronize_board(client: ProjectBoardClient, today: date) -> list[BoardChange]:
    board_changes: list[BoardChange] = synchronize_statuses(client, today, is_dry_run=False)
    logger.info("Board sync made %d change(s)", len(board_changes))
    return board_changes
