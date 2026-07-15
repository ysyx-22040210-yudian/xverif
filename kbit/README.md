# kbit

`kbit` 是给芯片验证 debug agent 使用的确定性 bit/value/expression 计算工具。

它回答的问题很窄：

- 这个 SV literal 到底是多少？
- 这个 slice、concat、repeat、mask、onehot、popcount 结果是多少？
- 这个 signed/unsigned 解释是否正确？
- 这个常量表达式或某一拍条件是否成立？

它明确不做：

- 不解析 RTL 文件
- 不读 filelist
- 不分析 module / instance / hierarchy
- 不做 parameter elaboration
- 不做 lint、formal 或仿真

## Quick Start

`kbit` wrapper 默认优先使用已配置的 Miniconda Python；没有可用配置时回退到 `python3`。如果已经按下面的 Shell 命令入口配置过，可以直接运行 `kbit ...`；否则在仓库根目录临时使用 `tools/kbit ...`。

默认输出为 `kout` 结构化文本；需要脚本解析完整字段时加 `--json`。

```bash
make -C kbit test

kbit conv "8'shff"
kbit slice "32'hdead_beef" 15 8
kbit eval "data[15:8] == 8'hbe" --var data=32'hdead_beef
kbit check --expr "valid && ready" --var valid=1'b1 --var ready=1'b0
```

未安装 shell 命令时的仓库内临时入口：

```bash
tools/kbit conv "8'shff"
tools/kbit conv "8'shff" --json
```

### Shell 命令入口

为了在任意目录和非交互 shell 中稳定调用，建议把仓库 `tools/` 加入 `PATH`。下面示例里的 `<kverif-root>` 表示本仓库根目录，请按本机实际路径替换；文档和 skill 中不固定记录个人机器路径。

Bash：加入 `~/.bashrc`。

```bash
export KVERIF_HOME=<kverif-root>
export PATH="$KVERIF_HOME/tools:$PATH"
```

Zsh：加入 `~/.zshrc`。

```zsh
export KVERIF_HOME=<kverif-root>
export PATH="$KVERIF_HOME/tools:$PATH"
```

Tcsh：加入 `~/.tcshrc`。

```tcsh
setenv KVERIF_HOME <kverif-root>
setenv PATH "$KVERIF_HOME/tools:$PATH"
```

配置后可以直接使用：

```bash
kbit conv "8'shff" --json
kbit eval "data[15:8] == 8'hbe" --var data=32'hdead_beef --json
```

兼容入口 `kbit/kbit` 仍保留为转发 wrapper，但新文档和 skill 推荐 `tools/kbit` 或 `PATH` 中的 `kbit`。

JSON 成功响应：

```json
{
  "ok": true,
  "schema": "kbit.result.v1",
  "op": "conv",
  "input": "8'shff",
  "result": {
    "width": 8,
    "signed": true,
    "known": true,
    "unsigned": 255,
    "signed_value": -1,
    "hex": "0xff",
    "bin": "1111_1111",
    "sv": "8'shff"
  },
  "warnings": []
}
```

失败响应：

```json
{
  "ok": false,
  "schema": "kbit.error.v1",
  "error": {
    "code": "WIDTH_OUT_OF_RANGE",
    "message": "slice range is invalid for value width"
  }
}
```

## Commands

### Value conversion

```bash
kbit conv "16'hff80" --json
kbit conv "8'shff" --json
kbit conv "32'd-1" --json
```

`result` 默认同时给 `width`、`signed`、`unsigned`、`signed_value`、`hex`、`bin`、`sv`。

### Bit operation

```bash
kbit slice "32'hdead_beef" 15 8 --json
kbit index "8'h80" 7 --json
kbit concat "4'ha" "4'h5" --json
kbit repeat 4 "2'b10" --json
kbit trunc "16'h12ff" --to 8 --json
kbit zext "8'h80" --to 16 --json
kbit sext "8'h80" --to 16 --json
kbit reverse "8'b1000_0001" --json
kbit mask --width 13 --json
kbit align "13'd17" --to 8 --json
kbit popcount "32'hdead_beef" --json
kbit onehot "8'h20" --json
kbit onehot0 "8'h00" --json
kbit gray2bin "4'b1110" --json
kbit bin2gray "4'b1011" --json
```

### Expression evaluation

```bash
kbit eval "8'shff >>> 1" --json
kbit eval "{4{2'b10}}" --json
kbit eval "{4'hA, 4'h5}" --json
kbit eval "ADDR_W + ID_W - 1" --var ADDR_W=32 --var ID_W=4 --json
kbit eval "valid && ready" --var valid=1'b1 --var ready=1'b0 --json
kbit eval "data[15:8] == 8'hbe" --var data=32'hdead_beef --json
```

支持范围：

- SV numeric literal
- arithmetic：`+ - * / %`
- bitwise：`~ & | ^`
- logical：`! && ||`
- comparison：`== != < <= > >=`
- shift：`<< >> <<< >>>`
- concat/repeat：`{a,b}`、`{N{value}}`
- slice/index：`value[msb:lsb]`、`value[bit]`
- ternary：`cond ? a : b`
- 用户显式传入变量：`--var name=value`

不支持宏展开、函数调用、typedef、packed struct、enum、module parameter 自动解析。

### Wave/debug check

`check` 用于吃波形或 kdebug/kwave compact values，并判断某个条件。

```bash
kbit check \
  --expr "valid && ready && data[15:8] == 8'hbe" \
  --var valid=1'b1 \
  --var ready=1'b1 \
  --var data=32'hdead_beef \
  --json
```

`--values` 支持直接 map：

```json
{
  "valid": "1'b1",
  "ready": "1'b1",
  "data": "32'hdead_beef"
}
```

也支持 compact 包装：

```json
{
  "values": {
    "valid": "1'b1",
    "ready": "1'b1",
    "data": "32'hdead_beef"
  }
}
```

### Agent stdio

```bash
kbit agent serve --stdio
```

输入一行 JSON request，输出一行 JSON response：

```json
{"id":1,"method":"kbit.eval","params":{"expr":"data[15:8] == 8'hbe","vars":{"data":"32'hdead_beef"}}}
```

支持方法：

- `kbit.conv`
- `kbit.eval`
- `kbit.slice`
- `kbit.concat`
- `kbit.repeat`
- `kbit.mask`
- `kbit.popcount`
- `kbit.check`

## 2-state 与 4-state

默认 `--state 2`。遇到 `x/z/?` 会失败，避免 agent 把未知值当确定值。

`--state 4` 可以保留 literal 中的 X/Z 展示信息，但表达式传播不是本轮目标；遇到无法确定的 4-state 运算会返回 `FOUR_STATE_UNSUPPORTED`。

## Agent 使用原则

当调试涉及以下内容时，agent 应调用 `kbit`，不要心算：

- 进制转换
- bit slice/index
- concat/repeat
- signed/unsigned 解释
- mask、popcount、onehot
- SystemVerilog literal
- 常量表达式
- valid-ready 条件判断
- expected value 比较

`kdebug` 负责查询 daidir/fsdb 事实，`kbit` 负责对这些事实做确定性 bit/value/expression 计算。
