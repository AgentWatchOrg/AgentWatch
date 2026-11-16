import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

JsonObject = dict[str, Any]

PROJECT_BOARD_TOKEN: str = os.environ["PROJECT_BOARD_TOKEN"]
PROJECT_OWNER: str = os.environ.get("PROJECT_OWNER", "AgentWatchOrg")
PROJECT_NUMBER: int = int(os.environ.get("PROJECT_NUMBER", "1"))
PROJECT_REPOSITORY: str = os.environ.get("PROJECT_REPOSITORY", "AgentWatchOrg/AgentWatch")
IS_DRY_RUN: bool = os.environ.get("IS_DRY_RUN", "false").lower() == "true"
TODAY: date = (date.fromisoformat(os.environ["SIMULATED_TODAY"]) if os.environ.get("SIMULATED_TODAY")
               else datetime.now(ZoneInfo("America/Edmonton")).date())

BACKLOG_STATUS: str = "Backlog"
DONE_STATUS: str = "Done"
SPRINT_LOG_ISSUE_TITLE: str = "Sprint Log"
CLOSED_CONTENT_STATES: frozenset[str] = frozenset({"CLOSED", "MERGED"})


@dataclass(frozen=True)
class SprintWeek:
    id: str
    title: str
    start_date: date
    duration_days: int

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.duration_days)

    def contains(self, day: date) -> bool:
        return self.start_date <= day < self.end_date


@dataclass(frozen=True)
class ProjectBoard:
    id: str
    title: str
    week_field_id: str
    weeks: list[SprintWeek]
    status_field_id: str
    status_option_ids_by_name: dict[str, str]


@dataclass(frozen=True)
class ProjectItem:
    id: str
    title: str
    status: str | None
    week_id: str | None
    week_title: str | None
    week_start_date: date | None
    issue_number: int | None
    issue_url: str | None
    issue_state: str | None
    assignee_logins: list[str]

    @property
    def is_closed(self) -> bool:
        return self.issue_state in CLOSED_CONTENT_STATES

    @property
    def is_finished(self) -> bool:
        return self.status == DONE_STATUS or self.is_closed

    def summary_line(self) -> str:
        assignees: str = ", ".join(f"@{login}" for login in self.assignee_logins) or "_unassigned_"
        reference: str = f"[#{self.issue_number}]({self.issue_url})" if self.issue_number else "(draft)"
        return f"- {reference} {self.title} ({assignees})"


def github_request(method: str, url: str, body: JsonObject | None = None) -> Any:
    request: urllib.request.Request = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {PROJECT_BOARD_TOKEN}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or "null")


def run_graphql(query: str, **variables: object) -> JsonObject:
    response: JsonObject = github_request("POST", "https://api.github.com/graphql",
                                          {"query": query, "variables": variables})
    if response.get("errors"):
        sys.exit(f"GraphQL error: {response['errors']}")
    data: JsonObject = response["data"]
    return data


def parse_sprint_week(node: JsonObject) -> SprintWeek:
    return SprintWeek(id=node["id"], title=node["title"],
                      start_date=date.fromisoformat(node["startDate"]), duration_days=node["duration"])


def load_project_board() -> ProjectBoard:
    data: JsonObject = run_graphql("""query($owner:String!,$number:Int!){repositoryOwner(login:$owner){
      ... on ProjectV2Owner{projectV2(number:$number){
        id title
        week: field(name:"Week"){... on ProjectV2IterationField{id configuration{
          iterations{id title startDate duration} completedIterations{id title startDate duration}}}}
        status: field(name:"Status"){... on ProjectV2SingleSelectField{id options{id name}}}}}}}""",
                                   owner=PROJECT_OWNER, number=PROJECT_NUMBER)
    project: JsonObject = data["repositoryOwner"]["projectV2"]
    week_configuration: JsonObject = project["week"]["configuration"]
    return ProjectBoard(
        id=project["id"],
        title=project["title"],
        week_field_id=project["week"]["id"],
        weeks=[parse_sprint_week(node) for node in
               week_configuration["iterations"] + week_configuration["completedIterations"]],
        status_field_id=project["status"]["id"],
        status_option_ids_by_name={option["name"]: option["id"] for option in project["status"]["options"]},
    )


def parse_project_item(node: JsonObject) -> ProjectItem:
    content: JsonObject = node["content"] or {}
    week: JsonObject = node["week"] or {}
    return ProjectItem(
        id=node["id"],
        title=content.get("title", "?"),
        status=(node["status"] or {}).get("name"),
        week_id=week.get("iterationId"),
        week_title=week.get("title"),
        week_start_date=date.fromisoformat(week["startDate"]) if week.get("startDate") else None,
        issue_number=content.get("number"),
        issue_url=content.get("url"),
        issue_state=content.get("state"),
        assignee_logins=[assignee["login"] for assignee in content.get("assignees", {}).get("nodes", [])],
    )


def load_project_items(project_id: str) -> list[ProjectItem]:
    project_items: list[ProjectItem] = []
    page_cursor: str | None = None
    while True:
        page: JsonObject = run_graphql("""query($projectId:ID!,$after:String){node(id:$projectId){
          ... on ProjectV2{items(first:100,after:$after){
            pageInfo{hasNextPage endCursor}
            nodes{id isArchived
              status: fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}
              week: fieldValueByName(name:"Week"){... on ProjectV2ItemFieldIterationValue{iterationId title startDate}}
              content{
                ... on Issue{title number url state assignees(first:10){nodes{login}}}
                ... on PullRequest{title number url state assignees(first:10){nodes{login}}}
                ... on DraftIssue{title assignees(first:10){nodes{login}}}}}}}}}""",
                                       projectId=project_id, after=page_cursor)["node"]["items"]
        project_items += [parse_project_item(node) for node in page["nodes"] if not node["isArchived"]]
        if not page["pageInfo"]["hasNextPage"]:
            return project_items
        page_cursor = page["pageInfo"]["endCursor"]


def current_or_next_week(weeks: list[SprintWeek]) -> SprintWeek:
    weeks_containing_today: list[SprintWeek] = [week for week in weeks if week.contains(TODAY)]
    upcoming_weeks: list[SprintWeek] = sorted((week for week in weeks if week.start_date > TODAY),
                                              key=lambda week: week.start_date)
    candidate_weeks: list[SprintWeek] = weeks_containing_today or upcoming_weeks
    if not candidate_weeks:
        sys.exit("No current or future week exists; add weeks to the Week field.")
    return candidate_weeks[0]


def set_item_week(board: ProjectBoard, item_id: str, week: SprintWeek) -> None:
    run_graphql("""mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$weekId:String!){
      updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,
        value:{iterationId:$weekId}}){projectV2Item{id}}}""",
                projectId=board.id, itemId=item_id, fieldId=board.week_field_id, weekId=week.id)


def clear_item_week(board: ProjectBoard, item_id: str) -> None:
    run_graphql("""mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!){
      clearProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId}){projectV2Item{id}}}""",
                projectId=board.id, itemId=item_id, fieldId=board.week_field_id)


def set_item_status(board: ProjectBoard, item_id: str, status_name: str) -> None:
    run_graphql("""mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$optionId:String!){
      updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,
        value:{singleSelectOptionId:$optionId}}){projectV2Item{id}}}""",
                projectId=board.id, itemId=item_id, fieldId=board.status_field_id,
                optionId=board.status_option_ids_by_name[status_name])


def add_issue_to_project(board: ProjectBoard, issue_node_id: str) -> str:
    added_item_id: str = run_graphql("""mutation($projectId:ID!,$contentId:ID!){
      addProjectV2ItemById(input:{projectId:$projectId,contentId:$contentId}){item{id}}}""",
                                     projectId=board.id, contentId=issue_node_id)["addProjectV2ItemById"]["item"]["id"]
    return added_item_id
