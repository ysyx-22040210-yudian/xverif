#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
example_root="$(cd "$script_dir/.." && pwd)"
json_helper="$example_root/json_response.py"
if [[ -n "${KVERIF_JSON_PYTHON:-}" ]]; then
  json_python="$KVERIF_JSON_PYTHON"
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

echo "PASS: CLI secondary-development examples"
