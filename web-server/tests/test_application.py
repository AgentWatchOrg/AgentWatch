from fastapi.testclient import TestClient
from httpx2 import Response


def test_swagger_page_and_openapi_schema_are_served(api_client: TestClient) -> None:
    swagger_response: Response = api_client.get("/docs")
    schema_response: Response = api_client.get("/openapi.json")

    assert swagger_response.status_code == 200
    assert "swagger-ui" in swagger_response.text
    assert set(schema_response.json()["paths"]) == {"/health"}
