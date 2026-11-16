import pytest
from doubles.github_test_doubles import ScriptedGitHubClient

from agent_watch.api.pull_request_review.pull_request_client import PullRequestClient


@pytest.fixture
def pull_request_client(github_client: ScriptedGitHubClient) -> PullRequestClient:
    return PullRequestClient(github_client, "AgentWatchOrg/AgentWatch")
