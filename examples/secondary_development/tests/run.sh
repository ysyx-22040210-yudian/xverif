#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
example_root="$(cd "$script_dir/.." && pwd)"
json_helper="$example_root/json_response.py"
if [[ -n "${KVERIF_JSON_PYTHON:-}" ]]; then
  json_python="$KVERIF_JSON_PYTHON"
elif [[ -n "${PYTHON:-}" ]]; then
  json_python="$PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  json_python=python3
else
  json_python=python
fi

for command_name in bash perl "$json_python"; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "ERROR: required test command is missing: $command_name" >&2
    exit 2
  }
done

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
chmod +x "$script_dir/fake_kdebug.sh" "$script_dir/fake_kcov.sh"
touch "$tmp_dir/waves.fsdb" "$tmp_dir/simv.daidir" "$tmp_dir/run1.vdb" "$tmp_dir/run2.vdb"

KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/signal_health.sh" \
    --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --min-changes 2 --max-unknown 0 --require-complete \
    --out "$tmp_dir/signal-health-sh"

if command -v csh >/dev/null 2>&1; then
  KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
  KVERIF_JSON_PYTHON="$json_python" \
    csh "$example_root/csh/signal_health.csh" \
      --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
      --begin 0ns --end 100ns --min-changes 2 --max-unknown 0 --require-complete \
      --out "$tmp_dir/signal-health-csh"
else
  echo "SKIP: csh signal-health contract (csh is not installed)"
fi

KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  perl "$example_root/perl/signal_health.pl" \
    --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --min-changes 2 --max-unknown 0 --require-complete \
    --out "$tmp_dir/signal-health-perl"

KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
  "$json_python" "$example_root/py/signal_health.py" \
    --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --min-changes 2 --max-unknown 0 --require-complete \
    --out "$tmp_dir/signal-health-python"

KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/waveform_window.sh" \
    --fsdb "$tmp_dir/waves.fsdb" \
    --signal tb.dut.valid --signal tb.dut.ready \
    --begin 0ns --end 100ns --time 50ns \
    --min-changes 1 --max-unknown 0 --require-complete \
    --out "$tmp_dir/wave-sh"

KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/module_connectivity.sh" \
    --daidir "$tmp_dir/simv.daidir" \
    --signal tb.dut.valid --signal tb.dut.ready \
    --require-edge --require-complete \
    --out "$tmp_dir/connectivity-sh"

KCOV_BIN="$script_dir/fake_kcov.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/coverage_convergence.sh" \
    --run base="$tmp_dir/run1.vdb" \
    --run next="$tmp_dir/run2.vdb" \
    --fail-under 80 --max-final-holes 20 --max-regression 0 --require-growth \
    --out "$tmp_dir/coverage-sh"

KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
KCOV_BIN="$script_dir/fake_kcov.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/regression_triage.sh" \
    --fsdb "$tmp_dir/waves.fsdb" \
    --daidir "$tmp_dir/simv.daidir" \
    --vdb "$tmp_dir/run2.vdb" \
    --signal tb.dut.valid --signal tb.dut.ready \
    --begin 0ns --end 100ns --time 50ns \
    --min-changes 1 --fail-under 80 --max-final-holes 20 \
    --out "$tmp_dir/triage-sh"

KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
  perl "$example_root/perl/waveform_window.pl" \
    --fsdb "$tmp_dir/waves.fsdb" \
    --signal tb.dut.valid --signal tb.dut.ready \
    --begin 0ns --end 100ns --time 50ns \
    --out "$tmp_dir/wave-perl"

"$json_python" "$json_helper" check-ok "$tmp_dir/wave-sh/scan.tb.dut.valid.json"
"$json_python" "$json_helper" check-ok "$tmp_dir/connectivity-sh/driver.tb.dut.valid.json"
[[ "$(wc -l < "$tmp_dir/coverage-sh/runs.ndjson")" -eq 2 ]]
"$json_python" "$json_helper" coverage-gate \
  --report "$tmp_dir/coverage-sh/convergence.json" --target 80
"$json_python" "$json_helper" check-ok "$tmp_dir/wave-perl/scan.tb.dut.valid.json"
test -s "$tmp_dir/triage-sh/report.json"

for language in sh perl python; do
  status_value="$("$json_python" "$json_helper" json-value \
    --file "$tmp_dir/signal-health-$language/conclusion.json" \
    --path conclusion.status)"
  [[ "$status_value" == HEALTHY ]]
done
if command -v csh >/dev/null 2>&1; then
  [[ "$("$json_python" "$json_helper" json-value \
    --file "$tmp_dir/signal-health-csh/conclusion.json" \
    --path conclusion.status)" == HEALTHY ]]
fi

set +e
FAKE_KDEBUG_UNKNOWN_COUNT=2 \
KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
  "$json_python" "$example_root/py/signal_health.py" \
    --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --max-unknown 0 \
    --out "$tmp_dir/signal-health-python-fail"
failure_rc=$?
set -e
[[ "$failure_rc" -eq 3 ]]
[[ "$("$json_python" "$json_helper" json-value \
  --file "$tmp_dir/signal-health-python-fail/conclusion.json" \
  --path conclusion.status)" == UNKNOWN_VALUES ]]

set +e
FAKE_KDEBUG_CHANGE_COUNT=0 \
KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  bash "$example_root/sh/signal_health.sh" \
    --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --min-changes 1 \
    --out "$tmp_dir/signal-health-sh-fail"
failure_rc=$?
set -e
[[ "$failure_rc" -eq 3 ]]
[[ "$("$json_python" "$json_helper" json-value \
  --file "$tmp_dir/signal-health-sh-fail/conclusion.json" \
  --path conclusion.status)" == INACTIVE ]]

set +e
FAKE_KDEBUG_TRUNCATED=true \
KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
KVERIF_JSON_PYTHON="$json_python" \
  perl "$example_root/perl/signal_health.pl" \
    --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --require-complete \
    --out "$tmp_dir/signal-health-perl-fail"
failure_rc=$?
set -e
[[ "$failure_rc" -eq 3 ]]
[[ "$("$json_python" "$json_helper" json-value \
  --file "$tmp_dir/signal-health-perl-fail/conclusion.json" \
  --path conclusion.status)" == INCOMPLETE ]]

if command -v csh >/dev/null 2>&1; then
  set +e
  FAKE_KDEBUG_UNKNOWN_COUNT=2 \
  KDEBUG_BIN="$script_dir/fake_kdebug.sh" \
  KVERIF_JSON_PYTHON="$json_python" \
    csh "$example_root/csh/signal_health.csh" \
      --fsdb "$tmp_dir/waves.fsdb" --signal tb.dut.valid \
      --begin 0ns --end 100ns --max-unknown 0 \
      --out "$tmp_dir/signal-health-csh-fail"
  failure_rc=$?
  set -e
  [[ "$failure_rc" -eq 3 ]]
  [[ "$("$json_python" "$json_helper" json-value \
    --file "$tmp_dir/signal-health-csh-fail/conclusion.json" \
    --path conclusion.status)" == UNKNOWN_VALUES ]]
fi

# Prove that the examples do not rely on the repository layout. The copied
# tree, fake tool directory, working directory, inputs, and outputs all contain
# spaces; tools are discoverable only through PATH.
portable_root="$tmp_dir/relocated examples"
portable_bin="$tmp_dir/portable tool bin"
portable_work="$tmp_dir/unrelated working directory"
mkdir -p "$portable_root" "$portable_bin" "$portable_work/input data"
cp -R "$example_root/." "$portable_root/"
cp "$script_dir/fake_kdebug.sh" "$portable_bin/kdebug"
cp "$script_dir/fake_kcov.sh" "$portable_bin/kcov"
chmod +x "$portable_bin/kdebug" "$portable_bin/kcov"
touch "$portable_work/input data/waves.fsdb" \
  "$portable_work/input data/simv.daidir" \
  "$portable_work/input data/run1.vdb" \
  "$portable_work/input data/run2.vdb"

(
  unset KDEBUG_BIN KCOV_BIN KVERIF_HOME KVERIF_JSON_PYTHON KVERIF_JSON_HELPER
  export PYTHON="$json_python"
  export PATH="$portable_bin:$PATH"
  cd "$portable_work"

  bash "$portable_root/sh/signal_health.sh" \
    --fsdb "$portable_work/input data/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --min-changes 2 --require-complete \
    --out "$portable_work/reports/signal sh"

  perl "$portable_root/perl/signal_health.pl" \
    --fsdb "$portable_work/input data/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --min-changes 2 --require-complete \
    --out "$portable_work/reports/signal perl"

  "$json_python" "$portable_root/py/signal_health.py" \
    --fsdb "$portable_work/input data/waves.fsdb" --signal tb.dut.valid \
    --begin 0ns --end 100ns --min-changes 2 --require-complete \
    --out "$portable_work/reports/signal python"

  if command -v csh >/dev/null 2>&1; then
    csh "$portable_root/csh/signal_health.csh" \
      --fsdb "$portable_work/input data/waves.fsdb" --signal tb.dut.valid \
      --begin 0ns --end 100ns --min-changes 2 --require-complete \
      --out "$portable_work/reports/signal csh"
  fi

  bash "$portable_root/sh/waveform_window.sh" \
    --fsdb "$portable_work/input data/waves.fsdb" \
    --signal tb.dut.valid --begin 0ns --end 100ns --time 50ns \
    --min-changes 1 --require-complete \
    --out "$portable_work/reports/waveform"

  bash "$portable_root/sh/module_connectivity.sh" \
    --daidir "$portable_work/input data/simv.daidir" \
    --signal tb.dut.valid --require-edge --require-complete \
    --out "$portable_work/reports/connectivity"

  bash "$portable_root/sh/coverage_convergence.sh" \
    --run "base=$portable_work/input data/run1.vdb" \
    --run "next=$portable_work/input data/run2.vdb" \
    --fail-under 80 --max-final-holes 20 --max-regression 0 --require-growth \
    --out "$portable_work/reports/coverage"

  bash "$portable_root/sh/regression_triage.sh" \
    --fsdb "$portable_work/input data/waves.fsdb" \
    --daidir "$portable_work/input data/simv.daidir" \
    --vdb "$portable_work/input data/run2.vdb" \
    --signal tb.dut.valid --begin 0ns --end 100ns --time 50ns \
    --min-changes 1 --fail-under 80 --max-final-holes 20 \
    --out "$portable_work/reports/triage"

  perl "$portable_root/perl/waveform_window.pl" \
    --fsdb "$portable_work/input data/waves.fsdb" \
    --signal tb.dut.valid --begin 0ns --end 100ns --time 50ns \
    --out "$portable_work/reports/waveform perl"
)

for report in \
  "$portable_work/reports/signal sh/conclusion.json" \
  "$portable_work/reports/signal perl/conclusion.json" \
  "$portable_work/reports/signal python/conclusion.json" \
  "$portable_work/reports/waveform/report.json" \
  "$portable_work/reports/connectivity/report.json" \
  "$portable_work/reports/coverage/convergence.json" \
  "$portable_work/reports/triage/report.json" \
  "$portable_work/reports/waveform perl/scan.tb.dut.valid.json"; do
  test -s "$report"
done
if command -v csh >/dev/null 2>&1; then
  test -s "$portable_work/reports/signal csh/conclusion.json"
fi

echo "PASS: CLI secondary-development examples"
