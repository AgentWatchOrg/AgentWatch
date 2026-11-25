#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIRECTORY="/opt/sensor-spike"
RESULTS_DIRECTORY="/var/tmp/sensor-spike-results"
SAMPLES_DIRECTORY="$RESULTS_DIRECTORY/samples"
SUMMARY_FILE="$RESULTS_DIRECTORY/summary.txt"
AVAILABILITY_FILE="$RESULTS_DIRECTORY/availability.env"
MANAGE_SENSOR="$INSTALL_DIRECTORY/manage_sensor.sh"
AUDIT_LOG_FILE="/var/log/audit/audit.log"
AGENT_USER="agentuser"
FILE_DIRECTORY="/tmp/spike-files"
NETWORK_PORT_BASE=41000
EXEC_COUNT="${EXEC_COUNT:-35}"
FILE_COUNT="${FILE_COUNT:-35}"
NETWORK_COUNT="${NETWORK_COUNT:-30}"
STRESS_ITERATIONS="${STRESS_ITERATIONS:-2000}"
TETRAGON_EVENTS_FILE="$RESULTS_DIRECTORY/tetragon-capture-events.json"
TETRAGON_AVAILABLE="no"
AUDITD_AVAILABLE="no"

if [[ -f "$AVAILABILITY_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$AVAILABILITY_FILE"
fi

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
  fi
}

log_summary() {
  echo "$1" | tee -a "$SUMMARY_FILE"
}

prepare_workload_files() {
  rm -rf "$FILE_DIRECTORY"
  mkdir -p "$FILE_DIRECTORY"
  local index
  for index in $(seq 1 "$FILE_COUNT"); do
    echo "spike" > "$FILE_DIRECTORY/spike-file-$index.txt"
  done
  chown -R "$AGENT_USER" "$FILE_DIRECTORY"
}

run_workload_as_agent() {
  sudo -u "$AGENT_USER" env \
    EXEC_COUNT="$EXEC_COUNT" FILE_COUNT="$FILE_COUNT" NETWORK_COUNT="$NETWORK_COUNT" STRESS_ITERATIONS="$STRESS_ITERATIONS" \
    bash "$INSTALL_DIRECTORY/run_workload.sh" "$1"
}

report_capture() {
  local activity="$1" pattern="$2" events_file="$3" first_number="$4" last_number="$5" expected_count="$6"
  local seen_numbers missing_numbers
  seen_numbers="$(grep -oE "$pattern" "$events_file" | grep -oE '[0-9]+$' | sort -un || true)"
  missing_numbers="$(comm -23 <(seq "$first_number" "$last_number" | sort) <(printf '%s\n' "$seen_numbers" | sort) | sort -n | tr '\n' ' ')"
  log_summary "  $activity captured: $(printf '%s\n' "$seen_numbers" | grep -c . || true) / $expected_count"
  log_summary "  $activity missing: ${missing_numbers:-none}"
}

sensor_cpu_ticks() {
  local sensor_pid
  sensor_pid="$(pgrep -x "$1" | head -1 || true)"
  if [[ -n "$sensor_pid" ]]; then
    awk '{print $14 + $15}' "/proc/$sensor_pid/stat"
  else
    echo 0
  fi
}

sensor_memory_kilobytes() {
  local sensor_pid
  sensor_pid="$(pgrep -x "$1" | head -1 || true)"
  if [[ -n "$sensor_pid" ]]; then
    ps -o rss= -p "$sensor_pid" | tr -d ' '
  else
    echo 0
  fi
}

run_timed_stress() {
  local sensor_name="$1" start_time end_time ticks_before ticks_after ticks_per_second
  ticks_per_second="$(getconf CLK_TCK)"
  ticks_before="$(sensor_cpu_ticks "$sensor_name")"
  start_time="$(date +%s.%N)"
  run_workload_as_agent stress
  end_time="$(date +%s.%N)"
  ticks_after="$(sensor_cpu_ticks "$sensor_name")"
  log_summary "  stress wall seconds ($STRESS_ITERATIONS iterations): $(awk -v s="$start_time" -v e="$end_time" 'BEGIN {printf "%.2f", e - s}')"
  log_summary "  sensor cpu seconds during stress: $(awk -v b="$ticks_before" -v a="$ticks_after" -v t="$ticks_per_second" 'BEGIN {printf "%.2f", (a - b) / t}')"
  log_summary "  sensor resident memory kB: $(sensor_memory_kilobytes "$sensor_name")"
}

run_baseline_phase() {
  log_summary "== baseline (no sensor) =="
  "$MANAGE_SENSOR" disable all > /dev/null
  run_timed_stress none
}

run_tetragon_phase() {
  local stream_pid
  if [[ "$TETRAGON_AVAILABLE" != "yes" ]]; then
    log_summary "== tetragon == SKIPPED (unavailable on this host; see host-info.txt)"
    return
  fi
  log_summary "== tetragon =="
  "$MANAGE_SENSOR" disable all > /dev/null
  "$MANAGE_SENSOR" enable tetragon > /dev/null
  tetra getevents -o json > "$TETRAGON_EVENTS_FILE" &
  stream_pid=$!
  sleep 2
  run_workload_as_agent capture
  sleep 3
  kill "$stream_pid" || true
  report_capture exec 'spike-exec-[0-9]+' "$TETRAGON_EVENTS_FILE" 1 "$EXEC_COUNT" "$EXEC_COUNT"
  report_capture file 'spike-file-[0-9]+' "$TETRAGON_EVENTS_FILE" 1 "$FILE_COUNT" "$FILE_COUNT"
  report_capture network '"dport": ?41[0-9]{3}' "$TETRAGON_EVENTS_FILE" "$((NETWORK_PORT_BASE + 1))" "$((NETWORK_PORT_BASE + NETWORK_COUNT))" "$NETWORK_COUNT"
  grep -m3 'spike-exec' "$TETRAGON_EVENTS_FILE" > "$SAMPLES_DIRECTORY/tetragon-exec.json" || true
  grep -m3 'spike-file' "$TETRAGON_EVENTS_FILE" > "$SAMPLES_DIRECTORY/tetragon-file.json" || true
  grep -m3 -E '"dport": ?41[0-9]{3}' "$TETRAGON_EVENTS_FILE" > "$SAMPLES_DIRECTORY/tetragon-network.json" || true
  run_timed_stress tetragon
}

run_auditd_phase() {
  if [[ "$AUDITD_AVAILABLE" != "yes" ]]; then
    log_summary "== auditd == SKIPPED (unavailable on this host; see host-info.txt)"
    return
  fi
  log_summary "== auditd =="
  "$MANAGE_SENSOR" disable all > /dev/null
  if [[ -f "$AUDIT_LOG_FILE" ]]; then
    : > "$AUDIT_LOG_FILE"
  fi
  "$MANAGE_SENSOR" enable auditd > /dev/null
  run_workload_as_agent capture
  sleep 3
  ausearch -i -k agent_exec > "$RESULTS_DIRECTORY/auditd-exec.txt" 2> /dev/null || true
  ausearch -i -k agent_file > "$RESULTS_DIRECTORY/auditd-file.txt" 2> /dev/null || true
  ausearch -i -k agent_net > "$RESULTS_DIRECTORY/auditd-network.txt" 2> /dev/null || true
  report_capture exec 'spike-exec-[0-9]+' "$RESULTS_DIRECTORY/auditd-exec.txt" 1 "$EXEC_COUNT" "$EXEC_COUNT"
  report_capture file 'spike-file-[0-9]+' "$RESULTS_DIRECTORY/auditd-file.txt" 1 "$FILE_COUNT" "$FILE_COUNT"
  report_capture network 'lport=41[0-9]{3}' "$RESULTS_DIRECTORY/auditd-network.txt" "$((NETWORK_PORT_BASE + 1))" "$((NETWORK_PORT_BASE + NETWORK_COUNT))" "$NETWORK_COUNT"
  head -30 "$RESULTS_DIRECTORY/auditd-exec.txt" > "$SAMPLES_DIRECTORY/auditd-exec.txt"
  head -30 "$RESULTS_DIRECTORY/auditd-file.txt" > "$SAMPLES_DIRECTORY/auditd-file.txt"
  head -30 "$RESULTS_DIRECTORY/auditd-network.txt" > "$SAMPLES_DIRECTORY/auditd-network.txt"
  run_timed_stress auditd
  "$MANAGE_SENSOR" disable auditd > /dev/null
}

require_root
mkdir -p "$SAMPLES_DIRECTORY"
: > "$SUMMARY_FILE"
prepare_workload_files
run_baseline_phase
run_tetragon_phase
run_auditd_phase
"$INSTALL_DIRECTORY/report_fields.sh"
"$INSTALL_DIRECTORY/sanitize_samples.sh"
log_summary "Done. Review $SUMMARY_FILE and $RESULTS_DIRECTORY/fields-report.txt, then run: sudo $INSTALL_DIRECTORY/archive_results.sh"
