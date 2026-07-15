# MCP LSF backend

MCP 使用 LSF 时设置：

```bash
KVERIF_MCP_BACKEND=lsf
```

链路：

```text
MCP client -> kverif-mcp -> LsfLauncher -> bsub -I tools/kdebug --stdio-loop
```

kcov 同理启动 `tools/kcov --stdio-loop`。

## 环境变量

- `KVERIF_MCP_BACKEND=lsf`
- `KVERIF_LSF_BSUB`
- `KVERIF_LSF_BKILL`
- `KVERIF_LSF_SESSION_QUEUE`
- `KVERIF_LSF_SESSION_RESOURCE`
- `KVERIF_MCP_STARTUP_TIMEOUT_SEC`
- `KVERIF_MCP_REQUEST_TIMEOUT_SEC`
- `KVERIF_MCP_FAKE_LSF=1` 本地 fake LSF

MCP server 子进程不会自动继承 IDE/shell 外的环境。必须在 MCP 配置里显式列出计算节点需要的 Verdi、NPI、license、PATH、LSF 变量。

如果必须 LSF 但不能使用 MCP SDK，或要脚本化驱动 session，改用 [../sdk-free-kdebug/overview.md](../sdk-free-kdebug/overview.md)。
