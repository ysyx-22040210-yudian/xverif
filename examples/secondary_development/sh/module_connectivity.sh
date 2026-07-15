#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: module_connectivity.sh --daidir DIR --signal NAME [--signal NAME ...]
                              [--max-depth N] [--max-items N]
                              [--no-loads] [--require-edge]
                              [--require-complete] --out DIR

Environment:
  KDEBUG_BIN  Absolute kdebug command. Defaults to <repo>/tools/kdebug.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
kdebug_bin="${KDEBUG_BIN:-$repo_root/tools/kdebug}"
json_helper="$repo_root/examples/secondary_development/json_response.py"
if [[ -n "${KVERIF_JSON_PYTHON:-}" ]]; then
  json_python="$KVERIF_JSON_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  json_python=python3
else
  json_python=python
fi
daidir=""
out_dir=""
max_depth=6
max_items=200
include_loads=1
require_edge=0
require_complete=0
signals=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --daidir) daidir="$2"; shift 2 ;;
    --signal) signals+=("$2"); shift 2 ;;
    --max-depth) max_depth="$2"; shift 2 ;;
    --max-items) max_items="$2"; shift 2 ;;
    --no-loads) include_loads=0; shift ;;
    --require-edge) require_edge=1; shift ;;
    --require-complete) require_complete=1; shift ;;
    --out) out_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$daidir" && -n "$out_dir" ]] || {
  echo "ERROR: --daidir and --out are required" >&2
  exit 2
}
[[ ${#signals[@]} -gt 0 ]] || { echo "ERROR: at least one --signal is required" >&2; exit 2; }
[[ -x "$kdebug_bin" ]] || { echo "ERROR: kdebug is not executable: $kdebug_bin" >&2; exit 2; }
command -v "$json_python" >/dev/null 2>&1 || { echo "ERROR: Python with the standard json module is required" >&2; exit 2; }
[[ -f "$json_helper" ]] || { echo "ERROR: JSON helper is missing: $json_helper" >&2; exit 2; }

mkdir -p "$out_dir"
session="cli_graph_${USER:-user}_$$"
opened=0
gate_failed=0
: >"$out_dir/signals.ndjson"
: >"$out_dir/gate-errors.txt"

run_json() {
  local output="$1"
  shift
  if ! "$@" >"$output" 2>"$output.stderr"; then
    echo "ERROR: command failed; see $output.stderr" >&2
    return 1
  fi
  "$json_python" "$json_helper" check-ok "$output" || {
    echo "ERROR: tool returned ok=false; see $output" >&2
    return 1
  }
}

cleanup() {
  if [[ "$opened" -eq 1 ]]; then
    "$kdebug_bin" --json session-close --session "$session" \
      >"$out_dir/session.close.json" 2>"$out_dir/session.close.stderr" || true
    opened=0
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_json "$out_dir/session.open.json" \
  "$kdebug_bin" --json session-open --name "$session" --daidir "$daidir"
opened=1

for signal in "${signals[@]}"; do
  safe_signal="$(printf '%s' "$signal" | tr -c 'A-Za-z0-9_.-' '_')"
  driver_response="$out_dir/driver.${safe_signal}.json"
  load_response=""
  graph_response="$out_dir/graph.${safe_signal}.json"
  run_json "$driver_response" \
    "$kdebug_bin" --json trace-driver \
      --session "$session" --signal "$signal" \
      --include-source --max-items "$max_items"
  if [[ "$include_loads" -eq 1 ]]; then
    load_response="$out_dir/load.${safe_signal}.json"
    run_json "$load_response" \
      "$kdebug_bin" --json action trace.load \
        --session "$session" --arg "signal=$signal" \
        --include-source --max-items "$max_items"
  fi
  run_json "$graph_response" \
    "$kdebug_bin" --json trace-graph \
      --session "$session" --signal "$signal" \
      --include-trace --max-depth "$max_depth" --max-items "$max_items"

  record_command=("$json_python" "$json_helper" connectivity-row \
    --signal "$signal" --driver "$driver_response" --graph "$graph_response")
  [[ -z "$load_response" ]] || record_command+=(--load "$load_response")
  "${record_command[@]}" >>"$out_dir/signals.ndjson"

  driver_edges="$("$json_python" "$json_helper" summary-value \
    --file "$driver_response" --key edge_count --default 0)"
  graph_truncated="$("$json_python" "$json_helper" summary-value \
    --file "$graph_response" --key truncated --default false)"
  if [[ "$require_edge" -eq 1 ]] && (( driver_edges < 1 )); then
    printf '%s: no driver edge found\n' "$signal" >>"$out_dir/gate-errors.txt"
    gate_failed=1
  fi
  if [[ "$require_complete" -eq 1 && "$graph_truncated" == true ]]; then
    printf '%s: dependency graph was truncated\n' "$signal" >>"$out_dir/gate-errors.txt"
    gate_failed=1
  fi
done

"$json_python" "$json_helper" wrap-report \
  --schema kverif.cli.module-connectivity.v2 \
  --records "$out_dir/signals.ndjson" \
  --output "$out_dir/report.json" \
  --meta "daidir=$daidir" --meta "max_depth=$max_depth" \
  --meta "include_loads=$([[ $include_loads -eq 1 ]] && echo true || echo false)" \
  --meta "gate_failed=$([[ $gate_failed -eq 1 ]] && echo true || echo false)"

cleanup
trap - EXIT
if [[ "$gate_failed" -eq 1 ]]; then
  echo "ERROR: connectivity gate failed; see $out_dir/gate-errors.txt" >&2
  exit 3
fi
printf 'connectivity results: %s\n' "$out_dir"
