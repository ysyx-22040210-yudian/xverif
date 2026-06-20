# xdebug transport

## 选择规则

- `uds`：默认本机调试首选。
- `tcp`：只有 UDS 不可达、容器/namespace 隔离或明确远程 daemon 需求时使用。
- `file`：登录机无法连接计算节点 TCP/UDS，但共享文件系统可见时使用，特别适合非 MCP 的 LSF/batch 场景。

## file transport

通过 xdebug JSON API 打开 file session，不要手工读写 transport 目录：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {"fsdb": "waves.fsdb"},
  "args": {"name": "s0", "transport": "file"},
  "output": {"format": "json"}
}
```

如果计算节点只能访问共享文件系统，不要建议暴露 TCP 端口或依赖跨节点 UDS。

## MCP/SDK-free 与 xdebug transport 的区别

- MCP/SDK-free 的 LSF backend 是 wrapper 如何启动 `tools/xdebug --stdio-loop`。
- xdebug `transport` 是 session 内部 daemon/client 如何通信。
- 两者不是同一层。LSF wrapper 可以启动 stdio-loop；session 内部仍可选择 UDS/TCP/file。
