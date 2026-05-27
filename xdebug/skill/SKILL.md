---
name: xdebug
description: 使用 xdebug 的 JSON 接口读取 RTL 设计因果、FSDB 波形事实以及联合动态驱动解释。
---

# xdebug

`xdebug` 只接受 `xdebug.v1` JSON 请求。调用公开入口：

```bash
printf '%s\n' '<json-request>' | tools/xdebug-env -
```

不要调用 `xdebug/libexec/` 下的私有后端程序，也不要构造文本子命令。

## 资源选择

- `target.daidir`：用于 `signal.resolve`、`trace.driver`、`trace.expand`、
  `sequential.update`、`fsm.explain`、`counter.explain`。
- `target.fsdb`：用于 `value.at`、`value.batch_at`、`signal.changes`、
  `signal.statistics`、`sampled_pulse.inspect`、事件和协议查询。
- 两者同时提供：用于 `trace.active_driver`，并可继续调用任一单资源动作。

信号查询只接受精确层次路径。先使用 `rg` 在 RTL 中寻找候选，再把完整路径
交给 `signal.resolve` 或追踪动作；不要请求 `signal.search`。

## 联合追踪

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {"daidir": "/path/simv.daidir", "fsdb": "/path/waves.fsdb"},
  "args": {"signal": "top.u_dut.sig", "requested_time": "22us", "include_control": true}
}
```

优先读取 `driver_status`、`active_time`、`driver`、`controls` 和相关时刻值。
`control_only` 表示已确认控制上下文，但没有可信赋值证据；不要补写推测结论。

## 推荐流程

1. 用 `actions` 或 `schema` 确认动作和输入形状。
2. 对设计问题先做精确路径解析，再做驱动、展开或语义解释。
3. 对波形问题先做关键时刻的值查询，再按需要扩大到变化、统计或协议事件。
4. 需要关联代码原因与动态表现时，提供两个资源并调用联合追踪。
5. 输出较大时收紧 `limits`，保留能复核结论的证据字段。

session 状态统一存放于 `~/.xdebug/`；可使用 `session.open`、
`session.doctor`、`session.list` 与 `session.kill` 管理可复用会话。
