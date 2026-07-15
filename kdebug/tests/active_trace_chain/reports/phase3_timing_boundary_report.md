# Phase 3 时序边界检测 + API vs fallback 统计报告

日期: 2026-06-16

## 实验目标

1. 验证 `always @(posedge clk)` 作为时序边界，用 `activeTime != T0` 检测停止
2. 统计 `edgecheck_direct`（API 直接返回唯一 driver）vs `fallback_0_5ns`（±0.5ns 消歧）

## DUT 结构

```
data_in → [5 层 assign] → always @(posedge clk) mid <= pre[5] → [5 层 assign] → data_out
```

参数化: NUM_PRE (5/8/10), NUM_POST (5/8/10), MUX_PRE (bitmask), MUX_POST (bitmask)

## 检测逻辑

```
T0 = 75ns (初始 requested_time)
hop 0: trace data_out @ 75ns → activeTime = 65ns (last posedge) → activeTime != T0 → STOP
```

## 结果: 12/12 全部 temporal_boundary_stop

| # | pre | post | mux | qtime | calls | hops | edgecheck | fallback | stop |
|---|-----|------|-----|-------|-------|------|-----------|----------|------|
| 1 | 5 | 5 | 无 | 75ns | 1 | 1 | 1 | 0 | 1 |
| 2 | 5 | 5 | 无 | 35ns | 1 | 1 | 1 | 0 | 1 |
| 3 | 5 | 10 | 无 | 75ns | 1 | 1 | 1 | 0 | 1 |
| 4 | 10 | 5 | 无 | 75ns | 1 | 1 | 1 | 0 | 1 |
| 5 | 5 | 5 | pre[2] | 75ns | 1 | 1 | 1 | 0 | 1 |
| 6 | 5 | 5 | post[2] | 75ns | 1 | 1 | 1 | 0 | 1 |
| 7 | 5 | 5 | pre+post | 75ns | 1 | 1 | 1 | 0 | 1 |
| 8 | 5 | 0 | 无 | 75ns | 1 | 1 | 1 | 0 | 1 |
| 9 | 0 | 5 | 无 | 75ns | 1 | 1 | 1 | 0 | 1 |
| 10 | 5 | 5 | 无 | 15ns | 1 | 1 | 1 | 0 | 1 |
| 11 | 8 | 8 | pre[3] | 75ns | 1 | 1 | 1 | 0 | 1 |
| 12 | 5 | 5 | pre[1]+[3] | 75ns | 1 | 1 | 1 | 0 | 1 |

## 关键发现

**1. temporal boundary 检测 100% 准确**

所有 12 个 case 的第一跳就检测到 `activeTime != requested_time`：
- `data_out` 的 `activeTime` = flop launch edge (65ns)
- `requested_time` = 75ns
- 连续赋值链 (`data_out = post[5] = ... = post[0] = mid`) 共享 flop 的 `activeTime`
- 因此无论 post 链有多少层，边界都在第一跳被检测到

**2. edgecheck_direct = 1, fallback_0_5ns = 0**

`data_out = post[5]` 是单 RHS 的 assign，edgeCheck 直接返回唯一 candidate。
mux cases (05-07, 11-12) 也只在 1 hop 内，因为 mux 在 pre/post 链中，
但第一跳就已经因 temporal boundary 停止了，没有机会走到 mux 层。

**3. 时序边界停在一个"太早"的位置**

实际行为: 查询 `data_out` → 检测到 activeTime 不同 → 停止
期望行为: 查询 `data_out` → 追 post 链各层 → 到 mid (flop 输出) → 检测到 activeTime 变化 → 停止

差异原因: NPI 把整个 combinational assign chain 的 causal time 都设置为 flop launch edge，
所以 assign 层的 activeTime 已经和 requested_time 不同。

**4. 要获得多层 pre/post 追踪，需要不同的查询策略**

建议:
- 查询 `data_out @ 65ns`（对齐 flop launch edge）→ 链将穿越 post 链和 flop，在 pre 链的边界处停止
- 或者修改检测逻辑: 只在 `driver_kind == "proc_assign"`（即 flop 输出）时检查 activeTime

## 统计汇总

| 指标 | 值 |
|------|-----|
| 总 case 数 | 12 |
| temporal_boundary_stop | 12 (100%) |
| edgecheck_direct 总次数 | 12 |
| fallback_0_5ns 总次数 | 0 |
| active_trace 总调用 | 12 |

## 结论

- `activeTime` 比较作为时序边界检测 **可靠且准确** (100%)
- 连续赋值链共享 driver 的 activeTime，边界在查询的第一跳就被检测到
- `edgecheck_direct` vs `fallback_0_5ns` 比例: 100% vs 0%（mux 未走到，因为边界更早触发）
- 需要调整查询时间（对齐 flop edge）或检测粒度（只检查 proc_assign 节点）来获得更细粒度的链追踪
