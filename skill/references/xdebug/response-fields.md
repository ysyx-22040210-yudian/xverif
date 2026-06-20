# xdebug 响应读取

## 通用读取顺序

1. 先看 `ok`。
2. 出错读 `error.code`、`error.message`、`summary`。
3. 成功读 `summary` 的 compact 事实，再看 `data` 或 action-specific 字段。
4. 看到 `truncated:true` 时，缩小请求或提高 `limits`；不要把结果当全量。

## 必须保留的证据

- signal/path
- time/window
- value/known
- finding/status
- file:line
- confidence
- truncated
- output_path

## xout 与 JSON

默认 `xout` 是结构化文本，适合对话摘要。脚本或测试必须请求 JSON。

MCP/SDK-free wrapper 中：

- `output_format:"xout"`：返回 compact 文本。
- `output_format:"json"`：返回 backend JSON payload。
- `output_format:"envelope"`：返回 stdio-loop envelope，定位 wrapper 问题时使用。

## 常见字段提示

- `session.session_id` / `summary.session_id`：后续 target 使用的 session。
- `payload_format`：stdio-loop envelope 的 payload 类型。
- `xbit_hints.commands[]`：下一步应该交给 xbit 的确定性计算命令。
- `source_location` / `evidence.file` / `evidence.line`：最终回答优先引用。
- `limits` / `returned` / `matched_count`：判断结果是否完整。
