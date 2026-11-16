#!/usr/bin/env bash
set -euo pipefail

issue_title=$1
priority=$(tr '[:upper:]' '[:lower:]' <<<"$2")
type_and_area_labels=${3:?"labels required, e.g. feature,backend"}
[[ $priority =~ ^p[0-4]$ ]] || { echo "priority must be p0-p4" >&2; exit 1; }

repository=AgentWatchOrg/AgentWatch
project_owner=AgentWatchOrg
project_number=1

issue_url=$(gh issue create -R "$repository" --title "$issue_title" --label "$priority,$type_and_area_labels" --body-file -)
project_item_id=$(gh project item-add "$project_number" --owner "$project_owner" --url "$issue_url" --format json --jq .id)
project_node_id=$(gh project view "$project_number" --owner "$project_owner" --format json --jq .id)
project_fields_json=$(gh project field-list "$project_number" --owner "$project_owner" --format json)

set_single_select_field() {
  local field_name=$1 option_name=$2
  gh project item-edit --id "$project_item_id" --project-id "$project_node_id" \
    --field-id "$(jq -r --arg field "$field_name" '.fields[] | select(.name == $field).id' <<<"$project_fields_json")" \
    --single-select-option-id "$(jq -r --arg field "$field_name" --arg option "$option_name" \
      '.fields[] | select(.name == $field).options[] | select(.name == $option).id' <<<"$project_fields_json")" >/dev/null
}
set_single_select_field Status Backlog
set_single_select_field Priority "$(tr '[:lower:]' '[:upper:]' <<<"$priority")"

echo "$issue_url"
