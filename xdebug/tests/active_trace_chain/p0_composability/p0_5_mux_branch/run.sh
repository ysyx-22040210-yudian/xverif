#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"; C="$(cd "$D/../.." && pwd)"
CM="$C/common"; A="$C/actual/p0_5_mux_branch"
R="$(cd "$C/../../.." && pwd)"; X="${XDEBUG:-$R/tools/xdebug}"
[ -x "$X" ] || X="$R/xdebug/xdebug"; mkdir -p "$A"
make -C "$D" fixture
"$X" --json - > "$A/session_open.json" <<JSON
{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"$D/out/simv.daidir","fsdb":"$D/out/waves.fsdb"},"args":{"name":"p0_5_$$","reopen":true},"output":{"format":"json","verbosity":"compact"}}
JSON
for sc in "a_12ns" "b_32ns" "c_53ns"; do
  case "$sc" in a_12ns) T="12ns";; b_32ns) T="32ns";; c_53ns) T="53ns";; esac
  ACT="$A/scene_$sc"; mkdir -p "$ACT"
  echo "=== Scene $sc @ $T ==="
  python3 "$CM/run_xdebug_chain.py" "p0_5_$$" "top.y" "$T" "$ACT"
  python3 "$CM/verdict.py" "$C/expected/p0_5_mux_branch.json" "$ACT/trace_chain.json" "$ACT/verdict.json" || true
done
