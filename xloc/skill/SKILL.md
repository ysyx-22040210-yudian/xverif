---
name: xloc
description: >
  当 AI agent 需要解析 UVM 仿真日志中由 xloc 替换的 loc_id（L_XXXXXXXX）时使用。
  提供 resolve（还原源码位置）、context（查看源码上下文）、stats（统计热点位置）、
  annotate（给日志加位置注释）四个子命令。也用于指导用户如何在 UVM 环境中集成
  xloc_report_server 以生成带 loc_id 的仿真日志。
---

# xloc Skill

`xloc` 是面向 LLM debug agent 的 UVM 日志位置压缩与恢复工具。它把 UVM 仿真日志中冗长的文件路径+行号替换为简短 `L_XXXXXXXX` ID，通过 sidecar JSONL 映射文件支持按需恢复源码上下文。

## 何时使用

遇到以下情况时使用本 skill：

- 用户提供了带有 `L_XXXXXXXX` 标记的 UVM 仿真日志，需要还原具体源码位置
- 需要查看某个 loc_id 对应的源码上下文
- 需要统计日志中高频报错位置
- 需要给带 loc_id 的日志添加可读的位置注释
- 用户询问如何在 UVM 环境中集成 xloc_report_server

## 工具定位

`xloc` 和 `xdebug`、`xbit` 同属于 xverif 体系，职责清晰：

| 工具 | 作用 |
|------|------|
| xdebug | 查询设计/波形事实 |
| xbit | 确定性 bit/value/expression 计算 |
| **xloc** | UVM 日志位置压缩与恢复 |

## 调用入口

优先使用 shell 中已安装的 `xloc` 命令。`xloc` 应指向仓库里的 `PYTHONPATH=<xverif-root>/xloc python3 -m xloc`，由用户在 shell rc 中配置。skill 和回答里不要暴露本机绝对路径；需要描述路径时使用 `<xverif-root>`、`<repo-root>` 或 `$XVERIF_HOME` 这类占位符。

```bash
xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
xloc context L_00000001 --map out/sim.log.xloc.jsonl
xloc stats out/sim.log
xloc annotate out/sim.log
```

如果当前 shell 尚未安装 `xloc`，并且当前工作目录就是仓库根目录，可以临时使用：

```bash
PYTHONPATH=xloc python3 -m xloc <command> <args>
```

实现只依赖 Python 标准库。

## 四个子命令

### `resolve <loc_id>`

查 sidecar JSONL，输出 file/line/msg_id：

```bash
xloc resolve L_00000005 --map out/sim.log.xloc.jsonl
```

输出：

```text
loc_id:  L_00000005
file:    /path/to/tb/simple_test.sv
line:    3
msg_id:  PKT_MISMATCH
```

### `context <loc_id>`

先 resolve，再读取源码文件附近行：

```bash
xloc context L_00000005 --map out/sim.log.xloc.jsonl --before 2 --after 2
```

输出 resolve 信息 + 源码片段，目标行以 `>>>` 标记。

### `stats <sim.log>`

统计 log 中所有 loc_id 出现频率：

```bash
xloc stats out/sim.log --top 20
```

自动查找同目录下的 `sim.log.xloc.jsonl`（或通过 `--map` 指定）。
输出 loc_id、出现次数、对应文件、msg_id。

### `annotate <sim.log>`

在 log 中每个首次出现的 loc_id 前插入 `[loc]` 注释行：

```bash
xloc annotate out/sim.log
```

输出到 stdout，可重定向：

```bash
xloc annotate out/sim.log > annotated.log
```

## Agent 使用原则

1. **不要在脑子里猜 loc_id 对应的文件**。用 `xloc resolve` 查询。
2. **只解析对 debug 有价值的 loc_id**。不需要把所有 loc_id 都 resolve 一遍。
3. **解析前先 stats**，了解哪些位置是高频热点，优先查这些。
4. **需要源码证据时用 context**，只是想知道文件在哪用 resolve。
5. **回答用户时引用 loc_id + 文件位置**，不要让用户自己查。

## 典型工作流

### 用户给你带 loc_id 的 log

1. `xloc stats sim.log` — 看热点位置
2. `xloc resolve L_XXXXXXXX` — 查具体位置
3. `xloc context L_XXXXXXXX --before 5 --after 5` — 看源码上下文
4. 结合 loc_id 和源码内容，给用户结论

### 用户想在自己的 UVM 环境中集成

指引用户：

1. 将 `sv/xloc_pkg.sv` 和 `sv/xloc_report_server.sv` 复制到验证环境
2. 在 testbench 顶层 `initial` 块中注册 server：
   ```systemverilog
   import xloc_pkg::*;
   xloc_report_server loc_svr;
   initial begin
     loc_svr = new();
     loc_svr.copy(uvm_coreservice_t::get().get_report_server());
     uvm_coreservice_t::get().set_report_server(loc_svr);
   end
   ```
3. 运行仿真，产物：
   - `sim.log` — 路径已替换为 `L_XXXXXXXX`
   - `sim.log.xloc.jsonl` — sidecar 映射文件

## loc_id 格式与机制

- 格式：`L_XXXXXXXX`（8 位 hex 序列号，如 `L_0000001F`）
- SV 侧用 static 关联数组去重：同一 file:line:msg_id 首次遇到时生成新 ID 并追加写 JSONL，后续命中直接复用
- JSONL 格式：
  ```jsonl
  {"loc_id":"L_00000001","file":"tb/scoreboard.sv","line":238,"msg_id":"PKT_MISMATCH"}
  ```
- `map_path` 默认 `sim.log.xloc.jsonl`（相对于仿真工作目录），可通过 `set_map_path()` 自定义

## 构建与测试

```bash
make -C xloc test       # Python 单元测试
make -f xloc/Makefile.test   # UVM 测试环境（需要 VCS + UVM）
```

UVM 测试环境位于 `xloc/tb/`，所有产物输出到 `xloc/out/`。
