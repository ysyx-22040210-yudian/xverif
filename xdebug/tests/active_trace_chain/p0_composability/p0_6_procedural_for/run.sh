#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"; C="$(cd "$D/../.." && pwd)"
CM="$C/common"; A="$C/actual/p0_6_procedural_for"
R="$(cd "$C/../../.." && pwd)"; X="${XDEBUG:-$R/tools/xdebug}"
[ -x "$X" ] || X="$R/xdebug/xdebug"; mkdir -p "$A"
make -C "$D" fixture
"$X" --json - > "$A/session_open.json" <<JSON
{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"$D/out/simv.daidir","fsdb":"$D/out/waves.fsdb"},"args":{"name":"p0_6_$$","reopen":true},"output":{"format":"json","verbosity":"compact"}}
JSON
python3 "$CM/run_xdebug_chain.py" "p0_6_$$" "top.y" "15ns" "$A"
python3 "$CM/verdict.py" "$C/expected/p0_6_procedural_for.json" "$A/trace_chain.json" "$A/verdict.json"
