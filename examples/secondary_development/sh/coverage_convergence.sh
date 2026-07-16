#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: coverage_convergence.sh --run LABEL=VDB [--run LABEL=VDB ...]
                               [--metrics line,toggle,branch]
                               [--hole-limit N] [--plateau-epsilon PCT]
                               [--fail-under PCT] [--max-final-holes N]
                               [--max-regression PCT] [--require-growth]
                               [--fake] [--kcov-bin CMD]
                               [--json-python CMD] [--json-helper FILE]
                               --out DIR

Environment:
  KCOV_BIN, KVERIF_HOME, KVERIF_JSON_PYTHON, KVERIF_JSON_HELPER, PYTHON
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out_dir=""
metrics="line,toggle,branch"
hole_limit=50
plateau_epsilon=0.01
fail_under=""
max_final_holes=""
max_regression=""
require_growth=0
fake=0
kcov_override=""
json_python_override=""
json_helper_override=""
runs=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run) runs+=("$2"); shift 2 ;;
    --metrics) metrics="$2"; shift 2 ;;
    --hole-limit) hole_limit="$2"; shift 2 ;;
    --plateau-epsilon) plateau_epsilon="$2"; shift 2 ;;
    --fail-under) fail_under="$2"; shift 2 ;;
    --max-final-holes) max_final_holes="$2"; shift 2 ;;
    --max-regression) max_regression="$2"; shift 2 ;;
    --require-growth) require_growth=1; shift ;;
    --fake) fake=1; shift ;;
    --kcov-bin) kcov_override="$2"; shift 2 ;;
    --json-python) json_python_override="$2"; shift 2 ;;
    --json-helper) json_helper_override="$2"; shift 2 ;;
    --out) out_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$out_dir" ]] || { echo "ERROR: --out is required" >&2; exit 2; }
[[ ${#runs[@]} -gt 0 ]] || { echo "ERROR: at least one --run is required" >&2; exit 2; }

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
if ! command -v "$kcov_bin" >/dev/null 2>&1 && [[ ! -x "$kcov_bin" ]]; then
  echo "ERROR: kcov is not executable: $kcov_bin" >&2; exit 2
fi
if ! "$json_python" -c 'import json, sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
  echo "ERROR: JSON helper requires a runnable Python 3 command: $json_python" >&2; exit 2
fi
[[ -f "$json_helper" ]] || { echo "ERROR: JSON helper is missing: $json_helper" >&2; exit 2; }

mkdir -p "$out_dir"
: >"$out_dir/runs.ndjson"
previous_pct=""

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

for spec in "${runs[@]}"; do
  [[ "$spec" == *=* ]] || { echo "ERROR: --run must be LABEL=VDB: $spec" >&2; exit 2; }
  label="${spec%%=*}"
  vdb="${spec#*=}"
  [[ "$label" =~ ^[A-Za-z0-9_.-]+$ ]] || {
    echo "ERROR: run label must match [A-Za-z0-9_.-]+: $label" >&2
    exit 2
  }
  if [[ "$fake" -eq 0 && ! -e "$vdb" ]]; then
    echo "ERROR: VDB does not exist: $vdb" >&2
    exit 2
  fi

  common=(--vdb "$vdb" --metrics "$metrics")
  [[ "$fake" -eq 0 ]] || common+=(--fake)
  run_json "$out_dir/${label}.summary.json" \
    "$kcov_bin" --json cov-summary "${common[@]}"
  run_json "$out_dir/${label}.holes.json" \
    "$kcov_bin" --json cov-holes "${common[@]}" --max-items "$hole_limit"

  stats="$("$json_python" "$json_helper" coverage-stats "$out_dir/${label}.summary.json")"
  IFS=$'\t' read -r covered coverable pct <<<"$stats"
  hole_count="$("$json_python" "$json_helper" holes-count "$out_dir/${label}.holes.json")"

  delta_json=null
  plateau=false
  if [[ -n "$previous_pct" ]]; then
    IFS=$'\t' read -r delta_json plateau <<<"$(
      "$json_python" "$json_helper" coverage-delta \
        --current "$pct" --previous "$previous_pct" --epsilon "$plateau_epsilon"
    )"
  fi

  "$json_python" "$json_helper" coverage-row \
    --label "$label" --vdb "$vdb" \
    --covered "$covered" --coverable "$coverable" \
    --coverage-pct "$pct" --delta "$delta_json" --plateau "$plateau" \
    --hole-count "$hole_count" \
    --summary-response "$out_dir/${label}.summary.json" \
    --holes-response "$out_dir/${label}.holes.json" \
    >>"$out_dir/runs.ndjson"
  previous_pct="$pct"
done

report_command=("$json_python" "$json_helper" coverage-report \
  --metrics "$metrics" --plateau-epsilon "$plateau_epsilon" \
  --runs "$out_dir/runs.ndjson" --output "$out_dir/convergence.json")
[[ -z "$fail_under" ]] || report_command+=(--fail-under "$fail_under")
[[ -z "$max_final_holes" ]] || report_command+=(--max-final-holes "$max_final_holes")
[[ -z "$max_regression" ]] || report_command+=(--max-regression "$max_regression")
[[ "$require_growth" -eq 0 ]] || report_command+=(--require-growth)
"${report_command[@]}"

gate_command=("$json_python" "$json_helper" coverage-gate \
  --report "$out_dir/convergence.json")
[[ -z "$fail_under" ]] || gate_command+=(--target "$fail_under")
[[ -z "$max_final_holes" ]] || gate_command+=(--max-final-holes "$max_final_holes")
[[ -z "$max_regression" ]] || gate_command+=(--max-regression "$max_regression")
[[ "$require_growth" -eq 0 ]] || gate_command+=(--require-growth)
if ! "${gate_command[@]}"; then
  echo "ERROR: coverage gate failed; see $out_dir/convergence.json" >&2
  exit 3
fi

printf 'coverage results: %s\n' "$out_dir/convergence.json"
