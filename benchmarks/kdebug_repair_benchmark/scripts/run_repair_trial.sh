#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run_repair_trial.sh --suite NAME --case-dir DIR --repair-root DIR --group with_kdebug|without_kdebug --model MODEL [--timeout 3600]

The script creates/uses:
  <repair-root>/<model>/<group>/<case_id>/

The model/agent is expected to work inside that repair directory and run the
case-local scripts. This wrapper enforces the timeout around the supplied
RUN_AGENT_CMD command.

Environment:
  RUN_AGENT_CMD   Command that launches the model/agent for this repair dir.
                  It receives CASE_DIR, REPAIR_DIR, GROUP, MODEL, and TIMEOUT_SEC.
  RESULTS_CSV     Optional CSV path. If set, append a standard result row.
  KDEBUG_PYTHON   Python 3.8+ executable used by wrapper helpers. PYTHON is the
                  fallback; default: python3.

If RUN_AGENT_CMD is not set, the script only prepares the workdir and exits 2.
USAGE
}

RETRY_LATER_EXIT_CODE=75
python_bin="${KDEBUG_PYTHON:-${PYTHON:-python3}}"
suite=""
case_dir=""
repair_root=""
group=""
model=""
timeout_sec=3600

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite) suite="$2"; shift 2 ;;
    --case-dir) case_dir="$2"; shift 2 ;;
    --repair-root) repair_root="$2"; shift 2 ;;
    --group) group="$2"; shift 2 ;;
    --model) model="$2"; shift 2 ;;
    --timeout) timeout_sec="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$suite" || -z "$case_dir" || -z "$repair_root" || -z "$group" || -z "$model" ]]; then
  usage >&2
  exit 2
fi

if [[ "$group" != "with_kdebug" && "$group" != "without_kdebug" ]]; then
  echo "ERROR: group must be with_kdebug or without_kdebug" >&2
  exit 2
fi
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "ERROR: benchmark Python executable not found: $python_bin" >&2
  exit 2
fi

case_id="$(basename "$case_dir")"
repair_dir="$repair_root/$model/$group/$case_id"
trial_log="$repair_dir/trial.log"
metrics_file="$repair_dir/trial_metrics.env"

slim_retry_later_dir() {
  local dir="$1"
  [[ -n "$dir" && -d "$dir" ]] || return 0
  case "$(readlink -f "$dir")" in
    "$(readlink -f "$repair_root")"/*) ;;
    *) echo "Refusing to slim unexpected path: $dir" >> "${trial_log:-/dev/null}"; return 0 ;;
  esac

  # RETRY_LATER workdirs are kept for evidence and later retry, but fullchip
  # FIR and VCS compile products are reproducible and can exceed several GB.
  find "$dir/rtl" -maxdepth 1 -type f \( -name '*.fir' -o -name '*.anno.json' \) -delete 2>/dev/null || true
  rm -rf \
    "$dir/out/simv.daidir" \
    "$dir/out/csrc" \
    "$dir/simv.daidir" \
    "$dir/kdebug.daidir" \
    "$dir/simv-compile" \
    "$dir/csrc" \
    "$dir/DVEfiles" \
    "$dir/verdiLog" \
    "$dir/ucli.key"
}

archive_existing_retry_later() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0
  local status=""
  local metrics_json=""
  if [[ -d "$dir/agent_logs" ]]; then
    metrics_json="$(find "$dir/agent_logs" -maxdepth 1 -name '*_metrics.json' -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"
  fi
  if [[ -n "$metrics_json" ]]; then
    status="$("$python_bin" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("final_status", ""))' "$metrics_json" 2>/dev/null || true)"
  elif [[ -f "$dir/trial_metrics.env" ]]; then
    status="$(awk -F= '$1=="final_status"{print $2}' "$dir/trial_metrics.env" | tail -1)"
  fi
  if [[ "$status" == "RETRY_LATER" ]]; then
    local stamp archive_dir
    stamp="$(date +%Y%m%d_%H%M%S)"
    archive_dir="$repair_root/_retry_later_archive/$model/$group/$case_id/$stamp"
    slim_retry_later_dir "$dir"
    mkdir -p "$(dirname "$archive_dir")"
    mv "$dir" "$archive_dir"
    echo "Archived previous RETRY_LATER repair dir to $archive_dir"
  fi
}

mkdir -p "$(dirname "$repair_dir")"
archive_existing_retry_later "$repair_dir"
rm -rf "$repair_dir"
mkdir -p "$repair_dir"
if ! cp -al "$case_dir"/. "$repair_dir"/ 2>/dev/null; then
  rm -rf "$repair_dir"
  cp -a "$case_dir" "$repair_dir"
fi

copy_private_tree() {
  local src="$1"
  local dst="$2"
  [[ -e "$src" ]] || return 0
  rm -rf "$dst"
  if ! cp -a --reflink=auto "$src" "$dst" 2>/dev/null; then
    cp -a "$src" "$dst"
  fi
}

# The repair loop may edit RTL and, for env/mixed cases, case-local build/run
# environment files. The initial workspace may use hardlinks to save disk, but
# mutable trees must be private so a repair cannot alter the original failing
# case or sibling trials.
copy_private_tree "$case_dir/rtl" "$repair_dir/rtl"
copy_private_tree "$case_dir/scripts" "$repair_dir/scripts"
copy_private_tree "$case_dir/env" "$repair_dir/env"
copy_private_tree "$case_dir/config" "$repair_dir/config"
copy_private_tree "$case_dir/filelists" "$repair_dir/filelists"
copy_private_tree "$case_dir/tb" "$repair_dir/tb"
copy_private_tree "$case_dir/cases" "$repair_dir/cases"
copy_private_tree "$case_dir/out" "$repair_dir/out"
copy_private_tree "$case_dir/run" "$repair_dir/run"
if [[ ! -f "$case_dir/build_kdb.sh" ]]; then
  copy_private_tree "$case_dir/simv" "$repair_dir/simv"
  copy_private_tree "$case_dir/simv.daidir" "$repair_dir/simv.daidir"
  copy_private_tree "$case_dir/simv-compile" "$repair_dir/simv-compile"
  copy_private_tree "$case_dir/csrc" "$repair_dir/csrc"
fi
for helper_file in Makefile makefile filelist.f vcs_args.f run_args.txt build_kdb.sh run_case.sh vcs_command.sh; do
  copy_private_tree "$case_dir/$helper_file" "$repair_dir/$helper_file"
done

rewrite_repair_local_paths() {
  local dir="$1"
  "$python_bin" - "$dir" <<'PY'
import re
import sys
from pathlib import Path

repair = Path(sys.argv[1]).resolve()
case_path_patterns = [
    re.compile(r"/root/XiangShan-build/build/kverif_fault_campaign/[^\s\"']*?/case_[0-9]{3}"),
    re.compile(r"/root/XiangShan-build/build/kverif_benchmark/[^\s\"']*?/case_[0-9]{3}"),
    re.compile(r"/home/host/kverif_runs/[^\s\"']*?/case_[0-9]{3}"),
]
paths = []
for rel in ("vcs_command.sh", "build_kdb.sh", "run_case.sh", "Makefile", "makefile", "filelist.f", "vcs_args.f", "run_args.txt"):
    p = repair / rel
    if p.is_file():
        paths.append(p)
scripts = repair / "scripts"
if scripts.is_dir():
    paths.extend(p for p in scripts.rglob("*") if p.is_file() and p.suffix.lower() in {".sh", ".bash", ".py", ".tcl", ".mk", ".f", ".args", ".txt", ".json", ".yaml", ".yml", ".cfg", ".ini", ".env"})
for dirname in ("env", "config", "filelists"):
    root = repair / dirname
    if root.is_dir():
        paths.extend(p for p in root.rglob("*") if p.is_file())

for p in paths:
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = p.read_text(encoding="utf-8", errors="replace")
    new_text = text
    for old_case_path in case_path_patterns:
        new_text = old_case_path.sub(str(repair), new_text)
    if new_text != text:
        p.write_text(new_text, encoding="utf-8")
PY
}

rewrite_repair_local_paths "$repair_dir"
find "$repair_dir/rtl" -maxdepth 1 -type f \( -name '*.fir' -o -name '*.anno.json' \) -delete 2>/dev/null || true
find "$repair_dir/scripts" -type f -name '*.sh' -exec chmod u+x {} + 2>/dev/null || true
if [[ -f "$repair_dir/out/simv" ]]; then
  chmod u+x,go+x "$repair_dir/out/simv" || true
fi
if [[ -f "$repair_dir/simv" ]]; then
  chmod u+x,go+x "$repair_dir/simv" || true
fi
for helper in build_kdb.sh run_case.sh vcs_command.sh; do
  [[ -f "$repair_dir/$helper" ]] && chmod u+x "$repair_dir/$helper" || true
done
if [[ "${KDEBUG_ENABLE_BASELINE_GIT:-0}" == "1" ]] && command -v git >/dev/null 2>&1; then
  (
    cd "$repair_dir"
    git init -q
    git config user.email "kdebug-benchmark@example.invalid"
    git config user.name "kdebug-benchmark"
    git add .
    git commit -q -m "baseline failing case" || true
  )
fi

slim_repair_dir() {
  local dir="$1"
  [[ "${KDEBUG_KEEP_REPAIR_RTL:-0}" == "1" ]] && return 0
  [[ -n "$dir" && -d "$dir" ]] || return 0
  case "$(readlink -f "$dir")" in
    "$(readlink -f "$repair_root")"/*) ;;
    *) echo "Refusing to slim unexpected path: $dir" >> "$trial_log"; return 0 ;;
  esac
  rm -rf \
    "$dir/.git" \
    "$dir/rtl" \
    "$dir/out" \
    "$dir/build" \
    "$dir/run" \
    "$dir/simv" \
    "$dir/simv.daidir" \
    "$dir/kdebug.daidir" \
    "$dir/simv-compile" \
    "$dir/csrc" \
    "$dir/ucli.key" \
    "$dir/DVEfiles" \
    "$dir/verdiLog"
}

start_epoch="$(date +%s)"
start_time="$(date -Is)"

cat > "$metrics_file" <<EOF
suite=$suite
case_id=$case_id
group=$group
model=$model
timeout_sec=$timeout_sec
start_time=$start_time
EOF

if [[ -z "${RUN_AGENT_CMD:-}" ]]; then
  echo "Prepared repair dir: $repair_dir" | tee "$trial_log"
  echo "RUN_AGENT_CMD is not set; no model/agent was launched." | tee -a "$trial_log"
  exit 2
fi

agent_rc_file="$repair_dir/.agent_rc"
rm -f "$agent_rc_file"
(
  set +e
  CASE_DIR="$case_dir" REPAIR_DIR="$repair_dir" GROUP="$group" MODEL="$model" TIMEOUT_SEC="$timeout_sec" \
    timeout "$timeout_sec" bash -lc "$RUN_AGENT_CMD"
  rc=$?
  printf '%s\n' "$rc" > "$agent_rc_file"
  exit 0
) > "$trial_log" 2>&1
cat "$trial_log"
agent_rc="$(cat "$agent_rc_file" 2>/dev/null || printf '1')"
case "$agent_rc" in
  ''|*[!0-9]*) agent_rc=1 ;;
esac

end_epoch="$(date +%s)"
end_time="$(date -Is)"
elapsed_sec=$((end_epoch - start_epoch))

api_metrics_json=""
if [[ -d "$repair_dir/agent_logs" ]]; then
  api_metrics_json="$(find "$repair_dir/agent_logs" -maxdepth 1 -name '*_metrics.json' -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"
fi

judge_rc=1
final_status="INFRA_ERROR"
if [[ -n "$api_metrics_json" ]]; then
  while IFS='=' read -r key value; do
    case "$key" in
      final_judge_rc) judge_rc="$value" ;;
      final_status) final_status="$value" ;;
    esac
  done < <("$python_bin" -c 'import json, sys; metrics=json.load(open(sys.argv[1], encoding="utf-8")); print("final_judge_rc=%s" % metrics.get("final_judge_rc", "")); print("final_status=%s" % metrics.get("final_status", ""))' "$api_metrics_json")
else
  echo "ERROR: missing API metrics JSON; not running a second judge in wrapper" >> "$trial_log"
  if [[ "$agent_rc" -eq "$RETRY_LATER_EXIT_CODE" ]]; then
    final_status="RETRY_LATER"
  elif [[ "$agent_rc" -eq 124 || "$elapsed_sec" -ge "$timeout_sec" ]]; then
    final_status="TIMEOUT"
  else
    final_status="INFRA_ERROR"
  fi
fi

cat >> "$metrics_file" <<EOF
end_time=$end_time
elapsed_sec=$elapsed_sec
agent_rc=$agent_rc
final_judge_rc=$judge_rc
final_status=$final_status
repair_dir=$repair_dir
api_metrics_json=$api_metrics_json
EOF

if [[ -n "${RESULTS_CSV:-}" ]]; then
  if [[ "$final_status" != "RETRY_LATER" ]]; then
    "$python_bin" "$(dirname "$0")/collect_results.py" \
      --repair-root "$repair_root" \
      --out "$RESULTS_CSV" \
      --single "$repair_dir" >> "$trial_log" 2>&1 || true
  else
    echo "RETRY_LATER: keeping repair workdir and not appending final results yet" >> "$trial_log"
  fi
fi

if [[ "$final_status" != "RETRY_LATER" ]]; then
  slim_repair_dir "$repair_dir"
else
  slim_retry_later_dir "$repair_dir"
fi

echo "FINAL_STATUS=$final_status elapsed_sec=$elapsed_sec agent_rc=$agent_rc judge_rc=$judge_rc" | tee -a "$trial_log"

if [[ "$final_status" == "PASS" ]]; then
  exit 0
fi
if [[ "$final_status" == "RETRY_LATER" ]]; then
  exit "$RETRY_LATER_EXIT_CODE"
fi
exit 1
