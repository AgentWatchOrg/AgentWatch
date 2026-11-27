#!/usr/bin/env bash
set -euo pipefail

mode="${1:-demo}"
case "$mode" in
  prepare|smoke|demo) ;;
  *) printf 'Usage: %s [prepare|smoke|demo]\n' "$0" >&2; exit 2 ;;
esac
if ((EUID == 0)); then
  printf 'Run this launcher as the unprivileged demo user.\n' >&2
  exit 1
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
pinned_ollama_dir="$HOME/.local/opt/ollama-0.40.18"

resolve_executable() {
  local override=$1
  shift
  if [[ -n $override ]]; then
    printf '%s\n' "$override"
    return
  fi
  local candidate
  for candidate in "$@"; do
    if [[ -x $candidate ]]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  local path_name=$1
  path_name=$(basename "$path_name")
  if command -v "$path_name" >/dev/null 2>&1; then
    command -v "$path_name"
    return
  fi
  printf '%s\n' "$1"
}

claude_bin=$(resolve_executable "${CLAUDE_BIN:-}" "$HOME/.local/bin/claude")
ollama_bin=$(resolve_executable "${OLLAMA_BIN:-}" \
  "$pinned_ollama_dir/bin/ollama" \
  "$pinned_ollama_dir/ollama")
ollama_host=127.0.0.1:11434
model=qwen3.5:4b
sample_url=http://127.0.0.1:8765/sample.txt
fixture=AgentWatch-synthetic-fixture
demo_path="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

for binary in "$claude_bin" "$ollama_bin"; do
  if [[ ! -x $binary ]]; then
    printf 'Missing executable: %s. See documentation/infrastructure/claude-code-demo.md.\n' "$binary" >&2
    exit 1
  fi
done

scratch=$(mktemp -d)
sample_dir="$scratch/sample"
children=()
cleanup() {
  if ((${#children[@]})); then
    kill "${children[@]}" 2>/dev/null || true
    wait "${children[@]}" 2>/dev/null || true
  fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_until_ready() {
  local label=$1 log=$2
  shift 2
  for ((attempt=0; attempt<20; attempt++)); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  printf '%s did not start. Recent output:\n' "$label" >&2
  tail -n 8 "$log" >&2
  return 1
}

ollama_ready() {
  curl --noproxy '*' -fsS --max-time 1 "http://$ollama_host/api/version" >/dev/null
}
if ! ollama_ready 2>/dev/null; then
  OLLAMA_HOST="$ollama_host" OLLAMA_NO_CLOUD=1 OLLAMA_CONTEXT_LENGTH=16384 \
    OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 \
    "$ollama_bin" serve </dev/null >"$scratch/ollama.log" 2>&1 &
  children+=("$!")
  wait_until_ready Ollama "$scratch/ollama.log" ollama_ready
fi

if [[ $mode == prepare ]]; then
  OLLAMA_HOST="$ollama_host" "$ollama_bin" pull "$model"
  exit
fi
if ! OLLAMA_HOST="$ollama_host" "$ollama_bin" show "$model" >/dev/null 2>&1; then
  printf 'Model %s is missing. Run %s prepare first.\n' "$model" "$0" >&2
  exit 1
fi

git init -q "$sample_dir"
printf '%s\n' "$fixture" >"$sample_dir/sample.txt"

run_task() {
  local command=$1 expected=$2 config
  config=$(mktemp -d "$scratch/claude.XXXXXX")
  printf '\nAsking Claude Code to run: %s\n' "$command"
  printf 'The local model may take a minute or two.\n'
  (
    cd "$sample_dir"
    env -i HOME="$HOME" PATH="$demo_path" \
      CLAUDE_CONFIG_DIR="$config" CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      DISABLE_AUTOUPDATER=1 CLAUDE_CODE_MAX_OUTPUT_TOKENS=1024 \
      ANTHROPIC_BASE_URL="http://$ollama_host" ANTHROPIC_AUTH_TOKEN=ollama \
      "$claude_bin" --bare --model "$model" --max-turns 3 --tools Bash \
      --allowedTools "Bash($command)" --permission-mode dontAsk \
      --system-prompt 'Use Bash to run the requested command exactly once, then briefly report the result.' \
      --output-format stream-json --verbose -p "Use Bash to run exactly $command."
  ) >"$scratch/out.jsonl" 2>"$scratch/claude.log" </dev/null || {
    cat "$scratch/claude.log" >&2
    return 1
  }
  python3 - "$command" "$expected" "$scratch/out.jsonl" <<'PY'
import json
import sys

command, expected, transcript = sys.argv[1:]
matches = set()
with open(transcript) as lines:
    for line in lines:
        event = json.loads(line)
        for part in event.get("message", {}).get("content", []):
            if part.get("type") == "tool_use" and part.get("name") == "Bash":
                if part.get("input", {}).get("command") == command:
                    matches.add(part["id"])
            if part.get("type") == "tool_result" and part.get("tool_use_id") in matches:
                output = part.get("content", "")
                if isinstance(output, str) and not part.get("is_error") and output.strip() == expected:
                    print(f"Bash returned: {output.strip()}")
                    sys.exit(0)
sys.exit("No successful Bash tool result matched this example.")
PY
}

start_event_viewer() {
  if [[ -z "${TETRA_ADDRESS:-}" ]]; then return 0; fi
  if [[ $(uname -s) != Linux ]]; then
    printf 'Tetragon event viewing is Linux-only. Unset TETRA_ADDRESS on macOS.\n' >&2
    exit 1
  fi
  local tetra_bin="${TETRA_BIN:-tetra}"
  if ! "$tetra_bin" --server-address "$TETRA_ADDRESS" tracingpolicy list \
    </dev/null >/dev/null; then
    printf 'Cannot reach Tetragon at %s. Check the sensor and socket access.\n' "$TETRA_ADDRESS" >&2
    exit 1
  fi
  "$tetra_bin" --server-address "$TETRA_ADDRESS" getevents -o json </dev/null \
    > >(python3 -u "$script_dir/show-events.py" "$sample_dir/sample.txt") &
  children+=("$!")
  sleep 2
  if ! kill -0 "$!" 2>/dev/null; then
    printf 'The Tetragon event stream disconnected.\n' >&2
    return 1
  fi
}

if [[ $mode == smoke ]]; then
  start_event_viewer
  run_task '/usr/bin/wc -l sample.txt' '1 sample.txt'
  exit
fi

sample_server_ready() {
  local response
  response=$(curl --noproxy '*' -fsS --max-time 1 "$sample_url") || return 1
  [[ $response == "$fixture" ]]
}
if ! sample_server_ready 2>/dev/null; then
  python3 -m http.server 8765 --bind 127.0.0.1 --directory "$sample_dir" \
    </dev/null >"$scratch/http.log" 2>&1 &
  children+=("$!")
  wait_until_ready 'Local test server' "$scratch/http.log" sample_server_ready
fi

start_event_viewer
printf 'Sample workspace: %s\n' "$sample_dir"
while true; do
  printf '\n1  Count lines (command and file open)\n2  Fetch the sample file (network)\nq  Quit\n'
  printf 'Choose 1, 2, or q: '
  if ! IFS= read -r choice; then break; fi
  case "$choice" in
    1) run_task '/usr/bin/wc -l sample.txt' '1 sample.txt' || true ;;
    2) run_task "/usr/bin/curl -fsS $sample_url" "$fixture" || true ;;
    q|Q) break ;;
    *) printf 'Enter 1, 2, or q.\n' ;;
  esac
done
