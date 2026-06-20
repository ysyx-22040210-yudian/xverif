# xdebug 常用流程

## 单点查值

1. 打开 FSDB session。
2. 用 `value.batch_at` 一次查多个信号。
3. 如果响应含 `xbit_hints.commands[]` 或 `slice_hint`，切到 xbit 计算，不要心算。

## 当前生效 driver

1. 确认同时有 `daidir` 和 `fsdb`。
2. 打开 combined session。
3. 用 `trace.active_driver`，传目标 signal 和 time/window。
4. 回答时保留 active assignment、guard 条件、value、file:line、confidence。

## 设计 driver/load/path

- 用 `trace.driver` 查静态 driver。
- 用 `trace.graph` / `trace.explain` 看依赖图和解释。
- 需要源码上下文时再用 `source.context`，不要默认拉整个 module。

## 事件和窗口验证

- 找边沿或条件命中：`event.find`。
- 验证窗口内稳定/违例：`window.verify`。
- handshake stall：`handshake.inspect`，不要直接导出全量 transaction。

## APB/AXI

1. 先 `apb.config.load` 或 `axi.config.load` 注册信号映射。
2. 再用 `apb.query`、`axi.analysis`、`axi.channel_stall`、`axi.latency_outlier`。
3. 没有 config 的 query 不可靠；不要跳过 config.load。

## X/Z 或异常

1. 用 `detect_anomaly` 找时间和信号。
2. 对关键点用 `value.batch_at` 和 `trace.active_driver` 连接到 RTL 因果。
3. `known:false` 不是 root cause，只是值未知的证据。
