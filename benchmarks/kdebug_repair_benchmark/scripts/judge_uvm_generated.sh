#!/usr/bin/env bash
set -euo pipefail

log="${1:-run/run.log}"
case_name="${2:-}"

if [[ ! -f "$log" ]]; then
  echo "FAIL: missing log $log" >&2
  exit 1
fi

if [[ -n "$case_name" ]]; then
  grep -q "XS_BENCH_PASS case=$case_name" "$log" || {
    echo "FAIL: missing XS_BENCH_PASS for $case_name" >&2
    exit 1
  }
else
  grep -q "XS_BENCH_PASS case=" "$log" || {
    echo "FAIL: missing XS_BENCH_PASS" >&2
    exit 1
  }
fi

grep -q "UVM_ERROR :    0" "$log" || {
  echo "FAIL: UVM_ERROR count is not zero" >&2
  exit 1
}

if grep -q "UVM_FATAL :    [1-9]" "$log"; then
  echo "FAIL: UVM_FATAL is non-zero" >&2
  exit 1
fi

echo "PASS: generated UVM case passed"
