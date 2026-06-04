---
name: xbit
description: 当 AI agent 需要确定性计算 bit、SV literal、signed/unsigned、slice、concat、mask、onehot、popcount、常量表达式、波形条件或 expected value 比较时使用；不要靠推理心算。
---

# xbit Skill

`xbit` 是 verification debug agent 的确定性 bit/value/expression calculator。它和 `xdebug` 同层：`xdebug` 查询设计/波形事实，`xbit` 计算这些事实里的 bit/value/expression 结果。

## 何时必须使用

遇到以下任一情况时，必须调用 `xbit`，不要靠心算：

- 进制转换：hex/bin/decimal/SV literal
- signed/unsigned 解释：例如 `8'shff`、`32'd-1`
- bit slice/index：例如 `data[15:8]`
- concat/repeat：例如 `{4'hA,4'h5}`、`{4{2'b10}}`
- trunc/zext/sext/reverse/mask/align
- popcount/onehot/onehot0/gray code
- 常量表达式：arithmetic、bitwise、logical、comparison、shift、ternary
- valid-ready 条件判断
- opcode/field/mask/expected value 比较
- 从 xdebug/xwave 返回的 compact values 做二次判断

## 边界

`xbit` 不理解 RTL：

- 不解析 RTL 文件
- 不读 filelist
- 不分析 module / instance / hierarchy
- 不做 parameter elaboration
- 不做 lint、formal 或仿真

如果需要查信号来源、波形值或协议事件，先用 `xdebug`；如果需要计算值、字段或条件，再用 `xbit`。

## 调用入口

优先使用 shell 中已安装的 `xbit` 命令。`xbit` 应来自仓库里的 `tools/xbit` wrapper，推荐通过把 `$XVERIF_HOME/tools` 加入 `PATH` 安装；skill 和回答里不要暴露本机绝对路径，需要描述路径时使用 `<xverif-root>`、`<repo-root>` 或 `$XVERIF_HOME` 这类占位符。

```bash
xbit conv "8'shff" --json
```

如果当前 shell 尚未安装 `xbit`，并且当前工作目录就是仓库根目录，可以临时使用 `tools/xbit conv "8'shff" --json`。

兼容入口 `xbit/xbit` 仍保留为转发 wrapper。`tools/xbit` 默认优先使用已配置的 Miniconda Python；没有可用配置时回退到 `python3`。实现只依赖 Python 标准库。

## JSON 响应读取

成功：

```json
{
  "ok": true,
  "schema": "xbit.result.v1",
  "op": "slice",
  "input": "32'hdead_beef",
  "result": {
    "width": 8,
    "signed": false,
    "known": true,
    "unsigned": 190,
    "signed_value": -66,
    "hex": "0xbe",
    "bin": "1011_1110",
    "sv": "8'hbe"
  },
  "warnings": []
}
```

失败：

```json
{
  "ok": false,
  "schema": "xbit.error.v1",
  "error": {
    "code": "WIDTH_OUT_OF_RANGE",
    "message": "slice range is invalid for value width"
  }
}
```

读取规则：

- 先检查 `ok`。
- bit 结果读 `result.width/result.unsigned/result.signed_value/result.hex/result.bin/result.sv`。
- 条件结果优先读 `result.bool` 或 `matched`。
- 如果 `known=false`，不要把结果当确定值。
- 错误时读 `error.code` 决定下一步。

## 常用模板

### 进制与 signed

```bash
xbit conv "8'shff" --json
xbit conv "16'hff80" --json
xbit conv "32'd-1" --json
```

### Slice / concat / repeat

```bash
xbit slice "32'hdead_beef" 15 8 --json
xbit concat "4'ha" "4'h5" --json
xbit repeat 4 "2'b10" --json
```

### 扩展和截断

```bash
xbit trunc "16'h12ff" --to 8 --json
xbit zext "8'h80" --to 16 --json
xbit sext "8'h80" --to 16 --json
```

### Mask / popcount / onehot

```bash
xbit mask --width 13 --json
xbit popcount "32'hdead_beef" --json
xbit onehot "8'h20" --json
xbit onehot0 "8'h00" --json
```

### 表达式

```bash
xbit eval "8'shff >>> 1" --json
xbit eval "{4{2'b10}}" --json
xbit eval "data[15:8] == 8'hbe" --var data=32'hdead_beef --json
xbit eval "valid && ready" --var valid=1'b1 --var ready=1'b0 --json
```

### 波形条件 check

```bash
xbit check \
  --expr "valid && ready && data[15:8] == 8'hbe" \
  --var valid=1'b1 \
  --var ready=1'b1 \
  --var data=32'hdead_beef \
  --json
```

如果有 xdebug/xwave compact values 文件：

```bash
xbit check --values values.json --expr "valid && ready && opcode == 4'ha" --json
```

## Agent stdio

```bash
xbit agent serve --stdio
```

单行请求：

```json
{"id":1,"method":"xbit.eval","params":{"expr":"data[15:8] == 8'hbe","vars":{"data":"32'hdead_beef"}}}
```

常用方法：

- `xbit.conv`
- `xbit.eval`
- `xbit.slice`
- `xbit.concat`
- `xbit.repeat`
- `xbit.mask`
- `xbit.popcount`
- `xbit.check`

## 错误处理

- `PARSE_ERROR`：表达式或 literal 语法不支持；不要猜，修正输入。
- `UNKNOWN_VARIABLE`：缺少 `--var` 或 `--values` 字段；先补变量。
- `WIDTH_OUT_OF_RANGE`：slice/resize 宽度非法；检查 msb/lsb/to。
- `FOUR_STATE_LITERAL`：默认 2-state 遇到 X/Z；若只需展示可加 `--state 4`。
- `FOUR_STATE_UNSUPPORTED`：4-state 运算无法确定；不要给确定性结论。
- `DIVISION_BY_ZERO`：表达式除零；报告条件不可计算。

## 推荐工作流

1. 用 `xdebug` 查事实，例如某时刻 values、driver evidence、event rows。
2. 把 compact values 中的字段交给 `xbit`。
3. 用 `xbit eval/check` 判断条件、字段、mask、expected value。
4. 在回答中引用 `xbit` JSON 结果，不要写“我心算得到”。
