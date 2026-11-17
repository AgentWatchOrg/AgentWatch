import pytest

from agent_watch.rest_api.rest_api_settings import RestApiSettings, load_rest_api_settings


def test_load_rest_api_settings_reads_secrets_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("PROJECT_BOARD_TOKEN", "")
    for variable_name in ("PROJECT_OWNER", "PROJECT_NUMBER", "PROJECT_REPOSITORY"):
        monkeypatch.delenv(variable_name, raising=False)

    settings: RestApiSettings = load_rest_api_settings()

    assert settings.github_webhook_secret == "webhook-secret"
    assert settings.project_board_token is None
    assert (settings.project_owner, settings.project_number, settings.repository) == (
        "AgentWatchOrg", 1, "AgentWatchOrg/AgentWatch")
