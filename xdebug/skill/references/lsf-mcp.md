# xdebug MCP LSF backend

本文说明 AI MCP 场景下如何让 `tools/xdebug-mcp` 把查询提交到 LSF 计算节点。它和 xdebug 原生 `transport:"file"` 是两件事：

- MCP LSF backend：AI 客户端通过 MCP tool 调用，wrapper 负责启动 LSF router/session job。
- 原生 file transport：xdebug daemon 通过共享文件系统交换 request/response，不依赖 MCP。

## 什么时候使用

使用 MCP LSF backend：

- AI 客户端或 Codex/Claude 在登录机上。
- Verdi/NPI license、FSDB 访问或运行环境只在 LSF 计算节点上可用。
- 登录机不能直接连接计算节点 TCP 端口。
- 用户希望 MCP wrapper 管多个 session，并且不同 session 可以并行查询。

不要使用 MCP LSF backend：

- 本机可以直接运行 `tools/xdebug`。
- 只需要普通命令行，不走 MCP；这时优先考虑 xdebug 原生 `transport:"file"`。
- 用户没有授权提交 LSF job。

## MCP 配置

```json
{
  "mcpServers": {
    "xdebug": {
      "command": "<xverif-root>/tools/xdebug-mcp",
      "env": {
        "XVERIF_HOME": "<xverif-root>",
        "XDEBUG_MCP_BACKEND": "lsf"
      }
    }
  }
}
```

常用环境变量：

| 变量 | 说明 |
| --- | --- |
| `XDEBUG_MCP_BACKEND=lsf` | 启用 LSF backend |
| `XDEBUG_LSF_BSUB` | 覆盖 `bsub` 命令，例如站点 wrapper |
| `XDEBUG_MCP_TIMEOUT_SEC` | direct backend 请求超时；LSF router/session 有自己的 request timeout |
| `PYTHON` | 指定 MCP wrapper Python，建议 Python 3.11+ |
| `XVERIF_HOME` | 指向仓库根，计算节点用它定位 `tools/xdebug` |

本地 fake smoke：

```bash
PYTHON=python3 XDEBUG_MCP_FAKE_LSF=1 tools/xdebug-lsf-doctor --fake
```

真实环境 smoke：

```bash
PYTHON=python3 tools/xdebug-lsf-doctor
```

## 架构

```text
AI MCP client
  -> tools/xdebug-mcp
  -> bsub -I router job
  -> per-session TCP endpoint jobs
  -> tools/xdebug
```

Router 是 JSONL 控制平面，只负责注册 session、转发 query、回收 dead session。每个 session endpoint 在计算节点上串行执行该 session 的请求，避免同一个 xdebug daemon 被并发访问。

并发规则：

- 不同 session 可以并行。
- 同一个 session 串行。
- Router stdout 写入有锁，避免多个响应互相交织。
- Router crash 后 wrapper 会重启 router，并重新注册仍 alive 的 session。
- 单个 session crash 不应影响其他 session。

## MCP tool 使用顺序

1. 打开 session：

```json
{
  "name": "case_a",
  "fsdb": "<waves.fsdb>",
  "daidir": "<simv.daidir>",
  "make_default": true
}
```

2. 查询：

```json
{
  "action": "value.at",
  "args": {
    "signal": "top.clk",
    "time": "100ns"
  }
}
```

3. 需要机器解析时显式请求 JSON：

```json
{
  "action": "value.at",
  "args": {
    "signal": "top.clk",
    "time": "100ns"
  },
  "output_format": "json"
}
```

`xdebug_query` 在 LSF backend 下默认返回 xout 文本；`output_format:"json"` 返回 xdebug JSON；`output_format:"envelope"` 返回 wrapper envelope、xout 和 session 摘要。

## 故障处理

- `SESSION_REQUIRED`：先调用 `xdebug_session_open`，或用 `xdebug_session_use` 切默认 session。
- `SESSION_DEAD`：该 session endpoint 已不可用；重新 `xdebug_session_open`。
- Router 不响应：跑 `tools/xdebug-lsf-doctor`，看 `bsub` 是否可用、router ready 是否能解析。
- stdout 污染：LSF banner 可以出现在 ready 前；ready 后 stdout 必须是 JSONL。
- 同一 session 查询太慢：检查 action 是否请求了 `debug/full/include_rows/include_transactions`，优先缩小窗口或用 compact。

## Agent 规则

- 不要让 AI 手写 router JSONL。
- 不要让 AI 暴露计算节点 TCP 端口给登录机直连。
- 不要把 MCP LSF backend 和原生 `transport:"file"` 混为一谈。
- 不确定 action 参数时仍然用 `xdebug_actions` / `xdebug_schema` 查询契约。
