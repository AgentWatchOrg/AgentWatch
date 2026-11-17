from datetime import date

import pytest
from fastapi import HTTPException

from agent_watch.rest_api.dependencies import BoardWebhookConfiguration, get_board_webhook_configuration, get_today


def test_get_board_webhook_configuration_builds_a_board_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("PROJECT_BOARD_TOKEN", "board-token")
    monkeypatch.setenv("PROJECT_NUMBER", "2")

    configuration: BoardWebhookConfiguration = get_board_webhook_configuration()

    assert configuration.webhook_secret == "webhook-secret"
    assert configuration.project_board_client.github_client.github_token == "board-token"
    assert configuration.project_board_client.project_number == 2


def test_get_board_webhook_configuration_requires_both_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.delenv("PROJECT_BOARD_TOKEN", raising=False)

    with pytest.raises(HTTPException) as raised:
        get_board_webhook_configuration()

    assert raised.value.status_code == 503


def test_get_today_returns_a_date() -> None:
    assert isinstance(get_today(), date)
