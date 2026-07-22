#!/usr/bin/env bash
set -euo pipefail

log="${1:-run/run.log}"
require_microbench="${2:-0}"

if [[ ! -f "$log" ]]; then
  echo "FAIL: missing log $log" >&2
  exit 1
fi

grep -q "HIT GOOD TRAP" "$log" || {
  echo "FAIL: missing HIT GOOD TRAP" >&2
  exit 1
}

grep -q "DIFFTEST WORKLOAD DONE" "$log" || {
  echo "FAIL: missing DIFFTEST WORKLOAD DONE" >&2
  exit 1
}

if [[ "$require_microbench" == "1" ]]; then
  grep -q "MicroBench PASS" "$log" || {
    echo "FAIL: missing MicroBench PASS" >&2
    exit 1
  }
fi

if grep -qiE "MISMATCH|ASSERT.*fail|Fatal|panic|HIT BAD TRAP|ABORT" "$log"; then
  echo "FAIL: failure marker found in full-chip log" >&2
  exit 1
fi

echo "PASS: full-chip workload passed"
