import json
import logging
import urllib.request
from typing import Any

JsonObject = dict[str, Any]

GITHUB_API_URL: str = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS: float = 30

logger: logging.Logger = logging.getLogger(__name__)


class GitHubApiError(Exception):
    pass


class GitHubClient:
    def __init__(self, github_token: str) -> None:
        self.github_token: str = github_token

    def request(self, method: str, path: str, body: JsonObject | None = None) -> Any:
        logger.debug("%s %s", method, path)
        http_request: urllib.request.Request = urllib.request.Request(
            f"{GITHUB_API_URL}{path}", method=method, data=json.dumps(body).encode() if body else None,
            headers={"Authorization": f"Bearer {self.github_token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(http_request, timeout=REQUEST_TIMEOUT_SECONDS) as http_response:
            return json.loads(http_response.read() or "null")

    def run_graphql(self, query: str, **variables: object) -> JsonObject:
        response: JsonObject = self.request("POST", "/graphql", {"query": query, "variables": variables})
        if response.get("errors"):
            raise GitHubApiError(str(response["errors"]))
        data: JsonObject = response["data"]
        return data

    def run_paginated_graphql(self, query: str, connection_path: list[str], **variables: object) -> list[JsonObject]:
        nodes: list[JsonObject] = []
        page_cursor: str | None = None
        while True:
            connection: JsonObject = self.run_graphql(query, after=page_cursor, **variables)
            for key in connection_path:
                connection = connection[key]
            nodes += connection["nodes"]
            if not connection["pageInfo"]["hasNextPage"]:
                return nodes
            page_cursor = connection["pageInfo"]["endCursor"]

    def request_all_pages(self, path: str, page_size: int = 100) -> list[Any]:
        separator: str = "&" if "?" in path else "?"
        items: list[Any] = []
        page_number: int = 1
        while True:
            page_items: list[Any] = self.request("GET", f"{path}{separator}per_page={page_size}&page={page_number}")
            items += page_items
            if len(page_items) < page_size:
                return items
            page_number += 1
