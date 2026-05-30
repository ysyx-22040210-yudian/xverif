# xdebug JSON API

xdebug 是原 xtrace 与 xwave 的统一 JSON-only 入口。agent 和自动化脚本应通过 JSON 请求访问工具能力，不再依赖传统人类 CLI 动作入口。

## 请求 Envelope

```json
{
  "api_version": "xdebug.v1",
  "request_id": "optional-id",
  "action": "trace.driver",
  "target": {
    "daidir": "path/to/simv.daidir",
    "fsdb": "path/to/waves.fsdb"
  },
  "args": {},
  "limits": {},
  "output": {
    "verbosity": "compact",
    "pretty": false
  }
}
```

`target` 决定路由：

| target | 行为 |
| --- | --- |
| 仅 `daidir` | 使用设计数据库能力，即原 xtrace 能力 |
| 仅 `fsdb` | 使用波形数据库能力，即原 xwave 能力 |
| 同时有 `daidir` 与 `fsdb` | 使用 combined/debug join 能力 |

## 输出档位

| verbosity | 行为 |
| --- | --- |
| `compact` | 默认，只保留 AI 决策所需事实 |
| `full` | 保留可用的详细旧 payload |
| `debug` | 保留 full 内容，并允许过程型调试字段 |

正常调试应先用 compact。只有 compact 结果缺少下一步所需证据时，再打开具体 `include_*`，不要一开始就请求 `debug`。

## Include 开关

设计侧开关：

```json
{
  "include_source": true,
  "include_ast": true,
  "include_candidates": true,
  "include_trace": true,
  "include_expanded_queries": true,
  "include_raw_edges": true,
  "include_graph": true,
  "include_debug": true
}
```

波形侧开关：

```json
{
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
    "max_events": 1000
  }
}
```

## 示例

### 查询 driver

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.driver",
  "target": {"daidir": "simv.daidir"},
  "args": {"signal": "top.u.ready"}
}
```

### 查询 graph 并取回内部过程

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.graph",
  "target": {"daidir": "simv.daidir"},
  "args": {
    "signal": "top.u.ready",
    "include_trace": true,
    "include_expanded_queries": true
  },
  "output": {"verbosity": "compact"}
}
```

### 查询波形值

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {"fsdb": "waves.fsdb"},
  "args": {
    "signal": "top.u.valid",
    "time": "100ns",
    "format": "hex"
  }
}
```

### 导出 event rows

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {"fsdb": "waves.fsdb"},
  "args": {
    "name": "valid_rise",
    "expr": "valid",
    "begin": "0ns",
    "end": "max",
    "include_rows": true
  },
  "limits": {"max_rows": 1000}
}
```

### combined active trace

```json
{
  "api_version": "xdebug.v1",
  "action": "active.trace",
  "target": {
    "daidir": "simv.daidir",
    "fsdb": "waves.fsdb"
  },
  "args": {
    "signal": "top.u.ready",
    "time": "120ns"
  }
}
```

## 错误与证据字段

常见错误码：

- `MISSING_FIELD`
- `UNKNOWN_ACTION`
- `INVALID_TARGET`
- `SESSION_NOT_FOUND`
- `SIGNAL_NOT_FOUND`
- `TIME_SPEC_INVALID`
- `WAVE_QUERY_FAILED`
- `INTERNAL_ERROR`

compact payload 优先返回 evidence，而不是大段源码文本：

```json
{
  "evidence": {
    "file": "rtl/foo.sv",
    "line": 123
  }
}
```

`meta.truncated=true` 表示结果被主动截断。需要更多明细时，使用精确 include 开关并设置限制。
