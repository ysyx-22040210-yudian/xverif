# xentry

`xentry` 是给 LLM debug agent 使用的确定性 entry 域段解析工具。它接收多拍 byte fragments，每拍指定有效 bit 选位；外部 config 定义字段布局。工具只负责拼接有效 bit、切 raw 域段、输出 provenance。

它明确不做：

- 不读波形。
- 不判断 valid/ready。
- 不理解协议。
- 不做字段类型语义解码。
- 不输出 enum/bool/ipv4/mac 等 decoded value。

## Quick Start

JSON request 是推荐入口：

```bash
printf '%s\n' '{
  "api_version": "xentry.v1",
  "action": "decode",
  "config_path": "xentry/examples/entry.yaml",
  "input_path": "xentry/examples/fragments.jsonl"
}' | xentry/xentry -
```

也可以直接传入单个 JSON 字符串：

```bash
xentry/xentry '{"api_version":"xentry.v1","action":"explain","config_path":"xentry/examples/entry.yaml"}'
```

或使用兼容的人类 CLI：

```bash
xentry/xentry decode --config xentry/examples/entry.yaml --input xentry/examples/fragments.jsonl --json
xentry/xentry explain --config xentry/examples/entry.yaml --json
xentry/xentry validate --config xentry/examples/entry.yaml --input xentry/examples/fragments.jsonl --json
```

## JSON Request

```json
{
  "api_version": "xentry.v1",
  "request_id": "optional-id",
  "action": "decode",
  "config": {},
  "fragments": [],
  "output": {
    "pretty": true
  }
}
```

`config` 可以内联，也可以使用 `config_path`。`fragments` 可以内联，也可以使用 `input_path` 指向 JSONL。

支持 action：

- `decode`：拼接 fragments 并输出 raw field slices。
- `explain`：解释 config 字段布局。
- `validate`：校验 config 和可选 fragments。

## Config

config 只定义 raw 字段布局：

```yaml
name: demo_entry
version: 1
total_bits: 20
fragment_byte_order: msb_first
bit_numbering: byte_lsb0
fields:
  - name: opcode
    bits: "[3:0]"
  - name: route
    bits: "[11:4]"
  - name: payload
    bits: "[19:12]"
```

`fragment_byte_order`：

- `msb_first`：data 中第一个 byte 是 fragment 高位 byte。
- `lsb_first`：data 中第一个 byte 是 fragment 低位 byte。

`bit_numbering`：

- `byte_lsb0`：byte 内 bit 0 是 LSB。
- `byte_msb0`：byte 内 bit 0 是 MSB。

字段只支持 `name`、`bits` 和可选 `description`。不支持 `type`、`enum`、`alias_of`、`ipv4`、`mac` 等语义字段。

## Fragments

输入是 JSONL multi-beat byte fragments：

```jsonl
{"seq":0,"data":"0x1234","valid_lsb":0,"valid_width":12,"source":"beat0"}
{"seq":1,"data":"0xab","valid_lsb":0,"valid_width":8,"source":"beat1"}
```

规则：

- 按 `seq` 升序处理。
- 每拍先按 config 转成 fragment bit vector。
- 取 `data[valid_lsb + valid_width - 1 : valid_lsb]`。
- seq 小的有效 bits append 到 entry 低位。
- 总有效 bit 必须等于 `total_bits`。

可选 `entry_id/time/source/line/tag` 只透传到 provenance。

## Output

`decode` 输出每个字段的 raw 域段：

```json
{
  "ok": true,
  "api_version": "xentry.v1",
  "action": "decode",
  "schema": {"name": "demo_entry", "version": 1},
  "total_bits": 20,
  "entry_raw": "0xab234",
  "fields": {
    "opcode": {
      "bits": "[3:0]",
      "raw_hex": "0x4",
      "raw_bin": "0100",
      "source": [
        {"seq": 0, "entry_bits": "[3:0]", "fragment_bits": "[3:0]"}
      ]
    }
  },
  "warnings": [],
  "errors": []
}
```

## Agent 使用原则

当你需要解释 entry、descriptor、context、metadata、table entry、WQE、CQE 或 header field 时，不要手工拼接 bit，也不要自己做 hex slicing。构造 JSON request 调用 `xentry`，只基于 `fields/raw_hex/raw_bin/source/errors/warnings` 做分析。

## 构建与测试

```bash
make -C xentry
make -C xentry test
```

`xentry` 只依赖 Python 标准库。
