---
name: kverif
description: >
  当 AI agent 需要使用 kverif 验证工具体系时使用：kdebug 查询 daidir/FSDB
  事实和 RTL 因果，SDK-free kdebug wrapper 在没有 MCP SDK 或需要脚本化 LSF
  stdio-loop session 时使用，MCP kverif tools 用于交互式 AI 工具访问，kcov 查询
  VCS/Verdi coverage database，kbit 做确定性 bit/SV literal/表达式计算，kloc
  还原压缩日志位置 ID，kentry 解 entry/descriptor fragments，kberif 管理项目
  context cards/details，ksva 解析 SVA IR，keda-runner 安全执行 EDA 命令。
---

# kverif 工具 Skill

这是 kverif 工具体系的导航 skill。只读取当前任务需要的 reference，不要默认加载全部文档。

## 任务路由

| 任务 | 读取 |
| --- | --- |
| 查询 daidir、FSDB、波形值、driver、active driver、APB/AXI、verify、rc | [references/kdebug/overview.md](references/kdebug/overview.md) |
| 构造 kdebug JSON request、raw CLI request、查 action/schema | [references/kdebug/json-api.md](references/kdebug/json-api.md) |
| 按流程做 kdebug debug | [references/kdebug/recipes.md](references/kdebug/recipes.md) |
| 参考 kdebug 实战示例和证据链写法 | [references/kdebug/examples.md](references/kdebug/examples.md) |
| 读取 kdebug compact/kout/JSON 字段 | [references/kdebug/response-fields.md](references/kdebug/response-fields.md) |
| 定位 kdebug 原生命令、session、socket、engine、日志问题 | [references/kdebug/troubleshooting.md](references/kdebug/troubleshooting.md) |
| 判断 kdebug UDS/TCP/file transport | [references/kdebug/transport.md](references/kdebug/transport.md) |
| 生成 nWave rc 证据 | [references/kdebug/rc-generate.md](references/kdebug/rc-generate.md) |
| 不用 MCP SDK、脚本化或必须 LSF 地运行 kdebug session | [references/sdk-free-kdebug/overview.md](references/sdk-free-kdebug/overview.md) |
| 使用 SDK-free UDS JSONL 协议 | [references/sdk-free-kdebug/uds-jsonl.md](references/sdk-free-kdebug/uds-jsonl.md) |
| 使用 SDK-free kdebug LSF backend | [references/sdk-free-kdebug/lsf.md](references/sdk-free-kdebug/lsf.md) |
| 定位 SDK-free wrapper 问题 | [references/sdk-free-kdebug/troubleshooting.md](references/sdk-free-kdebug/troubleshooting.md) |
| 使用 MCP kverif 工具、工具组、batch、raw request | [references/mcp/overview.md](references/mcp/overview.md) |
| 使用 MCP 托管的 kdebug/kcov stateful session | [references/mcp/stateful-sessions.md](references/mcp/stateful-sessions.md) |
| 使用 MCP LSF backend | [references/mcp/lsf.md](references/mcp/lsf.md) |
| 定位 MCP server、tool、session 问题 | [references/mcp/troubleshooting.md](references/mcp/troubleshooting.md) |
| 查询 VCS/Verdi coverage database | [references/kcov.md](references/kcov.md) |
| 计算 bit slice、SV literal、mask、表达式、expected value | [references/kbit.md](references/kbit.md) |
| 还原 `L_XXXXXXXX` 日志位置 ID | [references/kloc.md](references/kloc.md) |
| 解 entry/descriptor/header fragments | [references/kentry.md](references/kentry.md) |
| 管理项目 context cards/details | [references/kberif.md](references/kberif.md) |
| 解析和解释 SVA IR | [references/ksva.md](references/ksva.md) |
| 安全执行 make/vcs/simv/verdi 类 EDA 命令 | [references/keda-runner.md](references/keda-runner.md) |

## 入口选择

- 有 MCP client 且 MCP SDK 可用时，交互式 AI 工具调用优先用 MCP。
- MCP 场景下，kdebug 原生 action 能力从 `kverif_debug_query` 进入：先 `kverif_debug_session_open`，再把 `trace.driver`、`value.batch_at`、`event.find`、`trace.active_driver` 等 action 作为 query 参数传入。
- `kverif_debug_raw_request` 只用于需要完整 kdebug envelope 控制或验证 raw CLI 行为；常规 kdebug debug workflow 不默认使用 raw request。
- 必须使用 LSF，且不能使用 MCP、不能安装 MCP SDK，或需要脚本/批处理直接驱动长期 kdebug `--stdio-loop` session 时，优先用 SDK-free kdebug wrapper。
- 只需要一次性完整 JSON request 时，可以用 kdebug/kcov raw CLI；raw CLI 不是 wrapper 托管的 stdio-loop session。
- 项目里存在 keda-runner 配置时，EDA 命令必须走 `keda-runner`；不要直接跑 `make`、`vcs`、`simv`、`urg`、`verdi` 或项目 setup。

## 通用规则

- 脚本解析或字段比较时使用 JSON；不要解析默认人类文本。
- 不确定 action 参数时，先查 `actions` 和 action-specific `schema`，不要猜字段。
- 结论保留事实证据：signal/path/time/value/file:line/error code。
- 用户可见回答不要暴露本机绝对路径；用 `<kverif-root>`、`<project-root>` 或 `$KVERIF_HOME`。
- license/NPI/仿真/真实 LSF/UDS bind/file transport 实机验证可能需要在受限沙箱外运行。
- 返回 `truncated:true` 时，缩小查询或显式提高 limits；不要把 compact 输出当全量。
