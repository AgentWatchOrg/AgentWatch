import pytest
from fastapi.testclient import TestClient

from agent_watch_web_server.application import application


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(application)
