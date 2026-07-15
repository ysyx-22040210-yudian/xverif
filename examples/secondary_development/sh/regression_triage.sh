#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: regression_triage.sh --fsdb FILE --daidir DIR --vdb DIR
                            --signal NAME [--signal NAME ...]
                            --begin TIME --end TIME [--time TIME ...]
                            [--metrics LIST] [--fail-under PCT]
                            [--max-final-holes N] [--min-changes N]
                            [--active-signal NAME --active-time TIME]
                            --out DIR

Runs waveform, static connectivity, and coverage workflows and creates one
regression-triage report. Tool paths may be overridden with KDEBUG_BIN and
KCOV_BIN.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
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
vdb=""
begin=""
end=""
out_dir=""
metrics="line,toggle,branch"
fail_under=""
max_final_holes=""
min_changes=0
active_signal=""
active_time=""
signals=()
times=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fsdb) fsdb="$2"; shift 2 ;;
    --daidir) daidir="$2"; shift 2 ;;
    --vdb) vdb="$2"; shift 2 ;;
    --signal) signals+=("$2"); shift 2 ;;
    --begin|--start) begin="$2"; shift 2 ;;
    --end|--stop) end="$2"; shift 2 ;;
    --time) times+=("$2"); shift 2 ;;
    --metrics) metrics="$2"; shift 2 ;;
    --fail-under) fail_under="$2"; shift 2 ;;
    --max-final-holes) max_final_holes="$2"; shift 2 ;;
    --min-changes) min_changes="$2"; shift 2 ;;
    --active-signal) active_signal="$2"; shift 2 ;;
    --active-time) active_time="$2"; shift 2 ;;
    --out) out_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$fsdb" && -n "$daidir" && -n "$vdb" && -n "$begin" && -n "$end" && -n "$out_dir" ]] || {
  echo "ERROR: --fsdb, --daidir, --vdb, --begin, --end and --out are required" >&2
  exit 2
}
[[ ${#signals[@]} -gt 0 ]] || { echo "ERROR: at least one --signal is required" >&2; exit 2; }
if [[ -n "$active_signal" || -n "$active_time" ]]; then
  [[ -n "$active_signal" && -n "$active_time" ]] || {
    echo "ERROR: --active-signal and --active-time must be used together" >&2
    exit 2
  }
fi

mkdir -p "$out_dir"

wave_command=(bash "$script_dir/waveform_window.sh" \
  --fsdb "$fsdb" --daidir "$daidir" --begin "$begin" --end "$end" \
  --min-changes "$min_changes" --max-unknown 0 --require-complete \
  --out "$out_dir/waveform")
connectivity_command=(bash "$script_dir/module_connectivity.sh" \
  --daidir "$daidir" --require-edge --require-complete \
  --out "$out_dir/connectivity")
for signal in "${signals[@]}"; do
  wave_command+=(--signal "$signal")
  connectivity_command+=(--signal "$signal")
done
for sample_time in "${times[@]}"; do
  wave_command+=(--time "$sample_time")
done
if [[ -n "$active_signal" ]]; then
  wave_command+=(--active-signal "$active_signal" --active-time "$active_time")
fi

coverage_command=(bash "$script_dir/coverage_convergence.sh" \
  --run "current=$vdb" --metrics "$metrics" --out "$out_dir/coverage")
[[ -z "$fail_under" ]] || coverage_command+=(--fail-under "$fail_under")
[[ -z "$max_final_holes" ]] || coverage_command+=(--max-final-holes "$max_final_holes")

"${wave_command[@]}"
"${connectivity_command[@]}"
"${coverage_command[@]}"

"$json_python" "$json_helper" triage-report \
  --waveform "$out_dir/waveform/report.json" \
  --connectivity "$out_dir/connectivity/report.json" \
  --coverage "$out_dir/coverage/convergence.json" \
  --output "$out_dir/report.json"

printf 'regression triage report: %s\n' "$out_dir/report.json"
