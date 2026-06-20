# xdebug rc.generate

`rc.generate` 用于生成 nWave `signal.rc` 证据视图。它适合把关键波形、marker 和 debug evidence 固化给用户复查。

## 使用规则

- 先用 value/event/trace action 找到关键 signal 和时间窗口。
- 再用 `rc.generate` 生成 rc，不要让 AI 手写 nWave rc。
- 输出中保留 `output_path`，并说明生成了哪些 signal/marker。

## 常见流程

1. 打开 FSDB 或 combined session。
2. 用 `event.find` / `value.batch_at` / `trace.active_driver` 收集证据。
3. 调 `rc.generate`，传 signals、time window、markers。
4. 若路径写入失败，读 `error.code/message`，检查输出目录权限。
