import json
import urllib.request
from typing import Any

JsonObject = dict[str, Any]

GITHUB_API_URL: str = "https://api.github.com"


class GitHubApiError(Exception):
    pass


class GitHubClient:
    def __init__(self, github_token: str) -> None:
        self.github_token: str = github_token

    def request(self, method: str, path: str, body: JsonObject | None = None) -> Any:
        http_request: urllib.request.Request = urllib.request.Request(
            f"{GITHUB_API_URL}{path}", method=method, data=json.dumps(body).encode() if body else None,
            headers={"Authorization": f"Bearer {self.github_token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(http_request) as http_response:
            return json.loads(http_response.read() or "null")

    def run_graphql(self, query: str, **variables: object) -> JsonObject:
        response: JsonObject = self.request("POST", "/graphql", {"query": query, "variables": variables})
        if response.get("errors"):
            raise GitHubApiError(str(response["errors"]))
        data: JsonObject = response["data"]
        return data
