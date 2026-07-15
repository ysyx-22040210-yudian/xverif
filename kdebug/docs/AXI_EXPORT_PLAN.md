# kdebug AXI export implementation plan

## 目标

新增稳定 waveform action `axi.export`，把指定时间窗口内完成的 AXI
transaction 导出到文件。导出必须满足：

- 不管窗口起点在哪里，分析都从 FSDB 起点开始扫描，不能从窗口起点开始。
- 窗口过滤只看完成时间：write 以 B handshake 为完成点，read 以 RLAST
  handshake 为完成点。
- 读写分开导出，各自按完成时间排序。
- 导出记录 ID、地址、AXI 属性、响应、beat 数和时间字段。
- 不导出 `data`、`wdata`、`rdata` 或 per-beat `wstrb`，避免长 burst 造成
  文件和内存膨胀。
- 测试必须把导出结果和 AXI sequence 实际发出的 action 日志自动对比。

## 当前 AXI 时间窗行为

现有 AXI action 的时间窗能力需要在实现前后固定为文档和测试事实：

- `axi.query`、`axi.cursor`、`axi.analysis` 当前没有时间窗参数。
- `axi.request_response_pair` 和 `axi.latency_outlier` 支持 `time_range`。
  当前底层先做全局 AXI analyze，再用 `addr_time OR resp_time` 入窗；因此可
  包含窗口前发起、窗口内完成的事务，但语义不是纯 completion-time 过滤。
- `axi.outstanding_timeline` 支持 `time_range`。outstanding 状态来自全局
  analyze，所以窗口起点前遗留 outstanding 会体现在窗口内采样里。
- `axi.channel_stall` 支持 `time_range`，但它是 valid/ready stall 检查，不
  是 transaction 导出；窗口前已经开始的 stall 会从窗口起点重新计数。
- `axi.export` 不复用现有 `get_transactions_in_range` 的 OR 入窗语义，必须
  使用独立 completion-time 过滤。

## Public API

`axi.export` 是 stable waveform action，需要显式 live waveform session。

请求字段：

- `target.session_id`：必填，遵守当前显式 session 合同。
- `args.name`：必填，引用已经通过 `axi.config.load` 加载的 AXI 配置。
- `args.time_range.begin` / `args.time_range.end`：必填，或使用等价的
  `args.start` / `args.end`。
- `args.format`：可选，`tsv` 或 `csv`，默认 `tsv`。
- `args.output_prefix`：可选。省略时写到 session-local
  `axi_exports/<name>_<begin>_<end>_<timestamp>`。

输出文件：

- `<output_prefix>.write.tsv` 或 `<output_prefix>.write.csv`
- `<output_prefix>.read.tsv` 或 `<output_prefix>.read.csv`
- `<output_prefix>.meta.json`

每行字段固定为：

- `seq`
- `completion_time`
- `completion_time_ps`
- `addr_time`
- `addr_time_ps`
- `first_data_time`
- `first_data_time_ps`
- `last_data_time`
- `last_data_time_ps`
- `latency_ps`
- `id`
- `addr`
- `len`
- `size`
- `burst`
- `resp`
- `beat_count`
- `expected_beat_count`

响应 `data` 只返回导出摘要：

- `write_file`
- `read_file`
- `meta_file`
- `format`
- `name`
- `begin`
- `end`
- `scan_begin`
- `scan_end`
- `write_count`
- `read_count`
- `total_count`

默认 kout 只显示路径、count、窗口和排序语义，不内嵌 transaction rows。

## 实现设计

### Summary-only AXI 扫描

新增 AXI export 专用 summary 扫描路径，不向 `AxiTransaction.data` 或
`AxiTransaction.wstrb` 追加 per-beat 内容。扫描仍需要计数 beat，但只保留：

- channel handshakes 对应时间。
- ID、地址、`len`、`size`、`burst`、`resp`。
- `beat_count` 和 `expected_beat_count`。
- per-ID outstanding 增减信息。
- reset 清理和 incomplete transaction 统计。

扫描必须从 FSDB `min_time` 到 `max_time`，然后按 completion time 闭区间
`[begin, end]` 过滤导出行。这样可以覆盖窗口前 AW/AR 已发生、窗口内 B/RLAST
才完成的 transaction。

排序规则：

1. `completion_time`
2. `addr_time`
3. `seq`

读写分别排序，不混合到同一个导出文件。

### Meta JSON

meta JSON 至少包含：

- `name`
- `format`
- `begin`
- `end`
- `scan_begin`
- `scan_end`
- `write_count`
- `read_count`
- `total_count`
- `unique_write_ids`
- `unique_read_ids`
- `write_count_by_id`
- `read_count_by_id`
- `max_write_outstanding_by_id`
- `max_read_outstanding_by_id`
- `max_total_write_outstanding`
- `max_total_read_outstanding`
- `burst_histogram`
- `beat_count_mismatch_count`
- `incomplete_write_count`
- `incomplete_read_count`
- `reset_cleared_write_count`
- `reset_cleared_read_count`

`beat_count_mismatch_count` 统计 `beat_count != len + 1` 的事务。若 AXI4-Lite
或缺省 `len` 被归一化为 `0`，expected beat count 为 `1`。

### 注册和合同同步

实现必须同步以下交付面：

- engine protocol handler 注册 `axi.export`。
- public action registry 和 `specs/actions/actions.yaml`。
- request/response schema。
- basic request/response examples。
- `kdebug/docs/action-inventory.md`。
- `kdebug/README.md` 和 help text。
- compact kout 渲染。
- MCP smoke action list 或泛型 query smoke。

MCP 不新增独立 tool。AI 和 MCP client 通过已有
`kverif_debug_session_open` + `kverif_debug_query(action="axi.export")`
进入。

## AXI fixture 压力场景

默认 AXI 回归切换为压力参数：

- `NUM_IDS=16`
- `TRANS_PER_ID=200`
- 每个 ID 发送 200 write 和 200 read。
- `OUTSTANDING_DEPTH >= 4`
- `MIN_DELAY=50`
- `MAX_DELAY=100`
- 固定 seed，并在 `manifest.json` 和 README 中记录。

当前 AXI fixture 历史默认是 2 个 ID、每个 ID 6 笔、delay 1-8。旧 README
记录过 delay 提高到 20 可能触发 VIP constraint inconsistency。因此本计划把
delay 50-100 跑通作为实现范围：如果现有 SVT VIP 或参考 test 约束失败，需要
修正 fixture、test、sequence 或 constraint override，而不是把压力用例标为
可接受 blocked。

压力测试必须证明：

- read export 和 write export 都覆盖 16 个 unique ID。
- 每个 ID 的 write count 是 200。
- 每个 ID 的 read count 是 200。
- 每个 ID/方向都出现 outstanding 深度大于 1。
- 至少存在一个窗口内采样点，其中 16 个 ID 同时处于 outstanding。
- 每个 ID 至少覆盖一个 burst transaction。
- 所有导出 burst 满足 `beat_count == len + 1`。

## Sequence 日志和 golden 对比

AXI sequence 或 scoreboard 必须打印机器可解析日志，作为 export 正确性的
golden source。建议一行一个 JSON record，固定前缀：

```text
AXI_EXPECTED_TXN_JSON {"dir":"WR",...}
```

每条 JSON 至少包含：

- `dir`：`WR` 或 `RD`
- `id`
- `addr`
- `len`
- `size`
- `burst`
- `resp`
- `request_index`
- `id_index`
- `issue_order`
- `completion_order`，或能从 response 日志确定 completion order 的字段
- `expected_beat_count`

日志必须覆盖 read 和 write。不要依赖自由文本 UVM summary 作为 golden。

新增或扩展 pytest 脚本，解析 `sim.log` 中的 `AXI_EXPECTED_TXN_JSON`，生成
expected read/write tables，再解析 `axi.export` 产生的 read/write TSV 或 CSV。
对比规则：

- read 导出 3200 条，write 导出 3200 条。
- 每个 ID 的 read/write count 都是 200。
- 每个导出事务必须能在 expected log 中按
  `(dir, id, addr, len, size, burst, request_index 或 id_index)` 找到唯一匹配。
- `expected_beat_count == len + 1`。
- 导出的 `beat_count` 等于 expected `expected_beat_count`。
- 导出的 `resp` 等于 sequence/scoreboard 记录。
- 每个导出文件按 completion time 单调排序。
- header、rows、meta 均不包含 data 相关字段。

## 时间窗测试

新增 focused window tests：

- 选择一个 write，其中 AW 在窗口前，B 在窗口内；`axi.export` 必须导出。
- 选择一个 read，其中 AR 在窗口前，RLAST 在窗口内；`axi.export` 必须导出。
- 选择一个事务，其中 addr_time 在窗口内、completion_time 在窗口后；
  `axi.export` 不得导出。
- 对 `axi.request_response_pair`、`axi.latency_outlier`、
  `axi.outstanding_timeline` 增加测试，锁定当前时间窗语义并文档化，不让它们
  被误认为和 `axi.export` 一样是 completion-time-only。

## 验证门禁

基础合同门禁：

- `make -C kdebug schema-test`
- `make -C kdebug contract-test`

实现门禁：

- focused AXI export unit tests。
- 默认 AXI VIP real waveform regression，使用 16 ID、每 ID 200 write 和
  200 read、delay 50-100。
- log-vs-export 自动对比脚本。
- TSV 和 CSV smoke。
- `kverif_debug_query(action="axi.export")` MCP smoke。

凡是需要 NPI、Verdi、FSDB、VCS、license、真实 LSF 或 MCP stdio 的命令，按用户
要求在沙箱外运行。遇到进程通信、网络端口、文件系统或 license 类失败，先做
sandbox-vs-external A/B 排查，再判断是否为产品回归。

## 非目标

- v1 不提供 `include_data`。
- v1 不把 read/write 合并到同一个导出文件。
- v1 不改变现有 `axi.request_response_pair` 的 OR 入窗语义，只新增测试和文档
  把它与 `axi.export` 区分开。
