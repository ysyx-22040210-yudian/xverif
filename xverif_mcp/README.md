# xverif MCP

`xverif_mcp` 是 `tools/xverif-mcp` 的 Python 实现，基于 FastMCP SDK。它是 xverif 工具体系统一 MCP 入口：

- **xdebug**：唯一 stateful backend，通过 `tools/xdebug --stdio-loop` 提供设计/波形查询能力，支持 direct/LSF 模式。
- **xbit / xentry / xloc / xberif / xsva**：stateless CLI adapter，每次调用短生命周期 subprocess。

xdebug direct 和 LSF 共用 `XdebugLoopSession`，只在 `Launcher` 层分离。每 session 独立进程，同 session 串行（request_lock），多 session 可并行。

## 入口

```bash
tools/xverif-mcp
tools/xverif-lsf-doctor
```

## MCP 配置

### Claude Code

在项目根目录创建 `.mcp.json`（与 `.git/` 同级，**不是** `.claude/` 目录下）。

**direct 模式：**

```json
{
  "mcpServers": {
    "xverif": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xverif_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "XVERIF_MCP_BACKEND": "direct",
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
    "xverif": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xverif_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "XVERIF_MCP_BACKEND": "lsf",
        "XVERIF_LSF_SESSION_QUEUE": "interactive",
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
- `<conda-env>`：安装了 `mcp[cli]` 的 Python 环境路径（如 `~/miniconda3/envs/xdebug-mcp`）
- `<xverif>`：xverif 仓库根目录
- `<verdi-install>`：Synopsys Verdi 安装根目录
- `<lsf-install>`：LSF 安装根目录

`XVERIF_MCP_BACKEND` 可选值：
- `direct`：本机启动 `tools/xdebug --stdio-loop`
- `lsf`：通过 `bsub -I tools/xdebug --stdio-loop` 提交到 LSF

### 通用 MCP client

```json
{
  "mcpServers": {
    "xverif": {
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xverif_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xverif_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>"
      }
    }
  }
}
```

Claude Code 启动时自动加载项目根目录下的 `.mcp.json`，无需额外配置。

## 运行链路

```text
AI MCP client
  -> xverif-mcp FastMCP server
  -> XverifDebugAdapter (xdebug)
       -> McpSessionManager
       -> DirectLauncher:  tools/xdebug --stdio-loop  (direct)
       -> LsfLauncher:     bsub -I tools/xdebug --stdio-loop  (LSF)
  -> StatelessCliRunner (xbit/xentry/xloc/xberif/xsva)
       -> tools/<tool> --json ...
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `XVERIF_HOME` | 仓库根目录 |
| `XVERIF_MCP_BACKEND` | `direct`（默认）或 `lsf` |
| `XVERIF_MCP_TIMEOUT_SEC` | one-shot 请求超时（默认 360s） |
| `XVERIF_MCP_STARTUP_TIMEOUT_SEC` | session open 超时（默认 180s） |
| `XVERIF_MCP_REQUEST_TIMEOUT_SEC` | query 请求超时（默认 360s） |
| `XVERIF_MCP_CLOSE_TIMEOUT_SEC` | session close 超时（默认 30s） |
| `XVERIF_MCP_BKILL_TIMEOUT_SEC` | bkill 超时（默认 30s） |
| `XVERIF_MCP_ENABLE_WRITE=1` | 启用 xberif 写入操作 |
| `XVERIF_LSF_BSUB` | 覆盖 `bsub` 命令（默认 `bsub`） |
| `XVERIF_LSF_SESSION_QUEUE` | session job 的 LSF 队列（默认 `interactive`） |
| `XVERIF_LSF_BKILL` | 覆盖 `bkill` 命令 |
| `XVERIF_MCP_FAKE_LSF=1` | 本地测试用 fake LSF runner |
| `VERDI_HOME` | Verdi 安装目录 |
| `LD_LIBRARY_PATH` | 需包含 `<verdi-install>/share/NPI/lib/LINUX64` |

## 测试

```bash
make -C xdebug PYTHON=python3 mcp-test
PYTHON=python3 XVERIF_MCP_FAKE_LSF=1 tools/xverif-lsf-doctor --fake
```
