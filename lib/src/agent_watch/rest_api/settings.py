import os

INGESTION_API_KEY_ENVIRONMENT_VARIABLE: str = "AGENT_WATCH_INGESTION_API_KEY"


def load_ingestion_api_key() -> str | None:
    return os.environ.get(INGESTION_API_KEY_ENVIRONMENT_VARIABLE)
