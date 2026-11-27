#!/usr/bin/env bash
set -euo pipefail

WORKLOAD_MODE="${1:?usage: run_workload.sh capture|stress}"
EXEC_COUNT="${EXEC_COUNT:-35}"
FILE_COUNT="${FILE_COUNT:-35}"
NETWORK_COUNT="${NETWORK_COUNT:-30}"
STRESS_ITERATIONS="${STRESS_ITERATIONS:-2000}"
FILE_DIRECTORY="/tmp/spike-files"
NETWORK_PORT_BASE=41000

run_capture_workload() {
  local index
  for index in $(seq 1 "$EXEC_COUNT"); do
    /bin/echo "spike-exec-$index" > /dev/null
  done
  for index in $(seq 1 "$FILE_COUNT"); do
    : < "$FILE_DIRECTORY/spike-file-$index.txt"
  done
  for index in $(seq 1 "$NETWORK_COUNT"); do
    (exec 3<> "/dev/tcp/127.0.0.1/$((NETWORK_PORT_BASE + index))") 2> /dev/null || true
  done
}

run_stress_workload() {
  local index
  for index in $(seq 1 "$STRESS_ITERATIONS"); do
    /bin/true
    : < "$FILE_DIRECTORY/spike-file-1.txt"
  done
}

case "$WORKLOAD_MODE" in
  capture) run_capture_workload ;;
  stress) run_stress_workload ;;
  *) echo "Unknown mode: $WORKLOAD_MODE" >&2; exit 1 ;;
esac
