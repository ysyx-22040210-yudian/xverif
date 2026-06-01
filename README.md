# xverif

`xverif` 是面向芯片验证 debug agent 的本地工具仓库，当前包含三个互补工具：

- [`xdebug`](xdebug/README.md)：查询设计数据库和波形数据库里的事实。
- [`xbit`](xbit/README.md)：确定性计算 bit、literal、slice、表达式和 expected value。
- [`xloc`](xloc/README.md)：UVM 日志位置压缩与恢复，降低 LLM token 噪声。

简单说：`xdebug` 负责“事实从哪里来、某时刻发生了什么”，`xbit` 负责“这些值按 SystemVerilog 规则算出来到底是多少”，`xloc` 负责“这条 log 在哪个文件的哪一行，但只在需要时才查”。

## 工具概览

### xdebug

`xdebug` 是 xtrace 与 xwave 合并后的统一调试工具。它通过 JSON API 查询 Verdi/VCS `daidir` 设计事实、FSDB 波形事实，或在两者同时存在时做 combined/debug join。

适合的问题：

- 查信号 driver、load、依赖图、路径和源码 evidence。
- 查波形值、事件、窗口验证、signal changes、handshake 异常。
- 查 APB/AXI 协议异常、latency、outstanding、error response。
- 在具体波形时间点定位当前生效 RTL driver：`trace.active_driver`。

入口示例：

```bash
tools/xdebug-env -h
printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | tools/xdebug-env -
```

完整说明见 [`xdebug/README.md`](xdebug/README.md)。

### xbit

`xbit` 是确定性 bit/value/expression 计算器。它不读取 RTL、不分析层次结构，只负责把输入值按明确规则算对，避免 agent 靠心算处理位宽、符号位和表达式。

适合的问题：

- SV literal、hex/bin/decimal 转换。
- signed/unsigned 解释。
- bit slice/index、concat、repeat、mask、popcount、onehot。
- 常量表达式、valid-ready 条件、expected value 比较。
- 对 `xdebug` 返回的 compact values 做二次计算。

入口示例：

```bash
xbit/xbit conv "8'shff" --json
xbit/xbit eval "data[15:8] == 8'hbe" --var data=32'hdead_beef --json
```

完整说明见 [`xbit/README.md`](xbit/README.md)。

### xloc

`xloc` 是 LLM-friendly 的 UVM 日志位置压缩与恢复工具。它将 UVM 仿真日志中冗长的文件路径替换为简短 `L_XXXXXXXX` ID，通过 sidecar JSONL 映射文件支持按需恢复源码上下文，降低 LLM 处理 log 的 token 噪声。

适合的问题：

- 解析仿真日志中 `L_XXXXXXXX` 对应的源码位置。
- 统计日志中高频报错的热点位置。
- 查看 loc_id 对应的源码上下文。
- 给带 loc_id 的日志添加可读注释。

入口示例：

```bash
PYTHONPATH=xloc python3 -m xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
PYTHONPATH=xloc python3 -m xloc stats out/sim.log
```

完整说明见 [`xloc/README.md`](xloc/README.md)。

## 推荐 Shell 入口

为了在任意目录调用，建议在 shell rc 文件中配置统一入口。示例中的 `<xverif-root>` 表示本仓库根目录，请按本机实际路径替换。

Bash / Zsh：

```bash
export XVERIF_HOME=<xverif-root>
export XDEBUG_ENTRY="$XVERIF_HOME/tools/xdebug-env"
export XBIT_ENTRY="$XVERIF_HOME/xbit/xbit"
export XLOC_ENTRY="$XVERIF_HOME/xloc"
xdebug() { "$XDEBUG_ENTRY" "$@"; }
xbit() { "$XBIT_ENTRY" "$@"; }
xloc() { PYTHONPATH="$XLOC_ENTRY" python3 -m xloc "$@"; }
```

Tcsh：

```tcsh
setenv XVERIF_HOME <xverif-root>
setenv XDEBUG_ENTRY "$XVERIF_HOME/tools/xdebug-env"
setenv XBIT_ENTRY "$XVERIF_HOME/xbit/xbit"
setenv XLOC_ENTRY "$XVERIF_HOME/xloc"
alias xdebug '"$XDEBUG_ENTRY" \!*'
alias xbit '"$XBIT_ENTRY" \!*'
alias xloc 'PYTHONPATH=$XLOC_ENTRY python3 -m xloc \!*'
```

配置后：

```bash
xdebug -h
xbit conv "8'shff" --json
xloc resolve L_00000001 --map out/sim.log.xloc.jsonl
```

## 构建与测试

`xdebug` 需要可用的 Verdi/NPI 环境；`xbit` 只依赖 Python 标准库，优先使用已配置的 Miniconda Python，失败时回退到 `python3`。

```bash
make -C xdebug
make -C xdebug schema-test
make -C xdebug contract-test
make -C xdebug unit-test

make -C xbit test
make -C xloc test

make test
make full-test
```

`schema-test` 校验 xdebug JSON schema 和 examples，不依赖 Synopsys 环境；`contract-test` 在 xdebug 构建后校验 ActionSpec 与 runtime `actions` 输出一致。`make test` 覆盖仓库内常规单测、contract test 和自带夹具；`make full-test` 会加入更多设计、波形和真实数据回归，要求本机具备相应 Synopsys 运行环境和 license。

## 文档入口

- xdebug 用户文档：[`xdebug/README.md`](xdebug/README.md)
- xdebug agent skill：[`xdebug/skill/SKILL.md`](xdebug/skill/SKILL.md)
- xdebug JSON API 速查：[`xdebug/skill/references/json-api-reference.md`](xdebug/skill/references/json-api-reference.md)
- xbit 用户文档：[`xbit/README.md`](xbit/README.md)
- xbit agent skill：[`xbit/skill/SKILL.md`](xbit/skill/SKILL.md)
- xloc 用户文档：[`xloc/README.md`](xloc/README.md)
- xloc agent skill：[`xloc/skill/SKILL.md`](xloc/skill/SKILL.md)
