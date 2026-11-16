#!/usr/bin/env bash
# Usage: create.sh "<title>" <p0|p1|p2|p3|p4>   (issue body on stdin)
# Creates the issue, adds it to the AgentWatch Board as Backlog with its priority, prints the URL.
set -euo pipefail

title=$1
prio=$(tr '[:upper:]' '[:lower:]' <<<"$2")
[[ $prio =~ ^p[0-4]$ ]] || { echo "priority must be p0-p4" >&2; exit 1; }

repo=AgentWatchOrg/AgentWatch
owner=AgentWatchOrg
project=1

url=$(gh issue create -R "$repo" --title "$title" --label "$prio" --body-file -)
item=$(gh project item-add "$project" --owner "$owner" --url "$url" --format json --jq .id)
pid=$(gh project view "$project" --owner "$owner" --format json --jq .id)
fields=$(gh project field-list "$project" --owner "$owner" --format json)

set_field() {
  local field=$1 option=$2
  gh project item-edit --id "$item" --project-id "$pid" \
    --field-id "$(jq -r --arg f "$field" '.fields[] | select(.name == $f).id' <<<"$fields")" \
    --single-select-option-id "$(jq -r --arg f "$field" --arg o "$option" \
      '.fields[] | select(.name == $f).options[] | select(.name == $o).id' <<<"$fields")" >/dev/null
}
set_field Status Backlog
set_field Priority "$(tr '[:lower:]' '[:upper:]' <<<"$prio")"

echo "$url"
