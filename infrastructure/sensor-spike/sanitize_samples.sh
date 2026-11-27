#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIRECTORY="/var/lib/sensor-spike/results"
SAMPLES_DIRECTORY="$RESULTS_DIRECTORY/samples"
SANITIZED_DIRECTORY="$RESULTS_DIRECTORY/samples-sanitized"
HOST_NAME="$(hostname)"

check_for_hostname_leaks() {
  [[ -n "$HOST_NAME" ]] || return 0
  HOST_NAME="$HOST_NAME" perl -MMIME::Base64 -ne '
    BEGIN { $leaked = 0 }
    if (index(lc $_, lc $ENV{HOST_NAME}) >= 0) { $leaked = 1; print "$ARGV: hostname in plain text\n"; }
    while (/"(?:exec_id|parent_exec_id)":\s*"([A-Za-z0-9+\/=_-]+)"/g) {
      if (index(lc decode_base64($1), lc $ENV{HOST_NAME}) >= 0) { $leaked = 1; print "$ARGV: hostname inside an exec id\n"; }
    }
    END { exit $leaked }
  ' "$@"
}

mkdir -p "$SANITIZED_DIRECTORY"

for sample_file in "$SAMPLES_DIRECTORY"/*; do
  [[ -f "$sample_file" ]] || continue
  HOST_NAME="$HOST_NAME" OPERATOR_NAME="${SUDO_USER:-}" perl -MMIME::Base64 -pe '
    BEGIN {
      sub redact_exec_id {
        my ($encoded_id) = @_;
        my $decoded_id = decode_base64($encoded_id);
        return $encoded_id unless $decoded_id =~ /^.*:(\d+):(\d+)$/s;
        return encode_base64("redacted-host:$1:$2", "");
      }
    }
    s/("(?:exec_id|parent_exec_id)":\s*")([A-Za-z0-9+\/=_-]+)(")/my ($prefix, $id, $suffix) = ($1, $2, $3); $prefix . redact_exec_id($id) . $suffix/ge;
    s/\Q$ENV{HOST_NAME}\E/redacted-host/gi;
    if (length($ENV{OPERATOR_NAME}) >= 3 && $ENV{OPERATOR_NAME} !~ /^(root|agentuser)$/) { s/\b\Q$ENV{OPERATOR_NAME}\E\b/redacted-user/g; }
    s/\b(auid|uid|euid|suid|fsuid|ouid|gid|egid|sgid|fsgid|ogid)=(?!agentuser\b|root\b|unset\b|\d)[A-Za-z0-9._-]+/$1=redacted-user/g;
    s/"node_name":\s*"[^"]*"/"node_name":"redacted-host"/g;
    s{/home/(?!agentuser\b)[A-Za-z0-9._-]+}{/home/redacted-user}g;
    s/\b(?!127\.0\.0\.1\b|0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b/x.x.x.x/g;
    s/(ANTHROPIC_API_KEY=|sk-ant-)[^\s"]+/$1REDACTED/g;
    s/sk-[A-Za-z0-9_-]{20,}/REDACTED/g;
  ' "$sample_file" > "$SANITIZED_DIRECTORY/$(basename "$sample_file")"
done

sanitized_files=("$SANITIZED_DIRECTORY"/*)
if [[ -f "${sanitized_files[0]}" ]]; then
  if ! check_for_hostname_leaks "${sanitized_files[@]}"; then
    echo "Sanitizing failed: the hostname is still present in the files above. Do not commit them." >&2
    exit 1
  fi
fi

echo "Sanitized samples written to $SANITIZED_DIRECTORY. exec_id and parent_exec_id keep their lineage links but carry no hostname. Read the files before committing; redaction is pattern-based."
