import json
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

JsonObject = dict[str, Any]

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

    def current_or_next_week(self, today: date) -> SprintWeek:
        weeks_containing_today: list[SprintWeek] = [week for week in self.weeks if week.contains(today)]
        upcoming_weeks: list[SprintWeek] = sorted((week for week in self.weeks if week.start_date > today),
                                                  key=lambda week: week.start_date)
        candidate_weeks: list[SprintWeek] = weeks_containing_today or upcoming_weeks
        if not candidate_weeks:
            sys.exit("No current or future week exists; add weeks to the Week field.")
        return candidate_weeks[0]


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


def parse_sprint_week(node: JsonObject) -> SprintWeek:
    return SprintWeek(id=node["id"], title=node["title"],
                      start_date=date.fromisoformat(node["startDate"]), duration_days=node["duration"])


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


class ProjectBoardClient:
    def __init__(self, github_token: str, project_owner: str, project_number: int, repository: str) -> None:
        self.github_token: str = github_token
        self.project_owner: str = project_owner
        self.project_number: int = project_number
        self.repository: str = repository

    def github_request(self, method: str, url: str, body: JsonObject | None = None) -> Any:
        request: urllib.request.Request = urllib.request.Request(
            url, method=method, data=json.dumps(body).encode() if body else None,
            headers={"Authorization": f"Bearer {self.github_token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read() or "null")

    def run_graphql(self, query: str, **variables: object) -> JsonObject:
        response: JsonObject = self.github_request("POST", "https://api.github.com/graphql",
                                                   {"query": query, "variables": variables})
        if response.get("errors"):
            sys.exit(f"GraphQL error: {response['errors']}")
        data: JsonObject = response["data"]
        return data

    def load_project_board(self) -> ProjectBoard:
        data: JsonObject = self.run_graphql("""query($owner:String!,$number:Int!){repositoryOwner(login:$owner){
          ... on ProjectV2Owner{projectV2(number:$number){
            id title
            week: field(name:"Week"){... on ProjectV2IterationField{id configuration{
              iterations{id title startDate duration} completedIterations{id title startDate duration}}}}
            status: field(name:"Status"){... on ProjectV2SingleSelectField{id options{id name}}}}}}}""",
                                            owner=self.project_owner, number=self.project_number)
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

    def load_project_items(self, board: ProjectBoard) -> list[ProjectItem]:
        project_items: list[ProjectItem] = []
        page_cursor: str | None = None
        while True:
            page: JsonObject = self.run_graphql("""query($projectId:ID!,$after:String){node(id:$projectId){
              ... on ProjectV2{items(first:100,after:$after){
                pageInfo{hasNextPage endCursor}
                nodes{id isArchived
                  status: fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}
                  week: fieldValueByName(name:"Week"){... on ProjectV2ItemFieldIterationValue{iterationId title startDate}}
                  content{
                    ... on Issue{title number url state assignees(first:10){nodes{login}}}
                    ... on PullRequest{title number url state assignees(first:10){nodes{login}}}
                    ... on DraftIssue{title assignees(first:10){nodes{login}}}}}}}}}""",
                                                projectId=board.id, after=page_cursor)["node"]["items"]
            project_items += [parse_project_item(node) for node in page["nodes"] if not node["isArchived"]]
            if not page["pageInfo"]["hasNextPage"]:
                return project_items
            page_cursor = page["pageInfo"]["endCursor"]

    def load_open_issues(self) -> list[JsonObject]:
        repository_owner: str
        repository_name: str
        repository_owner, repository_name = self.repository.split("/")
        open_issues: list[JsonObject] = []
        page_cursor: str | None = None
        while True:
            page: JsonObject = self.run_graphql("""query($owner:String!,$name:String!,$after:String){
              repository(owner:$owner,name:$name){issues(states:OPEN,first:100,after:$after){
                pageInfo{hasNextPage endCursor} nodes{id number title}}}}""",
                                                owner=repository_owner, name=repository_name,
                                                after=page_cursor)["repository"]["issues"]
            open_issues += page["nodes"]
            if not page["pageInfo"]["hasNextPage"]:
                return open_issues
            page_cursor = page["pageInfo"]["endCursor"]

    def set_item_week(self, board: ProjectBoard, item_id: str, week: SprintWeek) -> None:
        self.run_graphql("""mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$weekId:String!){
          updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,
            value:{iterationId:$weekId}}){projectV2Item{id}}}""",
                         projectId=board.id, itemId=item_id, fieldId=board.week_field_id, weekId=week.id)

    def clear_item_week(self, board: ProjectBoard, item_id: str) -> None:
        self.run_graphql("""mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!){
          clearProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId}){
            projectV2Item{id}}}""",
                         projectId=board.id, itemId=item_id, fieldId=board.week_field_id)

    def set_item_status(self, board: ProjectBoard, item_id: str, status_name: str) -> None:
        self.run_graphql("""mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$optionId:String!){
          updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,
            value:{singleSelectOptionId:$optionId}}){projectV2Item{id}}}""",
                         projectId=board.id, itemId=item_id, fieldId=board.status_field_id,
                         optionId=board.status_option_ids_by_name[status_name])

    def add_issue_to_project(self, board: ProjectBoard, issue_node_id: str) -> str:
        added_item_id: str = self.run_graphql("""mutation($projectId:ID!,$contentId:ID!){
          addProjectV2ItemById(input:{projectId:$projectId,contentId:$contentId}){item{id}}}""",
                                              projectId=board.id,
                                              contentId=issue_node_id)["addProjectV2ItemById"]["item"]["id"]
        return added_item_id

    def replace_weeks(self, board: ProjectBoard, weeks: list[JsonObject], default_week_length_days: int) -> None:
        self.run_graphql("""mutation($fieldId:ID!,$configuration:ProjectV2IterationFieldConfigurationInput!){
          updateProjectV2Field(input:{fieldId:$fieldId,iterationConfiguration:$configuration}){
            projectV2Field{... on ProjectV2IterationField{id}}}}""",
                         fieldId=board.week_field_id,
                         configuration={"startDate": weeks[0]["startDate"], "duration": default_week_length_days,
                                        "iterations": weeks})

    def repository_collaborator_logins(self) -> set[str]:
        collaborators: list[JsonObject] = self.github_request(
            "GET", f"https://api.github.com/repos/{self.repository}/collaborators?per_page=100")
        return {collaborator["login"] for collaborator in collaborators if collaborator["type"] == "User"}

    def find_or_create_issue_number(self, title: str, body: str) -> int:
        search_results: list[JsonObject] = self.run_graphql(
            """query($searchQuery:String!){search(type:ISSUE,query:$searchQuery,first:5){
              nodes{... on Issue{number title}}}}""",
            searchQuery=f'repo:{self.repository} is:issue in:title "{title}"')["search"]["nodes"]
        for issue in search_results:
            if issue.get("title") == title:
                existing_issue_number: int = issue["number"]
                return existing_issue_number
        created_issue: JsonObject = self.github_request(
            "POST", f"https://api.github.com/repos/{self.repository}/issues", {"title": title, "body": body})
        created_issue_number: int = created_issue["number"]
        return created_issue_number

    def comment_on_issue(self, issue_number: int, body: str) -> None:
        self.github_request("POST", f"https://api.github.com/repos/{self.repository}/issues/{issue_number}/comments",
                            {"body": body})
