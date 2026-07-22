# KDebug XiangShan Benchmark 注错代码审计

> 公开性警告：本文披露了现有 16 个 case 的实际注错表达式。发布本文后，这批 case
> 不能继续作为答案对模型不可见的盲测集。后续正式 benchmark 应重新生成匿名 case，
> 更换触发条件和注错位置，并将新的 answer key 保留在模型不可访问的位置。

## 1. 审计范围

本审计针对历史 suite：

```text
/root/XiangShan-build/build/xverif_benchmark/v2_run_20260630_025641
```

代码比较方向统一为：

```text
干净基线（注错前） -> benchmark case（注错后）
```

核对方法：

1. generated UVM case 与干净 `benchmarks/xiangshan_uvm/rtl` 逐文件比较。
2. full-chip case 与干净 `/root/XiangShan-build/build/rtl` 逐文件比较。
3. 环境 case 与通过 judge 的 repair 目录及 suite construction log 交叉核对。
4. 复用 RTL 的 mixed case 使用 SHA-256 验证是否与来源 case 完全一致。

私有 answer key 只记录 case 来源和构造类别，没有逐行补丁。因此本文以实际文件 diff
为准，不根据公开 bug label 推测代码。

## 2. RTL 注错

### case_001：多 beat 写事务地址 bit 3 翻转

文件：`rtl/xs_generated_rtl_bridge.sv`

注错前：

```systemverilog
.auto_in_aw_bits_addr  (addr_q[30:0]),
```

注错后：

```systemverilog
.auto_in_aw_bits_addr  (
  (beats_q > 8'd1) ? (addr_q[30:0] ^ 31'h8) : addr_q[30:0]
),
```

影响：多 beat 写事务的 AW 地址被偏移 8 byte。公开标签称其为 AW/W/B 配对错误，
但实际代码直接破坏的是地址。

### case_002：特定 error burst 被伪装成 OK

文件：`rtl/xs_generated_rtl_bridge.sv`，B/R response 两处。

注错前：

```systemverilog
bus.resp_status <= (status_q != XS_ST_OK[3:0]) ? status_q :
                   (selected_b_resp == 2'b00) ? XS_ST_OK[3:0] : XS_ST_SLVERR[3:0];
```

注错后：

```systemverilog
bus.resp_status <= (sel_err && beats_q == 8'd4) ? XS_ST_OK[3:0] :
                   (status_q != XS_ST_OK[3:0]) ? status_q :
                   (selected_b_resp == 2'b00) ? XS_ST_OK[3:0] : XS_ST_SLVERR[3:0];
```

R response 使用相同的额外条件。影响：四 beat error transaction 的错误状态被吞掉。
公开标签称其为 burst length/last 错误，但实际没有修改 beat 数或 last 信号。

### case_003：非首 beat 的 byte lane 0 被禁止写入

文件：`rtl/xs_generated_rtl_bridge.sv`

注错前：

```systemverilog
.auto_in_w_bits_strb   (eff_mask_q),
```

注错后：

```systemverilog
.auto_in_w_bits_strb   (
  (beat_idx_q != 8'd0) ? (eff_mask_q & 8'hfe) : eff_mask_q
),
```

影响：从第二个 beat 开始强制清除 `strb[0]`，导致 byte lane 0 写后读不一致。

### case_004：把伪造地址页错误识别为 UART

文件：`rtl/xs_generated_rtl_bridge.sv`

注错前：

```systemverilog
is_uart_addr = ({addr[63:12], 12'h000} == XS_UART_BASE);
```

注错后：

```systemverilog
is_uart_addr = ({addr[63:12], 12'h000} == XS_UART_BASE) ||
               ({addr[63:12], 12'h000} == 64'h0000_0000_1bad_0000);
```

影响：`0x1bad_0000` 页被错误路由到 UART target。

### case_005：条件性吞掉 peripheral error status

文件：`rtl/xs_generated_rtl_bridge.sv`，B/R response 两处。

注错前：

```systemverilog
bus.resp_status <= (status_q != XS_ST_OK[3:0]) ? status_q :
                   (selected_b_resp == 2'b00) ? XS_ST_OK[3:0] : XS_ST_SLVERR[3:0];
```

注错后：

```systemverilog
bus.resp_status <= ((target_q == T_ERR) && addr_q[5]) ? XS_ST_OK[3:0] :
                   ((status_q != XS_ST_OK[3:0]) ? status_q :
                   (selected_b_resp == 2'b00) ? XS_ST_OK[3:0] : XS_ST_SLVERR[3:0]);
```

影响：错误 target 且地址 bit 5 为 1 时返回 OK。公开标签强调 backpressure/order，
但实际表达式没有修改 ready、valid 或队列顺序。

### case_006：运行较晚时翻转 ALU result LSB

文件：`rtl/Alu_3.sv`

注错前：

```systemverilog
AluDataModule_3 aluModule (
  .io_src_0  (io_in_bits_data_src_0),
  .io_src_1  (io_in_bits_data_src_1),
  .io_func   (io_in_bits_ctrl_fuOpType),
  .io_result (io_out_bits_res_data)
);
```

注错后：

```systemverilog
wire [63:0] _T_0;
AluDataModule_3 aluModule (
  .io_src_0  (io_in_bits_data_src_0),
  .io_src_1  (io_in_bits_data_src_1),
  .io_func   (io_in_bits_ctrl_fuOpType),
  .io_result (_T_0)
);
assign io_out_bits_res_data =
  io_in_bits_perfDebugInfo_issueTime > 64'h0000000000001388
    ? _T_0 ^ 64'h0000000000000001
    : _T_0;
```

影响：`issueTime > 5000` 后，每个经过该 ALU 的结果 bit 0 被翻转。

### case_007：运行较晚时吞掉整数寄存器写使能

文件：`rtl/Alu_3.sv`

注错前：

```systemverilog
assign io_out_bits_ctrl_rfWen = io_in_bits_ctrlPipe_0_rfWen;
```

注错后：

```systemverilog
assign io_out_bits_ctrl_rfWen =
  io_in_bits_perfDebugInfo_issueTime > 64'h00000000000003e8 &
  io_in_bits_ctrlPipe_0_rfWen
    ? 1'h0
    : io_in_bits_ctrlPipe_0_rfWen;
```

影响：`issueTime > 1000` 后，有效 `rfWen` 被强制清零，ALU 结果无法写回寄存器。

### case_008：所有有效整数 load 的返回数据 LSB 翻转

文件：`rtl/NewLoadUnit.sv`

注错前：

```systemverilog
assign io_ldout_toIntRf_bits_data = _dataPath_io_s3ShiftAndExtData[63:0];
```

注错后：

```systemverilog
assign io_ldout_toIntRf_bits_data = io_ldout_toIntRf_valid
  ? _dataPath_io_s3ShiftAndExtData[63:0] ^ 64'h0000000000000001
  : _dataPath_io_s3ShiftAndExtData[63:0];
```

影响：每个有效整数 load 写回值的 bit 0 被翻转。

### case_009：redirect target 增加或减少 2 byte

文件：`rtl/BranchUnit.sv`

注错前：

```systemverilog
assign io_out_bits_res_redirect_bits_target = _addModule_io_target[49:0];
assign io_out_bits_res_redirect_bits_fullTarget = _addModule_io_target;
```

注错后：

```systemverilog
assign io_out_bits_res_redirect_bits_target = io_out_bits_res_redirect_valid
  ? _addModule_io_target[49:0] ^ 50'h0000000000002
  : _addModule_io_target[49:0];
assign io_out_bits_res_redirect_bits_fullTarget = io_out_bits_res_redirect_valid
  ? _addModule_io_target ^ 64'h0000000000000002
  : _addModule_io_target;
```

影响：发生 redirect 时 target bit 1 被翻转。

### case_010：与 case_006 完全重复

`case_010/rtl/Alu_3.sv` 和 `case_006/rtl/Alu_3.sv` 的 SHA-256 均为：

```text
e9cf561719217c46dcdc511ea3d1870c48479053baf42c4ac2b594b02b21f8d2
```

实际注错仍是 `issueTime > 5000` 后 ALU result LSB 翻转，并非公开矩阵描述的
Cache/MMU/refill/permission interaction。

## 3. 环境注错

### case_011：删除 Difftest plusarg

注错前：

```bash
DIFF_ARG=+diff=/root/XiangShan-build/ready-to-run/riscv64-nemu-interpreter-so
```

注错后：

```bash
DIFF_ARG=
```

`scripts/run.sh` 只在 `DIFF_ARG` 非空时把它加入 simv 参数，因此仿真运行但没有有效
Difftest。

### case_012：运行错误的 UVM case

文件：`config/case.env`

注错前：

```bash
BENCH_CASE=ut_axi_burst_outstanding
STRESS_ITERS=120
```

注错后：

```bash
BENCH_CASE=ut_axi_error_backpressure
STRESS_ITERS=120
```

### case_013：把真实 simv 替换为退出码为 0 的假程序

文件：`config/run_target.env`

```bash
# 注错前
SIMV=./simv

# 注错后
SIMV=./env/stale_simv
```

注入的 `env/stale_simv`：

```bash
#!/usr/bin/env bash
echo "stale simulator image selected: workload was not executed"
echo "DIFFTEST disabled by stale executable"
exit 0
```

这会制造“run 返回 0，但 workload 和 Difftest 都没执行”的假成功。

## 4. 混合注错

### case_014：case_003 RTL mask 错误 + UVM case 选错

RTL 与 `case_003` 完全相同，SHA-256 为：

```text
53baaab519da3354716842818617e40e3caee08d484fe78e6b43b0258bcfc3d4
```

环境变化：

```bash
# 注错前
BENCH_CASE=it_memory_mixed_burst

# 注错后
BENCH_CASE=ut_axi_error_backpressure
```

公开矩阵把环境部分描述为 judge/log marker 错误，但实际 suite 是 run dispatch 选错。

### case_015：case_009 redirect 错误 + Difftest plusarg 丢失

RTL 与 `case_009` 完全相同，SHA-256 为：

```text
c2717c00d410580f0564d3bf4850c6ef617c03331f187bb0c2a5860e73af48a3
```

环境变化：

```bash
# 注错前
DIFF_ARG=+diff=/root/XiangShan-build/ready-to-run/riscv64-nemu-interpreter-so

# 注错后
DIFF_ARG=
```

### case_016：case_006 ALU 错误 + 一秒运行超时

RTL 与 `case_006` 完全相同，SHA-256 为：

```text
e9cf561719217c46dcdc511ea3d1870c48479053baf42c4ac2b594b02b21f8d2
```

注错前没有 `config/run.env`，`scripts/run.sh` 使用：

```bash
timeout "${RUN_TIMEOUT_SEC:-3300}" ...
```

注错后增加：

```bash
RUN_TIMEOUT_SEC=1
```

公开矩阵把 RTL 部分描述为 LSU/cache 错误，但实际是 `case_006` 的 ALU LSB 翻转。

## 5. 公开标签与实际代码的差异

| Case | 公开标签 | 实际代码 |
| --- | --- | --- |
| `001` | AW/W/B order | 多 beat AW 地址 bit 3 翻转 |
| `002` | burst length/last | 特定 error transaction 被改成 OK |
| `005` | error backpressure/order | 特定 error target 被改成 OK |
| `010` | Cache/MMU interaction | 与 `006` 完全相同的 ALU LSB 翻转 |
| `014` | RTL + wrong judge | RTL mask 错误 + wrong case dispatch |
| `016` | LSU/cache + timeout | ALU LSB 翻转 + timeout=1 |

因此，历史结果不能直接按这六个公开标签解释模型能力。尤其 `case_010` 不能作为
Cache/MMU 调试能力证据，`case_016` 不能作为 LSU/cache RTL 调试能力证据。

## 6. 模型如何获得问题线索

三个模型使用同一个 API repair runner。每轮都能看到当前 case 的 fail log、公开设计
约束、build/run/judge 脚本、允许修改的文件，以及上一轮 build/run/judge 反馈。

历史目录名为 `with_xdebug` 的名义工具组还会收到 `evidence/with_xdebug/` 文本。2026-07-23
逐文件复核后确认，这些文本不是 KDebug 从 FSDB/KDB 采集的动态证据：主要 payload 都是
两组共享 `fail/run.log` 的复制或裁剪，runner 也没有 KDebug/Verdi/NPI 执行通道。

因此，`with_xdebug` 与 `without_xdebug` 的历史结果只能按两种 prompt 变体解释，不能用于
证明 KDebug 对某个 case 的因果提升。16 个 case 的文件来源、模型结果和实际作用见
[KDebug 工具调用与逐 Case 作用审计](benchmark_kdebug_evidence_audit.md)。

模型返回 unified diff 后，由 runner 校验路径、应用补丁并执行原 workload。只有满足
所需 repair class、重新构建、重新运行且 judge 返回 0，才计为 PASS。
