#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: waveform_window.sh --fsdb FILE --signal NAME [--signal NAME ...]
                          --begin TIME --end TIME [--time TIME ...]
                          [--daidir DIR]
                          [--active-signal NAME --active-time TIME]
                          [--max-rows N] [--min-changes N]
                          [--max-unknown N] [--require-complete] --out DIR

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
fsdb=""
daidir=""
begin=""
end=""
out_dir=""
max_rows=200
min_changes=0
max_unknown=""
require_complete=0
active_signal=""
active_time=""
signals=()
times=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fsdb) fsdb="$2"; shift 2 ;;
    --daidir) daidir="$2"; shift 2 ;;
    --signal) signals+=("$2"); shift 2 ;;
    --begin|--start) begin="$2"; shift 2 ;;
    --end|--stop) end="$2"; shift 2 ;;
    --time) times+=("$2"); shift 2 ;;
    --max-rows) max_rows="$2"; shift 2 ;;
    --min-changes) min_changes="$2"; shift 2 ;;
    --max-unknown) max_unknown="$2"; shift 2 ;;
    --require-complete) require_complete=1; shift ;;
    --active-signal) active_signal="$2"; shift 2 ;;
    --active-time) active_time="$2"; shift 2 ;;
    --out) out_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$fsdb" && -n "$begin" && -n "$end" && -n "$out_dir" ]] || {
  echo "ERROR: --fsdb, --begin, --end and --out are required" >&2
  exit 2
}
[[ ${#signals[@]} -gt 0 ]] || { echo "ERROR: at least one --signal is required" >&2; exit 2; }
if [[ -n "$active_signal" || -n "$active_time" ]]; then
  [[ -n "$active_signal" && -n "$active_time" && -n "$daidir" ]] || {
    echo "ERROR: active-driver analysis requires --daidir, --active-signal and --active-time" >&2
    exit 2
  }
fi
[[ -x "$kdebug_bin" ]] || { echo "ERROR: kdebug is not executable: $kdebug_bin" >&2; exit 2; }
command -v "$json_python" >/dev/null 2>&1 || { echo "ERROR: Python with the standard json module is required" >&2; exit 2; }
[[ -f "$json_helper" ]] || { echo "ERROR: JSON helper is missing: $json_helper" >&2; exit 2; }

mkdir -p "$out_dir"
session="cli_wave_${USER:-user}_$$"
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
  if ! "$json_python" "$json_helper" check-ok "$output"; then
    echo "ERROR: tool returned ok=false; see $output" >&2
    return 1
  fi
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

open_command=("$kdebug_bin" --json session-open --name "$session" --fsdb "$fsdb")
[[ -z "$daidir" ]] || open_command+=(--daidir "$daidir")
run_json "$out_dir/session.open.json" "${open_command[@]}"
opened=1

for signal in "${signals[@]}"; do
  safe_signal="$(printf '%s' "$signal" | tr -c 'A-Za-z0-9_.-' '_')"
  run_json "$out_dir/scan.${safe_signal}.json" \
    "$kdebug_bin" --json action signal.scan \
      --session "$session" \
      --arg "signal=$signal" \
      --arg "begin=$begin" \
      --arg "end=$end" \
      --arg format=hex \
      --max-rows "$max_rows"
  "$json_python" "$json_helper" wave-row \
    --signal "$signal" --response "$out_dir/scan.${safe_signal}.json" \
    >>"$out_dir/signals.ndjson"
  IFS=$'\t' read -r change_count unknown_count truncated <<<"$(
    "$json_python" "$json_helper" wave-stats "$out_dir/scan.${safe_signal}.json"
  )"
  if (( change_count < min_changes )); then
    printf '%s: change_count=%s is below min_changes=%s\n' \
      "$signal" "$change_count" "$min_changes" >>"$out_dir/gate-errors.txt"
    gate_failed=1
  fi
  if [[ -n "$max_unknown" ]] && (( unknown_count > max_unknown )); then
    printf '%s: unknown_count=%s exceeds max_unknown=%s\n' \
      "$signal" "$unknown_count" "$max_unknown" >>"$out_dir/gate-errors.txt"
    gate_failed=1
  fi
  if [[ "$require_complete" -eq 1 && "$truncated" == true ]]; then
    printf '%s: scan result was truncated\n' "$signal" >>"$out_dir/gate-errors.txt"
    gate_failed=1
  fi
done

for sample_time in "${times[@]}"; do
  safe_time="$(printf '%s' "$sample_time" | tr -c 'A-Za-z0-9_.-' '_')"
  command=("$kdebug_bin" --json value-batch --session "$session")
  for signal in "${signals[@]}"; do
    command+=(--signal "$signal")
  done
  command+=(--time "$sample_time" --format hex)
  run_json "$out_dir/sample.${safe_time}.json" "${command[@]}"
done

active_response=""
if [[ -n "$active_signal" ]]; then
  active_response="$out_dir/active-driver.json"
  run_json "$active_response" \
    "$kdebug_bin" --json active-driver \
      --session "$session" --signal "$active_signal" --time "$active_time" \
      --include-control --include-trace --max-depth 8
fi

report_command=("$json_python" "$json_helper" wrap-report \
  --schema kverif.cli.waveform-window.v2 \
  --records "$out_dir/signals.ndjson" \
  --output "$out_dir/report.json" \
  --meta "fsdb=$fsdb" --meta "begin=$begin" --meta "end=$end" \
  --meta "sample_count=${#times[@]}" --meta "gate_failed=$([[ $gate_failed -eq 1 ]] && echo true || echo false)")
[[ -z "$daidir" ]] || report_command+=(--meta "daidir=$daidir")
[[ -z "$active_response" ]] || report_command+=(--meta "active_driver_response=$active_response")
"${report_command[@]}"

cleanup
trap - EXIT
if [[ "$gate_failed" -eq 1 ]]; then
  echo "ERROR: waveform gate failed; see $out_dir/gate-errors.txt" >&2
  exit 3
fi
printf 'waveform results: %s\n' "$out_dir"
