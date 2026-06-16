#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"; C="$(cd "$D/../.." && pwd)"
CM="$C/common"; A="$C/actual/p0_4_interface_modport"
R="$(cd "$C/../../.." && pwd)"; X="${XDEBUG:-$R/tools/xdebug}"
[ -x "$X" ] || X="$R/xdebug/xdebug"; mkdir -p "$A"
IFDIR="$R/xdebug/testdata/combined/interface_port_root"
[ -d "$IFDIR/out/simv.daidir" ] || make -C "$IFDIR" fixture
"$X" --json - > "$A/session_open.json" <<JSON
{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"$IFDIR/out/simv.daidir","fsdb":"$IFDIR/out/waves.fsdb"},"args":{"name":"p0_4_$$","reopen":true},"output":{"format":"json","verbosity":"compact"}}
JSON
python3 "$CM/run_xdebug_chain.py" "p0_4_$$" "if_root_tb.u_sink.observed_q" "30ns" "$A"
python3 "$CM/verdict.py" "$C/expected/p0_4_interface_modport.json" "$A/trace_chain.json" "$A/verdict.json"
