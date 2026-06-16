#!/usr/bin/env bash
# P0-4: interface + modport
# Reuses existing interface_port_root fixture
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHAIN_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMMON="$CHAIN_DIR/common"
ACTUAL="$CHAIN_DIR/actual/p0_4_interface_modport"

ROOT="$(cd "$CHAIN_DIR/../../../.." && pwd)"
XDEBUG="${XDEBUG:-$ROOT/tools/xdebug}"
if [ ! -x "$XDEBUG" ]; then XDEBUG="$ROOT/xdebug/xdebug"; fi

IF_FIXTURE="$ROOT/xdebug/testdata/combined/interface_port_root"
SESSION_ID="p0_4_$$"

mkdir -p "$ACTUAL"

# Reuse existing fixture (already built by combined-test)
if [ ! -d "$IF_FIXTURE/out/simv.daidir" ]; then
  echo "Building interface_port_root fixture..."
  make -C "$IF_FIXTURE" fixture
fi

"$XDEBUG" --json - > "$ACTUAL/session_open.json" <<JSON
{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"$IF_FIXTURE/out/simv.daidir","fsdb":"$IF_FIXTURE/out/waves.fsdb"},"args":{"name":"$SESSION_ID","reopen":true},"output":{"format":"json","verbosity":"compact"}}
JSON

python3 "$COMMON/run_xdebug_chain.py" "$SESSION_ID" "if_root_tb.u_sink.observed_q" "30ns" "$ACTUAL"

python3 "$COMMON/verdict.py" \
  "$CHAIN_DIR/expected/p0_4_interface_modport.json" \
  "$ACTUAL/trace_chain.json" \
  "$ACTUAL/verdict.json"
