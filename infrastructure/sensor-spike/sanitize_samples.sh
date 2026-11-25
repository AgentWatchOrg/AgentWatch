#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIRECTORY="/var/tmp/sensor-spike-results"
SAMPLES_DIRECTORY="$RESULTS_DIRECTORY/samples"
SANITIZED_DIRECTORY="$RESULTS_DIRECTORY/samples-sanitized"
HOST_NAME="$(hostname)"

mkdir -p "$SANITIZED_DIRECTORY"

for sample_file in "$SAMPLES_DIRECTORY"/*; do
  [[ -f "$sample_file" ]] || continue
  HOST_NAME="$HOST_NAME" perl -pe '
    s/\Q$ENV{HOST_NAME}\E/redacted-host/g;
    s/"node_name":\s*"[^"]*"/"node_name":"redacted-host"/g;
    s{/home/(?!agentuser\b)[A-Za-z0-9._-]+}{/home/redacted-user}g;
    s/\b(?!127\.0\.0\.1\b|0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b/x.x.x.x/g;
    s/(ANTHROPIC_API_KEY=|sk-ant-)[^\s"]+/$1REDACTED/g;
    s/sk-[A-Za-z0-9_-]{20,}/REDACTED/g;
  ' "$sample_file" > "$SANITIZED_DIRECTORY/$(basename "$sample_file")"
done

echo "Sanitized samples written to $SANITIZED_DIRECTORY. Read them before committing; redaction is pattern-based."
