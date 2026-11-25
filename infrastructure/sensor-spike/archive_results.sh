#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIRECTORY="/var/tmp/sensor-spike-results"
RESULTS_ARCHIVE="/var/tmp/sensor-spike-results.tar.gz"

tar -czf "$RESULTS_ARCHIVE" -C "$(dirname "$RESULTS_DIRECTORY")" "$(basename "$RESULTS_DIRECTORY")"
chmod 644 "$RESULTS_ARCHIVE"

echo "Results archived at $RESULTS_ARCHIVE"
echo "The archive contains unsanitized raw events; commit only the files in samples-sanitized/."
if grep -qi microsoft /proc/version; then
  echo "On WSL, copy it to Windows: cp $RESULTS_ARCHIVE /mnt/c/Users/<WindowsUserName>/Downloads/"
fi
