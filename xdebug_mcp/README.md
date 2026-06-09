# xdebug MCP / LSF backend

`xdebug_mcp` 是 `tools/xdebug-mcp` 的 Python 实现。它提供两个 backend：

- `direct`：默认模式，在本机直接调用 `tools/xdebug --json -`。
- `lsf`：通过 `bsub -I` 在集群内启动 router job 和 per-session TCP endpoint job，让 AI MCP 客户端访问计算节点上的 xdebug。

本目录只实现 wrapper、router、fake runner 和测试辅助；不读取 NPI、FSDB 或 daidir。

## 入口

```bash
tools/xdebug-mcp
tools/xdebug-lsf-doctor
```

建议使用 Python 3.11+：

```bash
PYTHON=python3 tools/xdebug-mcp
PYTHON=python3 tools/xdebug-lsf-doctor
```

## LSF backend

MCP client 配置：

```json
{
  "mcpServers": {
    "xdebug": {
      "command": "<xverif-root>/tools/xdebug-mcp",
      "env": {
        "XVERIF_HOME": "<xverif-root>",
        "XDEBUG_MCP_BACKEND": "lsf"
      }
    }
  }
}
```

运行链路：

```text
AI MCP client
  -> tools/xdebug-mcp
  -> bsub -I router job
  -> per-session TCP endpoint jobs
  -> tools/xdebug
```

并发语义：

- 不同 session 并行。
- 同一 session 串行。
- Router crash 后 wrapper 会重启 router，并重新注册仍 alive 的 session。
- 单个 session crash 只影响该 session。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `XDEBUG_MCP_BACKEND` | `direct` 或 `lsf` |
| `XDEBUG_LSF_BSUB` | 覆盖 `bsub` 命令 |
| `XDEBUG_MCP_FAKE_LSF=1` | 本地测试用 fake LSF runner |
| `XDEBUG_MCP_TIMEOUT_SEC` | direct backend 请求超时 |
| `XVERIF_HOME` | 仓库根目录 |
| `PYTHON` | wrapper 使用的 Python |

## 测试

```bash
make -C xdebug PYTHON=python3 mcp-test
PYTHON=python3 XDEBUG_MCP_FAKE_LSF=1 tools/xdebug-lsf-doctor --fake
```

测试里的 fake LSF 不需要真实 `bsub`，但会覆盖 ready 噪声、router 恢复、多 session 并行、同 session 串行、session crash 隔离和 xout/json/envelope 返回。

## 配置 Claude Code MCP

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "xdebug": {
      "type": "stdio",
      "command": "<conda-env>/bin/python",
      "args": ["-m", "xdebug_mcp.server"],
      "env": {
        "PYTHONPATH": "<xverif>/xdebug_mcp/src:<xverif>",
        "XVERIF_HOME": "<xverif>",
        "VERDI_HOME": "<verdi-install>",
        "LD_LIBRARY_PATH": "<verdi-install>/share/NPI/lib/LINUX64",
        "XDEBUG_MCP_BACKEND": "direct"
      }
    }
  }
}
```

替换说明：
- `<conda-env>`：安装了 `mcp[cli]` 的 Python 环境路径（如 `~/miniconda3/envs/xdebug-mcp`）
- `<xverif>`：xverif 仓库根目录
- `<verdi-install>`：Synopsys Verdi 安装根目录（`XDEBUG_MCP_BACKEND=lsf` 时不需要）

`XDEBUG_MCP_BACKEND` 可选值：
- `direct`：本机直接调用 `tools/xdebug --json -`
- `lsf`：通过 bsub 在 LSF 集群内启动 router + per-session TCP endpoint

Claude Code 在启动时会自动加载项目根目录下的 `.mcp.json`，无需额外配置。
