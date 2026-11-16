from fastapi.testclient import TestClient
from httpx import Response


def test_health_returns_ok(api_client: TestClient) -> None:
    response: Response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
