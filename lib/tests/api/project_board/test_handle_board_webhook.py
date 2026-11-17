import hashlib
import hmac
from datetime import date

import pytest
from doubles.project_board_test_doubles import FakeProjectBoardClient, FakeProjectBoardClientFactory

from agent_watch.api.github_client import JsonObject
from agent_watch.api.project_board.handle_board_webhook import (
    BoardWebhookOutcome, classify_board_webhook, is_change_to_synchronized_board, synchronize_board,
    verify_webhook_signature)
from agent_watch.api.project_board.models import OpenIssue, WebhookSignatureError
from agent_watch.api.project_board.synchronize_statuses import BoardChange

WEBHOOK_SECRET: str = "test-webhook-secret"
REPOSITORY: str = "AgentWatchOrg/AgentWatch"
FIRST_DAY_OF_WEEK_ONE: date = date(2026, 11, 16)


@pytest.fixture
def fake_client_with_new_issue(make_fake_client: FakeProjectBoardClientFactory) -> FakeProjectBoardClient:
    return make_fake_client(open_issues=[OpenIssue(id="issue-60", number=60, title="New spike")])


def sign(request_body: bytes, webhook_secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(webhook_secret.encode(), request_body, hashlib.sha256).hexdigest()


def test_verify_webhook_signature_accepts_a_matching_signature() -> None:
    verify_webhook_signature(WEBHOOK_SECRET, b"{}", sign(b"{}"))


@pytest.mark.parametrize("signature_header", [sign(b"{}", "wrong-secret"), "sha1=abc", None],
                         ids=["wrong secret", "other algorithm", "missing"])
def test_verify_webhook_signature_rejects_others(signature_header: str | None) -> None:
    with pytest.raises(WebhookSignatureError):
        verify_webhook_signature(WEBHOOK_SECRET, b"{}", signature_header)


@pytest.mark.parametrize(("event_name", "payload", "expected"), [
    ("ping", {}, BoardWebhookOutcome.PONG),
    ("issues", {"action": "opened", "repository": {"full_name": REPOSITORY}},
     BoardWebhookOutcome.SYNCHRONIZATION_STARTED),
    ("issues", {"action": "closed", "repository": {"full_name": REPOSITORY}},
     BoardWebhookOutcome.SYNCHRONIZATION_STARTED),
    ("issues", {"action": "labeled", "repository": {"full_name": REPOSITORY}}, BoardWebhookOutcome.IGNORED),
    ("issues", {"action": "opened", "repository": {"full_name": "AgentWatchOrg/Other"}}, BoardWebhookOutcome.IGNORED),
    ("projects_v2_item", {"action": "edited"}, BoardWebhookOutcome.SYNCHRONIZATION_STARTED),
    ("projects_v2_item", {"action": "archived"}, BoardWebhookOutcome.IGNORED),
    ("push", {}, BoardWebhookOutcome.IGNORED),
], ids=["ping", "issue opened", "issue closed", "issue labeled", "other repository", "card edited", "card archived",
        "other event"])
def test_classify_board_webhook(event_name: str, payload: JsonObject, expected: BoardWebhookOutcome) -> None:
    assert classify_board_webhook(event_name, payload, REPOSITORY) == expected


@pytest.mark.parametrize(("event_name", "payload", "expected"), [
    ("projects_v2_item", {"action": "edited", "projects_v2_item": {"project_node_id": "board-1"}}, True),
    ("projects_v2_item", {"action": "edited", "projects_v2_item": {"project_node_id": "PVT_other"}}, False),
    ("issues", {"action": "opened"}, True),
], ids=["card in this board", "card in another project", "issue opened"])
def test_is_change_to_synchronized_board(fake_client_with_new_issue: FakeProjectBoardClient, event_name: str,
                                         payload: JsonObject, expected: bool) -> None:
    assert is_change_to_synchronized_board(fake_client_with_new_issue, event_name, payload) is expected


def test_card_in_another_project_is_logged(fake_client_with_new_issue: FakeProjectBoardClient,
                                           caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        is_change_to_synchronized_board(fake_client_with_new_issue, "projects_v2_item",
                                        {"action": "edited", "projects_v2_item": {"project_node_id": "PVT_other"}})

    assert "Ignored a card change in project PVT_other; this server syncs AgentWatch Board (board-1)" in caplog.text


def test_synchronize_board_applies_changes(fake_client_with_new_issue: FakeProjectBoardClient) -> None:
    board_changes: list[BoardChange] = synchronize_board(fake_client_with_new_issue, FIRST_DAY_OF_WEEK_ONE)

    assert len(board_changes) == 1
    assert ("add_issue", "issue-60") in fake_client_with_new_issue.recorded_calls
