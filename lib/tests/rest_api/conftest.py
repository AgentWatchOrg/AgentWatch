import pytest
from fastapi.testclient import TestClient

from agent_watch.rest_api.application import application


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(application)
