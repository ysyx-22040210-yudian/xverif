# kverif MCP 总览

`tools/kverif-mcp` 是基于 FastMCP 的统一入口。交互式 AI 工具调用优先使用 MCP，除非用户无法使用 MCP SDK 或明确需要脚本化 SDK-free wrapper。

## 工具组

- kdebug：stateful backend，`kverif_debug_*`。
- kcov：stateful backend，`kverif_cov_*`。
- kbit/kentry/kloc/kberif/ksva：stateless CLI adapter。
- common：`kverif_tools`、`kverif_tool_help`、`kverif_batch`。

如果不确定哪些工具暴露，先调用 `kverif_tools`。`KVERIF_MCP_ENABLE_*` 可能关闭部分工具组。

## raw request

- `kverif_debug_raw_request` / `kverif_cov_raw_request` 是 one-shot CLI 路径。
- raw request 不走 MCP-managed session manager，也不维护 stdio-loop/LSF job。
- 需要长期 session 时使用 `kverif_debug_session_open` + `kverif_debug_query`。

## batch

`kverif_batch` 执行 NDJSON tool 请求文件，适合 open -> query -> close 的串行流程。batch 行里的 tool 参数需要嵌套在 `args` 里。
