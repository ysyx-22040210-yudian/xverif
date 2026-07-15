# MCP stateful sessions

MCP 的 kdebug/kcov stateful session 通过同一套 stdio-loop session manager 实现。

## kdebug

- `kverif_debug_session_open(name, fsdb=None, daidir=None, queue=None, resource=None)`
- `kverif_debug_query(session, action, args=None, limits=None, output=None, output_format="kout")`
- `kverif_debug_session_list()`
- `kverif_debug_session_close(name=..., session_id=...)`

## kcov

- `kverif_cov_session_open(name, vdb, queue=None, resource=None)`
- `kverif_cov_query(session, action, args=None, limits=None, output=None, output_format="kout")`
- `kverif_cov_session_list()`
- `kverif_cov_session_close(name=..., session_id=...)`

## 规则

- open 后保存 alias 或 backend `session_id`。
- 同 session 请求串行；多 session 可并行。
- `output_format="json"` 用于脚本字段读取，`envelope` 用于定位 wrapper/stdio-loop。
- `SESSION_LOST` 后该 session 已不可复用，必须重新 open。
