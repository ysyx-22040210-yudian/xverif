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
                            [--kdebug-bin CMD] [--kcov-bin CMD]
                            [--json-python CMD] [--json-helper FILE]
                            --out DIR

Runs waveform, static connectivity, and coverage workflows and creates one
regression-triage report. Tools are resolved from explicit options, environment,
KVERIF_HOME/tools, the repository, then PATH.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
kdebug_override=""
kcov_override=""
json_python_override=""
json_helper_override=""
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
    --kdebug-bin) kdebug_override="$2"; shift 2 ;;
    --kcov-bin) kcov_override="$2"; shift 2 ;;
    --json-python) json_python_override="$2"; shift 2 ;;
    --json-helper) json_helper_override="$2"; shift 2 ;;
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

resolve_tool() {
  local explicit="$1" env_value="$2" tool_name="$3"
  if [[ -n "$explicit" ]]; then printf '%s\n' "$explicit"
  elif [[ -n "$env_value" ]]; then printf '%s\n' "$env_value"
  elif [[ -n "${KVERIF_HOME:-}" && -x "$KVERIF_HOME/tools/$tool_name" ]]; then printf '%s\n' "$KVERIF_HOME/tools/$tool_name"
  elif [[ -x "$script_dir/../../../tools/$tool_name" ]]; then printf '%s\n' "$script_dir/../../../tools/$tool_name"
  else command -v "$tool_name" 2>/dev/null || return 1
  fi
}
resolve_python() {
  if [[ -n "$json_python_override" ]]; then printf '%s\n' "$json_python_override"
  elif [[ -n "${KVERIF_JSON_PYTHON:-}" ]]; then printf '%s\n' "$KVERIF_JSON_PYTHON"
  elif [[ -n "${PYTHON:-}" ]]; then printf '%s\n' "$PYTHON"
  elif command -v python3 >/dev/null 2>&1; then command -v python3
  else command -v python 2>/dev/null || return 1
  fi
}
kdebug_bin="$(resolve_tool "$kdebug_override" "${KDEBUG_BIN:-}" kdebug)" || {
  echo "ERROR: cannot find kdebug; use --kdebug-bin, KDEBUG_BIN, KVERIF_HOME, or PATH" >&2; exit 2;
}
kcov_bin="$(resolve_tool "$kcov_override" "${KCOV_BIN:-}" kcov)" || {
  echo "ERROR: cannot find kcov; use --kcov-bin, KCOV_BIN, KVERIF_HOME, or PATH" >&2; exit 2;
}
json_python="$(resolve_python)" || {
  echo "ERROR: cannot find Python 3; use --json-python, KVERIF_JSON_PYTHON, or PYTHON" >&2; exit 2;
}
if [[ -n "$json_helper_override" ]]; then json_helper="$json_helper_override"
elif [[ -n "${KVERIF_JSON_HELPER:-}" ]]; then json_helper="$KVERIF_JSON_HELPER"
elif [[ -f "$script_dir/../json_response.py" ]]; then json_helper="$script_dir/../json_response.py"
elif [[ -n "${KVERIF_HOME:-}" && -f "$KVERIF_HOME/examples/secondary_development/json_response.py" ]]; then json_helper="$KVERIF_HOME/examples/secondary_development/json_response.py"
else json_helper="$script_dir/../json_response.py"
fi
for command_path in "$kdebug_bin" "$kcov_bin"; do
  if ! command -v "$command_path" >/dev/null 2>&1 && [[ ! -x "$command_path" ]]; then
    echo "ERROR: tool is not executable: $command_path" >&2; exit 2
  fi
done
if ! "$json_python" -c 'import json, sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
  echo "ERROR: JSON helper requires a runnable Python 3 command: $json_python" >&2; exit 2
fi
[[ -f "$json_helper" ]] || { echo "ERROR: JSON helper is missing: $json_helper" >&2; exit 2; }
for child_script in waveform_window.sh module_connectivity.sh coverage_convergence.sh; do
  [[ -f "$script_dir/$child_script" ]] || {
    echo "ERROR: regression_triage.sh requires sibling script: $script_dir/$child_script" >&2; exit 2;
  }
done

mkdir -p "$out_dir"

wave_command=(bash "$script_dir/waveform_window.sh" \
  --fsdb "$fsdb" --daidir "$daidir" --begin "$begin" --end "$end" \
  --min-changes "$min_changes" --max-unknown 0 --require-complete \
  --kdebug-bin "$kdebug_bin" --json-python "$json_python" --json-helper "$json_helper" \
  --out "$out_dir/waveform")
connectivity_command=(bash "$script_dir/module_connectivity.sh" \
  --daidir "$daidir" --require-edge --require-complete \
  --kdebug-bin "$kdebug_bin" --json-python "$json_python" --json-helper "$json_helper" \
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
  --run "current=$vdb" --metrics "$metrics" \
  --kcov-bin "$kcov_bin" --json-python "$json_python" --json-helper "$json_helper" \
  --out "$out_dir/coverage")
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
