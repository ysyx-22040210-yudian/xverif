# 下一轮 Benchmark 的 KDebug 证据门禁

本文定义下一轮 repair benchmark 的最低合格标准。核心规则只有一句：

> 每个 case 必须在注错和原始失败运行完成后，由独立采集步骤真实执行 KDebug，并生成可机器复算、可逐 case 追溯、不可跨 case 复用的 manifest；通过门禁后才允许启动任何模型 trial。

历史 suite 中仅存在非空 `evidence/` 文件并不等于执行过 KDebug。文件名、人工说明或从
`fail/run.log` 复制出来的文本都不能作为工具调用证明。

## 1. 强制执行顺序

每个 case 必须按以下顺序准备：

1. 创建匿名 case 并完成 RTL、环境或 mixed 注错。
2. 执行该 case 的原始 failing workload，固定 `case_meta.json`、`fail/*.log` 和 `fail/run.rc`。
3. 准备当前 case 专用的 KDebug request 和 `evidence/kdebug_plan.json`。
4. 对当前 case 单独执行 `kdebug_evidence.py collect`。collector 直接调用真实
   `/home/host/kverif/tools/kdebug --json <canonical-request>`。
5. 对当前 case 执行完整 hash、输入、请求、stdout、响应和时间顺序校验。
6. 全部选中 case 采集完成后执行 `validate-suite`，检查 collection UUID 是否跨 case 重用。
7. 只有 suite 校验成功后，`run_matrix.sh` 才创建 repair workdir 和调用模型 API。

`run_matrix.sh` 已强制执行第 4 至第 7 步。采集或校验失败时脚本立即退出，不会消耗模型
token，也不会生成一个看似正常的 `with_kdebug` 成绩。

## 2. 每个 Case 的目录合同

```text
case_001/
  case_meta.json
  fail/
    run.log
    run.rc
  inputs/
    waves.fsdb                 # 或 case-local/外部的真实 FSDB
    simv.daidir/               # 设计查询需要；仅波形查询可没有
  evidence/
    kdebug_plan.json           # 本 case 的采集计划
    requests/
      failure_value.json       # 人工准备、但不包含 request_id 的原始请求
    with_kdebug/               # 只能由 collector 生成
      manifest.json
      manifest.sha256
      kdebug_failure_value.json
      _requests/
        failure_value.json     # collector 规范化后的实际请求
      _raw/
        failure_value.stdout   # KDebug 原始 stdout
      _stderr/
        failure_value.txt
```

禁止从基础 case 或其他 case 继承 `evidence/with_kdebug/`。同一个 FSDB 可以在确有设计理由时
被多个查询使用，但每个 case 必须有自己的 request、真实调用、collection UUID 和 manifest。

## 3. 三份输入必须一致

### 3.1 `case_meta.json`

```json
{
  "case_id": "case_001",
  "tool_evidence": {
    "required_for_with_kdebug": true,
    "plan": "evidence/kdebug_plan.json",
    "expected_files": ["kdebug_failure_value.json"],
    "minimum_nonempty_files": 1
  }
}
```

### 3.2 `evidence/kdebug_plan.json`

```json
{
  "schema_version": "kdebug-evidence-plan.v1",
  "case_id": "case_001",
  "request_timeout_sec": 600,
  "minimum_successful_invocations": 1,
  "minimum_diagnostic_invocations": 1,
  "max_fail_log_similarity": 0.8,
  "requests": [
    {
      "id": "failure_value",
      "request": "evidence/requests/failure_value.json",
      "output": "kdebug_failure_value.json",
      "diagnostic": true,
      "timeout_sec": 600
    }
  ]
}
```

### 3.3 `evidence/requests/failure_value.json`

```json
{
  "api_version": "kdebug.v1",
  "action": "value.at",
  "target": {"fsdb": "inputs/waves.fsdb"},
  "args": {
    "signal": "tb_top.dut.failure_signal",
    "time": "100ns",
    "format": "hex"
  }
}
```

上例中的 FSDB、信号和时间只是占位符，建 suite 时必须替换成当前 case 的真实输入和真实信号。
需要静态 driver 时使用 `target.daidir` 和 `trace.driver`；需要某时刻 active driver 时同时提供
同一次构建生成的 `target.fsdb` 与 `target.daidir`。

`case_meta.json.tool_evidence.expected_files` 必须与 plan 中所有 `output` 完全一致。`actions`、
`schema`、`server.ping` 等控制 action 不能计作 diagnostic invocation。

## 4. Manifest 记录什么

`manifest.json` 使用 `kdebug-evidence-manifest.v1`，至少记录：

| 类别 | 机器校验字段 |
| --- | --- |
| Case 身份 | `case_id`、独立 `collection_id`、真实 `case_root` |
| 时间 | collection 与每次 invocation 的 ISO 时间、纳秒时间戳和 duration |
| Collector | collector 名称、版本和 SHA-256 |
| KDebug | command prefix、wrapper/runtime 文件路径、size、SHA-256、Git commit、响应版本 |
| Case 来源 | `case_meta.json`、plan、全部 `fail/*.log` 的相对路径、size 和 SHA-256 |
| 实际调用 | 完整 `command_argv`、action、timeout、exit code、是否超时 |
| 真实输入 | FSDB 文件 SHA-256；daidir 全目录逐文件确定性 SHA-256、文件数和总大小 |
| 请求与输出 | source request、canonical request、raw stdout、stderr、parsed response 的 size 和 SHA-256 |
| 汇总 | invocation 数、成功数、成功 diagnostic invocation 数 |

`manifest.sha256` 校验 `manifest.json` 本身。JSON Schema 位于：

```text
/home/host/kverif/benchmarks/kdebug_repair_benchmark/schemas/kdebug_evidence_manifest.schema.json
/home/host/kverif/benchmarks/kdebug_repair_benchmark/schemas/kdebug_evidence_plan.schema.json
```

## 5. 校验器拒绝什么

| 情况 | 结果 |
| --- | --- |
| manifest 或 sidecar 缺失 | 拒绝 |
| KDebug exit code 非 0、超时、`ok != true`、响应不是 `kdebug.v1` | 拒绝 |
| control action 冒充 diagnostic action | 拒绝 |
| FSDB 内容、daidir 任意文件或工具 runtime 在采集后改变 | 拒绝 |
| `case_meta.json`、plan、request 或 fail log 在采集后改变 | 拒绝 |
| canonical request 无法由 case 原始 request 重建 | 拒绝 |
| parsed response 与 KDebug 原始 stdout 不一致 | 拒绝 |
| request/response 的 action 或 `request_id` 不一致 | 拒绝 |
| KDebug 响应缺少统一后的 `tool.name=kdebug` 或版本 | 拒绝 |
| response 长文本复制自 `fail/*.log`，或相似度超过 plan 阈值 | 拒绝 |
| `evidence/with_kdebug/` 出现 plan 未声明的附加文件 | 拒绝 |
| summary 或 reported version 无法从 invocation 重新计算 | 拒绝 |
| 两个 case 复用同一个 collection UUID | suite 整体拒绝 |

普通缺文件记为 `TOOL_EVIDENCE_MISSING`；manifest、hash、输入、调用或自洽性检查失败记为
`TOOL_EVIDENCE_INVALID`。两者都是无效 trial，不算模型失败，也不能进入工具组有效成功率分母。

## 6. 普通用户 `host` 的单 Case 命令

以下命令不调用模型 API，可以直接验证采集门禁：

```bash
su - host

export KVERIF_HOME=/home/host/kverif
export PATH="$KVERIF_HOME/tools:$PATH"
export VERDI_HOME=/home/synopsys/verdi/Verdi_O-2018.09-SP2
export VCS_HOME=/home/synopsys/vcs/O-2018.09-SP2
export VCS_TARGET_ARCH=linux64
export LM_LICENSE_FILE=27000@IC_EDA
export SNPSLMD_LICENSE_FILE=27000@IC_EDA

CASE=/home/host/kverif_runs/xiangshan_next/case_001
EVIDENCE_PY=/home/host/kverif/benchmarks/kdebug_repair_benchmark/scripts/kdebug_evidence.py

/usr/local/bin/python3.8 "$EVIDENCE_PY" collect \
  --case-dir "$CASE" \
  --kdebug /home/host/kverif/tools/kdebug

/usr/local/bin/python3.8 "$EVIDENCE_PY" validate --case-dir "$CASE"
```

成功时两个命令均退出 0，并输出：

```json
{
  "valid": true,
  "case_id": "case_001",
  "successful_diagnostic_invocations": 1
}
```

要有意重新采集，必须显式使用 `--force`。旧证据会移动到
`evidence/_kdebug_archive/<timestamp>/`，不会被静默覆盖：

```bash
/usr/local/bin/python3.8 "$EVIDENCE_PY" collect \
  --case-dir "$CASE" \
  --kdebug /home/host/kverif/tools/kdebug \
  --force
```

## 7. Suite 与 Matrix 命令

只校验已有证据，不调用模型：

```bash
/usr/local/bin/python3.8 /home/host/kverif/benchmarks/kdebug_repair_benchmark/scripts/kdebug_evidence.py \
  validate-suite \
  --suite-root /home/host/kverif_runs/xiangshan_next \
  --cases case_001,case_002,case_003
```

默认 matrix 模式会逐 case 采集、做 suite 校验，然后启动模型：

```bash
export KDEBUG_BIN=/home/host/kverif/tools/kdebug
export KDEBUG_PYTHON=/usr/local/bin/python3.8
export KDEBUG_REPORT_PYTHON=/bin/python3

bash /home/host/kverif/benchmarks/kdebug_repair_benchmark/scripts/run_matrix.sh \
  --suite-root /home/host/kverif_runs/xiangshan_next \
  --bench-root /home/host/kverif/benchmarks/kdebug_repair_benchmark \
  --cases case_001,case_002,case_003 \
  --models qwen3.6-35b \
  --timeout 3600 \
  --evidence-mode collect
```

已有证据需要只读复核时使用 `--evidence-mode validate`。只有明确需要重新运行 KDebug 时才加
`--force-evidence`。API key 只能通过运行时环境变量提供，不能写入 case、manifest、日志或报告。
VM 上 `host` 的系统 `python3` 可能仍是 3.6，因此 matrix 命令必须显式设置
`KDEBUG_PYTHON=/usr/local/bin/python3.8` 或其他 Python 3.8+ 解释器。当前 VM 的
`python-docx/Pillow` 安装在系统 Python 3.6 中，因此报告阶段另设
`KDEBUG_REPORT_PYTHON=/bin/python3`；在依赖统一的机器上可省略该变量。

## 8. A/B 公平性

- 采集步骤在模型 trial 之前完成，采集耗时不占任一模型的 3600 秒 repair budget。
- `with_kdebug` 与 `without_kdebug` 共用同一 failing case、fail log、设计说明和 judge。
- `with_kdebug` prompt 只加入 plan 声明且已经校验的 parsed response；不会暴露 manifest、raw
  stdout、collector 内部文件或私有答案。
- `without_kdebug` 不能读取 `evidence/`。模型也不能修改 evidence、fail log、case metadata 或 judge。
- 工具效果必须按 case 结合“有效 manifest、模型公开回复中实际采用的独有字段、补丁位置和最终
  judge”审计；仅有 `tool_evidence_valid=true` 不等于工具帮助模型命中根因。

## 9. 信任边界

该门禁能发现文件篡改、陈旧输入、复制日志、request/response 拼装、跨 case UUID 复用和工具
runtime 漂移。它不是密码学签名系统：如果攻击者同时控制采集主机、KDebug 可执行文件并重写全部
manifest，单纯 SHA-256 不能证明其身份。需要对抗这种威胁时，应在可信 CI/VM 中采集，并对
`manifest.json` 增加外部签名或透明日志。本 benchmark 的最低标准假设 VM 和 suite 管理员可信，
但模型与 case 内文件均不可信。
