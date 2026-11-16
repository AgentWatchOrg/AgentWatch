from typing import Any

from agent_watch.api.github_client import GitHubClient, JsonObject


class ScriptedGitHubClient(GitHubClient):
    def __init__(self) -> None:
        super().__init__("unused-token")
        self.graphql_responses: list[JsonObject] = []
        self.rest_responses: list[Any] = []
        self.graphql_calls: list[tuple[str, dict[str, object]]] = []
        self.rest_calls: list[tuple[str, str, JsonObject | None]] = []

    def run_graphql(self, query: str, **variables: object) -> JsonObject:
        self.graphql_calls.append((query, variables))
        return self.graphql_responses.pop(0) if self.graphql_responses else {}

    def request(self, method: str, path: str, body: JsonObject | None = None) -> Any:
        self.rest_calls.append((method, path, body))
        return self.rest_responses.pop(0) if self.rest_responses else None
