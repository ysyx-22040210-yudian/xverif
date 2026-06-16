#!/usr/bin/env bash
# P0-0: continuous assign chain
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHAIN_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMMON="$CHAIN_DIR/common"
ACTUAL="$CHAIN_DIR/actual/p0_0_assign_chain"

ROOT="$(cd "$CHAIN_DIR/../../../.." && pwd)"
XDEBUG="${XDEBUG:-$ROOT/tools/xdebug}"
if [ ! -x "$XDEBUG" ]; then XDEBUG="$ROOT/xdebug/xdebug"; fi

SESSION_ID="p0_0_$$"

mkdir -p "$ACTUAL"

# 1. Build fixture
make -C "$SCRIPT_DIR" fixture

# 2. Open session
echo "=== session.open ==="
"$XDEBUG" --json - > "$ACTUAL/session_open.json" <<JSON
{"api_version":"xdebug.v1","action":"session.open","target":{"daidir":"$SCRIPT_DIR/out/simv.daidir","fsdb":"$SCRIPT_DIR/out/waves.fsdb"},"args":{"name":"$SESSION_ID","reopen":true},"output":{"format":"json","verbosity":"compact"}}
JSON

# 3. Run chain
echo "=== run_xdebug_chain ==="
python3 "$COMMON/run_xdebug_chain.py" "$SESSION_ID" "top.out" "10ns" "$ACTUAL"

# 4. Verdict
echo "=== verdict ==="
python3 "$COMMON/verdict.py" \
  "$CHAIN_DIR/expected/p0_0_assign_chain.json" \
  "$ACTUAL/trace_chain.json" \
  "$ACTUAL/verdict.json"
