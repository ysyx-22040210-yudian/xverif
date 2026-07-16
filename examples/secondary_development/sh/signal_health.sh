#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: signal_health.sh --fsdb FILE --signal NAME --begin TIME --end TIME
                        [--max-rows N] [--min-changes N]
                        [--max-unknown N] [--require-complete]
                        [--kdebug-bin CMD] [--json-python CMD]
                        [--json-helper FILE] --out DIR

The script invokes kdebug, parses signal.scan JSON, and emits conclusion.json.
Environment:
  KDEBUG_BIN, KVERIF_HOME, KVERIF_JSON_PYTHON, KVERIF_JSON_HELPER, PYTHON

Command resolution: explicit option, environment, KVERIF_HOME/tools,
repository-relative tools, then PATH.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fsdb=""
signal=""
begin=""
end=""
out_dir=""
max_rows=200
min_changes=1
max_unknown=0
require_complete=false
kdebug_override=""
json_python_override=""
json_helper_override=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fsdb) fsdb="$2"; shift 2 ;;
    --signal) signal="$2"; shift 2 ;;
    --begin|--start) begin="$2"; shift 2 ;;
    --end|--stop) end="$2"; shift 2 ;;
    --max-rows) max_rows="$2"; shift 2 ;;
    --min-changes) min_changes="$2"; shift 2 ;;
    --max-unknown) max_unknown="$2"; shift 2 ;;
    --require-complete) require_complete=true; shift ;;
    --kdebug-bin) kdebug_override="$2"; shift 2 ;;
    --json-python) json_python_override="$2"; shift 2 ;;
    --json-helper) json_helper_override="$2"; shift 2 ;;
    --out) out_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$fsdb" && -n "$signal" && -n "$begin" && -n "$end" && -n "$out_dir" ]] || {
  echo "ERROR: --fsdb, --signal, --begin, --end and --out are required" >&2
  exit 2
}
for item in "$max_rows" "$min_changes" "$max_unknown"; do
  [[ "$item" =~ ^[0-9]+$ ]] || { echo "ERROR: numeric options must be non-negative integers" >&2; exit 2; }
done

resolve_tool() {
  local explicit="$1" env_value="$2" tool_name="$3"
  if [[ -n "$explicit" ]]; then
    printf '%s\n' "$explicit"
  elif [[ -n "$env_value" ]]; then
    printf '%s\n' "$env_value"
  elif [[ -n "${KVERIF_HOME:-}" && -x "$KVERIF_HOME/tools/$tool_name" ]]; then
    printf '%s\n' "$KVERIF_HOME/tools/$tool_name"
  elif [[ -x "$script_dir/../../../tools/$tool_name" ]]; then
    printf '%s\n' "$script_dir/../../../tools/$tool_name"
  else
    command -v "$tool_name" 2>/dev/null || return 1
  fi
}

resolve_python() {
  if [[ -n "$json_python_override" ]]; then
    printf '%s\n' "$json_python_override"
  elif [[ -n "${KVERIF_JSON_PYTHON:-}" ]]; then
    printf '%s\n' "$KVERIF_JSON_PYTHON"
  elif [[ -n "${PYTHON:-}" ]]; then
    printf '%s\n' "$PYTHON"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    command -v python 2>/dev/null || return 1
  fi
}

kdebug_bin="$(resolve_tool "$kdebug_override" "${KDEBUG_BIN:-}" kdebug)" || {
  echo "ERROR: cannot find kdebug; use --kdebug-bin, KDEBUG_BIN, KVERIF_HOME, or PATH" >&2
  exit 2
}
json_python="$(resolve_python)" || {
  echo "ERROR: cannot find Python 3; use --json-python, KVERIF_JSON_PYTHON, or PYTHON" >&2
  exit 2
}
if [[ -n "$json_helper_override" ]]; then
  json_helper="$json_helper_override"
elif [[ -n "${KVERIF_JSON_HELPER:-}" ]]; then
  json_helper="$KVERIF_JSON_HELPER"
elif [[ -f "$script_dir/../json_response.py" ]]; then
  json_helper="$script_dir/../json_response.py"
elif [[ -n "${KVERIF_HOME:-}" && -f "$KVERIF_HOME/examples/secondary_development/json_response.py" ]]; then
  json_helper="$KVERIF_HOME/examples/secondary_development/json_response.py"
else
  json_helper="$script_dir/../json_response.py"
fi

if ! command -v "$kdebug_bin" >/dev/null 2>&1 && [[ ! -x "$kdebug_bin" ]]; then
  echo "ERROR: kdebug is not executable: $kdebug_bin" >&2
  exit 2
fi
if ! "$json_python" -c 'import json, sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
  echo "ERROR: JSON helper requires a runnable Python 3 command: $json_python" >&2
  exit 2
fi
[[ -f "$json_helper" ]] || { echo "ERROR: JSON helper is missing: $json_helper" >&2; exit 2; }

mkdir -p "$out_dir"
response="$out_dir/tool-response.json"
stderr_file="$out_dir/tool-response.stderr"
report="$out_dir/conclusion.json"

if ! "$kdebug_bin" --json action signal.scan \
    --fsdb "$fsdb" --arg "signal=$signal" --arg "begin=$begin" --arg "end=$end" \
    --arg format=hex --max-rows "$max_rows" >"$response" 2>"$stderr_file"; then
  echo "ERROR: kdebug failed; see $stderr_file" >&2
  exit 1
fi
"$json_python" "$json_helper" check-ok "$response"

IFS=$'\t' read -r change_count unknown_count truncated <<<"$(
  "$json_python" "$json_helper" wave-stats "$response"
)"

conclusion=HEALTHY
reason="signal activity satisfies all configured gates"
if [[ "$require_complete" == true && "$truncated" == true ]]; then
  conclusion=INCOMPLETE
  reason="signal.scan was truncated, so the complete window was not evaluated"
elif (( unknown_count > max_unknown )); then
  conclusion=UNKNOWN_VALUES
  reason="unknown_count exceeds the configured maximum"
elif (( change_count < min_changes )); then
  conclusion=INACTIVE
  reason="change_count is below the configured minimum"
fi

"$json_python" "$json_helper" signal-health-report \
  --output "$report" --language sh --signal "$signal" --response "$response" \
  --change-count "$change_count" --unknown-count "$unknown_count" --truncated "$truncated" \
  --min-changes "$min_changes" --max-unknown "$max_unknown" \
  --require-complete "$require_complete" --conclusion "$conclusion" --reason "$reason"

printf 'signal health: %s (%s)\nreport: %s\n' "$conclusion" "$reason" "$report"
[[ "$conclusion" == HEALTHY ]] || exit 3
