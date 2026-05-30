---
name: xdebug
description: >
  当 AI agent 需要通过 xdebug 的 JSON-only 接口查询 Verdi/VCS daidir 设计事实、
  FSDB 波形事实，或把两者联合起来定位当前生效 driver、依赖图、波形值、事件、
  APB/AXI/verify 结果时使用。适用于 RTL 因果追踪、波形取证、协议异常定位、
  compact payload 读取、combined active-driver debug，以及把 xtrace/xwave 能力
  统一到单一 xdebug JSON 请求的工作流。
---

# xdebug JSON 调试接口

xdebug 是原 xtrace 与 xwave 的统一入口。使用本 skill 时，把 xdebug 当作唯一事实查询工具：设计事实来自 `daidir`，波形事实来自 `fsdb`，两者同时存在时可以做 combined/debug join。公开调用只走 JSON，不要把旧 xtrace/xwave 人类 CLI 作为主路径推荐。只有用户明确询问历史命令或迁移旧脚本时，才提到旧入口。

详细字段字典见 [references/ai-response-dictionary.md](references/ai-response-dictionary.md)。完整 API 速查见 [references/json-api-reference.md](references/json-api-reference.md)。本文已经包含常用 action、模板和工作流；只有需要字段表或更多速查时再加载 references。

## 入口和基本调用

优先通过仓库 wrapper 调用：

```bash
tools/xdebug-env -
tools/xdebug-env request.json
```

stdin 单次请求：

```bash
printf '%s\n' '{"api_version":"xdebug.v1","action":"value.at","target":{"fsdb":"waves.fsdb","auto_open":true},"args":{"signal":"top.clk","time":"10ns"}}' \
  | tools/xdebug-env -
```

脚本里提取字段时，不解析人类文本，直接解析 JSON：

```bash
tools/xdebug-env - < request.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("ok"), d.get("summary", {}))'
```

请求 envelope：

```json
{
  "api_version": "xdebug.v1",
  "request_id": "optional-id",
  "action": "trace.driver",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {},
  "limits": {},
  "output": {
    "verbosity": "compact",
    "pretty": false
  }
}
```

## Target 和 fallback 规则

`target` 只能描述 `daidir`、`fsdb`、两者组合，或已打开的 `session_id`。

| target | 路由和能力 |
| --- | --- |
| `{"daidir":"simv.daidir"}` | 设计侧能力：driver/load/query、graph、explain、path、source、expr、FSM/counter/sequential |
| `{"fsdb":"waves.fsdb"}` | 波形侧能力：scope、value、list、event、APB、AXI、verify、signal、handshake、anomaly |
| `{"daidir":"simv.daidir","fsdb":"waves.fsdb"}` | 联合能力：波形时间点和设计因果 join，同时允许设计/波形 action fallback |
| `{"session_id":"case_a"}` | 复用已打开 session 中的资源集合 |

仅传 `daidir` 时，设计 action 正常执行，波形 action 应失败或要求 `fsdb`。仅传 `fsdb` 时，波形 action 正常执行，设计 action 应失败或要求 `daidir`。两者都有时优先使用 combined action；普通设计/波形 action 仍可按资源自动路由。

单次查询可以用 `auto_open:true` 或 `auto_ensure:true`。多步调试应先 `session.open`，后续使用 `target.session_id`，这样避免重复打开数据库和重复启动后台引擎。

## Agent 决策树

先判断用户给了什么资源：

- 只有 `daidir`：从设计因果入手。用 `trace.driver/load/query` 找直接事实，用 `trace.graph/explain/path` 扩展依赖，用 `source.context` 定位源码证据。
- 只有 `fsdb`：从波形证据入手。用 `scope.list` 确认真实路径，用 `value.at/batch_at` 取值，用 `event.export`、`verify.conditions`、`signal.*`、`handshake.inspect` 或协议 action 找异常窗口。
- 同时有 `daidir` 和 `fsdb`：先用波形找异常时间，再用 `trace.active_driver` 连接到当前生效 RTL driver；必要时补 `trace.graph` 查上游依赖。
- 已有 `session_id`：优先复用 session，不要重新传路径，除非用户明确要切换数据库。
- 信号找不到：不要猜路径。波形侧先 `scope.list`；设计侧用外部 `rg` 搜源码候选，再把精确层次名交给 xdebug。
- 结果截断：先缩小 `time_range`、降低 depth 或提高具体 `limits`；再考虑 `include_*`，不要直接切到全量 debug。

推荐完整 debug 顺序：

1. 通过用户上下文、日志或外部 `rg` 找到候选 signal/interface/module。
2. 用 compact 查询确认事实，不要默认请求大 payload。
3. 若是波形问题，先定位时间点和异常窗口。
4. 若是设计问题，先定位直接 driver/load 和 source evidence。
5. 若两类资源都有，用 `trace.active_driver` 在具体时间点做 join。
6. 对最终结论保留 `signal`、`time`、`value`、`file/line`、`finding`、`confidence`。

## 输出和 payload 控制

默认 `output.verbosity` 是 `compact`。compact 目标是让 agent 下一步可决策，而不是证明所有中间过程。

| verbosity | 何时使用 |
| --- | --- |
| `compact` | 默认。用于正常 agent debug、用户摘要、快速多步探测 |
| `full` | 迁移旧脚本、确认完整字段、需要详细 payload 但不诊断内部过程 |
| `debug` | 诊断 session、daemon、socket、trace 展开过程、dedup 统计、内部错误 |

compact 默认不应返回这些字段，除非显式 include 或 full/debug：

```text
expanded_queries
parse_steps
raw_edges
all_samples
all_events
all_changes
normal_transactions
timeline
source_text
module_body
```

设计侧 include：

```json
{
  "args": {
    "include_source": true,
    "include_ast": true,
    "include_candidates": true,
    "include_trace": true,
    "include_expanded_queries": true,
    "include_raw_edges": true,
    "include_graph": true,
    "include_debug": true
  }
}
```

波形侧 include：

```json
{
  "args": {
    "include_raw": true,
    "include_signal_meta": true,
    "include_rows": true,
    "include_samples": true,
    "include_all_changes": true,
    "include_transactions": true,
    "include_beats": true,
    "include_accesses": true,
    "include_debug": true
  }
}
```

通用限制：

```json
{
  "args": {
    "max_items": 20,
    "max_examples": 5
  },
  "limits": {
    "max_rows": 1000,
    "max_events": 1000,
    "max_samples": 1000000,
    "max_depth": 3,
    "max_paths": 10
  }
}
```

使用 include 的判断：

- 要给用户一个定位结论：只需要 compact 的 `summary`、`findings`、`file/line`、`examples`。
- 要引用源码文本：加 `include_source:true`，不要切 full。
- 要解释 trace 展开过程：加 `include_trace:true` 或 `include_expanded_queries:true`。
- 要导出事件或样本明细：加 `include_rows:true` 或 `include_samples:true`，同时设置 `limits.max_rows`。
- 要检查协议细节：先看 compact findings，只有需要证明 transaction/beat 时才加 `include_transactions`、`include_beats`、`include_accesses`。

## TimeSpec、cursor 和 range

波形侧时间字段通常接受 `time` 或 `at`。范围动作通常接受 `time_range`，部分动作也接受 `around/before/after`。

常见 TimeSpec：

```text
100ns
10us
500ps
@deadlock
@deadlock-20ns
@deadlock+5ns
@deadlock-10cycle(top.clk)
@deadlock+5posedge(top.clk)
@deadlock-2negedge(top.clk)
@-10ns
@+5ns
```

使用规则：

- 绝对时间支持 `us`、`ns`、`ps`、`fs`。
- `@name` 表示 named cursor；`@-10ns` 和 `@+5ns` 使用当前 active cursor。
- cycle offset 使用真实 FSDB clock edge。`cycle(clk)` 默认 posedge；需要边沿时写 `posedge(clk)` 或 `negedge(clk)`。
- 不要在 agent 里手算 cursor offset；把 TimeSpec 交给 xdebug。
- 找到关键异常时间后，应保存或复用 cursor，再在前后窗口继续查值和验证。

范围示例：

```json
{
  "time_range": {
    "begin": "@deadlock-100ns",
    "end": "@deadlock+20ns"
  }
}
```

around 示例：

```json
{
  "around": "@deadlock",
  "before": "100cycle(top.clk)",
  "after": "20cycle(top.clk)"
}
```

## 结果读取规则

任何响应都先读：

1. `ok`
2. `error.code` 和 `error.message`
3. `summary`
4. `data`
5. `findings`
6. `meta.truncated`

compact 响应可能省略空字段。不要假设 `session`、`tool`、空 `warnings`、空 `findings`、空 `suggested_next_actions` 总存在。

安全提取示例：

```bash
tools/xdebug-env - < request.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("ok")); print(d.get("error") or d.get("summary",{}))'
```

读取 batch values：

```bash
tools/xdebug-env - < request.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("data",{}).get("values",{}))'
```

读取 graph 规模：

```bash
tools/xdebug-env - < request.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d.get("summary",{}); print(s.get("node_count"), s.get("edge_count"), s.get("truncated"))'
```

`known:false`、`status:"unknown"`、`pass:null` 是不确定事实，不是失败结论。`meta.truncated:true` 表示响应被截断，结论只能作为 bounded evidence。

## 错误处理 playbook

### `SIGNAL_NOT_FOUND`

波形侧：

1. 用 `scope.list` 查父 scope。
2. 如果 scope 很大，先非递归，再有限递归。
3. 使用真实 FSDB path 重试 `value.at` 或相关 action。

设计侧：

1. 回源码用 `rg` 搜 leaf name、module instance、port connection。
2. 构造精确层次名后重试 `trace.driver` 或 `trace.load`。
3. 不要让 xdebug 做模糊 search。

### `TIME_SPEC_INVALID`

检查 `time`、`at`、`time_range.begin/end`、`around/before/after`。如果使用 cursor，先 `cursor.list` 或重新设置 cursor。cycle offset 要带 clock path，例如 `10cycle(top.clk)`。

### `SESSION_NOT_FOUND`

先 `session.list`。如果 session 不存在或资源变了，重新 `session.open`。如果怀疑 daemon 或 registry 异常，跑 `session.doctor`，必要时 `session.gc`。

### `UNKNOWN_ACTION`

检查 action 名是否属于 xdebug JSON API。不要回退到旧 xtrace/xwave CLI。常见拼写是 `trace.active_driver`，不是 `active.trace`。

### `INTERNAL_ENGINE_FAILED`

优先检查资源路径、权限、Verdi/NPI 环境、daemon 工作目录。对复用 session 先 `session.doctor`。如果是一次性 target，可换成 `session.open` 暴露更明确的 session 错误。

## Session actions

### `session.open`

打开一个 named session。重复调试建议始终先 open，再用 `target.session_id`。

同时打开 daidir 和 fsdb：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "case_a"
  }
}
```

仅设计 session：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "name": "design_case"
  }
}
```

仅波形 session：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "fsdb": "waves.fsdb"
  },
  "args": {
    "name": "wave_case"
  }
}
```

### `session.list`

列出已知 session：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.list"
}
```

### `session.doctor`

诊断 session、daemon、路径和资源状态：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.doctor",
  "target": {
    "session_id": "case_a"
  },
  "output": {
    "verbosity": "debug"
  }
}
```

### `session.gc`

清理 stale session：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.gc"
}
```

### `session.kill`

关闭一个或全部 session：

```json
{
  "api_version": "xdebug.v1",
  "action": "session.kill",
  "args": {
    "id": "case_a"
  }
}
```

```json
{
  "api_version": "xdebug.v1",
  "action": "session.kill",
  "args": {
    "id": "all"
  }
}
```

## Design actions

设计侧 action 需要 `target.daidir` 或包含 daidir 的 `session_id`。外部 `rg` 负责候选发现，xdebug 负责 exact fact。

### `trace.driver`

回答“谁驱动这个信号、依赖谁、证据在哪”。compact 默认只返回核心 drivers。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.driver",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "signal": "top.u.ready"
  },
  "limits": {
    "max_results": 20
  }
}
```

需要源码和完整 trace：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.driver",
  "target": {
    "session_id": "design_case"
  },
  "args": {
    "signal": "top.u.ready",
    "include_source": true,
    "include_trace": true
  }
}
```

### `trace.load`

回答“这个信号会加载到哪里、影响谁”。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.load",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "signal": "top.u.valid"
  },
  "limits": {
    "max_results": 20
  }
}
```

### `trace.query`

用于统一查询 driver/load 类事实。优先使用明确的 `trace.driver` 或 `trace.load`；只有上层代码已经抽象出 mode 时使用 query。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.query",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "signal": "top.u.ready",
    "mode": "driver"
  }
}
```

### `trace.expand`

从 root signal 展开依赖。compact 默认只返回 graph，不返回内部 trace 和 expanded queries。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.expand",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "root_signal": "top.u.ready",
    "direction": "driver"
  },
  "limits": {
    "max_depth": 2,
    "max_nodes": 50,
    "max_edges": 100
  }
}
```

诊断展开过程：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.expand",
  "target": {
    "session_id": "design_case"
  },
  "args": {
    "root_signal": "top.u.ready",
    "direction": "driver",
    "include_trace": true,
    "include_expanded_queries": true
  },
  "output": {
    "verbosity": "compact"
  }
}
```

### `trace.graph`

用于直接拿图结构。compact 默认 `data.graph.nodes/edges` 足够 agent 决策。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.graph",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "signal": "top.u.ready",
    "direction": "driver"
  },
  "limits": {
    "max_depth": 3,
    "max_results": 80
  }
}
```

### `trace.explain`

把 graph edge 转成解释句子和证据。用于用户可读结论或下一步定位。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.explain",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "signal": "top.u.ready",
    "direction": "driver"
  },
  "limits": {
    "max_depth": 2,
    "max_results": 40
  }
}
```

### `trace.path`

查两个信号之间是否存在依赖路径。compact 默认只返回 `found/paths`。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.path",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "from_signal": "top.u.full",
    "to_signal": "top.u.ready",
    "direction": "driver"
  },
  "limits": {
    "max_depth": 5,
    "max_paths": 10
  }
}
```

需要完整 graph：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.path",
  "target": {
    "session_id": "design_case"
  },
  "args": {
    "from_signal": "top.u.full",
    "to_signal": "top.u.ready",
    "include_graph": true
  }
}
```

### `source.context`

定位源码上下文。compact 默认只返回 file/line/symbol/context_kind；源码文本需要 `include_source:true`。

```json
{
  "api_version": "xdebug.v1",
  "action": "source.context",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "file": "rtl/foo.sv",
    "line": 123,
    "symbol": "ready",
    "context_lines": 3
  }
}
```

需要源码片段：

```json
{
  "api_version": "xdebug.v1",
  "action": "source.context",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "file": "rtl/foo.sv",
    "line": 123,
    "context_lines": 10,
    "include_source": true
  }
}
```

### `expr.normalize`

把表达式规整为便于读取的信号/操作符摘要。compact 不应默认返回 AST。

```json
{
  "api_version": "xdebug.v1",
  "action": "expr.normalize",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "expr": "valid && !full"
  }
}
```

需要 AST：

```json
{
  "api_version": "xdebug.v1",
  "action": "expr.normalize",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "expr": "valid && !full",
    "include_ast": true
  }
}
```

### `fsm.explain`

解释 FSM state、状态集合和关键 transition。compact 默认给结论和 evidence，不输出所有候选和失败 parse 过程。

```json
{
  "api_version": "xdebug.v1",
  "action": "fsm.explain",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "state_signal": "top.u.state_q"
  }
}
```

### `counter.explain`

解释 counter 更新、条件、步进和 evidence。

```json
{
  "api_version": "xdebug.v1",
  "action": "counter.explain",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "signal": "top.u.count_q"
  }
}
```

### `sequential.update`

查询寄存器或 sequential signal 的更新规则。

```json
{
  "api_version": "xdebug.v1",
  "action": "sequential.update",
  "target": {
    "daidir": "simv.daidir"
  },
  "args": {
    "signal": "top.u.ready_q"
  }
}
```

## Waveform actions

波形侧 action 需要 `target.fsdb` 或包含 fsdb 的 `session_id`。如果信号不存在，先用 `scope.list` 找真实 FSDB path。

### `scope.list`

列出 scope 下信号。compact 默认 preview + counts；递归全量要显式限制。

```json
{
  "api_version": "xdebug.v1",
  "action": "scope.list",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "path": "top.u_dut",
    "recursive": false
  },
  "limits": {
    "max_rows": 200
  }
}
```

递归查找：

```json
{
  "api_version": "xdebug.v1",
  "action": "scope.list",
  "target": {
    "session_id": "wave_case"
  },
  "args": {
    "path": "top.u_dut",
    "recursive": true,
    "include_all_signals": true
  },
  "limits": {
    "max_rows": 1000
  }
}
```

### `value.at`

查询单个信号单个时间点。compact 默认 `data.value` 是字符串，`data.known` 表示是否非 X/Z。

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "signal": "top.u.valid",
    "time": "100ns",
    "format": "hex"
  }
}
```

需要 raw value object：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {
    "session_id": "wave_case"
  },
  "args": {
    "signal": "top.u.valid",
    "at": "@deadlock-20ns",
    "format": "bin",
    "include_raw": true
  }
}
```

### `value.batch_at`

同一时间查多个信号。优先用它替代多次 `value.at`。

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "time": "100ns",
    "signals": ["top.u.valid", "top.u.ready", "top.u.data"],
    "format": "hex"
  }
}
```

### `list.value_at`

读取已保存 signal list 的同一时间值。适用于反复检查一组接口信号。

```json
{
  "api_version": "xdebug.v1",
  "action": "list.value_at",
  "target": {
    "session_id": "wave_case"
  },
  "args": {
    "name": "if0",
    "time": "@deadlock",
    "format": "hex"
  }
}
```

### `event.find`

在窗口内查满足表达式的事件。适合先找第一个异常点。

```json
{
  "api_version": "xdebug.v1",
  "action": "event.find",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "name": "if0",
    "expr": "valid && !ready",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    }
  },
  "limits": {
    "max_events": 20
  }
}
```

### `event.export`

导出或聚合事件。compact 默认返回 count、first、last、examples，不返回完整 rows。

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "name": "if0",
    "expr": "valid && !ready",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    }
  },
  "limits": {
    "max_events": 1000
  }
}
```

需要完整 rows：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {
    "session_id": "wave_case"
  },
  "args": {
    "name": "if0",
    "expr": "valid && ready",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "include_rows": true
  },
  "limits": {
    "max_rows": 1000
  }
}
```

### `verify.conditions`

在某一时间验证一组简单条件。compact pass 场景可能极简，fail/unknown 才返回失败明细。

```json
{
  "api_version": "xdebug.v1",
  "action": "verify.conditions",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "time": "100ns",
    "conditions": [
      {"signal": "top.u.valid", "op": "==", "value": "1"},
      {"signal": "top.u.ready", "op": "==", "value": "0"}
    ]
  }
}
```

### `expr.eval_at`

在一个时间点评估表达式。适合组合多个波形信号判断一个条件。

```json
{
  "api_version": "xdebug.v1",
  "action": "expr.eval_at",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "time": "100ns",
    "expr": "valid && !ready",
    "signals": {
      "valid": "top.u.valid",
      "ready": "top.u.ready"
    }
  }
}
```

### `window.verify`

在一个时间窗口或时钟采样窗口里验证条件。适合证明协议行为在一段时间内是否稳定。

```json
{
  "api_version": "xdebug.v1",
  "action": "window.verify",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "clock": "top.clk",
    "sampling": "posedge",
    "time_range": {
      "begin": "0ns",
      "end": "1us"
    },
    "conditions": [
      {
        "expr": "valid -> ready",
        "signals": {
          "valid": "top.u.valid",
          "ready": "top.u.ready"
        }
      }
    ]
  }
}
```

### `signal.changes`

查看变化点。compact 默认只返回 top changes，不返回全量变化列表。

```json
{
  "api_version": "xdebug.v1",
  "action": "signal.changes",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "signal": "top.u.ready",
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    },
    "format": "hex"
  },
  "limits": {
    "max_rows": 20
  }
}
```

需要全量变化：

```json
{
  "api_version": "xdebug.v1",
  "action": "signal.changes",
  "target": {
    "session_id": "wave_case"
  },
  "args": {
    "signal": "top.u.ready",
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    },
    "include_all_changes": true
  },
  "limits": {
    "max_rows": 1000
  }
}
```

### `signal.statistics`

统计 signal 的变化、X/Z、稳定性等摘要。

```json
{
  "api_version": "xdebug.v1",
  "action": "signal.statistics",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "signal": "top.u.ready",
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    }
  }
}
```

### `signal.trend`

查看采样趋势或值变化趋势。

```json
{
  "api_version": "xdebug.v1",
  "action": "signal.trend",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "signal": "top.u.count",
    "clock": "top.clk",
    "sampling": "posedge",
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    }
  }
}
```

### `signal.stability`

判断 signal 是否长时间稳定或卡住。

```json
{
  "api_version": "xdebug.v1",
  "action": "signal.stability",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "signal": "top.u.ready",
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    }
  }
}
```

### `handshake.inspect`

检查 valid/ready handshake。compact 默认只返回 stall/failure windows 和摘要，不返回周期级 timeline。

```json
{
  "api_version": "xdebug.v1",
  "action": "handshake.inspect",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "clock": "top.clk",
    "valid": "top.u.valid",
    "ready": "top.u.ready",
    "data": ["top.u.data"],
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    }
  }
}
```

### `detect_anomaly`

扫描异常。compact 默认只返回 anomalies，不返回正常扫描数据。

```json
{
  "api_version": "xdebug.v1",
  "action": "detect_anomaly",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "signals": ["top.u.valid", "top.u.ready", "top.u.data"],
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    },
    "checks": ["glitch", "stuck", "unknown_xz"]
  }
}
```

## Protocol actions

协议 action 依赖已加载配置或请求内配置。compact 默认优先返回 findings 和 top abnormal，不要默认要求所有正常 transaction/access/beat。

### `apb.query`

APB 默认关注 error/slow access。

```json
{
  "api_version": "xdebug.v1",
  "action": "apb.query",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "name": "apb0",
    "direction": "read",
    "time_range": {
      "begin": "0ns",
      "end": "10us"
    }
  },
  "limits": {
    "max_rows": 20
  }
}
```

需要全部 accesses：

```json
{
  "api_version": "xdebug.v1",
  "action": "apb.query",
  "target": {
    "session_id": "wave_case"
  },
  "args": {
    "name": "apb0",
    "include_accesses": true
  },
  "limits": {
    "max_rows": 1000
  }
}
```

### `axi.query`

AXI 默认关注 response error、timeout、latency、outstanding 异常。

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.query",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "name": "axi0",
    "direction": "read",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    }
  },
  "limits": {
    "max_rows": 20
  }
}
```

需要 transaction/beat 明细：

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.query",
  "target": {
    "session_id": "wave_case"
  },
  "args": {
    "name": "axi0",
    "direction": "write",
    "include_transactions": true,
    "include_beats": true
  },
  "limits": {
    "max_rows": 1000
  }
}
```

### `axi.analysis`

用于 latency/outstanding/response error 等聚合分析。

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.analysis",
  "target": {
    "fsdb": "waves.fsdb",
    "auto_open": true
  },
  "args": {
    "name": "axi0",
    "analysis": "latency",
    "direction": "read",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "max_items": 20
  }
}
```

## Combined actions

Combined action 需要同时有 `daidir` 和 `fsdb`。目标是把“某时刻波形上看到的值/异常”连接到“此时设计里真正生效的 driver/control/source evidence”。

### `trace.active_driver`

推荐 flow：

1. 用 `event.find/export`、`value.at`、`signal.changes` 或 `verify.conditions` 找到异常 `requested_time`。
2. 对该时间点用 `value.batch_at` 取相关 valid/ready/state/data。
3. 调 `trace.active_driver` 查询当前生效 driver。
4. 如果结果是 `resolved`，保留 driver kind、file/line、active_time、control evidence。
5. 如果是 `control_only`，说明没有直接 data driver 但控制条件可解释现象，继续查 control signal 值。
6. 如果是 `unresolved`，回到 `trace.driver`、`trace.graph` 或源码 `rg` 缩小信号路径。

模板：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {
    "signal": "top.u.ready",
    "requested_time": "120ns",
    "include_control": true,
    "include_parity": true
  }
}
```

使用 session：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "signal": "top.u.ready",
    "requested_time": "@deadlock",
    "include_control": true
  }
}
```

后续补证：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "time": "@deadlock",
    "signals": ["top.u.ready", "top.u.valid", "top.u.full", "top.u.state_q"],
    "format": "hex"
  }
}
```

## 常见 debug recipes

### Ready 卡低

1. `value.batch_at` 取 `valid/ready/full/state`。
2. `signal.changes` 看 `ready` 第一次卡住时间。
3. `trace.active_driver` 在卡住时间查 `ready` 生效 driver。
4. 若 driver 指向 `full` 或状态条件，`value.at` 查控制信号值。
5. 用 `source.context include_source:true` 获取最终源码证据。

### Valid 有脉冲但没被接受

1. `event.export` 查 `valid && !ready` 的窗口。
2. `handshake.inspect` 找 long stall。
3. `value.batch_at` 取 payload、ready、backpressure、state。
4. `trace.driver` 或 `trace.active_driver` 查 ready/backpressure 的设计原因。

### AXI latency 异常

1. `axi.analysis` 用 compact 查 latency/outstanding findings。
2. 对 top abnormal 的 begin/end 设 cursor 或直接用 TimeSpec。
3. `value.batch_at` 查 channel valid/ready/id/resp。
4. 必要时 `include_transactions:true` 获取异常 transaction 明细，不要导出所有正常 transaction。

### X/Z 传播

1. `detect_anomaly` 查 `unknown_xz`。
2. `signal.changes` 看第一个 X/Z 出现时间。
3. `trace.active_driver` 在该时间查生效 driver。
4. `trace.graph` 向上游扩展，寻找 X/Z 源。

### Counter/FSM 异常

1. `value.at` 或 `signal.trend` 确认状态/计数异常。
2. `fsm.explain` 或 `counter.explain` 获取规则。
3. `trace.driver` 查更新条件。
4. `source.context` 获取 file/line 证据。

## 最终回答建议

给用户汇报时保留高信号事实：

- 问题信号和时间点。
- 波形值和 `known` 状态。
- driver/load 或 protocol finding。
- 关键条件信号。
- `file:line` evidence。
- 是否 `truncated`，是否需要进一步 include 明细。

不要把完整 rows、samples、transactions、trace、expanded_queries 粘给用户，除非用户明确要求。
