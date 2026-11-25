import pytest

from agent_watch.api.splunk_export.models import SplunkHecSettings
from agent_watch.rest_api.settings import (
    INGESTION_API_KEY_ENVIRONMENT_VARIABLE, SPLUNK_HEC_TOKEN_ENVIRONMENT_VARIABLE, SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE,
    SPLUNK_HEC_VERIFY_TLS_ENVIRONMENT_VARIABLE, SPLUNK_INDEX_ENVIRONMENT_VARIABLE, load_ingestion_api_key,
    load_splunk_hec_settings)


def test_load_ingestion_api_key_returns_the_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, "a-configured-key")

    assert load_ingestion_api_key() == "a-configured-key"


def test_load_ingestion_api_key_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(INGESTION_API_KEY_ENVIRONMENT_VARIABLE, raising=False)

    assert load_ingestion_api_key() is None


def test_load_splunk_hec_settings_returns_none_without_a_url_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setenv(SPLUNK_HEC_TOKEN_ENVIRONMENT_VARIABLE, "a-token")

    assert load_splunk_hec_settings() is None


def test_load_splunk_hec_settings_reads_every_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE, "https://localhost:8088")
    monkeypatch.setenv(SPLUNK_HEC_TOKEN_ENVIRONMENT_VARIABLE, "a-token")
    monkeypatch.setenv(SPLUNK_INDEX_ENVIRONMENT_VARIABLE, "agentwatch")
    monkeypatch.setenv(SPLUNK_HEC_VERIFY_TLS_ENVIRONMENT_VARIABLE, "false")

    assert load_splunk_hec_settings() == SplunkHecSettings(
        hec_url="https://localhost:8088", hec_token="a-token", index="agentwatch", should_verify_tls=False)


def test_load_splunk_hec_settings_verifies_certificates_and_uses_the_token_index_by_default(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE, "https://splunk.example:8088")
    monkeypatch.setenv(SPLUNK_HEC_TOKEN_ENVIRONMENT_VARIABLE, "a-token")
    monkeypatch.delenv(SPLUNK_INDEX_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.delenv(SPLUNK_HEC_VERIFY_TLS_ENVIRONMENT_VARIABLE, raising=False)

    hec_settings: SplunkHecSettings | None = load_splunk_hec_settings()

    assert hec_settings is not None
    assert (hec_settings.index, hec_settings.should_verify_tls) == (None, True)
