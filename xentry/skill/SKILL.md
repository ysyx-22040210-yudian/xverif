---
name: xentry
description: >
  当 AI agent 需要解析 entry、descriptor、context、metadata、table entry、WQE、CQE
  或 header field 的多拍 byte fragments，并按外部 config 切 raw 域段时使用。
  xentry 是 JSON-first 的确定性 field decoder，不做波形读取、协议理解或字段类型解码。
---

# xentry

`xentry` 用来把多拍 byte fragments 按 config 切成 raw field slices。不要让 LLM 自己跨拍拼接、hex slicing 或猜字段来源。

## 何时使用

使用 xentry：

- 用户提供了 entry/descriptor/header 的 byte fragments。
- 每拍有 `seq/data/valid_lsb/valid_width`。
- 用户提供或需要你构造字段布局 config。
- 需要知道某个 field 来自哪一拍、哪些 bit。

不要使用 xentry：

- 需要读波形或判断 valid/ready：先用 xdebug 或上游 adapter。
- 需要计算 SV 表达式或 expected value：用 xbit。
- 需要还原 log 位置：用 xloc。

## 调用入口

首选 JSON request：

```bash
xentry/xentry '{"api_version":"xentry.v1","action":"decode","config":{...},"fragments":[...]}'
```

也可从 stdin：

```bash
printf '%s\n' '<json-request>' | xentry/xentry -
```

## Agent 规则

1. config 必须声明 `total_bits`、`fragment_byte_order`、`bit_numbering` 和 `fields`。
2. fragment 必须是多拍 byte fragments：`seq/data/valid_lsb/valid_width`。
3. 不要在 config 里放 `type/enum/ipv4/mac`，xentry 只输出 raw。
4. 分析时引用 `field.raw_hex` 和 `field.source`，尤其是跨拍字段。
5. 如果 `ok:false`，先报告 config/fragments 问题，不要猜字段值。
