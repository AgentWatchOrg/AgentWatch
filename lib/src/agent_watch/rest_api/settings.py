import os

from agent_watch.api.splunk_export.models import SplunkHecSettings

INGESTION_API_KEY_ENVIRONMENT_VARIABLE: str = "AGENT_WATCH_INGESTION_API_KEY"
SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE: str = "AGENT_WATCH_SPLUNK_HEC_URL"
SPLUNK_HEC_TOKEN_ENVIRONMENT_VARIABLE: str = "AGENT_WATCH_SPLUNK_HEC_TOKEN"
SPLUNK_INDEX_ENVIRONMENT_VARIABLE: str = "AGENT_WATCH_SPLUNK_INDEX"
SPLUNK_HEC_VERIFY_TLS_ENVIRONMENT_VARIABLE: str = "AGENT_WATCH_SPLUNK_HEC_VERIFY_TLS"


def load_ingestion_api_key() -> str | None:
    return os.environ.get(INGESTION_API_KEY_ENVIRONMENT_VARIABLE)


def load_splunk_hec_settings() -> SplunkHecSettings | None:
    hec_url: str | None = os.environ.get(SPLUNK_HEC_URL_ENVIRONMENT_VARIABLE)
    hec_token: str | None = os.environ.get(SPLUNK_HEC_TOKEN_ENVIRONMENT_VARIABLE)
    if not hec_url or not hec_token:
        return None
    return SplunkHecSettings(
        hec_url=hec_url, hec_token=hec_token, index=os.environ.get(SPLUNK_INDEX_ENVIRONMENT_VARIABLE) or None,
        should_verify_tls=os.environ.get(SPLUNK_HEC_VERIFY_TLS_ENVIRONMENT_VARIABLE, "true").lower() != "false")
