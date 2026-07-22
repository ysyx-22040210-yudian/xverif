# KDebug XiangShan Benchmark 工具调用与逐 Case 作用审计

> 审计日期：2026-07-23
>
> 历史 suite：`/root/XiangShan-build/build/xverif_benchmark/v2_run_20260630_025641`
>
> 命名说明：该 suite 创建于工具更名前，因此目录和原始文件仍使用 `xdebug`、
> `with_xdebug`。本文统一称当前工具为 KDebug，引用历史路径时保留原名。

## 1. 先给结论

**没有。这个历史 benchmark 的“工具组”并未在每个 case 或每个 repair trial 中真实执行
KDebug。**

能够确认的实际流程是：

1. 16 个 case 都预先放置了 `evidence/with_xdebug/` 文本文件。
2. runner 检查 `case_meta.json` 声明的 evidence 文件是否非空。
3. 对 `with_xdebug` 组，runner 把这些文本连同 `fail/run.log`、RTL、脚本和公开元数据一起
   拼入模型 prompt。
4. 模型只能返回 unified diff 或请求另一个允许查看的文件。
5. runner 只执行补丁应用、build、run 和 judge，没有执行 KDebug、Verdi、NPI 或 FSDB 查询。

所以需要严格区分以下说法：

| 说法 | 历史 suite 是否成立 | 证据 |
| --- | --- | --- |
| case 被分到名义工具组 | 是 | 路径为 `repair/<model>/with_xdebug/<case>` |
| case 目录存在非空 evidence | 是，16/16 | 每个 case 都有两个期望文件，另有一个 smoke 文件 |
| evidence 被 runner 加入模型上下文 | 是 | `collect_context()` 读取 `evidence/with_xdebug/` |
| 每个 case 真实调用了 KDebug | **否** | runner 和 matrix log 均无 KDebug 执行路径或命令记录 |
| evidence 是 KDebug 从 FSDB/KDB 采集的波形结果 | **不能成立** | suite 内无 FSDB/VCD/VPD，文件正文是已有日志的复制或裁剪 |
| 模型通过工具调用继续查询信号 | **否** | API 只接受文本回复；模型没有 shell 或 tool-call 通道 |
| 工具组 PASS 差异可归因于 KDebug | **否** | 工具组新增内容不含独立工具观测，且与基线输入高度重复 |

这不是“工具完全没有能力”的结论，而是“这次历史实验没有形成可以证明工具作用的实验
链路”。KDebug 本身的功能测试与 benchmark 的工具使用有效性是两件不同的事。

## 2. 审计依据

### 2.1 Runner 没有 KDebug 调用通道

历史 runner 的上下文组装顺序如下：

```text
所有组：
  case_meta.json 的公开字段
  fail/build.log
  fail/run.log
  fail/run.rc
  上一轮 build/run/judge 日志
  公开设计说明、脚本和允许查看的源码

仅 with_xdebug 组：
  evidence/with_xdebug/ 下的文本文件
```

模型响应只会进入两条路径：

- 返回文件名：下一轮把该允许文件加入上下文；
- 返回 unified diff：runner 应用补丁，然后执行 case 的 build、run、judge。

runner 提示中还明确写有 `Do not include shell commands unless they are explanatory`。也就是说，
即便模型在回复中写出 KDebug 命令，runner 也不会执行它。

### 2.2 `tool_evidence_present` 只检查“文件非空”

`list_evidence_files()` 的有效性条件是：

- 文件名命中 `case_meta.json` 的 `expected_files`；
- 文件大小大于 0；
- 命中文件数达到 `minimum_nonempty_files`。

它不校验：

- 谁生成了文件；
- 是否执行过 KDebug；
- 输入 FSDB/KDB/elab 库是什么；
- action、参数、开始/结束时间和退出码；
- 输出是否只是 `fail/run.log` 的复制；
- 文件是否来自当前 case、当前构建和当前 workload。

因此 `tool_evidence_present=true` 和 `evidence_used="xdebug evidence + ..."` 都是 runner 的分组
元数据，不是工具调用证明。

### 2.3 证据文件的内容来源

逐文件结构化比对得到：

| Case 范围 | Evidence 形式 | 与基线可见输入的关系 |
| --- | --- | --- |
| `001-005` | 一个 JSON + 一个 CSV | JSON 的 `observed_failure_tail` 是 `fail/run.log` 的精确子串；5 个 CSV 正文完全相同，只写“查看 run.log” |
| `006-010` | 一个 JSON + 一个 Markdown | JSON 的 failure tail 与 Markdown 代码块都是 `fail/run.log` 的精确子串 |
| `011` | 两个文本文件 | 两份正文相同，都是 507 字符的 `fail/run.log` 内容 |
| `012` | 一个 JSON + 一个 Markdown | 两者都是错误 case 的 `fail/run.log` 裁剪 |
| `013` | 两个文本文件 | 两份正文相同，都是 95 字符的 stale simulator 日志 |
| `014` | 一个通用 CSV + 一个 Markdown | CSV 是模板；Markdown 是从基础 `case_003` 继承的 run log 裁剪 |
| `015` | 一个 JSON + 一个 Markdown | 两者是从基础 `case_009` 继承的 Difftest failure tail，未审计新增的缺失 Difftest 参数 |
| `016` | 一个 JSON + 一个 Markdown | 两者是从基础 `case_006` 继承的 ALU failure tail，未审计新增的 1 秒 timeout |

另外：

- 16 份 `xdebug_tool_smoke.md` 完全相同，SHA-256 都是
  `bcd007858a0f9c66d4412caf50aa06f6306b4f168fe675dcfd23e59da8ed0fc5`。
- smoke 文件只说 `/root/xverif/tools/xdebug is installed`，没有执行 action。
- evidence 文件在 repair 目录中通过硬链接复制；抽查 link count 为 45，说明它们不是每个
  trial 独立生成的结果。
- suite 中没有 `.fsdb`、`.vcd` 或 `.vpd` 文件。
- `matrix_api.log` 记录了 group、文件名和 `tool_evidence_present=true`，没有 KDebug/Verdi/NPI
  命令、action、退出码或输出哈希。
- `suite_construction.log` 记录 case 复制和组合过程，没有记录 evidence 的生成命令。

## 3. 如何判定“工具起作用”

本文采用五级证据链。只有第 4、5 级同时成立，才可以声称某个 PASS 受益于 KDebug：

| 级别 | 必须回答的问题 | 本次历史 suite |
| --- | --- | --- |
| L1 分组 | trial 是否标成工具组 | 成立 |
| L2 文件 | 是否存在非空 evidence | 成立 |
| L3 调用 | 是否有 KDebug 命令、输入、action、时间、rc 和版本记录 | 不成立 |
| L4 增量 | 工具输出是否包含基线没有的 case-specific 动态观测 | 不成立 |
| L5 使用 | 模型是否引用该独有观测，并据此形成正确补丁和 PASS | 无法证明 |

模型在回复中写“根据 evidence”或复述 mismatch 值，只能证明它读到了文本。由于相同 mismatch
也在两组共享的 `fail/run.log` 中，这不构成 KDebug 语义使用证明。

## 4. 逐 Case 审计总表

表中“调用”是指 repair trial 内真实执行 KDebug，而不是 evidence 文件存在。

| Case | 期望的 KDebug 观测 | 实际 evidence | 调用 | 可归因的工具作用 |
| --- | --- | --- | --- | --- |
| `001` | AW/W/B 握手、ID、地址和 first mismatch 时间窗 | AXI read mismatch 日志尾部 + 通用 CSV | 否 | 无 |
| `002` | 四 beat error transaction 的 first bad response/beat | `got=0, exp=2` 日志尾部 + 通用 CSV | 否 | 无 |
| `003` | write address/data/strobe 到 readback 的链路 | readback 为 0 的日志尾部 + 通用 CSV | 否 | 无 |
| `004` | MMIO decode target、response status、scoreboard 对比 | unmapped status mismatch 日志尾部 + 通用 CSV | 否 | 无 |
| `005` | backpressure 下 response payload/valid/ready 保持 | status mismatch 地址列表 + 通用 CSV | 否 | 无 |
| `006` | first divergent commit、ALU result 和 writeback 窗口 | Difftest 最终状态尾部的两份包装 | 否 | 无法证明 |
| `007` | first lost `rfWen`、producer 和下游 assertion 顺序 | 最终寄存器差异/assertion 日志尾部 | 否 | 无 |
| `008` | load request、cache/refill、writeback first bad value | 最终 Difftest 单 bit mismatch 日志尾部 | 否 | 无 |
| `009` | redirect producer、target 与 frontend/commit PC | 最终 exception/PC 日志尾部 | 否 | 无 |
| `010` | 声明为 TLB/cache 的 first bad refill | 实际为 case 006 ALU 失败日志 | 否 | 反而可能受错误标签误导 |
| `011` | 实际 simv 命令和 Difftest enable 检查 | 两份相同的 `NEMU_HOME` 失败日志 | 否 | 无 |
| `012` | BENCH_CASE dispatch 与 judge 期望值映射 | 错误 case 的 run log 两份包装 | 否 | 无 |
| `013` | simv 路径、构建指纹和时间戳 | 两份相同的 stale simulator 文本 | 否 | 无 |
| `014` | case dispatch + write strobe/data mismatch 双链路 | 基础 case 003 日志 + 通用 CSV | 否 | 未覆盖环境注错 |
| `015` | redirect trace + `REF_SO/DIFF_ARG` 命令审计 | 基础 case 009 Difftest failure tail | 否 | 未覆盖环境注错 |
| `016` | ALU/写回 first bad value + timeout 配置审计 | 基础 case 006 failure tail | 否 | 未覆盖 timeout，且 subsystem 错标 |

## 5. 逐 Case 详细说明

### 5.1 `case_001`：多 beat AW 地址 bit 3 翻转

- **真实问题**：多 beat 写事务的 AW 地址被额外 XOR `8`。
- **应该由工具提供**：AW、W、B 三通道的 valid/ready、ID、地址、beat 以及 scoreboard 第一次
  分歧的同一时间窗。
- **实际提供**：`xdebug_trace_summary.json` 只是已有 UVM readback mismatch 日志尾部；
  `xdebug_signal_windows.csv` 只有“first_failure 来自 run.log”和“只能修改 repair scope”两行。
- **模型表现**：GPT 和 Qwen 两组都 PASS；GLM 两组都 TIMEOUT。GPT 基线 1 轮，名义工具组
  3 轮，说明这个 case 靠静态 RTL 中明显的 XOR 表达式就能定位。
- **作用结论**：没有 KDebug action、波形或信号窗口，不能声称工具参与了修复。

### 5.2 `case_002`：四 beat error transaction 被改成 OK

- **真实问题**：B/R response 在特定四 beat error transaction 上被强制改成 OK。
- **应该由工具提供**：error request 到 B/R response 的 first bad beat、status 和握手时间窗。
- **实际提供**：JSON 复制了 `got=0, exp=2` 的 UVM 日志；CSV 与 case 001 完全相同，未含
  beat、valid/ready 或 response 波形。
- **模型表现**：GPT 两组都 PASS；Qwen 名义工具组 2 轮 PASS，基线虽然文字定位正确，却因
  补丁没有有效落地而 TIMEOUT；GLM 两组 TIMEOUT。
- **作用结论**：Qwen 的结果差异不能归因于 KDebug，因为 `got/exp` 和地址在基线
  `fail/run.log` 中同样存在。它说明的是模型采样与补丁落地差异，不是工具调用收益。

### 5.3 `case_003`：非首 beat 的 `strb[0]` 被清零

- **真实问题**：从第二个 beat 起，write strobe 的 byte lane 0 被清除。
- **应该由工具提供**：write request、mask、data beat、RAM 更新与 readback 的 provenance。
- **实际提供**：JSON 只复制 readback 大量为 0 的日志；CSV 没有任何真实 data/strobe 信号。
- **模型表现**：GPT 两组都从静态 RTL 修复并 PASS；Qwen、GLM 两组都追错 read path 并
  TIMEOUT。
- **作用结论**：实际 evidence 只强化了下游症状，没有给出写掩码链路；不能计为工具帮助。

### 5.4 `case_004`：伪造地址页被识别为 UART

- **真实问题**：`0x1bad_0000` 页被错误加入 UART decode。
- **应该由工具提供**：请求地址、decode target、response status 与 scoreboard 期望的同窗
  对照。
- **实际提供**：JSON 是 unmapped status mismatch 地址列表；CSV 没有 decode signal 或
  target 采样。
- **模型表现**：GPT、Qwen 两组都 PASS；Qwen 都是 1 轮。GLM 两组 TIMEOUT。
- **作用结论**：硬编码常量可由静态源码直接发现，结果没有显示 KDebug 增量。

### 5.5 `case_005`：条件性吞掉 peripheral error status

- **真实问题**：error target 且地址 bit 5 为 1 时，B/R status 被强制改成 OK。
- **应该由工具提供**：`resp_valid && !resp_ready` 窗口、地址 bit 5、payload hold 和 first bad
  response。
- **实际提供**：JSON 中只有每隔 `0x40` 的 status mismatch 日志；所谓 response-order CSV
  仍是通用两行模板。
- **模型表现**：GPT 两组 PASS；Qwen 名义工具组注意到 offset 模式并 PASS，基线后期也说出
  bit 5 条件但补丁未落地；GLM 两组 TIMEOUT。
- **作用结论**：地址模式来自两组共享日志。可以说名义工具组模型利用了日志，不能说
  KDebug 采集并提供了该模式。

### 5.6 `case_006`：`Alu_3` 结果 LSB 延迟翻转

- **真实问题**：`issueTime > 5000` 后，`Alu_3` 输出 XOR `1`。
- **应该由工具提供**：第一个错误 commit 前后的 PC、指令、operand、原始 ALU result、最终
  writeback 和实例名。
- **实际提供**：`xdebug_commit_window.json` 的 payload 是 `fail/run.log` 尾部；
  `xdebug_wave_notes.md` 又复制其中约 3000 字符。没有 commit action、真实信号名、时间窗或
  FSDB 来源。
- **模型表现**：GPT 名义工具组最终修改 `Alu_3.sv` 并 PASS，基线 TIMEOUT；Qwen、GLM 两组
  都 TIMEOUT。
- **作用结论**：这是结果差异最大的 case，但仍不能归因于 KDebug。GPT 使用的是共享失败
  日志、请求到的 RTL 和迭代反馈；历史 evidence 没有提供独立的 first-bad commit 观测。
  现有报告把它写成“KDebug 动态 commit 证据的代表案例”是不成立的，已在模型分析文档中
  更正。

### 5.7 `case_007`：有效 `rfWen` 被延迟清零

- **真实问题**：`Alu_3` 的有效整数寄存器写使能在阈值后被强制清零。
- **应该由工具提供**：producer 的 `rfWen` 首次消失、redirect/flush 条件、下游
  RegCache assertion 的先后顺序。
- **实际提供**：两份正文都只是最终寄存器随机值和 `RegCacheDataModule.sv` assertion
  附近的 run log。
- **模型表现**：GPT、Qwen 两组都把下游 assertion 当成根因并 TIMEOUT；GLM 工具组只有
  限流前的部分轨迹，基线无数据。
- **作用结论**：没有上游控制信号链。文件名 `first_divergence` 并不代表正文真的包含 first
  divergence，材料还可能加强错误的下游定位。

### 5.8 `case_008`：load 写回数据 LSB 翻转

- **真实问题**：`NewLoadUnit` 在有效整数 load 写回时把数据 XOR `1`。
- **应该由工具提供**：load request、DCache/MSHR/refill、load data generation 和最终
  writeback 的 first bad event。
- **实际提供**：JSON 与 Markdown 都只是最终 Difftest mismatch 日志，没有 LSU/cache
  transaction 或有效信号采样。
- **模型表现**：GPT、Qwen 两组全部 TIMEOUT，常把单 bit 差异解释成 byte lane、flash 或
  AMO 问题；GLM 无数据。
- **作用结论**：没有形成工具可归因的定位，文件名 `lsu_trace` 与正文不符。

### 5.9 `case_009`：redirect target bit 1 翻转

- **真实问题**：`BranchUnit` 在 redirect valid 时把 target XOR `2`。
- **应该由工具提供**：redirect producer、原始 target、修改后 target、frontend PC 和 commit
  PC 的因果链。
- **实际提供**：JSON 和 Markdown 都来自最终 Difftest/exception 日志尾部，没有 redirect
  signal trace。
- **模型表现**：GPT 两组都是第 2 轮 PASS；Qwen 两组都 TIMEOUT；GLM 无数据。
- **作用结论**：GPT 基线同样根据 2-byte PC 差值定位，未显示 KDebug 独有贡献。

### 5.10 `case_010`：错标为 cache/MMU 的重复 ALU 注错

- **真实问题**：与 case 006 字节级相同，仍是 `Alu_3` result XOR `1`。
- **应该由工具提供**：如果 metadata 声称 TLB/cache，应以信号观测验证 first bad event 是否
  真在该链路，并能反证错误标签。
- **实际提供**：名为 `xdebug_tlb_cache_trace.json` 和 `first_bad_refill.md` 的文件，正文却是
  case 006 的 ALU/Difftest failure tail。
- **模型表现**：GPT、Qwen 两组全部 TIMEOUT，受错误 subsystem 标签影响，长期搜索 UART、
  DMA、AMO 或 cache。
- **作用结论**：没有真实工具观测来纠正 metadata，反而存在文件名和标签锚定风险。

### 5.11 `case_011`：Difftest 参数缺失

- **真实问题**：`DIFF_ARG` 为空，实际 Difftest 启动链不完整。
- **应该由工具提供**：展开后的 simv 命令、`+diff` 参数、参考模型路径、日志中的 Difftest
  enabled 标记。
- **实际提供**：`xdebug_run_command_audit.md` 与
  `xdebug_difftest_enable_check.txt` 正文完全相同，都是 `NEMU_HOME is not defined` 的
  `fail/run.log`，没有展开命令或独立 enable 检查。
- **模型表现**：GPT、Qwen 两组都 PASS；GPT 工具组轮数少，Qwen 工具组反而多一轮，差异
  不一致。
- **作用结论**：模型通过共享日志、脚本和 config 修复。不能把轮数差异归因于 KDebug。

### 5.12 `case_012`：运行错误的 UVM case

- **真实问题**：run 实际执行 `ut_axi_error_backpressure`，judge 期待
  `ut_axi_burst_outstanding`。
- **应该由工具提供**：启动参数、`Starting case`、PASS marker 与 judge 期望值的结构化映射。
- **实际提供**：JSON 和 Markdown 都复制了错误 case 已 PASS 的 run log；没有独立 action，
  但日志本身足以说明配置不一致。
- **模型表现**：GPT 两组都是 2 轮 PASS；Qwen 两组都是 1 轮 PASS。
- **作用结论**：基线已看到相同 run log 和 judge 反馈，工具组没有增量。

### 5.13 `case_013`：假 `stale_simv` 返回 0

- **真实问题**：`SIMV` 指向一个打印假成功文本后退出的脚本。
- **应该由工具提供**：实际可执行文件路径、inode/hash、构建时间戳和当前 build 产物的
  对比。
- **实际提供**：所谓 build fingerprint 和 timestamp audit 两个文件正文完全相同，只是
  95 字符的 stale simulator 日志，没有 hash 或 stat 数据。
- **模型表现**：GPT、Qwen 两组全部 1 轮 PASS。
- **作用结论**：静态 `config/run_target.env` 和共享日志已足够，未体现工具作用。

### 5.14 `case_014`：write mask + wrong case dispatch

- **真实问题**：case 003 的 write strobe RTL 注错，再叠加错误 UVM case 配置。
- **应该由工具提供**：当前 mixed case 的实际启动 case，以及 write strobe 到 readback 的
  first mismatch 链路。
- **实际提供**：CSV 仍是通用模板；`xdebug_judge_audit.md` 是从基础 case 003 继承的 run
  log 尾部，没有展示新增的 wrong-case 配置。
- **模型表现**：GPT 两组都是 2 轮 PASS；Qwen 两组都 TIMEOUT；GLM 无数据。
- **作用结论**：evidence 没有覆盖 mixed case 的环境半边，不能证明工具参与完整修复。

### 5.15 `case_015`：redirect target + Difftest 缺失

- **真实问题**：case 009 的 redirect XOR `2`，再叠加 `DIFF_ARG` 为空。
- **应该由工具提供**：当前 case 的 redirect trace，以及展开后的 simv/REF_SO/DIFF_ARG
  审计。
- **实际提供**：JSON 和 Markdown 都是基础 case 009 的 Difftest failure tail；所谓
  `ref_so_audit` 没有显示当前缺失的 Difftest 参数。
- **模型表现**：GPT 两组都是 3 轮 PASS；Qwen 两组都 TIMEOUT；GLM 无数据。
- **作用结论**：GPT 是通过共享配置、源码和日志完成 mixed repair，不是依据已证明的
  KDebug command audit。

### 5.16 `case_016`：ALU LSB 翻转 + 一秒 timeout

- **真实问题**：case 006 的 ALU 注错，再叠加 `RUN_TIMEOUT_SEC=1`；公开 subsystem 还被错标
  为 LSU/cache。
- **应该由工具提供**：当前 run 的 timeout 参数/退出状态，以及能把 first bad producer
  定位到 ALU 而不是 LSU 的动态链路。
- **实际提供**：`xdebug_lsu_trace.json` 和 `xdebug_timeout_audit.md` 都是基础 case 006 的
  完整运行失败尾部，正文没有 1 秒 timeout 记录，也没有 LSU trace。
- **模型表现**：GPT、Qwen 两组全部 TIMEOUT；模型能从 config 看到 1 秒问题，但都没有修对
  ALU。GLM 无数据。
- **作用结论**：工具 evidence 既没覆盖新增环境注错，也没纠正错误 subsystem 标签，没有
  可归因帮助。

## 6. 结果应该如何重新解读

最终名义分组成绩仍可作为 repair prompt A/B 的历史记录：

| 模型 | 名义工具组 | 基线组 | 可否解释为 KDebug 提升 |
| --- | ---: | ---: | --- |
| GPT-5.5 | 12/16 PASS | 11/16 PASS | 否 |
| Qwen3.6-35B | 7/16 PASS | 5/16 PASS | 否 |
| GLM-4.7 | 已完成项 0 PASS | 已完成项 0 PASS | 否；且 `008-016` 无数据 |

两组 prompt 并非字节级相同：工具组多了重复日志包装、文件名和“xdebug”标签，因此这些
成绩可以描述“该 prompt 变体的结果”，但不能测量 KDebug 的真实效应。尤其不能用
`case_002`、`005`、`006` 的单侧 PASS 直接宣称工具有效。

## 7. 下一轮 benchmark 的最低合格标准（已实现）

上述审计建议已经落地为 runner 的强制前置门禁，规范和命令见：

- [`benchmarks/kdebug_repair_benchmark/benchmark_evidence_gate.md`](../benchmarks/kdebug_repair_benchmark/benchmark_evidence_gate.md)
- [`kdebug_evidence.py`](../benchmarks/kdebug_repair_benchmark/scripts/kdebug_evidence.py)
- [`kdebug-evidence-manifest.v1` Schema](../benchmarks/kdebug_repair_benchmark/schemas/kdebug_evidence_manifest.schema.json)

`run_matrix.sh` 现在先逐 case 调用 collector，再执行 suite-wide validation；全部通过后才会
调度模型。collector 保存真实 command argv、case 来源、KDebug wrapper/Tcl runtime、Git
commit、FSDB 或 daidir 全量指纹、source/canonical request、raw stdout、stderr、parsed
response、时间戳和独立 collection UUID。

validator 会重新计算这些信息，并额外检查：

1. evidence 采集晚于当前 case metadata、plan 和失败日志，不能从基础 case 继承。
2. canonical request 能由当前 case 的 source request 重建，request/response action 和
   `request_id` 一致。
3. parsed response 与真实 raw stdout 中的 KDebug response 完全一致。
4. KDebug 返回 `ok=true`、统一后的 `tool.name=kdebug` 和版本，且 diagnostic action 不是
   `actions`、`schema`、`server.ping` 等控制操作。
5. response 不是 shared fail log 的长子串或高相似度包装。
6. manifest summary 和 reported versions 可由 invocation 重新计算。
7. `evidence/with_kdebug/` 没有 plan 未声明的额外文件。
8. suite 内没有跨 case 复用 collection UUID。

缺少声明文件时标记 `TOOL_EVIDENCE_MISSING`；manifest、退出码、输入、工具 runtime、hash、
freshness、raw response 自洽性或唯一性失败时标记 `TOOL_EVIDENCE_INVALID`。校验发生在 API
key 查询和模型调用之前，两种状态都不计为模型失败或有效工具组结果。

工具调用有效仍不等于工具对修复有贡献。最终逐 case 报告仍应分别审计“manifest 有效”“模型
公开回复引用了哪个独有事实”“补丁是否命中该事实指向的根因”“judge 是否 PASS”。

## 8. 可复核命令

以下命令只读取历史 suite：

```bash
SUITE=/root/XiangShan-build/build/xverif_benchmark/v2_run_20260630_025641

# 查看 16 份 smoke 文件是否完全相同。
sha256sum "$SUITE"/case_*/evidence/with_xdebug/xdebug_tool_smoke.md

# 查找真实波形输入；本次结果为空。
find "$SUITE" -type f \( -iname '*.fsdb' -o -iname '*.vcd' -o -iname '*.vpd' \)

# 查看 matrix 是否出现真实工具命令，而不只是分组名和 evidence 字段。
grep -niE 'kdebug|xdebug|verdi|npi|fsdb' "$SUITE/matrix_api.log"

# 查看 runner 同时加入 shared fail log 和工具组 evidence 的代码。
sed -n '492,530p' \
  /root/xverif/benchmarks/xdebug_repair_benchmark/scripts/api_model_runner.py

# 查看模型是否具有任意工具执行通道；该循环只处理文件请求或 diff。
sed -n '1380,1580p' \
  /root/xverif/benchmarks/xdebug_repair_benchmark/scripts/api_model_runner.py
```

配套文档：

- [真实注错代码审计](benchmark_fault_injection_audit.md)
- [逐 Case 模型修复轨迹](benchmark_model_case_analysis.md)
