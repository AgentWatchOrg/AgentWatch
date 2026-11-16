"""Weekly sprint rollover for the AgentWatch project board.

Runs every Monday from .github/workflows/sprint-rollover.yml:
  1. Moves every card from a past week that is not Done (and whose issue/PR is
     still open) into the current week.
  2. Adds more weeks to the "Week" field if fewer than MIN_FUTURE_WEEKS remain.
  3. Posts a summary comment on the "Sprint Log" issue: finished last week,
     carried over, and who has no cards this week.

Uses only the Python standard library. Configuration comes from env vars:
  GH_TOKEN          token with `project` and `repo` scopes (required)
  OWNER             org or user that owns the project   (default AgentWatchOrg)
  PROJECT_NUMBER    project number                      (default 1)
  REPO              owner/name for the Sprint Log issue (default AgentWatchOrg/AgentWatch)
  DRY_RUN           "true" to print what would change without changing anything
  POST_SUMMARY      "false" to skip the Sprint Log comment
  TODAY             YYYY-MM-DD to simulate another date (testing only)
  MIN_FUTURE_WEEKS  default 4
"""

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["GH_TOKEN"]
OWNER = os.environ.get("OWNER", "AgentWatchOrg")
PROJECT_NUMBER = int(os.environ.get("PROJECT_NUMBER", "1"))
REPO = os.environ.get("REPO", "AgentWatchOrg/AgentWatch")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
POST_SUMMARY = os.environ.get("POST_SUMMARY", "true").lower() == "true"
MIN_FUTURE_WEEKS = int(os.environ.get("MIN_FUTURE_WEEKS", "4"))
TODAY = (date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY")
         else datetime.now(ZoneInfo("America/Edmonton")).date())

STATUS_FIELD, WEEK_FIELD, DONE = "Status", "Week", "Done"
LOG_TITLE = "Sprint Log"


def request(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOKEN}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read() or "null")


def gql(query, **variables):
    data = request("POST", "https://api.github.com/graphql", {"query": query, "variables": variables})
    if data.get("errors"):
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]


def load_project():
    data = gql("""query($owner:String!,$n:Int!){repositoryOwner(login:$owner){... on ProjectV2Owner{projectV2(number:$n){
      id title
      fields(first:50){nodes{
        ... on ProjectV2SingleSelectField{id name}
        ... on ProjectV2IterationField{id name configuration{
          iterations{id title startDate duration} completedIterations{id title startDate duration}}}}}}}}}""",
               owner=OWNER, n=PROJECT_NUMBER)
    project = data["repositoryOwner"]["projectV2"]
    fields = {f["name"]: f for f in project["fields"]["nodes"] if f}
    return project, fields[WEEK_FIELD]


def load_items(project_id):
    items, cursor = [], None
    while True:
        page = gql("""query($p:ID!,$after:String){node(id:$p){... on ProjectV2{items(first:100,after:$after){
          pageInfo{hasNextPage endCursor}
          nodes{id isArchived
            status: fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}
            week: fieldValueByName(name:"Week"){... on ProjectV2ItemFieldIterationValue{iterationId title startDate}}
            content{
              ... on Issue{title number url state assignees(first:10){nodes{login}}}
              ... on PullRequest{title number url state assignees(first:10){nodes{login}}}
              ... on DraftIssue{title assignees(first:10){nodes{login}}}}}}}}}""",
                   p=project_id, after=cursor)["node"]["items"]
        items += [i for i in page["nodes"] if not i["isArchived"]]
        if not page["pageInfo"]["hasNextPage"]:
            return items
        cursor = page["pageInfo"]["endCursor"]


def start(it):
    return date.fromisoformat(it["startDate"])


def is_finished(item):
    """Done on the board, or the underlying issue/PR is closed or merged."""
    if (item["status"] or {}).get("name") == DONE:
        return True
    return (item["content"] or {}).get("state") in ("CLOSED", "MERGED")


def label(item):
    c = item["content"] or {}
    who = ", ".join("@" + a["login"] for a in c.get("assignees", {}).get("nodes", [])) or "_unassigned_"
    ref = f"[#{c['number']}]({c['url']})" if c.get("number") else "(draft)"
    return f"- {ref} {c.get('title', '?')} ({who})"


def top_up_weeks(field, weeks):
    future = [w for w in weeks if start(w) > TODAY]
    if len(future) >= MIN_FUTURE_WEEKS:
        return []
    new, last = [], max(weeks, key=start)
    next_start = start(last) + timedelta(days=last["duration"])
    for n in range(len(weeks) + 1, len(weeks) + 1 + MIN_FUTURE_WEEKS - len(future)):
        new.append({"startDate": next_start.isoformat(), "duration": 7,
                    "title": f"Week {n} ({next_start.strftime('%b')} {next_start.day})"})
        next_start += timedelta(days=7)
    if not DRY_RUN:
        # Existing weeks are resent with their ids so cards stay attached to them.
        keep = [{k: w[k] for k in ("id", "startDate", "duration", "title")} for w in sorted(weeks, key=start)]
        gql("""mutation($f:ID!,$c:ProjectV2IterationFieldConfigurationInput!){
          updateProjectV2Field(input:{fieldId:$f,iterationConfiguration:$c}){projectV2Field{... on ProjectV2IterationField{id}}}}""",
            f=field["id"], c={"startDate": keep[0]["startDate"], "duration": 7, "iterations": keep + new})
    return new


def post_summary(target, previous, done, moved, current_items):
    owner, name = REPO.split("/")
    people = {c["login"] for c in request("GET", f"https://api.github.com/repos/{REPO}/collaborators?per_page=100")
              if c["type"] == "User"}
    busy = {a["login"] for i in current_items for a in (i["content"] or {}).get("assignees", {}).get("nodes", [])}
    idle = sorted(people - busy, key=str.lower)

    lines = [f"## {target['title']} has started", ""]
    if previous:
        lines += [f"**Finished in {previous['title']}** ({len(done)})"] + [label(i) for i in done] + ["" if done else "- nothing marked Done", ""]
    lines += [f"**Carried over into {target['title']}** ({len(moved)})"] + ([label(i) for i in moved] or ["- nothing to carry over"]) + [""]
    lines += ["**No cards this week:** " + (", ".join("@" + p for p in idle) if idle else "everyone has work 🎉")]
    body = "\n".join(lines)

    if DRY_RUN:
        print("\n--- summary (not posted, dry run) ---\n" + body)
        return
    found = gql("""query($q:String!){search(type:ISSUE,query:$q,first:5){nodes{... on Issue{number title}}}}""",
                q=f'repo:{REPO} is:issue in:title "{LOG_TITLE}"')["search"]["nodes"]
    log = next((i for i in found if i.get("title") == LOG_TITLE), None)
    if log is None:
        log = request("POST", f"https://api.github.com/repos/{REPO}/issues", {
            "title": LOG_TITLE,
            "body": "Automated weekly sprint summaries, posted every Monday by `.github/workflows/sprint-rollover.yml`. "
                    "Pin this issue so it is easy to find."})
    request("POST", f"https://api.github.com/repos/{REPO}/issues/{log['number']}/comments", {"body": body})
    print(f"Posted summary on {REPO}#{log['number']}")


def main():
    project, field = load_project()
    weeks = field["configuration"]["iterations"] + field["configuration"]["completedIterations"]
    print(f"{project['title']}: today is {TODAY}{' (dry run)' if DRY_RUN else ''}")

    # The week containing today, or during a break, the next week to start.
    current = [w for w in weeks if start(w) <= TODAY < start(w) + timedelta(days=w["duration"])]
    upcoming = sorted((w for w in weeks if start(w) > TODAY), key=start)
    target = (current or upcoming or [None])[0]
    if target is None:
        sys.exit("No current or future week exists; add weeks to the Week field.")
    past = sorted((w for w in weeks if start(w) < start(target)), key=start)
    previous = past[-1] if past else None
    print(f"Target week: {target['title']}")

    items = load_items(project["id"])
    moved = [i for i in items if i["week"] and start(i["week"]) < start(target) and not is_finished(i)]
    for item in moved:
        print(f"Move {label(item)[2:]}: {item['week']['title']} -> {target['title']}")
        if not DRY_RUN:
            gql("""mutation($p:ID!,$i:ID!,$f:ID!,$w:String!){updateProjectV2ItemFieldValue(input:{
              projectId:$p,itemId:$i,fieldId:$f,value:{iterationId:$w}}){projectV2Item{id}}}""",
                p=project["id"], i=item["id"], f=field["id"], w=target["id"])
    print(f"Carried over {len(moved)} card(s)")

    for w in top_up_weeks(field, weeks):
        print(f"Added {w['title']}")

    if POST_SUMMARY:
        done = [i for i in items if previous and i["week"] and i["week"]["iterationId"] == previous["id"] and is_finished(i)]
        current_items = [i for i in items if i["week"] and i["week"]["iterationId"] == target["id"]] + moved
        post_summary(target, previous, done, moved, current_items)


if __name__ == "__main__":
    main()
