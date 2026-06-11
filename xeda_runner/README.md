# xeda-runner

带环境快照缓存的阻塞式 allowlist command runner。

纯 Python 标准库实现，零 pip 依赖。支持 bash / zsh / tcsh。

## 快速开始

```bash
# 初始化环境快照
xeda-runner init

# 查看可用 action
xeda-runner list-actions

# 了解 action 详情
xeda-runner describe-action --action sim

# 执行
xeda-runner run --action sim --target compile --option TEST=smoke_test --option SEED=123

# 仅预览，不执行
xeda-runner run --action sim --target compile --dry-run
```

## 配置文件

`.xeda-runner.json`，详细格式见目录下示例文件。

## 长任务说明

xeda-runner 是阻塞式 runner，不会后台化执行。如果预估命令执行时间超过 **5 分钟**，建议使用 `tmux` 或 `nohup` 保证任务不会被 terminal / shell 生命周期影响：

```bash
# tmux（推荐）
tmux new -d -s sim "xeda-runner run --action sim --target compile --option TEST=smoke"

# 查看输出
tmux capture-pane -t sim -p

# nohup
nohup xeda-runner run --action sim --target compile --option TEST=smoke > sim.log 2>&1 &

# 查看输出
tail -f sim.log
```

xeda-runner 只负责启动进程，不负责后台存活和结果监控。

## License

MIT
