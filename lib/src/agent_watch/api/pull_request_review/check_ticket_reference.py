import re

from agent_watch.api.pull_request_review.models import PullRequest, ReferencedIssue, TicketReferenceCheck
from agent_watch.api.pull_request_review.pull_request_client import PullRequestClient

TICKET_REFERENCE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|part of)\s*:?\s+#(\d+)\b", re.IGNORECASE)


def find_referenced_issue_numbers(pull_request_body: str) -> list[int]:
    referenced_numbers: list[int] = [int(number) for number in TICKET_REFERENCE_PATTERN.findall(pull_request_body)]
    return list(dict.fromkeys(referenced_numbers))


def check_ticket_reference(client: PullRequestClient, pull_request_number: int) -> TicketReferenceCheck:
    pull_request: PullRequest = client.load_pull_request(pull_request_number)
    referenced_issue_numbers: list[int] = find_referenced_issue_numbers(pull_request.body)
    referenced_issues: dict[int, ReferencedIssue | None] = {
        issue_number: client.find_issue(issue_number) for issue_number in referenced_issue_numbers}
    return TicketReferenceCheck(
        pull_request_number=pull_request_number,
        referenced_issue_numbers=referenced_issue_numbers,
        missing_issue_numbers=[number for number, issue in referenced_issues.items() if issue is None],
        pull_request_numbers_referenced_as_tickets=[
            number for number, issue in referenced_issues.items() if issue and issue.is_pull_request],
    )
