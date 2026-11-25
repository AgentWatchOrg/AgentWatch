#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIRECTORY="/var/tmp/sensor-spike-results"
SAMPLES_DIRECTORY="$RESULTS_DIRECTORY/samples"
FIELDS_REPORT_FILE="$RESULTS_DIRECTORY/fields-report.txt"

list_tetragon_field_paths() {
  jq -r 'paths(scalars) | map(if type == "number" then "[]" else . end) | join(".")' "$1" | sed 's/\.\[\]/[]/g' | sort -u
}

print_checklist_item() {
  local label="$1" pattern="$2" paths_file="$3"
  if grep -qE "$pattern" "$paths_file"; then
    echo "  [x] $label"
  else
    echo "  [ ] $label"
  fi
}

report_tetragon_sample() {
  local sample_file="$1" activity_label="$2" paths_file
  paths_file="$(mktemp)"
  list_tetragon_field_paths "$sample_file" > "$paths_file"

  echo "## Tetragon $activity_label ($(basename "$sample_file"))"
  echo "All field paths:"
  sed 's/^/  /' "$paths_file"
  echo "Process identity:"
  print_checklist_item "exec_id" '\.process\.exec_id$' "$paths_file"
  print_checklist_item "pid" '\.process\.pid$' "$paths_file"
  print_checklist_item "uid" '\.process\.uid$' "$paths_file"
  print_checklist_item "auid" '\.process\.auid$' "$paths_file"
  print_checklist_item "binary" '\.process\.binary$' "$paths_file"
  print_checklist_item "start_time" '\.process\.start_time$' "$paths_file"
  echo "Lineage:"
  print_checklist_item "process.parent_exec_id" '\.process\.parent_exec_id$' "$paths_file"
  print_checklist_item "parent.exec_id" '\.parent\.exec_id$' "$paths_file"
  print_checklist_item "parent.pid" '\.parent\.pid$' "$paths_file"
  print_checklist_item "parent.binary" '\.parent\.binary$' "$paths_file"
  echo "Activity details:"
  print_checklist_item "arguments" '\.process\.arguments$' "$paths_file"
  print_checklist_item "cwd" '\.process\.cwd$' "$paths_file"
  print_checklist_item "function_name" 'function_name$' "$paths_file"
  print_checklist_item "file path" 'file_arg\.path$' "$paths_file"
  print_checklist_item "socket destination address" 'sock_arg\.daddr$' "$paths_file"
  print_checklist_item "socket destination port" 'sock_arg\.dport$' "$paths_file"
  echo
  rm -f "$paths_file"
}

report_auditd_sample() {
  local sample_file="$1" activity_label="$2"
  echo "## auditd $activity_label ($(basename "$sample_file"))"
  echo "Record types:"
  grep -oE 'type=[A-Z_]+' "$sample_file" | sort | uniq -c | sed 's/^/  /' || true
  echo "Field names seen:"
  echo "  $(grep -oE '[a-z0-9_]+=' "$sample_file" | sort -u | tr '\n' ' ')"
  echo "Process identity:"
  print_checklist_item "pid" ' pid=' "$sample_file"
  print_checklist_item "uid" ' uid=' "$sample_file"
  print_checklist_item "auid" ' auid=' "$sample_file"
  print_checklist_item "exe" ' exe=' "$sample_file"
  print_checklist_item "comm" ' comm=' "$sample_file"
  echo "Lineage:"
  print_checklist_item "ppid" ' ppid=' "$sample_file"
  print_checklist_item "unique exec id (expected absent)" 'exec_id' "$sample_file"
  echo "Activity details:"
  print_checklist_item "exec arguments (a0=, a1=)" ' a1=' "$sample_file"
  print_checklist_item "file path (name=)" ' name=' "$sample_file"
  print_checklist_item "socket address (laddr=)" 'laddr=' "$sample_file"
  print_checklist_item "socket port (lport=)" 'lport=' "$sample_file"
  echo
}

{
  echo "# Field inventory generated $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  for tetragon_activity in exec file network; do
    if [[ -s "$SAMPLES_DIRECTORY/tetragon-$tetragon_activity.json" ]]; then
      report_tetragon_sample "$SAMPLES_DIRECTORY/tetragon-$tetragon_activity.json" "$tetragon_activity"
    else
      echo "## Tetragon $tetragon_activity: no sample captured"
      echo
    fi
  done
  for auditd_activity in exec file network; do
    if [[ -s "$SAMPLES_DIRECTORY/auditd-$auditd_activity.txt" ]]; then
      report_auditd_sample "$SAMPLES_DIRECTORY/auditd-$auditd_activity.txt" "$auditd_activity"
    else
      echo "## auditd $auditd_activity: no sample captured"
      echo
    fi
  done
} > "$FIELDS_REPORT_FILE"

echo "Field inventory written to $FIELDS_REPORT_FILE"
