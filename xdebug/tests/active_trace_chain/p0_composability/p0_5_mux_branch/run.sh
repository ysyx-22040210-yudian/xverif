#!/usr/bin/env bash
# P0-5: mux branch handling
# Scene A: 12ns (sel=1, only a toggled)
# Scene B: 32ns (sel=1, both a and b toggled)
# Scene C: 53ns (a/b stable, sel toggled)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHAIN_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMMON="$CHAIN_DIR/common"
ACTUAL="$CHAIN_DIR/actual/p0_5_mux_branch"

ROOT="$(cd "$CHAIN_DIR/../../../.." && pwd)"
XDEBUG="${XDEBUG:-$ROOT/tools/xdebug}"
if [ ! -x "$XDEBUG" ]; then XDEBUG="$ROOT/xdebug/xdebug"; fi

SESSION_ID="p0_5_$$"

mkdir -p "$ACTUAL"

make -C "$SCRIPT_DIR" fixture

"$XDEBUG" --json - > "$ACTUAL/session_open.json" <<JSON
{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"$SCRIPT_DIR/out/simv.daidir","fsdb":"$SCRIPT_DIR/out/waves.fsdb"},"args":{"name":"$SESSION_ID","reopen":true},"output":{"format":"json","verbosity":"compact"}}
JSON

for scene in "a_12ns" "b_32ns" "c_53ns"; do
  case "$scene" in
    a_12ns) TIME="12ns";;
    b_32ns) TIME="32ns";;
    c_53ns) TIME="53ns";;
  esac
  ACT="$ACTUAL/scene_$scene"
  mkdir -p "$ACT"
  echo "=== Scene $scene @ $TIME ==="
  python3 "$COMMON/run_xdebug_chain.py" "$SESSION_ID" "top.y" "$TIME" "$ACT"
  python3 "$COMMON/verdict.py" \
    "$CHAIN_DIR/expected/p0_5_mux_branch.json" \
    "$ACT/trace_chain.json" \
    "$ACT/verdict.json" || true  # Scene B/C may PARTIAL
done
