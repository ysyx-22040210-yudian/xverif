# xloc

`xloc` 是给 LLM debug agent 使用的 UVM 日志位置压缩与恢复工具。

它回答的问题很窄：

- 这个 `L_XXXXXXXX` 对应哪个文件的哪一行？
- 这段仿真日志里哪些位置报错最多？
- 这个 loc_id 附近源码是什么样的？

它明确不做：

- 不分析 RTL 逻辑
- 不读 FSDB 波形
- 不查设计层次结构
- 不做仿真或 formal

## 核心思路

UVM 仿真日志中大量出现这种内容：

```text
UVM_ERROR <project-root>/tb/env/scoreboard.sv(238) @ 100ns: packet mismatch
```

对 LLM 来说，`<project-root>/tb/env/scoreboard.sv(238)` 消耗 token 但大部分时候决策价值很低。

`xloc` 把它变成：

```text
UVM_ERROR L_00000001 @ 100ns: packet mismatch
```

当 LLM 需要知道具体位置时，调用 `xloc resolve L_00000001` 还原。

## Quick Start

```bash
make -C xloc test

# 用一个手动构造的 JSONL 试一下
echo '{"loc_id":"L_00000001","file":"tb/test.sv","line":42,"msg_id":"ERROR_TEST"}' > /tmp/test.xloc.jsonl
PYTHONPATH=xloc python3 -m xloc resolve L_00000001 --map /tmp/test.xloc.jsonl
```

### Shell 命令入口

为了在任意目录调用，建议把 `xloc` 安装成 shell function。下面示例里的 `<xverif-root>` 表示本仓库根目录，请按本机实际路径替换。

Bash / Zsh：

```bash
export XVERIF_HOME=<xverif-root>
export XLOC_ENTRY="$XVERIF_HOME/xloc"
xloc() { PYTHONPATH="$XLOC_ENTRY" python3 -m xloc "$@"; }
```

Tcsh：

```tcsh
setenv XVERIF_HOME <xverif-root>
setenv XLOC_ENTRY "$XVERIF_HOME/xloc"
alias xloc 'PYTHONPATH=$XLOC_ENTRY python3 -m xloc \!*'
```

配置后可以直接使用：

```bash
xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
xloc stats out/sim.log
```

## Commands

### resolve — 还原源码位置

```bash
xloc resolve L_00000005 --map out/sim.log.xloc.jsonl
```

输出：

```text
loc_id:  L_00000005
file:    tb/simple_test.sv
line:    3
msg_id:  PKT_MISMATCH
```

### context — 查看源码上下文

```bash
xloc context L_00000005 --map out/sim.log.xloc.jsonl --before 5 --after 5
```

先 resolve，再打印目标行附近源码，目标行以 `>>>` 标记。

`--before` / `--after` 默认各 20 行。

### stats — 统计热点位置

```bash
xloc stats out/sim.log --top 20
```

自动查找同目录下的 `sim.log.xloc.jsonl`（或通过 `--map` 指定）。

输出：

```text
loc_id          count  file                            msg_id
L_00000001        127  tb/scoreboard.sv                PKT_MISMATCH
L_00000002         31  tb/monitor.sv                   BAD_PKT
...
27 unique locations, 320 total occurrences
```

### annotate — 给日志加注释

```bash
xloc annotate out/sim.log --map out/sim.log.xloc.jsonl
```

在 log 中每个首次出现的 loc_id 前插入一行：

```text
[loc] L_00000001 -> tb/test.sv:42
```

输出到 stdout，可重定向到文件。

## UVM 集成

### 在你的验证环境中使用

将仓库中 `sv/xloc_pkg.sv` 和 `sv/xloc_report_server.sv` 两个文件复制到你的验证环境，然后在 testbench 顶层注册：

```systemverilog
import xloc_pkg::*;

xloc_report_server loc_svr;

initial begin
  loc_svr = new();
  loc_svr.copy(uvm_coreservice_t::get().get_report_server());
  uvm_coreservice_t::get().set_report_server(loc_svr);
end
```

仿真后产物：

- `sim.log` — 路径已替换为 `L_XXXXXXXX`
- `sim.log.xloc.jsonl` — sidecar 映射文件

可以通过 `set_map_path("custom/path.jsonl")` 自定义 JSONL 输出路径。

### 机制

- loc_id 使用递增序列号：`L_%08X`（零碰撞）
- 通过 static 关联数组去重：同一 file:line:msg_id 只生成一次
- JSONL 逐行追加写入，仿真中断不丢数据

## 内建 UVM 测试环境

```bash
make -f Makefile.test   # 需要 VCS + UVM
```

测试环境位于 `xloc/tb/`，在不同文件中调用 `uvm_error`/`uvm_warning`/`uvm_info`，验证多文件 loc_id 生成和去重。产物输出到 `xloc/out/`。

## Agent 使用原则

当 LLM debug agent 处理带 loc_id 的日志时：

1. **不要猜 loc_id**。用 `xloc resolve` 查询。
2. **先 stats 后 resolve**。了解高频位置，优先查这些。
3. **需要源码证据时才 context**。只是想知道文件在哪用 resolve 就够了。
4. **回答时引用 loc_id + 文件位置**。例如：`L_00000005 (simple_test.sv:3)`。

## 构建与测试

```bash
make -C xloc          # 语法检查
make -C xloc test     # Python 单元测试
make -f Makefile.test # UVM 测试环境（需 VCS + UVM）
```

`xloc` 只依赖 Python 标准库，不依赖 NPI、Verdi 或任何 Synopsys 工具。UVM 测试环境需要 VCS。
