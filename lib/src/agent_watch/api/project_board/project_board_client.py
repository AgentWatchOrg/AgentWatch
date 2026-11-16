from datetime import date

from agent_watch.api.github_client import GitHubClient, JsonObject
from agent_watch.api.project_board.models import NewSprintWeek, OpenIssue, ProjectBoard, ProjectItem, SprintWeek

PROJECT_BOARD_QUERY: str = """query($owner:String!,$number:Int!){repositoryOwner(login:$owner){
  ... on ProjectV2Owner{projectV2(number:$number){
    id title
    week: field(name:"Week"){... on ProjectV2IterationField{id configuration{
      iterations{id title startDate duration} completedIterations{id title startDate duration}}}}
    status: field(name:"Status"){... on ProjectV2SingleSelectField{id options{id name}}}}}}}"""

PROJECT_ITEMS_QUERY: str = """query($projectId:ID!,$after:String){node(id:$projectId){
  ... on ProjectV2{items(first:100,after:$after){
    pageInfo{hasNextPage endCursor}
    nodes{id isArchived
      status: fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}
      week: fieldValueByName(name:"Week"){... on ProjectV2ItemFieldIterationValue{iterationId title startDate}}
      content{
        ... on Issue{title number url state assignees(first:10){nodes{login}}}
        ... on PullRequest{title number url state assignees(first:10){nodes{login}}}
        ... on DraftIssue{title assignees(first:10){nodes{login}}}}}}}}}"""

OPEN_ISSUES_QUERY: str = """query($owner:String!,$name:String!,$after:String){
  repository(owner:$owner,name:$name){issues(states:OPEN,first:100,after:$after){
    pageInfo{hasNextPage endCursor} nodes{id number title}}}}"""

SET_FIELD_VALUE_MUTATION: str = """mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$value:ProjectV2FieldValue!){
  updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,value:$value}){
    projectV2Item{id}}}"""

CLEAR_FIELD_VALUE_MUTATION: str = """mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!){
  clearProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId}){projectV2Item{id}}}"""

ADD_ITEM_MUTATION: str = """mutation($projectId:ID!,$contentId:ID!){
  addProjectV2ItemById(input:{projectId:$projectId,contentId:$contentId}){item{id}}}"""

REPLACE_WEEKS_MUTATION: str = """mutation($fieldId:ID!,$configuration:ProjectV2IterationFieldConfigurationInput!){
  updateProjectV2Field(input:{fieldId:$fieldId,iterationConfiguration:$configuration}){
    projectV2Field{... on ProjectV2IterationField{id}}}}"""

FIND_ISSUE_QUERY: str = """query($searchQuery:String!){search(type:ISSUE,query:$searchQuery,first:5){
  nodes{... on Issue{number title}}}}"""


class ProjectBoardClient:
    def __init__(self, github_client: GitHubClient, project_owner: str, project_number: int, repository: str) -> None:
        self.github_client: GitHubClient = github_client
        self.project_owner: str = project_owner
        self.project_number: int = project_number
        self.repository: str = repository

    def load_board(self) -> ProjectBoard:
        project: JsonObject = self.github_client.run_graphql(
            PROJECT_BOARD_QUERY, owner=self.project_owner, number=self.project_number)["repositoryOwner"]["projectV2"]
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

    def load_items(self, board: ProjectBoard) -> list[ProjectItem]:
        item_nodes: list[JsonObject] = self.github_client.run_paginated_graphql(
            PROJECT_ITEMS_QUERY, ["node", "items"], projectId=board.id)
        return [parse_project_item(node) for node in item_nodes if not node["isArchived"]]

    def load_open_issues(self) -> list[OpenIssue]:
        repository_owner: str
        repository_name: str
        repository_owner, repository_name = self.repository.split("/")
        issue_nodes: list[JsonObject] = self.github_client.run_paginated_graphql(
            OPEN_ISSUES_QUERY, ["repository", "issues"], owner=repository_owner, name=repository_name)
        return [OpenIssue(id=node["id"], number=node["number"], title=node["title"]) for node in issue_nodes]

    def set_item_week(self, board: ProjectBoard, item_id: str, week: SprintWeek) -> None:
        self.github_client.run_graphql(SET_FIELD_VALUE_MUTATION, projectId=board.id, itemId=item_id,
                                       fieldId=board.week_field_id, value={"iterationId": week.id})

    def clear_item_week(self, board: ProjectBoard, item_id: str) -> None:
        self.github_client.run_graphql(CLEAR_FIELD_VALUE_MUTATION, projectId=board.id, itemId=item_id,
                                       fieldId=board.week_field_id)

    def set_item_status(self, board: ProjectBoard, item_id: str, status_name: str) -> None:
        self.github_client.run_graphql(SET_FIELD_VALUE_MUTATION, projectId=board.id, itemId=item_id,
                                       fieldId=board.status_field_id,
                                       value={"singleSelectOptionId": board.status_option_ids_by_name[status_name]})

    def add_issue(self, board: ProjectBoard, issue_id: str) -> str:
        added_item_id: str = self.github_client.run_graphql(
            ADD_ITEM_MUTATION, projectId=board.id, contentId=issue_id)["addProjectV2ItemById"]["item"]["id"]
        return added_item_id

    def add_weeks(self, board: ProjectBoard, new_weeks: list[NewSprintWeek], default_week_length_days: int) -> None:
        # The API replaces the whole week list; resending existing weeks with their ids keeps cards attached.
        existing_week_inputs: list[JsonObject] = [
            {"id": week.id, "title": week.title, "startDate": week.start_date.isoformat(), "duration": week.duration_days}
            for week in sorted(board.weeks, key=lambda week: week.start_date)]
        new_week_inputs: list[JsonObject] = [
            {"title": week.title, "startDate": week.start_date.isoformat(), "duration": week.duration_days}
            for week in new_weeks]
        self.github_client.run_graphql(REPLACE_WEEKS_MUTATION, fieldId=board.week_field_id, configuration={
            "startDate": existing_week_inputs[0]["startDate"], "duration": default_week_length_days,
            "iterations": existing_week_inputs + new_week_inputs})

    def repository_collaborator_logins(self) -> set[str]:
        collaborators: list[JsonObject] = self.github_client.request(
            "GET", f"/repos/{self.repository}/collaborators?per_page=100")
        return {collaborator["login"] for collaborator in collaborators if collaborator["type"] == "User"}

    def find_or_create_issue(self, title: str, body: str) -> int:
        search_results: list[JsonObject] = self.github_client.run_graphql(
            FIND_ISSUE_QUERY, searchQuery=f'repo:{self.repository} is:issue in:title "{title}"')["search"]["nodes"]
        for issue in search_results:
            if issue.get("title") == title:
                existing_issue_number: int = issue["number"]
                return existing_issue_number
        created_issue: JsonObject = self.github_client.request(
            "POST", f"/repos/{self.repository}/issues", {"title": title, "body": body})
        created_issue_number: int = created_issue["number"]
        return created_issue_number

    def comment_on_issue(self, issue_number: int, body: str) -> None:
        self.github_client.request("POST", f"/repos/{self.repository}/issues/{issue_number}/comments", {"body": body})


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
