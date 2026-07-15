# kverif MCP

`kverif_mcp` 是 `tools/kverif-mcp` 的 Python 实现，基于 FastMCP SDK。它是 kverif 工具体系统一 MCP 入口：

- **kdebug**：stateful backend，通过 `tools/kdebug --stdio-loop` 提供设计/波形查询能力，支持 direct/LSF 模式。
- **kcov**：stateful backend，通过 `tools/kcov --stdio-loop` 提供 VCS/Verdi coverage database 查询能力，支持 direct/LSF 模式。
- **kbit / kentry / kloc / kberif / ksva**：stateless CLI adapter，每次调用短生命周期 subprocess。

kdebug/kcov direct 和 LSF 共用 stdio-loop session manager，只在 `Launcher` 层分离。每 session 独立进程，同 session 串行（request_lock），多 session 可并行。

MCP 层保持轻量：它只负责启动/终止 `tools/kdebug --stdio-loop` 或
`tools/kcov --stdio-loop` 进程、维护 alias/default 映射、转发 JSON request、
处理 direct/LSF transport cleanup。设计/波形 session 状态由 kdebug 管理；
coverage database session、scope/cache/query 状态由 kcov 管理。直接 Verdi/NPI
访问不在 MCP 层实现，统一在 `kdebug/tcl_engine/kdebug_npi.tcl` 和
`kcov/tcl_engine/kcov_npi.tcl` 中执行。

## 环境要求

| 组件 | 要求 |
|---|---|
| GCC | **5.0+** |
| Python | **3.11+**（`pip install "mcp[cli]"`） |
| Verdi | 建议使用站点已验证版本；当前直接 NPI 后端按 Verdi **O-2018.09-SP2** 兼容路径维护 |
| NPI | 直接 NPI 调用只允许在 Tcl backend 中实现 |

> 如果使用其他 Verdi 版本遇到 NPI 兼容性问题，不要新增非 Tcl 的直接 NPI 访问路径。应在 Tcl backend 或请求转换层修复，并在目标 VM/EDA 环境中做功能测试。

## 入口

```bash
tools/kverif-mcp
tools/kverif-lsf-doctor
tools/kverif-loop-server
tools/kverif-loop-client
```

`tools/kverif-loop-server` / `tools/kverif-loop-client` 是不依赖 MCP SDK 的
UDS wrapper，只覆盖 stateful `kdebug`/`kcov` session open/list/query/close。
日常手动调用可使用 `kverif-loop-client ping/debug-open/debug-query/cov-query`
这类参数式命令；JSONL 仍作为脚本和批处理协议保留。
它复用同一套 stdio-loop session manager 和 direct/LSF launcher，适合不能安装
MCP SDK 或不想走 MCP 协议、但仍需要 LSF 维护 `--stdio-loop` 后端的场景。

## MCP 配置

### Claude Code

在项目根目录创建 `.mcp.json`（与 `.git/` 同级，**不是** `.claude/` 目录下）。

**direct 模式：**

```json
{
  "mcpServers": {
    "kverif": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "kverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<kverif>/kverif_mcp/src:<kverif>",
        "KVERIF_HOME": "<kverif>",
        "KVERIF_MCP_BACKEND": "direct",
        "VERDI_HOME": "<verdi-install>",
        "LD_LIBRARY_PATH": "<verdi-install>/share/NPI/lib/LINUX64"
      }
    }
  }
}
```

**LSF 模式：**

```json
{
  "mcpServers": {
    "kverif": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "kverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<kverif>/kverif_mcp/src:<kverif>",
        "KVERIF_HOME": "<kverif>",
        "KVERIF_MCP_BACKEND": "lsf",
        "KVERIF_LSF_SESSION_QUEUE": "interactive",
        "VERDI_HOME": "<verdi-install>",
        "LD_LIBRARY_PATH": "<verdi-install>/share/NPI/lib/LINUX64",
        "LSF_ENVDIR": "<lsf-install>/conf",
        "LSF_BINDIR": "<lsf-install>/bin",
        "LSF_LIBDIR": "<lsf-install>/lib",
        "LSF_SERVERDIR": "<lsf-install>/etc",
        "PATH": "<你的完整 PATH>",
        "SNPSLMD_LICENSE_FILE": "<synopsys-license>",
        "LM_LICENSE_FILE": "<cadence-license>",
        "MGLS_LICENSE_FILE": "<mentor-license>",
        "CDS_LIC_FILE": "<cadence-license>",
        "CDS_LIC_ONLY": "1",
        "DW_WAIT_LICENSE": "1"
      }
    }
  }
}
```

> **关键**：MCP server 子进程**不会自动继承**父进程（shell / IDE）的环境变量。`bsub` 提交的 LSF job 从 MCP server 子进程继承环境，因此**所有**必须在计算节点上生效的变量都要显式列在 `.mcp.json` 的 `env` 中——包括 `VERDI_HOME`、`LD_LIBRARY_PATH`、LSF 路径、EDA license 等。`PATH` 尤其重要，必须确保 `bsub`、`bkill` 等命令在其中。

替换说明：
- `<conda-env>`：安装了 `mcp[cli]` 的 Python 3.11 环境路径
- `<kverif>`：kverif 仓库根目录
- `<verdi-install>`：Synopsys Verdi 安装根目录
- `<lsf-install>`：LSF 安装根目录

`KVERIF_MCP_BACKEND` 可选值：
- `direct`：本机启动 `tools/kdebug --stdio-loop` 或 `tools/kcov --stdio-loop`
- `lsf`：通过 `bsub -I tools/<backend> --stdio-loop` 提交到 LSF

### 通用参数

所有 MCP tool 自动支持以下可选参数，无需每个 tool 单独声明：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `kverif_output_path` | `str \| None` | `None` | 指定文件路径时，tool 响应会额外写入该文件 |
| `kverif_output_append` | `bool` | `False` | True 为追加写入，False（默认）为覆盖写入 |

示例：
```python
# 将 cov.holes 响应写入 /tmp/holes.json
kverif_cov_query(action="cov.holes", args={...},
                 kverif_output_path="/tmp/holes.json")

# 追加模式
kverif_debug_query(action="value.at", args={...},
                   kverif_output_path="/tmp/wave.log",
                   kverif_output_append=True)
```

写文件失败不会影响 tool 正常返回。

### 批量执行：`kverif_batch`

`kverif_batch` 允许 AI 将多个 tool 请求写入 NDJSON 文件，一次提交批量串行执行，
结果写入另一个 NDJSON 文件。适合需要按序执行 session.open → query → session.close
的场景。

**注意嵌套 args**：`kverif_debug_query` / `kverif_cov_query` 自身有 `args` 参数，
在 batch 行中需要再嵌套一层：
```jsonl
{"tool":"kverif_debug_query","args":{"action":"value.at","args":{"signal":"top.clk","time":"10ns"}}}
```

**1. 生成批量请求文件（bash inline）：**

```bash
cat > /tmp/batch_requests.ndjson << 'EOF'
{"tool": "kverif_cov_session_open", "args": {"name": "uart0", "vdb": "/path/to/merged.vdb"}}
{"tool": "kverif_cov_query", "args": {"session": "uart0", "action": "cov.holes", "args": {"metrics": ["line"], "limits": {"max_items": 5}}, "output_format": "json"}}
{"tool": "kverif_cov_query", "args": {"session": "uart0", "action": "cov.holes", "args": {"metrics": ["toggle"], "limits": {"max_items": 5}}, "output_format": "json"}}
{"tool": "kverif_cov_session_close", "args": {"name": "uart0"}}
EOF
```

或 Python inline：

```python
import json
requests = [
    {"tool": "kverif_cov_session_open", "args": {"name": "uart0", "vdb": "/path/to/merged.vdb"}},
    {"tool": "kverif_cov_query", "args": {"session": "uart0", "action": "cov.holes",
        "args": {"metrics": ["line"], "limits": {"max_items": 5}}, "output_format": "json"}},
    {"tool": "kverif_cov_session_close", "args": {"name": "uart0"}},
]
with open("/tmp/batch_requests.ndjson", "w") as f:
    for req in requests:
        f.write(json.dumps(req) + "\n")
```

**2. 提交执行：**

```
kverif_batch(batch_file="/tmp/batch_requests.ndjson", output_file="/tmp/batch_results.ndjson")
```

**3. 查看结果：**

```python
import json
with open("/tmp/batch_results.ndjson") as f:
    for line in f:
        r = json.loads(line)
        status = "OK" if r["ok"] else f"FAIL: {r['error']}"
        print(f"[{status}] {r['tool']} ({r['elapsed_ms']}ms)")
```

输出格式：每行 `{"tool": "...", "ok": true/false, "elapsed_ms": 123, "error": null}`。
格式错误行 `tool` 为 `null`，`error` 包含错误原因。

### 通用 MCP client

```json
{
  "mcpServers": {
    "kverif": {
      "command": "<conda-env>/bin/python",
      "args": ["-m", "kverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<kverif>/kverif_mcp/src:<kverif>",
        "KVERIF_HOME": "<kverif>"
      }
    }
  }
}
```

Claude Code 启动时自动加载项目根目录下的 `.mcp.json`，无需额外配置。

## 运行链路

```text
AI MCP client
  -> kverif-mcp FastMCP server
  -> KverifDebugAdapter (kdebug)
       -> McpSessionManager
       -> DirectLauncher:  tools/kdebug --stdio-loop  (direct)
       -> LsfLauncher:     bsub -I tools/kdebug --stdio-loop  (LSF)
  -> KverifCoverageAdapter (kcov)
       -> McpSessionManager
       -> DirectLauncher:  tools/kcov --stdio-loop  (direct)
       -> LsfLauncher:     bsub -I tools/kcov --stdio-loop  (LSF)
  -> StatelessCliRunner (kbit/kentry/kloc/kberif/ksva)
       -> tools/<tool> --json ...
```

非 MCP wrapper 链路：

```text
kverif-loop-client parameter CLI or JSONL client
  -> kverif-loop-server Unix domain socket
  -> LoopWrapperService
       -> McpSessionManager (kdebug)
       -> DirectLauncher: tools/kdebug --stdio-loop
       -> LsfLauncher:    bsub -I tools/kdebug --stdio-loop
       -> McpSessionManager (kcov)
       -> DirectLauncher: tools/kcov --stdio-loop
       -> LsfLauncher:    bsub -I tools/kcov --stdio-loop
```

示例：

```bash
KVERIF_LOOP_BACKEND=lsf \
KVERIF_LOOP_SOCKET=/tmp/kverif-loop.sock \
tools/kverif-loop-server

tools/kverif-loop-client --socket /tmp/kverif-loop.sock --json \
  '{"id":"1","method":"debug.session.open","params":{"name":"s0","fsdb":"waves.fsdb"}}'

tools/kverif-loop-client --socket /tmp/kverif-loop.sock --json \
  '{"id":"2","method":"debug.query","params":{"session":"s0","action":"value.at","args":{"signal":"top.clk"},"output_format":"json"}}'
```

同样的操作也可以不用手写 JSON：

```bash
tools/kverif-loop-client --socket /tmp/kverif-loop.sock ping
tools/kverif-loop-client --socket /tmp/kverif-loop.sock debug-open --name s0 --fsdb waves.fsdb
tools/kverif-loop-client --socket /tmp/kverif-loop.sock debug-query \
  --session s0 \
  --action value.at \
  --arg signal=top.clk \
  --arg time=10ns \
  --output-format json
tools/kverif-loop-client --socket /tmp/kverif-loop.sock debug-close --session s0
```

Coverage commands do not time out by default. The parameter CLI and raw JSON-RPC
client both inspect the method: `cov.*` uses an unlimited socket wait, while
`debug.*` and `server.ping` retain the 30-second client default. Zero or a
negative value explicitly disables the client timeout; a positive value enables
one:

```bash
tools/kverif-loop-client --socket /tmp/kverif-loop.sock \
  cov-query --session cov0 --action cov.holes

tools/kverif-loop-client --socket /tmp/kverif-loop.sock --timeout-sec 0 \
  cov-query --session cov0 --action cov.holes

tools/kverif-loop-client --socket /tmp/kverif-loop.sock --timeout-sec 900 \
  cov-query --session cov0 --action cov.holes
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `KVERIF_HOME` | 仓库根目录 |
| `KVERIF_MCP_BACKEND` | `direct`（默认）或 `lsf` |
| `KVERIF_MCP_TIMEOUT_SEC` | one-shot 请求超时（默认 360s） |
| `KVERIF_MCP_STARTUP_TIMEOUT_SEC` | session open 超时（默认 180s） |
| `KVERIF_MCP_REQUEST_TIMEOUT_SEC` | query 请求超时（默认 360s） |
| `KVERIF_MCP_CLOSE_TIMEOUT_SEC` | session close 超时（默认 30s） |
| `KVERIF_MCP_BKILL_TIMEOUT_SEC` | bkill 超时（默认 30s） |
| `KVERIF_MCP_LOG_DIR` | MCP structured log 根目录，默认 `~/.kverif/mcp` |
| `KVERIF_MCP_ENABLE_WRITE=1` | 启用 kberif 写入操作 |
| `KVERIF_MCP_ENABLE_COMMON` | 暴露 common 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_DEBUG` | 暴露 kdebug/session 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_COV` | 暴露 kcov coverage 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_BIT` | 暴露 kbit 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_ENTRY` | 暴露 kentry 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_LOC` | 暴露 kloc 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_CONTEXT` | 暴露 kberif 只读 context 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_SVA` | 暴露 ksva 工具，默认 `1` |
| `KVERIF_MCP_ENABLE_CONTEXT_WRITE` | 暴露 kberif 写入/修复工具，默认 `0` |
| `KVERIF_LSF_BSUB` | 覆盖 `bsub` 命令（默认 `bsub`） |
| `KVERIF_LSF_SESSION_QUEUE` | session job 的 LSF 队列（默认 `interactive`） |
| `KVERIF_LSF_BKILL` | 覆盖 `bkill` 命令 |
| `KVERIF_KCOV_BIN` | 覆盖 kcov 可执行文件路径，默认 `tools/kcov` |
| `KVERIF_KCOV_PYTHON` | 覆盖 kcov 使用的 Python runtime |
| `KVERIF_KCOV_VERDI_HOME` | 覆盖 kcov 使用的 Verdi 安装路径 |
| `KVERIF_KCOV_TCL_TIMEOUT_SEC` | 单次 Verdi Tcl NPI 调用超时；默认 `0`（无限等待），正数启用秒数限制 |
| `KVERIF_KCOV_STARTUP_TIMEOUT_SEC` | kcov session open/ready 超时；默认 `0`（无限等待） |
| `KVERIF_KCOV_REQUEST_TIMEOUT_SEC` | kcov session query/one-shot 超时；默认 `0`（无限等待） |
| `KVERIF_KCOV_LOG_DIR` | 覆盖 kcov 日志目录，默认 `~/.kverif/kcov` |
| `KVERIF_KCOV_LOG=0` | 关闭 kcov 日志 |
| `KVERIF_MCP_FAKE_LSF=1` | 本地测试用 fake LSF runner |
| `KVERIF_LOOP_BACKEND` | 非 MCP UDS wrapper backend，`direct`（默认）或 `lsf` |
| `KVERIF_LOOP_SOCKET` | 非 MCP UDS wrapper socket 路径，默认 `/tmp/kverif-loop-<uid>.sock` |
| `KVERIF_LOOP_LOG_DIR` | 非 MCP UDS wrapper structured log 根目录，默认 `~/.kverif/loop-wrapper` |
| `KVERIF_LOOP_STARTUP_TIMEOUT_SEC` | 非 MCP UDS wrapper session open 超时 |
| `KVERIF_LOOP_REQUEST_TIMEOUT_SEC` | 非 MCP UDS wrapper query 请求超时 |
| `KVERIF_LOOP_CLOSE_TIMEOUT_SEC` | 非 MCP UDS wrapper session close 超时 |
| `KVERIF_LOOP_BKILL_TIMEOUT_SEC` | 非 MCP UDS wrapper bkill 超时 |
| `KVERIF_LOOP_FAKE_LSF=1` | 非 MCP UDS wrapper 本地测试用 fake LSF runner |
| `VERDI_HOME` | Verdi 安装目录 |
| `LD_LIBRARY_PATH` | 需包含 `<verdi-install>/share/NPI/lib/LINUX64` |

kdebug/kcov stateful session 会写结构化 MCP 日志：

- server：`~/.kverif/mcp/logs/server.ndjson`
- session lifecycle：`~/.kverif/mcp/sessions/<alias>/session.ndjson`
- stdio-loop protocol：`~/.kverif/mcp/sessions/<alias>/stdio.ndjson`
- LSF launcher / job / cleanup：`~/.kverif/mcp/sessions/<alias>/lsf.ndjson`

当 open/query 返回 `SESSION_LOST`、ready timeout、stdout pollution、fake/real LSF
启动失败或 cleanup 失败时，优先读这些日志；事件会包含 alias、backend、launcher、
pid、job_id/job_name、request_id、stderr_tail 和 cleanup 结果。

非 MCP UDS wrapper 会写结构化日志：

- server：`~/.kverif/loop-wrapper/logs/server.ndjson`
- UDS protocol：`~/.kverif/loop-wrapper/logs/uds.ndjson`
- session lifecycle：`~/.kverif/loop-wrapper/sessions/<alias>/session.ndjson`
- stdio-loop protocol：`~/.kverif/loop-wrapper/sessions/<alias>/stdio.ndjson`
- LSF launcher / job / cleanup：`~/.kverif/loop-wrapper/sessions/<alias>/lsf.ndjson`

kdebug session 工具使用明确前缀：

```text
kverif_debug_session_open
kverif_debug_session_list
kverif_debug_session_close
```

kcov session 工具使用 coverage 前缀：

```text
kverif_cov_session_open
kverif_cov_session_list
kverif_cov_session_close
kverif_cov_query
```

## 工具暴露开关

每个工具组都有独立开关，取值支持 `1/0`、`true/false`、`yes/no`、`on/off`。未设置时，read-only 工具组默认开启；写入类工具默认不暴露。

```bash
# 只暴露 kdebug + common
KVERIF_MCP_ENABLE_BIT=0 \
KVERIF_MCP_ENABLE_ENTRY=0 \
KVERIF_MCP_ENABLE_LOC=0 \
KVERIF_MCP_ENABLE_CONTEXT=0 \
KVERIF_MCP_ENABLE_SVA=0 \
tools/kverif-mcp

# 关闭 ksva
KVERIF_MCP_ENABLE_SVA=0 tools/kverif-mcp

# 暴露 kberif 写工具
KVERIF_MCP_ENABLE_CONTEXT=1 \
KVERIF_MCP_ENABLE_CONTEXT_WRITE=1 \
KVERIF_MCP_ENABLE_WRITE=1 \
tools/kverif-mcp
```

`context_write` 工具需要同时满足：

```text
KVERIF_MCP_ENABLE_CONTEXT=1
KVERIF_MCP_ENABLE_CONTEXT_WRITE=1
KVERIF_MCP_ENABLE_WRITE=1
```

关闭某组后，该组工具不会注册到 FastMCP，因此不会出现在 MCP `tools/list` 中，也不能被 MCP client 直接调用。`kverif_tools` 和 `kverif_tool_help` 使用同一套策略；AI agent 不确定当前暴露范围时应先调用 `kverif_tools`。

## 测试

```bash
make -C kdebug PYTHON=python3 mcp-test
PYTHON=python3 KVERIF_MCP_FAKE_LSF=1 tools/kverif-lsf-doctor --fake
```
