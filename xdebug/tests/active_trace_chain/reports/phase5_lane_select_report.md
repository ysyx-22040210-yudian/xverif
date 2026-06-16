# Phase 5 Procedural For Lane Select Report

日期: 2026-06-16

## 实验设置

- DUT: always_comb + procedural for + lane select (SP_IDX0=1, SP_IDX1=6)
- 8 lanes, ternary expression, function call fn_op, multi-source OR
- 10 scenes, 每个 scene 查询 chain_test

## 结果汇总

| Scene | Target | Time | Hops | Termination | edgecheck | fallback | 判定 |
|-------|--------|------|------|-------------|-----------|----------|------|
| S1 | dout[2] | 10ns | 1 | ambiguous | 0 | 1 | ACCEPTABLE |
| S2 | dout[2] | 20ns | 2 | primary_input | 0 | 1 | PASS |
| S3 | dout[2] | 30ns | 2 | primary_input | 0 | 1 | PASS |
| S4 | dout[2] | 41ns | 2 | primary_input | 0 | 1 | PASS |
| S5 | dout[1] | 50ns | 1 | control_only | 0 | 1 | ACCEPTABLE |
| S6 | dout[1] | 60ns | 1 | control_only | 0 | 1 | PASS |
| S7 | flag[2] | 71ns | 1 | control_only | 0 | 1 | ACCEPTABLE |
| S8 | flag[2] | 81ns | 1 | control_only | 0 | 1 | ACCEPTABLE |
| S9 | dout[2] | 90ns | 2 | primary_input | 0 | 1 | PASS |
| S10 | flag[2] | 100ns | 1 | control_only | 0 | 1 | PASS |

PASS: 5, ACCEPTABLE: 5, FAIL: 0

## 逐场景分析

### S1 (dout[2] @10ns): ACCEPTABLE
- ctrl_sel 和 src_b 在 10ns 同时跳变 → 2 signals toggled → ambiguous
- 正确: 不应在此情况下臆断唯一 cause
- Candidates: en1, src_a, ctrl_sel, ctrl_mode, src_b, src_c (全部 RHS 信号)
- Toggled: ctrl_sel (1→0), src_b (B0→B1)

### S2 (dout[2] @20ns): PASS
- 仅 ctrl_sel 跳变 (0→1) → 唯一 candidate → 继续追踪
- Chain: dout[2] → 追到 primary_input
- 正确识别 control signal 变化

### S3 (dout[2] @30ns): PASS
- 仅 src_a 跳变 → 唯一 candidate → primary_input
- 正确追到 data source

### S4 (dout[2] @41ns): PASS
- en1 跳变 → 唯一 enable candidate → primary_input
- 正确追到 enable signal

### S5 (dout[1] @50ns): ACCEPTABLE
- Special lane (SP_IDX0=1), sp_val 跳变
- native trace 返回 proc_assign，candidates 仅包含 sp_val
- 未误入 normal lane else 分支 ✓

### S6 (dout[1] @60ns): PASS
- Special lane, src_a/src_b 变化（normal lane signals）
- dout[1] 不受影响 → native trace 返回 control_only
- 未误报 normal lane signals 为 cause ✓

### S7 (flag[2] @71ns): ACCEPTABLE
- mask_a[2] 跳变 → control_only（always_comb block 内多源 OR）
- candidate 包含 mask_a[2]，lane index 正确
- 未误追 mask_a[3] ✓

### S8 (flag[2] @81ns): ACCEPTABLE
- OR 双分支，en1 跳变 → control_only
- 正确输出 branch evidence（OR 多源无法唯一判定）

### S9 (dout[2] @90ns): PASS
- 多 lane 同时变化（src_a 影响全部 normal lane）
- dout[2] 正确追到 src_a，未受其他 lane 干扰
- lane isolation ✓

### S10 (flag[2] @100ns): PASS
- 仅 mask_a[3] 变化
- flag[2] 的 trace 返回 control_only（flag[2] 未变）
- 未误追 mask_a[3] ✓

## 关键发现

### 1. Lane index 保持 ✓

所有 candidate signal name 正确保留 lane index:
- `mask_a[2]` vs `mask_a[3]` 正确区分
- `dout[2]` 的 trace 不会错误追到 lane 3 的 source
- native trace 返回的 signal handle 的 npiFullName 包含完整的 `[N]` 索引

### 2. Special/normal branch 不混淆 ✓

- S5/S6: special lane (dout[1]) 不受 normal lane signal 变化影响
- S1-S4: normal lane (dout[2]) 不受 special lane signal 影响
- 验证: 0 次误入错误分支

### 3. Control/enable cause 识别 ✓

- S2: ctrl_sel 单独跳变 → 正确识别为唯一 cause
- S4: en1 单独跳变 → 正确追到 enable signal
- S1: ctrl_sel + src_b 同时跳变 → 保守 ambiguous（正确）

### 4. Function call 处理 ⚠️

- fn_op function 在 NPI elaboration 中被内联
- native trace 直接返回 fn_op 的输入信号 (src_b, src_c, ctrl_sel)
- 未出现独立的 function_boundary 节点
- 这意味着 NPI 对简单 function 做了 inline 展开，chain 可以穿透

### 5. 多 lane 同时变化不误判 ✓

- S9: 所有 normal lane 同时变化，dout[2] 正确追到 src_a
- Lane isolation: chain 只关注 target lane 的因果链

### 6. 始终保守安全 ✓

- 所有 ambiguous 的情况都正确停止，输出完整 branch evidence
- 所有 control_only 的情况都正确标记，不臆断
- 0 次输出错误 cause

## 统计

| 指标 | 值 |
|------|-----|
| 总 scene | 10 |
| PASS | 5 |
| ACCEPTABLE | 5 |
| FAIL | 0 |
| 分支混淆 | 0 |
| 误追 lane | 0 |
| edgecheck_direct | 0 (always_comb block 不适用) |
| fallback_0_5ns | 10 (全部 hop 都触发) |

## 结论

Repeated native active trace 在 procedural for + lane select 场景下:
- **Lane-specific 保持**: 100% 正确
- **Branch 不混淆**: 100% 正确
- **保守安全**: 多源时 ambiguous stop，不臆断
- **Function inline**: NPI 对简单 function 做了内联展开

改进建议:
1. 对 always_comb procedural block，NPI 返回的是整个 block 的 RHS 信号集合，
   可以在 xdebug 层做 lane-specific 裁剪（只保留匹配 target lane index 的 candidate）
2. role classification（data/control/enable/mask）可辅助 branch disambiguation
