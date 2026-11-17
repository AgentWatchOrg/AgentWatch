import hashlib
import hmac
from collections.abc import Iterator
from datetime import date

import pytest
from doubles.project_board_test_doubles import FakeProjectBoardClient, FakeProjectBoardClientFactory
from fastapi.testclient import TestClient
from httpx2 import Response

from agent_watch.api.github_client import JsonObject
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_board.synchronize_statuses import BoardChange
from agent_watch.rest_api.application import application
from agent_watch.rest_api.dependencies import BoardWebhookConfiguration, get_board_webhook_configuration, get_today
from agent_watch.rest_api.routers import github_webhook_router

WEBHOOK_SECRET: str = "test-webhook-secret"
CARD_MOVED_BODY: bytes = b'{"action": "edited", "projects_v2_item": {"project_node_id": "board-1"}}'


@pytest.fixture
def recorded_synchronizations(monkeypatch: pytest.MonkeyPatch) -> list[date]:
    synchronizations: list[date] = []

    def fake_synchronize_board(client: ProjectBoardClient, today: date) -> list[BoardChange]:
        synchronizations.append(today)
        return []

    monkeypatch.setattr(github_webhook_router, "synchronize_board", fake_synchronize_board)
    return synchronizations


@pytest.fixture
def configured_api_client(make_fake_client: FakeProjectBoardClientFactory) -> Iterator[TestClient]:
    fake_client: FakeProjectBoardClient = make_fake_client()
    application.dependency_overrides[get_board_webhook_configuration] = lambda: BoardWebhookConfiguration(
        project_board_client=fake_client, webhook_secret=WEBHOOK_SECRET)
    application.dependency_overrides[get_today] = lambda: date(2026, 11, 17)
    yield TestClient(application)
    application.dependency_overrides.clear()


def sign(request_body: bytes, webhook_secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(webhook_secret.encode(), request_body, hashlib.sha256).hexdigest()


def test_card_move_starts_the_board_sync_after_responding(
        configured_api_client: TestClient, recorded_synchronizations: list[date]) -> None:
    response: Response = configured_api_client.post(
        "/github/webhooks", content=CARD_MOVED_BODY,
        headers={"X-GitHub-Event": "projects_v2_item", "X-Hub-Signature-256": sign(CARD_MOVED_BODY)})

    assert response.status_code == 202
    assert response.json() == {"outcome": "synchronization started"}
    assert recorded_synchronizations == [date(2026, 11, 17)]


def test_forged_signature_is_rejected(configured_api_client: TestClient,
                                      recorded_synchronizations: list[date]) -> None:
    response: Response = configured_api_client.post(
        "/github/webhooks", content=CARD_MOVED_BODY,
        headers={"X-GitHub-Event": "projects_v2_item", "X-Hub-Signature-256": sign(CARD_MOVED_BODY, "forged")})

    assert response.status_code == 401
    assert recorded_synchronizations == []


@pytest.mark.parametrize(("event_name", "expected_outcome"), [("ping", "pong"), ("push", "ignored")],
                         ids=["ping", "unrelated event"])
def test_events_that_do_not_sync(configured_api_client: TestClient, recorded_synchronizations: list[date],
                                 event_name: str, expected_outcome: str) -> None:
    response: Response = configured_api_client.post(
        "/github/webhooks", content=b"{}", headers={"X-GitHub-Event": event_name, "X-Hub-Signature-256": sign(b"{}")})

    assert response.json() == {"outcome": expected_outcome}
    assert recorded_synchronizations == []


def test_unconfigured_server_answers_service_unavailable(api_client: TestClient,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("PROJECT_BOARD_TOKEN", raising=False)

    response: Response = api_client.post("/github/webhooks", content=b"{}", headers={"X-GitHub-Event": "ping"})

    assert response.status_code == 503


def test_synchronize_board_one_at_a_time_runs_the_sync(make_fake_client: FakeProjectBoardClientFactory,
                                                       recorded_synchronizations: list[date]) -> None:
    github_webhook_router.synchronize_board_one_at_a_time(make_fake_client(), "issues", {}, date(2026, 11, 17))

    assert recorded_synchronizations == [date(2026, 11, 17)]
    assert not github_webhook_router.board_synchronization_lock.locked()
    assert not github_webhook_router.waiting_synchronization_lock.locked()


def test_change_arriving_while_a_sync_waits_is_folded_into_it(make_fake_client: FakeProjectBoardClientFactory,
                                                               recorded_synchronizations: list[date]) -> None:
    github_webhook_router.waiting_synchronization_lock.acquire()
    try:
        github_webhook_router.synchronize_board_one_at_a_time(make_fake_client(), "issues", {}, date(2026, 11, 17))
    finally:
        github_webhook_router.waiting_synchronization_lock.release()

    assert recorded_synchronizations == []


def test_card_change_in_another_project_does_not_sync(make_fake_client: FakeProjectBoardClientFactory,
                                                      recorded_synchronizations: list[date]) -> None:
    github_webhook_router.synchronize_board_one_at_a_time(
        make_fake_client(), "projects_v2_item", {"projects_v2_item": {"project_node_id": "PVT_other"}},
        date(2026, 11, 17))

    assert recorded_synchronizations == []
