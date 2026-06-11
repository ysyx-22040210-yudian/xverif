---
name: xeda-runner
description: 芯片项目 EDA 命令安全执行器。当 AI 需要执行 make/vcs/simv 等依赖项目 setup.csh/module 环境的命令时使用。
---

本项目的 EDA 命令必须通过 xeda-runner 执行。

## 禁止直接执行的命令

- make
- vcs
- simv
- urg
- verdi
- xrun
- xdebug
- 以及其他依赖项目 setup.csh / module 环境的命令

## 标准工作流

```bash
# 1. 首次使用：初始化环境快照
xeda-runner init

# 2. 查看可用 action
xeda-runner list-actions

# 3. 了解 action 支持的 target 和 option（含 command/fixed_args，仅供审计）
xeda-runner describe-action --action <name>

# 4. 预览命令（不需要 init）
xeda-runner run --action <name> --target <t> --option KEY=VALUE --dry-run

# 5. 执行命令
xeda-runner run --action <name> --target <t> --option KEY=VALUE
```

## 输出解读

执行命令时终端和 `~/.xeda_runner/<pid>.log` 同步输出：

- `runner_pid`：xeda-runner 自身进程
- `child_pid`：实际启动的命令进程（make/vcs/simv），用户需要 `kill` 或监控任务时使用此 pid
- `exit_code`：命令真实退出码，0 表示成功

## 配置

配置文件为当前工作目录下的 `.xeda-runner.yaml`。如不在当前目录，可通过 `--config` 显式指定。

- `workdir`：工作目录，runner 自动 `cd`，**不要在 `init_steps` 里手动写 `cd`**
- `init_steps`：每步失败即退出（fail-fast），不成功的 init 不会生成有效 env 快照
- `actions`：白名单，option 支持 `required`、`values` 枚举、`pattern` 正则校验

## 规则

- xeda-runner 是阻塞式命令，执行完成后根据 `exit_code` 判断结果
- `describe-action` 输出的 `command`/`fixed_args` 仅供审计，不可绕过 runner 直接使用
- 禁止自行 source setup.csh / setup.sh
- 禁止自行设置环境变量
- 禁止自行拼接底层 EDA command
- 禁止绕过 xeda-runner 调用 make/vcs/simv/urg 等命令
- 如果预估执行时间超过 **5 分钟**，必须建议用户使用 `tmux` 或 `nohup`：
  `tmux new -d -s <name> "xeda-runner run ..."` 或 `nohup xeda-runner run ... &`
- xeda-runner 只负责启动进程，不负责后台监控
