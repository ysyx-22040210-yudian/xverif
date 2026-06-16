#!/usr/bin/env bash
# P0-2: module boundary
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHAIN_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMMON="$CHAIN_DIR/common"
ACTUAL="$CHAIN_DIR/actual/p0_2_module_boundary"

ROOT="$(cd "$CHAIN_DIR/../../../.." && pwd)"
XDEBUG="${XDEBUG:-$ROOT/tools/xdebug}"
if [ ! -x "$XDEBUG" ]; then XDEBUG="$ROOT/xdebug/xdebug"; fi

SESSION_ID="p0_2_$$"

mkdir -p "$ACTUAL"

make -C "$SCRIPT_DIR" fixture

"$XDEBUG" --json - > "$ACTUAL/session_open.json" <<JSON
{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"$SCRIPT_DIR/out/simv.daidir","fsdb":"$SCRIPT_DIR/out/waves.fsdb"},"args":{"name":"$SESSION_ID","reopen":true},"output":{"format":"json","verbosity":"compact"}}
JSON

python3 "$COMMON/run_xdebug_chain.py" "$SESSION_ID" "top.y" "10ns" "$ACTUAL"

python3 "$COMMON/verdict.py" \
  "$CHAIN_DIR/expected/p0_2_module_boundary.json" \
  "$ACTUAL/trace_chain.json" \
  "$ACTUAL/verdict.json"
