# Phase 5 Procedural For Lane Select Report

日期: 2026-06-16

## 实验设置

- DUT: always_comb + procedural for + lane select (SP_IDX0=1, SP_IDX1=6)
- 8 lanes, ternary expression, function call fn_op, multi-source OR
- 10 scenes, 每个 scene 查询 chain_test

## termination 含义

| termination | 含义 | 是否错误 |
|-------------|------|---------|
| `primary_input` | 链追到了最上游（input port / initial block），成功 | 正常结束 |
| `ambiguous` | ≥2 个 data candidate 同时跳变，无法唯一确定根因，保守停止 | 正确行为 |
| `control_only` | NPI 只返回了 if/case/event_control，没有具体赋值源 | 预期行为 |

### ambiguous 详解

以 S1 为例，`dout[2]` 的 RHS 有 6 个信号。NPI 返回全部 6 个，chain_test 对每个做 ±0.5ns 值比较。
结果 `ctrl_sel` 和 `src_b` 两个信号同时跳变，无法确定唯一根因，`termination="ambiguous"`。

这是**正确行为**，不是错误。chain_test 的规则是"禁止因为某个 candidate toggled 就无条件选它"。

ambiguous 返回的完整 JSON：

```json
{
  "chain": [{
    "hop": 0,
    "signal": "top.u_dut.dout[2]",
    "requested_time": "10ns",
    "active_time": "10.0n",
    "value": "00000001",
    "value_known": true,
    "driver_kind": "proc_assign",
    "file": ".../phase5/dut.sv",
    "line": 37,
    "text": "npiAssignment, top.u_dut.lane_proc...dout[ln] = (en1 & ((ctrl_sel | ctrl_mode) ? src_a : fn_op(src_b, src_c, ctrl_sel)));..."
  }],
  "branch_evidence": [{
    "signal": "top.u_dut.dout[2]",
    "time": "10ns",
    "reason": "2 signals toggled simultaneously",
    "candidates": [
      {"name": "top.u_dut.en1",       "before": "1",        "after": "1",        "toggled": false},
      {"name": "top.u_dut.src_a",     "before": "10100000", "after": "10100000", "toggled": false},
      {"name": "top.u_dut.ctrl_sel",  "before": "1",        "after": "0",        "toggled": true},
      {"name": "top.u_dut.ctrl_mode", "before": "0",        "after": "0",        "toggled": false},
      {"name": "top.u_dut.src_b",     "before": "10110000", "after": "10110001", "toggled": true},
      {"name": "top.u_dut.src_c",     "before": "11000000", "after": "11000000", "toggled": false}
    ]
  }],
  "termination": "ambiguous",
  "active_trace_calls": 1,
  "edgecheck_direct_count": 0,
  "fallback_0_5ns_count": 1
}
```

AI 可从 `branch_evidence` 中直接读取:
- `ctrl_sel` 从 1→0，`src_b` 从 B0→B1，两个同时跳变
- `chain[0].text` 给出了完整的 RTL 赋值语句
- `chain[0].line` 指向 dut.sv:37（normal lane else 分支）
- 结论：不是"无法分析"，而是"两个信号同时变化，不应臆断"

## 结果汇总

| Scene | Target | Time | Hops | Termination | 判定 |
|-------|--------|------|------|-------------|------|
| S1 | dout[2] | 10ns | 1 | ambiguous | ACCEPTABLE |
| S2 | dout[2] | 20ns | 2 | primary_input | PASS |
| S3 | dout[2] | 30ns | 2 | primary_input | PASS |
| S4 | dout[2] | 41ns | 2 | primary_input | PASS |
| S5 | dout[1] | 50ns | 1 | control_only | ACCEPTABLE |
| S6 | dout[1] | 60ns | 1 | control_only | PASS |
| S7 | flag[2] | 71ns | 1 | control_only | ACCEPTABLE |
| S8 | flag[2] | 81ns | 1 | control_only | ACCEPTABLE |
| S9 | dout[2] | 90ns | 2 | primary_input | PASS |
| S10 | flag[2] | 100ns | 1 | control_only | PASS |

PASS: 5, ACCEPTABLE: 5, FAIL: 0

## 逐场景实际返回

### S1 (dout[2] @10ns): ambiguous → ACCEPTABLE

```
ctrl_sel: 1→0  src_b: B0→B1  同时跳变 → ambiguous
```

candidates: en1, src_a, ctrl_sel, ctrl_mode, src_b, src_c（全部 RHS 信号）
toggled: ctrl_sel, src_b

完整 JSON 见上文"ambiguous 详解"。

### S2 (dout[2] @20ns): primary_input → PASS

```json
{
  "chain": [
    {"hop":0, "signal":"top.u_dut.dout[2]", "driver_kind":"proc_assign",
     "next_signal":"top.u_dut.ctrl_sel", "active_time":"20.0n"},
    {"hop":1, "signal":"top.u_dut.ctrl_sel", "driver_kind":"proc_assign",
     "next_signal":"", "hop_type":"temporal_boundary"}
  ],
  "termination": "primary_input",
  "active_trace_calls": 2,
  "edgecheck_direct_count": 0,
  "fallback_0_5ns_count": 1
}
```

仅 ctrl_sel 跳变 (0→1)，唯一 candidate → 链正确追到 ctrl_sel → primary_input。

### S3 (dout[2] @30ns): primary_input → PASS

```json
{
  "chain": [
    {"hop":0, "signal":"top.u_dut.dout[2]", "next_signal":"top.u_dut.src_a"},
    {"hop":1, "signal":"top.u_dut.src_a", "driver_kind":"proc_assign"}
  ],
  "termination": "primary_input",
  "active_trace_calls": 2
}
```

仅 src_a 跳变 → 唯一 data source，正确。

### S4 (dout[2] @41ns): primary_input → PASS

```json
{
  "chain": [
    {"hop":0, "signal":"top.u_dut.dout[2]", "next_signal":"top.u_dut.en1"},
    {"hop":1, "signal":"top.u_dut.en1", "driver_kind":"proc_assign"}
  ],
  "termination": "primary_input"
}
```

仅 en1 跳变 → 唯一 enable source。

### S5 (dout[1] @50ns): control_only → ACCEPTABLE

```json
{
  "chain": [{"hop":0, "signal":"top.u_dut.dout[1]", "driver_kind":"if",
             "text":"npiIf, top.u_dut.lane_proc...if ((ln == SP_IDX0) || (ln == SP_IDX1))..."}],
  "termination": "control_only",
  "branch_evidence": [{"reason":"no data toggled, control ambiguous",
    "candidates":[{"name":"top.u_dut.sp_val","before":"01010000","after":"01010001","toggled":true}]}]
}
```

Special lane。NPI 返回 if 语句（不是具体赋值），sp_val toggled 但落在 control_only 分支。
未误入 normal else ✓

### S6 (dout[1] @60ns): control_only → PASS

```json
{
  "chain": [{"hop":0, "signal":"top.u_dut.dout[1]", "driver_kind":"if"}],
  "termination": "control_only"
}
```

Special lane，normal lane signals (src_a, src_b) 变化。dout[1] 不受影响 → NPI 返回 if。
未误报 normal signals 为 cause ✓

### S7 (flag[2] @71ns): control_only → ACCEPTABLE

```json
{
  "chain": [{"hop":0, "signal":"top.u_dut.flag[2]", "driver_kind":"if_else"}],
  "termination": "control_only",
  "branch_evidence": [{"reason":"no data toggled, control ambiguous",
    "candidates":[
      {"name":"top.u_dut.en2","toggled":false},
      {"name":"top.u_dut.mask_a[2]","before":"1","after":"0","toggled":true},
      {"name":"top.u_dut.mask_b[2]","toggled":false},
      {"name":"top.u_dut.en1","toggled":false},
      {"name":"top.u_dut.ctrl_sel","toggled":false},
      {"name":"top.u_dut.ctrl_mode","toggled":false}
    ]}]
}
```

mask_a[2] toggled。candidate 包含 mask_a[2]（lane index 正确），未误追 mask_a[3] ✓

### S8 (flag[2] @81ns): control_only → ACCEPTABLE

```json
{
  "chain": [{"hop":0, "signal":"top.u_dut.flag[2]", "driver_kind":"if_else"}],
  "termination": "control_only",
  "branch_evidence": [{"reason":"no data toggled, control ambiguous",
    "candidates":[
      {"name":"top.u_dut.en1","before":"0","after":"1","toggled":true},
      {"name":"top.u_dut.ctrl_sel","toggled":false},
      {"name":"top.u_dut.ctrl_mode","toggled":false}
    ]}]
}
```

OR 第二路 en1 跳变。en1 是唯一 toggled signal。但因 always_comb 的 NPI 返回的是 control statement（if_else），终止为 control_only。

### S9 (dout[2] @90ns): primary_input → PASS

```json
{
  "chain": [
    {"hop":0, "signal":"top.u_dut.dout[2]", "next_signal":"top.u_dut.src_a"},
    {"hop":1, "signal":"top.u_dut.src_a"}
  ],
  "termination": "primary_input"
}
```

多 lane 同时变化（src_a 影响全部 normal lane），dout[2] 正确追到 src_a。
Lane isolation: 其他 lane 的同时变化未造成误判 ✓

### S10 (flag[2] @100ns): control_only → PASS

```json
{
  "chain": [{"hop":0, "signal":"top.u_dut.flag[2]", "driver_kind":"if_else"}],
  "termination": "control_only"
}
```

仅 mask_a[3] 变化。flag[2] 未变 → NPI 返回 if_else → control_only。
未误追 mask_a[3] ✓

## 关键发现

1. **Lane index 保持**: `mask_a[2]` vs `mask_a[3]` 正确区分，0 次误追
2. **Branch 不混淆**: special/normal lane 0 次混淆
3. **Control cause 识别**: ctrl_sel 单独跳变 → 正确追到 primary_input
4. **Function inline**: NPI 对 fn_op 做了内联展开，无 function_boundary
5. **多 lane 同时变不误判**: S9 所有 normal lane 同时变，dout[2] 正确隔离
6. **保守安全**: 0 次错误 cause，ambiguous/control_only 均正确停止

## 统计

| 指标 | 值 |
|------|-----|
| 总 scene | 10 |
| PASS | 5 |
| ACCEPTABLE | 5 |
| FAIL | 0 |
| 分支混淆 | 0 |
| 误追 lane | 0 |
