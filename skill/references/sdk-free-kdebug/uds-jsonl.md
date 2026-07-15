# SDK-free UDS JSONL 协议

启动 server：

```bash
KVERIF_LOOP_SOCKET=/tmp/kverif-loop.sock tools/kverif-loop-server
```

发送单个请求：

```bash
tools/kverif-loop-client --socket /tmp/kverif-loop.sock --json \
  '{"id":"1","method":"debug.session.open","params":{"name":"s0","fsdb":"waves.fsdb"}}'
```

也可从 stdin 发送 JSONL。

## 请求格式

```json
{"id":"1","method":"debug.query","params":{"session":"s0","action":"value.at","args":{"signal":"top.clk","time":"10ns"},"output_format":"json"}}
```

成功：

```json
{"id":"1","ok":true,"result":{}}
```

失败：

```json
{"id":"1","ok":false,"error":{"code":"SESSION_LOST","message":"..."}}
```

## kdebug 方法

- `server.ping`
- `server.shutdown`
- `debug.session.open`
- `debug.session.list`
- `debug.session.close`
- `debug.query`

`debug.query` 会把 `action/args/limits/output/output_format` 转给当前 managed session，并固定 target 为该 session。不要用它发送 lifecycle raw request。

## 环境变量

- `KVERIF_LOOP_SOCKET`：socket 路径。
- `KVERIF_LOOP_BACKEND=direct|lsf`：启动模式。
- `KVERIF_LOOP_LOG_DIR`：日志根目录。
- `KVERIF_LOOP_STARTUP_TIMEOUT_SEC`：open timeout。
- `KVERIF_LOOP_REQUEST_TIMEOUT_SEC`：query timeout。
- `KVERIF_LOOP_CLOSE_TIMEOUT_SEC`：close timeout。
