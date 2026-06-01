# xdebug

xdebug 是 xtrace 与 xwave 合并后的统一调试工具。公开入口只支持 JSON 请求，面向 AI agent、自动化脚本和可复现调试流程；旧的 xtrace/xwave 人类 CLI 不再作为主路径维护。

仓库内 skill source-of-truth 位于 [skill/SKILL.md](skill/SKILL.md)。更细的字段字典和 API 速查位于 [skill/references](skill/references)。

## Quick Start

`-h` 和 `-help` 是 xdebug 唯一的非 JSON 命令，用于查看详尽的人类可读帮助：

```bash
tools/xdebug-env -h
tools/xdebug-env -help
```

机器可读帮助仍通过 JSON action 获取：

```bash
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | tools/xdebug-env -
printf '%s\n' '{"api_version":"xdebug.v1","action":"schema"}' | tools/xdebug-env -
```

推荐通过仓库根目录的 wrapper 调用，它会设置 Verdi/NPI 运行所需环境：

```bash
tools/xdebug-env -
```

从 stdin 传入 JSON：

```bash
printf '%s\n' '{"api_version":"xdebug.v1","action":"value.at","target":{"fsdb":"waves.fsdb","auto_open":true},"args":{"signal":"top.clk","time":"10ns"}}' \
  | tools/xdebug-env -
```

也可以使用请求文件：

```bash
tools/xdebug-env request.json
```

### Shell 命令入口

为了在任意目录调用，建议把 `xdebug` 安装成 shell function。下面示例里的 `<xverif-root>` 表示本仓库根目录，请按本机实际路径替换；文档和 skill 中不固定记录个人机器路径。

Bash：加入 `~/.bashrc`。

```bash
export XVERIF_HOME=<xverif-root>
export XDEBUG_ENTRY="$XVERIF_HOME/tools/xdebug-env"
xdebug() { "$XDEBUG_ENTRY" "$@"; }
```

Zsh：加入 `~/.zshrc`。

```zsh
export XVERIF_HOME=<xverif-root>
export XDEBUG_ENTRY="$XVERIF_HOME/tools/xdebug-env"
xdebug() { "$XDEBUG_ENTRY" "$@"; }
```

Tcsh：加入 `~/.tcshrc`。

```tcsh
setenv XVERIF_HOME <xverif-root>
setenv XDEBUG_ENTRY "$XVERIF_HOME/tools/xdebug-env"
alias xdebug '"$XDEBUG_ENTRY" \!*'
```

配置后可以直接使用：

```bash
xdebug -h
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | xdebug -
xdebug request.json
```

重复调试建议先打开 session，再用 `target.session_id` 访问：

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

## Core Concepts

### 资源与 fallback

xdebug 当前只支持两类输入资源：

- `daidir`：Verdi/VCS 设计数据库，例如 `simv.daidir`。
- `fsdb`：FSDB 波形数据库，例如 `waves.fsdb`。

`target` 决定路由：

| target | 行为 |
| --- | --- |
| 仅 `daidir` | 使用设计侧能力，覆盖原 xtrace 的 driver/load/graph/path/source 等事实查询 |
| 仅 `fsdb` | 使用波形侧能力，覆盖原 xwave 的 value/event/APB/AXI/verify 等事实查询 |
| 同时有 `daidir` 与 `fsdb` | 启用 combined/debug join 能力，把波形现象连接到设计因果 |

### JSON envelope

所有请求统一使用这个 envelope：

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

### 输出档位

`output.verbosity` 默认是 `compact`：

| verbosity | 用途 |
| --- | --- |
| `compact` | 默认，只返回 AI 下一步决策需要的摘要、证据、少量 examples、关键 graph/path |
| `full` | 兼容旧脚本或人工查看完整 payload |
| `debug` | 诊断 session、daemon、内部过程和截断原因 |

compact 默认不返回大字段，例如 `expanded_queries`、`raw_edges`、`all_samples`、`all_events`、`all_changes`、`normal_transactions`、`timeline`、`source_text`、`module_body`。需要时用精确 `include_*` 开关，不要一开始请求 `debug`。

### include 开关与限制

设计侧常用开关：

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

波形侧常用开关：

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
    "max_samples": 1000000
  }
}
```

### TimeSpec

波形相关动作的时间字段接受 TimeSpec 字符串。常见形式：

```text
100ns
10us
@deadlock
@deadlock-20ns
@deadlock+5ns
@deadlock-10cycle(top.clk)
@deadlock+5posedge(top.clk)
```

绝对时间支持 `us`、`ns`、`ps`、`fs`。使用 cursor 时，优先让 xdebug 解析 `@name` 和 cycle offset，不要在 agent 里自己重算波形时间。

## Main Workflows

### 设计因果：driver / graph / path

先用外部 `rg` 或源码索引找候选信号名，再把精确 RTL path 交给 xdebug 查询。

查询 driver：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.driver",
  "target": {"daidir": "simv.daidir"},
  "args": {"signal": "top.u.ready"}
}
```

查询依赖图：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.graph",
  "target": {"daidir": "simv.daidir"},
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

查询路径：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.path",
  "target": {"daidir": "simv.daidir"},
  "args": {
    "from_signal": "top.u.full",
    "to_signal": "top.u.ready"
  },
  "limits": {
    "max_depth": 5,
    "max_paths": 10
  }
}
```

### 波形取证：value / batch / verify

查询单点值：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
  "args": {
    "signal": "top.u.valid",
    "time": "100ns",
    "format": "hex"
  }
}
```

批量查询同一时间的多个信号：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
  "args": {
    "time": "100ns",
    "signals": ["top.u.valid", "top.u.ready", "top.u.data"],
    "format": "hex"
  }
}
```

验证条件：

```json
{
  "api_version": "xdebug.v1",
  "action": "verify.conditions",
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
  "args": {
    "time": "100ns",
    "conditions": [
      {"signal": "top.u.valid", "op": "==", "value": "1"},
      {"signal": "top.u.ready", "op": "==", "value": "0"}
    ]
  }
}
```

### 协议与事件：event / APB / AXI

导出事件默认只返回聚合信息和少量 examples。完整 rows 必须显式请求：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {"fsdb": "waves.fsdb", "auto_open": true},
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

需要 rows：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {"session_id": "case_a"},
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

APB/AXI 查询应先加载对应配置，再执行 `apb.query`、`axi.query` 或分析动作。compact 默认优先返回 error/slow/high-latency/outstanding finding，而不是所有正常 transaction/beat。

### 联合定位：trace.active_driver

当同时有 `daidir` 和 `fsdb` 时，用 `trace.active_driver` 把“某时刻波形值”连接到“当前生效的设计驱动证据”：

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
    "include_control": true
  }
}
```

推荐 debug flow：

1. 用 `value.at` 或 `event.export` 找到异常时间。
2. 用 `value.batch_at` 取相关握手、状态、数据寄存器。
3. 用 `trace.driver` 或 `trace.graph` 查设计依赖。
4. 如果两类资源都有，用 `trace.active_driver` 给出当前时间点的生效驱动。
5. 只有当 compact 证据不足时，再打开 `include_source`、`include_trace`、`include_rows` 等细节。

## 错误、截断与证据

常见错误码：

- `MISSING_FIELD`
- `UNKNOWN_ACTION`
- `INVALID_TARGET`
- `SESSION_NOT_FOUND`
- `SIGNAL_NOT_FOUND`
- `TIME_SPEC_INVALID`
- `WAVE_QUERY_FAILED`
- `INTERNAL_ENGINE_FAILED`
- `INTERNAL_ERROR`

所有脚本必须先检查 `ok`。失败时读取 `error.code` 和 `error.message`，不要解析 stderr 或人类文本。

`meta.truncated=true` 表示结果被主动截断。优先缩小查询范围或提高 `limits`；只有确实需要证明明细时才打开对应 `include_*`。

compact payload 优先返回 evidence，而不是大段源码：

```json
{
  "evidence": {
    "file": "rtl/foo.sv",
    "line": 123
  }
}
```

## 日志与排障

xdebug 默认静默记录结构化日志。日志只写文件，不打印到 stdout/stderr，不改变 JSON API 响应；日志写入失败也不会影响 action 执行。

主要位置：

- public action：`~/.xdebug/sessions/<session_id>/logs/actions.ndjson`
- 无 session 或解析失败：`~/.xdebug/sessions/adhoc/logs/actions.ndjson`
- 设计后端生命周期：`~/.xdebug/design/sessions/<hashed-session>/logs/lifecycle.ndjson`
- 波形后端生命周期：`~/.xdebug/waveform/sessions/<hashed-session>/logs/lifecycle.ndjson`
- 后端连接与请求：`~/.xdebug/{design,waveform}/sessions/<hashed-session>/logs/transport.ndjson`
- 旧有 daemon debug 文本：`~/.xdebug/{design,waveform}/sessions/<hashed-session>/debug.log`

每行都是一个 JSON event，常见字段包括 `ts`、`event_id`、`layer`、`component`、`session_id`、`action`、`phase`、`elapsed_ms`、`ok`、`context`。成功 action 默认只记录摘要、路由、耗时和 `summary/meta`；失败 action 会额外记录裁剪后的 request/response。

定位工具问题时推荐顺序：

1. 先看 public `actions.ndjson`，确认 action、session、路由和最终 error。
2. 如果是 `session.open/session.ensure`、`SESSION_UNHEALTHY` 或 `INTERNAL_ENGINE_FAILED`，再看后端 `lifecycle.ndjson`。
3. 如果怀疑 socket/TCP/ping/daemon 连接问题，看 `transport.ndjson`。
4. 如果卡在 Verdi/NPI 初始化或 daemon bind/listen，结合 `lifecycle.ndjson` 和 `debug.log`。

## 参考文档

- [docs/JSON_API.md](docs/JSON_API.md)：JSON envelope、target、输出策略。
- [docs/PAYLOAD_COMPACT.md](docs/PAYLOAD_COMPACT.md)：业务 payload 压缩契约。
- [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)：面向 agent 的最短调试指南。
- [skill/SKILL.md](skill/SKILL.md)：Codex skill source-of-truth。
- [skill/references/json-api-reference.md](skill/references/json-api-reference.md)：skill 内 API 速查。
- [skill/references/ai-response-dictionary.md](skill/references/ai-response-dictionary.md)：skill 内响应字段字典。
