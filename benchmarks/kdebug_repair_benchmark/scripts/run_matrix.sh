#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run_matrix.sh --suite-root DIR --bench-root DIR [--cases case_001,case_002] [--models gpt-5.5,glm-4.7,qwen3.6-35b] [--timeout 3600] [--evidence-mode collect|validate] [--force-evidence]

Expected suite layout:
  <suite-root>/case_001/
  <suite-root>/case_002/
  ...

Outputs:
  <suite-root>/repair/<model>/<group>/<case>/
  <suite-root>/results.csv
  <suite-root>/screenshots/
  <suite-root>/docx_out/

Environment:
  GPT55_BASE_URL      Optional for gpt-5.5; defaults to http://165.154.147.120:8080/v1.
  GPT55_API_KEY       Required for gpt-5.5. OPENAI_API_KEY is also accepted.
  MAAS_BASE_URL       Optional for glm-4.7/qwen3.6-35b; defaults to https://maas-coding-api.cn-huabei-1.xf-yun.com/v2.
  MAAS_API_KEY        Required for glm-4.7/qwen3.6-35b. AIAPI_* names are still accepted for compatibility.
  KDEBUG_RESET_RESULTS        Set to 1 to discard an existing results.csv before running.
  KDEBUG_RATE_LIMIT_SLEEP_SEC  Delay before retrying a rate-limited model. Default: 1800.
  KDEBUG_BIN                  KDebug CLI path. Default: <repository>/tools/kdebug.
  KDEBUG_PYTHON               Python 3.8+ executable used by collection and runner code.
                              PYTHON is accepted as a fallback; default: python3.
  KDEBUG_REPORT_PYTHON        Python with Pillow and python-docx for final reports.
                              Default: KDEBUG_PYTHON.
  KDEBUG_EVIDENCE_MODE        collect (default) or validate.
  KDEBUG_FORCE_EVIDENCE       Set to 1 to archive and recollect otherwise-valid evidence.
USAGE
}

RETRY_LATER_EXIT_CODE=75
suite_root=""
bench_root=""
cases=""
models="gpt-5.5,glm-4.7,qwen3.6-35b"
timeout_sec=3600
rate_limit_sleep_sec="${KDEBUG_RATE_LIMIT_SLEEP_SEC:-1800}"
evidence_mode="${KDEBUG_EVIDENCE_MODE:-collect}"
force_evidence="${KDEBUG_FORCE_EVIDENCE:-0}"
python_bin="${KDEBUG_PYTHON:-${PYTHON:-python3}}"
report_python="${KDEBUG_REPORT_PYTHON:-$python_bin}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite-root) suite_root="$2"; shift 2 ;;
    --bench-root) bench_root="$2"; shift 2 ;;
    --cases) cases="$2"; shift 2 ;;
    --models) models="$2"; shift 2 ;;
    --timeout) timeout_sec="$2"; shift 2 ;;
    --evidence-mode) evidence_mode="$2"; shift 2 ;;
    --force-evidence) force_evidence=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$suite_root" || -z "$bench_root" ]]; then
  usage >&2
  exit 2
fi
if [[ "$evidence_mode" != "collect" && "$evidence_mode" != "validate" ]]; then
  echo "ERROR: --evidence-mode must be collect or validate" >&2
  exit 2
fi
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "ERROR: benchmark Python executable not found: $python_bin" >&2
  exit 2
fi
if ! command -v "$report_python" >/dev/null 2>&1; then
  echo "ERROR: report Python executable not found: $report_python" >&2
  exit 2
fi
export KDEBUG_PYTHON="$python_bin"

suite_root="$(cd "$suite_root" && pwd)"
bench_root="$(cd "$bench_root" && pwd)"
repair_root="$suite_root/repair"
results_csv="$suite_root/results.csv"
screenshot_dir="$suite_root/screenshots"
docx_dir="$suite_root/docx_out"
retry_budget_py="$bench_root/scripts/matrix_retry_budget.py"
evidence_py="$bench_root/scripts/kdebug_evidence.py"
repo_root="$(cd "$bench_root/../.." && pwd)"
kdebug_bin="${KDEBUG_BIN:-$repo_root/tools/kdebug}"

if [[ -z "$cases" ]]; then
  cases="$(find "$suite_root" -maxdepth 1 -type d -name 'case_[0-9][0-9][0-9]' -printf '%f\n' | sort | paste -sd, -)"
fi
if [[ -z "$cases" ]]; then
  echo "ERROR: no cases found" >&2
  exit 2
fi

IFS=',' read -r -a case_list <<< "$cases"
IFS=',' read -r -a model_list <<< "$models"
groups=(with_kdebug without_kdebug)

if [[ "${KDEBUG_RESET_RESULTS:-0}" == "1" ]]; then
  rm -f "$results_csv"
fi
mkdir -p "$repair_root" "$screenshot_dir" "$docx_dir"

if [[ ! -f "$evidence_py" ]]; then
  echo "ERROR: missing KDebug evidence collector: $evidence_py" >&2
  exit 2
fi
if [[ "$evidence_mode" == "collect" && ! -x "$kdebug_bin" ]]; then
  echo "ERROR: KDebug CLI is not executable: $kdebug_bin" >&2
  exit 2
fi

for case_id in "${case_list[@]}"; do
  case_dir="$suite_root/$case_id"
  if [[ ! -d "$case_dir" ]]; then
    echo "ERROR: missing case dir $case_dir" >&2
    exit 2
  fi
  if [[ "$evidence_mode" == "collect" ]]; then
    collect_args=(collect --case-dir "$case_dir" --kdebug "$kdebug_bin")
    if [[ "$force_evidence" == "1" ]]; then
      collect_args+=(--force)
    fi
    echo "===== KDEBUG EVIDENCE COLLECT case=$case_id ====="
    "$python_bin" "$evidence_py" "${collect_args[@]}"
  fi
done

echo "===== KDEBUG EVIDENCE SUITE VALIDATION ====="
"$python_bin" "$evidence_py" validate-suite \
  --suite-root "$suite_root" \
  --cases "$(IFS=,; echo "${case_list[*]}")"

declare -a task_model=()
declare -a task_group=()
declare -a task_case=()
declare -A model_next_epoch=()
declare -A model_retry_count=()

for model in "${model_list[@]}"; do
  model_next_epoch["$model"]=0
  model_retry_count["$model"]=0
done

retry_budget_status() {
  local model="$1"
  local group="$2"
  local case_id="$3"
  if [[ ! -f "$results_csv" ]]; then
    echo "PENDING cumulative_elapsed_sec=0.000 retry_later_attempts=0 remaining_sec=$timeout_sec"
    return 0
  fi
  "$python_bin" "$retry_budget_py" \
    --results "$results_csv" \
    --model "$model" \
    --group "$group" \
    --case-id "$case_id" \
    --timeout "$timeout_sec" \
    --mark-timeout
}

task_already_closed() {
  local model="$1"
  local group="$2"
  local case_id="$3"
  local status
  status="$(retry_budget_status "$model" "$group" "$case_id")"
  case "$status" in
    DONE*|MARKED_TIMEOUT*)
      echo "===== SKIP model=$model group=$group case=$case_id: $status ====="
      return 0
      ;;
  esac
  return 1
}

for case_id in "${case_list[@]}"; do
  case_dir="$suite_root/$case_id"
  if [[ ! -d "$case_dir" ]]; then
    echo "ERROR: missing case dir $case_dir" >&2
    exit 2
  fi
  for model in "${model_list[@]}"; do
    for group in "${groups[@]}"; do
      if task_already_closed "$model" "$group" "$case_id"; then
        continue
      fi
      task_model+=("$model")
      task_group+=("$group")
      task_case+=("$case_id")
    done
  done
done

check_model_key() {
  local model="$1"
  if [[ "$model" == "gpt-5.5" ]]; then
    if [[ -z "${GPT55_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
      echo "ERROR: GPT55_API_KEY or OPENAI_API_KEY is required for gpt-5.5" >&2
      exit 2
    fi
  else
    if [[ -z "${MAAS_API_KEY:-}" && -z "${AIAPI_API_KEY:-}" ]]; then
      echo "ERROR: MAAS_API_KEY is required for $model" >&2
      exit 2
    fi
    export MAAS_BASE_URL="${MAAS_BASE_URL:-${AIAPI_BASE_URL:-https://maas-coding-api.cn-huabei-1.xf-yun.com/v2}}"
  fi
}

run_one_task() {
  local model="$1"
  local group="$2"
  local case_id="$3"
  local effective_timeout="${4:-$timeout_sec}"
  local case_dir="$suite_root/$case_id"

  check_model_key "$model"
  export RUN_AGENT_CMD="\"$python_bin\" \"$bench_root/scripts/api_model_runner.py\" --model \"\$MODEL\" --repair-dir \"\$REPAIR_DIR\" --group \"\$GROUP\" --timeout \"\$TIMEOUT_SEC\" --results-csv \"$results_csv\""
  export RESULTS_CSV="$results_csv"

  echo "===== RUN model=$model group=$group case=$case_id timeout=$effective_timeout ====="
  set +e
  bash "$bench_root/scripts/run_repair_trial.sh" \
    --suite "$(basename "$suite_root")" \
    --case-dir "$case_dir" \
    --repair-root "$repair_root" \
    --model "$model" \
    --group "$group" \
    --timeout "$effective_timeout"
  local rc=$?
  echo "===== DONE rc=$rc model=$model group=$group case=$case_id ====="
  return "$rc"
}

compact_task_queue() {
  local -a new_model=()
  local -a new_group=()
  local -a new_case=()
  local j

  for j in "${!task_model[@]}"; do
    new_model+=("${task_model[$j]}")
    new_group+=("${task_group[$j]}")
    new_case+=("${task_case[$j]}")
  done

  task_model=()
  task_group=()
  task_case=()
  if ((${#new_model[@]} > 0)); then
    task_model=("${new_model[@]}")
    task_group=("${new_group[@]}")
    task_case=("${new_case[@]}")
  fi
}

while ((${#task_model[@]} > 0)); do
  now="$(date +%s)"
  selected=-1
  earliest=0

  for i in "${!task_model[@]}"; do
    model="${task_model[$i]}"
    next="${model_next_epoch[$model]:-0}"
    if (( next <= now )); then
      selected="$i"
      break
    fi
    if (( earliest == 0 || next < earliest )); then
      earliest="$next"
    fi
  done

  if (( selected < 0 )); then
    sleep_sec=$((earliest - now))
    (( sleep_sec < 1 )) && sleep_sec=1
    echo "===== ALL_PENDING_MODELS_RATE_LIMITED sleep=${sleep_sec}s ====="
    sleep "$sleep_sec"
    continue
  fi

  model="${task_model[$selected]}"
  group="${task_group[$selected]}"
  case_id="${task_case[$selected]}"

  budget_status="$(retry_budget_status "$model" "$group" "$case_id")"
  if [[ "$budget_status" == MARKED_TIMEOUT* || "$budget_status" == DONE* ]]; then
    echo "===== BUDGET_PRECHECK_CLOSED model=$model group=$group case=$case_id: $budget_status ====="
    unset 'task_model[selected]'
    unset 'task_group[selected]'
    unset 'task_case[selected]'
    compact_task_queue
    continue
  fi
  task_timeout="$timeout_sec"
  if [[ "$budget_status" =~ remaining_sec=([0-9]+) ]]; then
    task_timeout="${BASH_REMATCH[1]}"
  fi

  set +e
  run_one_task "$model" "$group" "$case_id" "$task_timeout"
  rc=$?
  set -e

  if [[ "$rc" -eq "$RETRY_LATER_EXIT_CODE" ]]; then
    budget_status="$(retry_budget_status "$model" "$group" "$case_id")"
    if [[ "$budget_status" == MARKED_TIMEOUT* || "$budget_status" == DONE* ]]; then
      echo "===== CUMULATIVE_RETRY_BUDGET_CLOSED model=$model group=$group case=$case_id: $budget_status ====="
      unset 'task_model[selected]'
      unset 'task_group[selected]'
      unset 'task_case[selected]'
      compact_task_queue
      continue
    fi
    retry_count="${model_retry_count[$model]:-0}"
    retry_count=$((retry_count + 1))
    model_retry_count["$model"]="$retry_count"
    model_next_epoch["$model"]=$(( $(date +%s) + rate_limit_sleep_sec ))
    echo "===== RATE_LIMIT model=$model group=$group case=$case_id retry_count=$retry_count $budget_status: skip this model until epoch=${model_next_epoch[$model]} and continue other models ====="
    continue
  fi

  budget_status="$(retry_budget_status "$model" "$group" "$case_id")"
  echo "===== FINALIZED model=$model group=$group case=$case_id: $budget_status ====="

  unset 'task_model[selected]'
  unset 'task_group[selected]'
  unset 'task_case[selected]'
  compact_task_queue
done

"$report_python" "$bench_root/scripts/capture_terminal_screenshots.py" \
  --results "$results_csv" \
  --log-root "$repair_root" \
  --out-dir "$screenshot_dir" \
  --overwrite \
  --require-logs

"$report_python" "$bench_root/scripts/generate_word_reports.py" \
  --results "$results_csv" \
  --screenshots "$screenshot_dir" \
  --out-dir "$docx_dir" \
  --require-screenshots

"$python_bin" "$bench_root/scripts/summarize_results.py" "$results_csv" \
  --out "$suite_root/summary.md"

echo "RESULTS: $results_csv"
echo "SCREENSHOTS: $screenshot_dir"
echo "DOCX: $docx_dir"
