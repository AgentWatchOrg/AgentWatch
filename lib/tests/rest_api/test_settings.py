import pytest

from agent_watch.rest_api.settings import INGESTION_API_KEY_ENVIRONMENT_VARIABLE, load_ingestion_api_key


def test_load_ingestion_api_key_returns_the_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, "a-configured-key")

    assert load_ingestion_api_key() == "a-configured-key"


def test_load_ingestion_api_key_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, raising=False)

    assert load_ingestion_api_key() is None
