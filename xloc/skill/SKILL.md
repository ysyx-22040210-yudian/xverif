---
name: xloc
description: >
  当 AI agent 处理 UVM/仿真日志里的 xloc 位置 ID（L_XXXXXXXX）、需要把压缩后的 log
  位置还原为源码 file/line、查看源码上下文、统计报错热点或给日志加位置注释时使用。
  xloc 是 xverif 的日志位置工具，不负责 RTL 因果、波形查询或 bit 计算。
---

# xloc

`xloc` 用来把 UVM 仿真日志里的 `L_XXXXXXXX` 还原成源码位置。它只回答“这条 log 来自哪个文件哪一行”和“哪些位置最常出现”，不要用它分析 RTL、读 FSDB、计算 bit；这些任务分别交给 `xdebug` 和 `xbit`。

## 何时使用

使用 xloc：

- 用户给了包含 `L_00000001` 这类 loc_id 的仿真日志。
- 需要知道某个 loc_id 对应的 `file/line/msg_id`。
- 需要查看 loc_id 附近源码上下文。
- 需要统计日志中最常出现的报错/告警位置。
- 需要把压缩日志临时注释成人类可读日志。

不要使用 xloc：

- 查询设计 driver/load/path/波形值：用 `xdebug`。
- 计算 SV literal、slice、mask、expected value：用 `xbit`。
- 日志里没有 `L_XXXXXXXX`，且用户没有 sidecar map。

## 程序入口

优先调用已安装的命令：

```bash
xloc <command> ...
```

如果当前 shell 没有 `xloc` 函数，而当前目录是 xverif 仓库根目录，可用临时入口：

```bash
tools/xloc <command> ...
```

回答和文档里不要暴露本机绝对路径；需要说明路径时用 `<xverif-root>`、`<project-root>`、`$XVERIF_HOME`。

## 命令速查

还原单个 loc_id：

```bash
xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
```

查看源码上下文：

```bash
xloc context L_00000001 --map out/sim.log.xloc.jsonl --before 5 --after 5
```

统计日志热点。若未传 `--map`，默认找 `<log>.xloc.jsonl`：

```bash
xloc stats out/sim.log --top 20
```

给压缩日志加 `[loc]` 注释，输出到 stdout：

```bash
xloc annotate out/sim.log --map out/sim.log.xloc.jsonl
```

## Agent 决策流程

1. 如果用户给的是一整段压缩日志，先保存或定位日志文件，再跑 `xloc stats <log> --top N` 找高频 loc_id。
2. 对最关键的 loc_id 用 `xloc resolve <loc_id> --map <map.jsonl>`，不要靠猜。
3. 只有需要源码证据时再跑 `xloc context <loc_id> --before 5 --after 5`。
4. 如果用户要可读日志，用 `xloc annotate <log>`，但不要默认把整份长日志贴回对话。
5. 回答时引用 `loc_id + file:line + msg_id`，例如：`L_00000005 -> tb/scoreboard.sv:238 [PKT_MISMATCH]`。

## Map 文件规则

- sidecar map 通常叫 `<log>.xloc.jsonl`，例如 `sim.log.xloc.jsonl`。
- `resolve` 和 `context` 必须传 `--map`。
- `stats` 和 `annotate` 可以省略 `--map`，工具会尝试查找 `<log>.xloc.jsonl`。
- 如果 map 缺失，先告诉用户无法还原源码位置；仍可用 `stats` 统计 loc_id 出现频率。

## 结果读取

`resolve` 输出通常包含：

```text
loc_id:  L_00000001
file:    tb/scoreboard.sv
line:    238
msg_id:  PKT_MISMATCH
```

`context` 会在目标源码行前标记 `>>>`。最终结论优先引用这行，而不是引用整段上下文。

`stats` 输出热点表；先处理 count 高、severity 高、或用户点名的 loc_id。

## 错误处理

- `not found in <map>`：loc_id 不在该 map 中。检查是否拿错了 `sim.log.xloc.jsonl`。
- 找不到源码文件：map 仍能证明原始 `file/line`，但当前机器缺少源码；回答时说明只能定位，不能展示上下文。
- 命令不存在：在 xverif 仓库根目录用 `tools/xloc ...` 临时调用；推荐把 `$XVERIF_HOME/tools` 加入 `PATH`。
