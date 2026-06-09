---
name: xdebug
description: >
  当 AI agent 需要通过 xdebug 的 JSON request 接口查询 Verdi/VCS daidir 设计事实、
  FSDB 波形事实，或把两者联合起来定位当前生效 driver、依赖图、波形值、事件、
  APB/AXI/verify 结果时使用。适用于 RTL 因果追踪、波形取证、协议异常定位、
  compact payload 读取、combined active-driver debug，以及把 xtrace/xwave 能力
  统一到单一 xdebug JSON 请求的工作流。
---

# xdebug JSON Request / XOUT 调试接口

xdebug 是原 xtrace 与 xwave 的统一事实查询入口。设计事实来自 `daidir`，波形事实来自 `fsdb`，两者同时存在时可以做 combined/debug join。公开调用用 JSON request 描述动作；默认输出是 `xout` 结构化文本，机器解析必须加 `--json`。

主 skill 只规定 agent 行为。详细 API、字段和工作流放在 references：

- API 速查：[references/json-api-reference.md](references/json-api-reference.md)
- 响应字段字典：[references/ai-response-dictionary.md](references/ai-response-dictionary.md)
- 常见 debug recipes：[references/recipes.md](references/recipes.md)
- MCP LSF backend：[references/lsf-mcp.md](references/lsf-mcp.md)
- LSF/file transport：[references/file-transport.md](references/file-transport.md)
- nWave rc 生成：[references/rc-generate.md](references/rc-generate.md)

## 什么时候使用

使用 xdebug：

- 用户给出 `daidir`、`fsdb`、`session_id`、波形时间点、RTL 信号路径、APB/AXI/handshake/debug 现象。
- 需要查“事实”：某个 signal 的值、变化、driver、load、依赖路径、源码 evidence、协议 finding。
- 需要把波形异常时间点连接到当前生效 RTL driver：用 `trace.active_driver`。
- 需要生成 nWave `signal.rc` 证据视图：用 `rc.generate`。

不要用 xdebug：

- 只是做 bit slice、mask、concat、signed/unsigned、expected value 计算；用 xbit。
- 只是从日志位置 ID 还原源码行；用 xloc。
- 只是按配置切 entry field；用 xentry。
- 只是管理项目 summary cards；用 xberif。

## 强制规则

- 默认使用 `xdebug` 或 `tools/xdebug`；不要推荐旧 `xtrace` / `xwave` 人类 CLI 作为主路径。
- 机器解析必须加 `--json`；不要解析默认 `xout` 文本。
- 不确定 action 参数时，先查 `actions`，再查 action-specific `schema`，不要猜字段。
- 多步调试先 `session.open`，后续用 `target.session_id`，不要反复 `auto_open`。
- LSF / 登录机无法连接计算节点 TCP 端口时，使用 `transport:"file"`，不要继续尝试 TCP 直连。
- 默认 `output.verbosity:"compact"`；需要证据时只打开精确 `include_*`，不要直接 `debug`。
- 结论必须保留 `signal`、`time/window`、`value/finding`、`file:line`、`confidence`、`truncated`。

## 入口选择

优先使用 shell 中已安装的 `xdebug` 命令。`xdebug` 应来自仓库 `tools/xdebug` wrapper。回答和文档中不要暴露本机绝对路径；使用 `<xverif-root>`、`<repo-root>` 或 `$XVERIF_HOME`。

```bash
xdebug -h
xdebug -help
xdebug -
xdebug --json -
xdebug request.json
```

`-h` / `-help` 是唯一非 JSON 人类帮助入口。机器可读能力用 JSON action：

```bash
xdebug --json - <<'JSON'
{
  "api_version": "xdebug.v1",
  "action": "actions"
}
JSON
```

如果当前 shell 未安装 `xdebug`，且当前目录是仓库根目录，可以临时使用 `tools/xdebug`。兼容入口 `tools/xdebug-env` 只作为旧脚本转发。

MCP 场景使用 `tools/xdebug-mcp`，它内部仍调用 `tools/xdebug --json -` 或 LSF backend 里的 per-session endpoint，但会维护多个 session 别名和默认 session。MCP tool 选择：

- `xdebug_session_open`：打开/复用 `daidir`、`fsdb` 或 combined session。
- `xdebug_session_use`：切换默认 session。
- `xdebug_query`：用默认 session 调 action。
- `xdebug_request`：需要完整 envelope 控制时直接传 xdebug JSON request。
- `xdebug_actions` / `xdebug_schema`：查询机器契约。

当用户说明 AI 客户端在登录机、查询必须跑到 LSF 计算节点、且登录机无法直连计算节点 TCP 端口时，MCP 首选 `XDEBUG_MCP_BACKEND=lsf`。这个 backend 由 `tools/xdebug-mcp` 启动 LSF router job 和 per-session endpoint job；agent 仍只调用 MCP tools，不手写 router JSONL。详细规则见 [references/lsf-mcp.md](references/lsf-mcp.md)。

## 资源 target 决策

| target | 能力 |
| --- | --- |
| `{"daidir":"simv.daidir"}` | 设计侧：driver/load/query、graph、explain、path、source、expr、FSM/counter/sequential |
| `{"fsdb":"waves.fsdb"}` | 波形侧：scope、value、list、event、APB、AXI、verify、signal、handshake、anomaly、rc.generate |
| `{"daidir":"simv.daidir","fsdb":"waves.fsdb"}` | 联合侧：波形时间点和设计因果 join，同时允许设计/波形 action fallback |
| `{"session_id":"case_a"}` | 复用已打开 session 的资源集合 |

仅传 `daidir` 时，波形 action 应失败或要求 `fsdb`。仅传 `fsdb` 时，设计 action 应失败或要求 `daidir`。两者都有时，优先考虑 `trace.active_driver` 这类 combined action。

## session / transport 决策

单次查询可用 `auto_open:true` 或 `auto_ensure:true`。多步调试必须先 `session.open`，后续复用 `target.session_id`。

同名 `session.open` 默认返回 `SESSION_ID_EXISTS`。确认资源相同并希望复用时传 `args.reuse:true`；要强制替换旧 session 时传 `args.reopen:true`。

Transport 选择：

- 默认 `uds`：同机本地调试首选，不要主动切 TCP/file。
- `tcp`：仅在 UDS socket 不可达、容器/namespace 隔离或用户明确需要跨进程/远程 daemon 时使用。
- `file`：登录机无法连接计算节点 TCP 端口、LSF batch、共享文件系统可见时使用。

注意区分：

- MCP 场景的 LSF backend 是 `tools/xdebug-mcp` 的运行模式，适合 AI 客户端通过 MCP 访问集群计算节点。
- xdebug 原生 `transport:"file"` 是 daemon/session 通信模式，适合不走 MCP 的命令行或共享文件系统 request/response。

file transport 规则：

- agent 只通过 xdebug JSON API 打开 file session。
- 不要建议暴露计算节点 TCP port。
- 不要依赖 UDS 跨节点。
- 不要手动读写 `requests/`、`responses/`、`claims/` 文件。
- 需要诊断时读日志、`done/`、`failed/`，不要手工修改 transport 目录。

详细目录状态机和环境变量见 [references/file-transport.md](references/file-transport.md)。

## 高频意图到 action

| 用户意图 | 首选 action | 补充 action | 禁忌 |
| --- | --- | --- | --- |
| 单点查值 | `value.batch_at` | `value.at` | 同一时间多信号不要多次单独 `value.at` |
| 找异常时间 | `event.find` | `signal.changes` / `handshake.inspect` | 不要先拉全量 changes |
| 证明窗口稳定/违例 | `window.verify` | `signal.statistics` | 不要靠 agent 自己扫 rows |
| 查 ready/valid stall | `handshake.inspect` | `event.export` | 不要直接导出所有 transaction |
| 查 driver | `trace.driver` | `trace.graph` / `trace.explain` | 不要靠源码文本猜 |
| 查当前生效 driver | `trace.active_driver` | `value.batch_at` | 必须有 daidir + fsdb + time |
| 查源码证据 | `source.context` | `trace.explain` | 不要默认 include 整个 module |
| 查 APB/AXI 异常 | `apb.query` / `axi.analysis` | `axi.query` | 不要默认 include 正常 transaction/beat |
| 查 X/Z | `detect_anomaly` | `signal.changes` / `trace.active_driver` | 不要把 `known:false` 直接当 root cause |
| 生成波形证据 | `rc.generate` | `value.batch_at` / marker config | 不要让 AI 手写 nWave rc |

不确定 action 是否存在、参数怎么写、compact 响应字段叫什么时，按“机器可读契约查询流程”执行。

## 机器可读契约查询流程

1. 查 action catalog：

```bash
xdebug --json - <<'JSON'
{
  "api_version": "xdebug.v1",
  "action": "actions"
}
JSON
```

2. 查具体 action request schema：

```bash
xdebug --json - <<'JSON'
{
  "api_version": "xdebug.v1",
  "action": "schema",
  "args": {
    "action": "trace.driver",
    "kind": "request"
  }
}
JSON
```

3. 查具体 action response schema：

```bash
xdebug --json - <<'JSON'
{
  "api_version": "xdebug.v1",
  "action": "schema",
  "args": {
    "action": "trace.driver",
    "kind": "response"
  }
}
JSON
```

4. 若 schema 仍不直观，读取 catalog 给出的 request/response example 文件。构造真实请求时优先从 example 改 `target` 和 `args`。

真实契约优先级：

1. runtime `actions`
2. runtime `schema`
3. `xdebug/schemas/v1/actions/*.schema.json`
4. `xdebug/examples/requests` 和 `xdebug/examples/responses`
5. skill references

## 标准 debug workflow

1. 从用户上下文、日志或外部 `rg` 找候选 signal/module/interface。
2. 先用 compact 查询确认事实，不要默认请求大 payload。
3. 波形问题：先定位时间点和异常窗口，再取相关信号值。
4. 设计问题：先查直接 driver/load/source evidence，再扩 graph/path。
5. 两类资源都有：用 `trace.active_driver` 在具体时间点做 join。
6. 最终结论保留 evidence chain，不输出大 rows/samples/transactions。

资源分支：

- 只有 `daidir`：`trace.driver/load/query` -> `trace.graph/explain/path` -> `source.context`。
- 只有 `fsdb`：`scope.list` -> `value.batch_at` -> `event.find/window.verify/signal.*` -> protocol/handshake。
- 同时有 `daidir` 和 `fsdb`：波形定时点 -> `value.batch_at` -> `trace.active_driver` -> `source.context`。
- 已有 `session_id`：优先复用 session，不要重新传路径。
- 信号找不到：波形侧先 `scope.list`；设计侧先外部 `rg` 找候选，再给 xdebug exact path。
- 结果截断：先缩小 `time_range`、降低 depth 或提高具体 `limits`；再考虑精确 `include_*`。

## payload 控制

默认 `output.verbosity` 是 `compact`。compact 目标是让 agent 下一步可决策，不是证明所有中间过程。

| verbosity | 使用时机 |
| --- | --- |
| `compact` | 默认，多步探测、用户摘要、快速决策 |
| `full` | 迁移旧脚本、确认完整字段、需要详细 payload |
| `debug` | 诊断 session、daemon、transport、trace 展开过程、内部错误 |

compact 默认不应返回：

```text
expanded_queries
parse_steps
raw_edges
all_samples
all_events
all_changes
normal_transactions
timeline
source_text
module_body
```

include 原则：

- 引源码文本：只加 `include_source:true`。
- 看 trace 展开过程：只加 `include_trace:true` 或 `include_expanded_queries:true`。
- 导出事件/样本明细：只加 `include_rows:true` 或 `include_samples:true`，并设置 `limits.max_rows`。
- 查协议明细：先看 compact findings，只在需要证明异常 transaction/beat/access 时加 `include_transactions`、`include_beats`、`include_accesses`。

## 禁止模式

- 不要用 `signal.changes` 的 row count 当周期数；周期统计用 `signal.statistics` 加 clock。
- 不要多次调用 `value.at` 查同一时间多信号；用 `value.batch_at`。
- 不要默认 `include_rows/include_transactions/include_source/debug`。
- 不要在 agent 中手算 bit slice；用 `slice_hint` 后调用 xbit。
- 不要在 agent 中手算 TimeSpec/cursor offset；交给 xdebug。
- 不要把 `known:false`、`pass:null`、`status:"unknown"` 当作失败。
- 不要把 `meta.truncated:true` 的结果当成全集。
- 不要让 xdebug 做模糊 signal search；波形用 `scope.list`，源码候选用 `rg`。
- 不要把旧 xtrace/xwave CLI 作为主路径。

## 错误处理 playbook

- `SIGNAL_NOT_FOUND`：波形侧先 `scope.list`；设计侧先外部 `rg` 搜源码候选，再重试 exact path。
- `TIME_SPEC_INVALID`：检查 `time`、`at`、`time_range`、cursor 名和 clock path；cycle offset 交给 xdebug 解析。
- `SESSION_NOT_FOUND`：先 `session.list`，再 `session.open reuse:true` 或重新 open。
- `SESSION_UNHEALTHY`：跑 `session.doctor`；看 lifecycle/transport logs。
- `UNKNOWN_ACTION`：查 `actions`；不要回退旧 CLI；combined 生效驱动是 `trace.active_driver`。
- `INTERNAL_ENGINE_FAILED`：检查资源路径、权限、Verdi/NPI 环境、daemon 工作目录和日志。

## 最终回答证据链格式

基于 xdebug 给出 root cause 或 debug 判断时，按这个结构回答：

1. 现象
   - `signal`
   - `time/window`
   - observed value
   - expected behavior
2. 波形证据
   - action
   - key values
   - event/finding
   - `truncated`
3. 设计证据
   - driver/source
   - control condition
   - `file:line`
   - confidence
4. 判断
   - root cause candidate
   - why this explains waveform
   - uncertainty
5. 下一步
   - one focused query or one manual check

只给用户高信号事实。不要粘贴完整 rows、samples、transactions、trace、expanded_queries，除非用户明确要求。

## 需要更多细节时读取哪些 reference

- 不知道 action 参数、request envelope、TimeSpec、include 开关：读 [references/json-api-reference.md](references/json-api-reference.md)。
- 不知道响应字段含义、compact/full/debug 读取规则：读 [references/ai-response-dictionary.md](references/ai-response-dictionary.md)。
- 要处理 ready 卡低、valid 脉冲、AXI latency、X/Z、FSM/counter：读 [references/recipes.md](references/recipes.md)。
- 用户提到 LSF、共享文件系统、TCP 不可达、file session：读 [references/file-transport.md](references/file-transport.md)。
- 用户要生成 nWave `signal.rc`、marker、analog、表达式信号：读 [references/rc-generate.md](references/rc-generate.md)。
