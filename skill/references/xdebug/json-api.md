# xdebug JSON API

## 契约查询流程

先查 action catalog：

```bash
xdebug --json - <<'JSON'
{"api_version":"xdebug.v1","action":"actions","output":{"format":"json"}}
JSON
```

再查 request/response schema：

```bash
xdebug --json - <<'JSON'
{"api_version":"xdebug.v1","action":"schema","args":{"action":"value.at","kind":"request"},"output":{"format":"json"}}
JSON
```

真实契约优先级：runtime `actions`、runtime `schema`、`xdebug/schemas/v1/actions/*.schema.json`、examples、skill reference。

## request envelope

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {"session_id": "s0"},
  "args": {"signal": "top.clk", "time": "10ns"},
  "limits": {"max_items": 100},
  "output": {"format": "json", "verbosity": "compact"}
}
```

## raw CLI request

raw CLI 是一次性短进程，不走 wrapper 托管的 `--stdio-loop`：

```bash
tools/xdebug --json - <<'JSON'
{"api_version":"xdebug.v1","action":"session.open","target":{"fsdb":"waves.fsdb"},"args":{"name":"s0"},"output":{"format":"json"}}
JSON
```

raw 可以打开 xdebug 原生 session，但 alias map、stdio-loop 进程、LSF job 生命周期要由调用者自己管理。

## stdio-loop query 边界

MCP 和 SDK-free wrapper 的 managed session 路径走：

```text
session.open/query/close -> session manager -> tools/xdebug --stdio-loop
```

公开 query 接口会固定 `target.session_id` 并透传 `action/args/limits/output`。底层有完整 JSON request 发送能力，但默认不暴露任意 raw-over-stdio-loop，以避免绕过 session 生命周期保护。

## 输出格式

- `output.format:"json"`：脚本解析和字段比较。
- 默认 `xout`：AI 读 compact evidence。
- MCP/SDK-free wrapper 的 `output_format:"envelope"`：定位 wrapper/stdio-loop 时使用。
