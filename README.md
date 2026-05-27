# xdebug

`xdebug` 是基于 Verdi/NPI 的统一调试工具。公开入口只接受 JSON 请求，并返回 JSON 响应。

## 构建与调用

```bash
export VERDI_HOME=/path/to/verdi
make

printf '%s\n' '{"api_version":"xdebug.v1","action":"actions"}' | tools/xdebug-env -
tools/xdebug-env request.json
```

不提供文本子命令模式。状态统一位于 `~/.xdebug/`，运行日志位于
`~/.xdebug/work/{design,waveform,combined}/`。

## 资源模式

| `target` | 模式 | 主要能力 |
| --- | --- | --- |
| `daidir` | `design` | 信号解析、驱动/负载追踪、控制依赖、时序/FSM/计数器解释 |
| `fsdb` | `waveform` | 值查询、范围检查、列表、事件、APB/AXI、异常与握手分析 |
| `daidir` 与 `fsdb` | `combined` | 单资源能力加动态生效驱动追踪 |

设计动作使用精确层次路径；候选名称应先通过源码中的 `rg` 搜索定位。
`signal.search` 明确不支持。

## 请求示例

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {
    "daidir": "/path/to/simv.daidir",
    "fsdb": "/path/to/waves.fsdb"
  },
  "args": {
    "signal": "top.u_dut.valid",
    "requested_time": "22us",
    "include_control": true,
    "include_parity": false
  }
}
```

仅提供 `daidir` 时可执行 `trace.driver`、`trace.expand`、
`sequential.update` 等设计动作；仅提供 `fsdb` 时可执行
`value.at`、`signal.statistics`、`event.export` 等波形动作。

`trace.active_driver` 返回请求时刻、实际生效时刻、可信驱动语句与控制证据。
当只确认控制分支而无法确认赋值语句时，`driver_status` 为
`control_only`，工具不会推测赋值来源。

## 代码结构

```text
xdebug/
├── skill/SKILL.md
├── third_party/json.hpp
├── src/
│   ├── api/          # xdebug.v1 解析、响应与路由
│   ├── core/         # 路径、基础类型与通信公共件
│   ├── session/      # 统一会话索引
│   ├── runtime/      # 工作目录与日志隔离
│   ├── backend/      # 私有服务进程适配
│   ├── design/       # 设计数据库查询能力
│   ├── waveform/     # 波形及协议查询能力
│   └── combined/     # 联合动态追踪能力
├── tests/            # unit/design/waveform/combined/realdata
└── testdata/         # 仓库自带可生成夹具
```

`xdebug/libexec/` 仅包含构建生成的私有后端程序，不能作为公开调用入口。

## 测试

```bash
make test       # 单元测试与自带联合夹具
make full-test  # 加入设计、波形及可用真实数据回归
```

完整回归日志写入 `/tmp/xdebug_full_regression_<timestamp>/`。需要真实
NPI/FSDB 执行的用例必须在具备 Synopsys 运行环境和 license 的机器上运行。
