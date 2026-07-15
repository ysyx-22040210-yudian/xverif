#!/bin/bash
# 批量运行 ksva VCS 测试
# 要求: VCS 在 PATH 中，VERDI_HOME 已设置

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "ksva VCS Test Suite"
echo "==================="

for case_dir in "$SCRIPT_DIR"/cases/*/; do
    c=$(basename "$case_dir")
    echo ""
    echo "--- $c ---"
    make -C "$SCRIPT_DIR" cmp CASE="$c" 2>&1 | tail -1
    make -C "$SCRIPT_DIR" run CASE="$c" 2>&1 | grep -i "assertion\|Summary\|FAIL\|PASS" || true
done

echo ""
echo "==================="
echo "VCS test suite complete"
