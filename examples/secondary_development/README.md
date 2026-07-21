# kverif CLI 二次开发示例

这里的示例不导入任何 kverif Python 包，并分别给出 Bash、csh、Perl 和 Python
调用方式。每个语言示例都会调用真实工具命令、解析工具输出，并生成新的项目结论。
稳定集成面只有四项：

1. `tools/` 下的可执行命令。
2. 命令行参数或原始 JSON request。
3. `--json` 返回的结构化结果。
4. 进程退出码：`0` 成功，非 `0` 失败。

目录内容：

```text
secondary_development/
  sh/signal_health.sh           Bash 调 kdebug、解析 summary 并生成信号健康结论
  sh/waveform_window.sh        多信号 FSDB scan、批量采样、active-driver 和门禁
  sh/module_connectivity.sh    KDB driver/load/graph 查询和连线门禁
  sh/coverage_convergence.sh   多轮 VDB 趋势、防回退、平台期和准入判断
  sh/regression_triage.sh      FSDB/KDB/VDB 跨工具回归分诊和统一报告
  csh/signal_health.csh        csh 调 kdebug、处理字段并生成信号健康结论
  perl/signal_health.pl        Perl 调 kdebug、处理字段并生成信号健康结论
  perl/waveform_window.pl      Perl 直接调用 kdebug 的完整示例
  py/signal_health.py          Python subprocess/json 标准库完整闭环
  fixtures/fsdb_handshake/    可复现 RTL、testbench、真实 FSDB 和真实信号清单
  json_response.py             独立进程式 JSON 校验和聚合器，不是 SDK
  tests/run.sh                 使用假 CLI 的无 EDA 合约测试
  tests/run_real_fsdb.sh       使用 Verdi 和随库 FSDB 的真实后端回归
```

## 随仓库提供的真实 FSDB、RTL 和信号

示例不再要求用户先自行准备 `waves.fsdb`。仓库包含一套完整 fixture：

```text
fixtures/fsdb_handshake/
  rtl/kverif_handshake_dut.sv  valid/ready 握手 DUT RTL
  tb/tb_kverif_handshake.sv    产生 stall 和四次有效传输的 testbench
  waves.fsdb                    VCS/Verdi 2018 真实生成的 9,107-byte FSDB
  signal_manifest.json          FSDB 真实层次名、位宽、变化次数和检查点
  SHA256SUMS                     FSDB 完整性校验
  build_vcs.sh                   重新生成 FSDB 和 simv.daidir
```

预生成 FSDB 的 SHA-256 是：

```text
f1c50e6e502f84450469932ceb7fe151057a06df02487840911b034134d38fb0
```

以下信号均已在该 FSDB 中用 Verdi 2018 + 真实 kdebug 查询通过：

| 信号 | 位宽 | RTL 含义 | FSDB 变化记录数 |
| --- | ---: | --- | ---: |
| `tb_kverif_handshake.clk` | 1 | 10ns 周期时钟 | 26 |
| `tb_kverif_handshake.rst_n` | 1 | 低有效复位 | 2 |
| `tb_kverif_handshake.dut.req_valid` | 1 | 请求有效 | 5 |
| `tb_kverif_handshake.dut.req_ready` | 1 | 下游 ready | 7 |
| `tb_kverif_handshake.dut.req_fire` | 1 | 内部 `valid && ready` | 7 |
| `tb_kverif_handshake.dut.req_data` | 8 | 请求数据 | 5 |
| `tb_kverif_handshake.dut.rsp_valid` | 1 | 响应有效 | 7 |
| `tb_kverif_handshake.dut.rsp_data` | 8 | `req_data ^ 8'h5a` | 5 |
| `tb_kverif_handshake.dut.accepted_count` | 4 | 已接收请求计数 | 5 |
| `tb_kverif_handshake.dut.state_q` | 2 | IDLE/WAIT_READY/RESPOND | 8 |
| `tb_kverif_handshake.dut.last_accepted_q` | 8 | 最近接收的数据 | 5 |

开箱即用的直接查询：

```bash
export KVERIF_HOME=/home/host/kverif
FIXTURE=$KVERIF_HOME/examples/secondary_development/fixtures/fsdb_handshake

$KVERIF_HOME/tools/kdebug --json action signal.scan \
  --fsdb $FIXTURE/waves.fsdb \
  --arg signal=tb_kverif_handshake.dut.accepted_count \
  --arg begin=0ns --arg end=125ns --arg format=hex \
  --max-rows 100

$KVERIF_HOME/tools/kdebug --json value-batch \
  --fsdb $FIXTURE/waves.fsdb \
  --signal tb_kverif_handshake.dut.req_fire \
  --signal tb_kverif_handshake.dut.rsp_data \
  --signal tb_kverif_handshake.dut.accepted_count \
  --time 95ns --format hex
```

95ns 的实测值为 `accepted_count=4`、`rsp_data=ec`。完整 fixture 说明见
[`fixtures/fsdb_handshake/README.md`](fixtures/fsdb_handshake/README.md)。
重新生成的 FSDB 可能因内嵌路径或时间元数据而具有不同 SHA-256；应使用 manifest 的
信号变化次数和检查点确认功能一致性。

无需重新编译即可做 FSDB value/scan 查询。driver/load/graph 和 active-driver 还需要
与当前设备 VCS/Verdi 匹配的 KDB；使用同一份 RTL 生成：

```bash
cd $FIXTURE
export VCS_TARGET_ARCH=linux64
bash ./build_vcs.sh
# KDB:  $FIXTURE/build/simv.daidir
# FSDB: $FIXTURE/build/waves.fsdb
```

## 跨设备与脱离仓库运行

建议复制整个 `secondary_development/` 目录，而不是只复制单个脚本。Bash、csh 和
Perl 示例会从各自脚本目录的上一层查找 `json_response.py`，`regression_triage.sh`
还需要同目录的三个子工作流。脚本不依赖启动时的当前工作目录，目录名、输入路径和
输出路径可以包含空格。

工具发现顺序固定如下，排在前面的配置优先：

| 对象 | 发现顺序 |
| --- | --- |
| `kdebug` | `--kdebug-bin` -> `KDEBUG_BIN` -> `$KVERIF_HOME/tools/kdebug` -> 仓库相对路径 -> `PATH` |
| `kcov` | `--kcov-bin` -> `KCOV_BIN` -> `$KVERIF_HOME/tools/kcov` -> 仓库相对路径 -> `PATH` |
| JSON Python | `--json-python` -> `KVERIF_JSON_PYTHON` -> `PYTHON` -> `python3/python` in `PATH` |
| JSON helper | `--json-helper` -> `KVERIF_JSON_HELPER` -> 脚本旁的 `../json_response.py` -> `$KVERIF_HOME/examples/...` |

例如，把示例复制到另一台设备的项目目录，而 kverif 工具安装在 `/opt/kverif`：

```bash
cp -R /opt/kverif/examples/secondary_development \
  "/work/team flow/kverif examples"
export PATH="/opt/kverif/tools:$PATH"

cd /work/project-a
FSDB="/work/team flow/kverif examples/fixtures/fsdb_handshake/waves.fsdb"
bash "/work/team flow/kverif examples/sh/signal_health.sh" \
  --fsdb "$FSDB" --signal tb_kverif_handshake.dut.accepted_count \
  --begin 0ns --end 125ns --min-changes 5 --require-complete \
  --out "/work/project-a/reports/signal health"
```

CI 中也可完全不用 `PATH`，显式传入所有运行入口：

```bash
bash "/work/team flow/kverif examples/sh/coverage_convergence.sh" \
  --kcov-bin /opt/kverif/tools/kcov \
  --json-python /usr/bin/python3 \
  --json-helper "/work/team flow/kverif examples/json_response.py" \
  --run base=/data/regress/001/simv.vdb \
  --run next=/data/regress/002/simv.vdb \
  --out /data/reports/coverage
```

这里的“可移植”指调用和结果处理层不绑定仓库绝对路径，也不要求安装语言 SDK。
真实 FSDB 查询仍要求目标设备能够执行 `kdebug`，并具备兼容的 Verdi、FSDB 和
license；KDB 查询还需要与构建匹配的 `simv.daidir`；真实 coverage 查询要求
`kcov`、VDB 和对应 Synopsys 环境。没有 EDA 环境的设备只能运行假 CLI 合约测试，
不能把真实数据库查询替换成 mock 结果。

## 工作流能力

| 示例 | 查询链 | 项目门禁 | 主要产物 |
| --- | --- | --- | --- |
| `waveform_window.sh` | session open -> 每信号 `signal.scan` -> 每时间点 `value.batch_at` -> 可选 active-driver | 最小变化次数、最大未知值、禁止截断 | 原始 response、`signals.ndjson`、`gate-errors.txt`、`report.json` |
| `module_connectivity.sh` | 每信号 driver -> load -> dependency graph | driver edge 必须存在、禁止 graph 截断 | driver/load/graph response、`signals.ndjson`、`report.json` |
| `coverage_convergence.sh` | 每轮 `cov-summary` + `cov-holes` -> 趋势聚合 | 最终覆盖率、最大 hole、最大回退、必须增长 | 每轮 response、`runs.ndjson`、`convergence.json` |
| `regression_triage.sh` | waveform + connectivity + coverage | 三类门禁串联，任一失败即非零退出 | 三个子目录和统一 `report.json` |

## 四种语言的完整闭环

四个 `signal_health` 示例执行完全相同的验证规则：

```text
脚本参数
  -> 启动 tools/kdebug --json action signal.scan
  -> 保存 tool-response.json
  -> 读取 summary.change_count / unknown_count / truncated
  -> 在当前语言脚本中应用项目阈值
  -> 生成 conclusion.json
  -> HEALTHY 返回 0，门禁不通过返回 3
```

| 结论 | 判定规则 | 新结论含义 |
| --- | --- | --- |
| `INCOMPLETE` | 使用 `--require-complete` 且 `truncated=true` | 查询窗口不完整，当前证据不足以签核 |
| `UNKNOWN_VALUES` | `unknown_count > max_unknown` | X/Z 数超过项目容忍值 |
| `INACTIVE` | `change_count < min_changes` | 信号在目标窗口内活动不足 |
| `HEALTHY` | 上述规则均未触发 | 信号活动满足当前项目阈值 |

优先级按表格从上到下。也就是说，被截断的查询不会被误判成“信号不活动”。

Bash、csh 和 Perl 使用 `json_response.py wave-stats` 作为独立 JSON parser 进程，但
状态优先级、阈值比较和最终结论都写在各自脚本中。Python 示例直接使用标准库
`subprocess` 和 `json`，只执行工具命令，不导入 kverif 模块。

统一调用示例：

```bash
export KVERIF_HOME=/home/host/kverif
export KDEBUG_BIN=$KVERIF_HOME/tools/kdebug
export KVERIF_JSON_PYTHON=/usr/bin/python3
export KVERIF_FSDB_FIXTURE=$KVERIF_HOME/examples/secondary_development/fixtures/fsdb_handshake

bash $KVERIF_HOME/examples/secondary_development/sh/signal_health.sh \
  --fsdb $KVERIF_FSDB_FIXTURE/waves.fsdb \
  --signal tb_kverif_handshake.dut.accepted_count \
  --begin 0ns --end 125ns --min-changes 5 --max-unknown 0 --require-complete \
  --out /data/run/conclusions/sh

csh $KVERIF_HOME/examples/secondary_development/csh/signal_health.csh \
  --fsdb $KVERIF_FSDB_FIXTURE/waves.fsdb \
  --signal tb_kverif_handshake.dut.accepted_count \
  --begin 0ns --end 125ns --min-changes 5 --max-unknown 0 --require-complete \
  --out /data/run/conclusions/csh

perl $KVERIF_HOME/examples/secondary_development/perl/signal_health.pl \
  --fsdb $KVERIF_FSDB_FIXTURE/waves.fsdb \
  --signal tb_kverif_handshake.dut.accepted_count \
  --begin 0ns --end 125ns --min-changes 5 --max-unknown 0 --require-complete \
  --out /data/run/conclusions/perl

/usr/bin/python3 $KVERIF_HOME/examples/secondary_development/py/signal_health.py \
  --fsdb $KVERIF_FSDB_FIXTURE/waves.fsdb \
  --signal tb_kverif_handshake.dut.accepted_count \
  --begin 0ns --end 125ns --min-changes 5 --max-unknown 0 --require-complete \
  --out /data/run/conclusions/python
```

每个目录都保存 `tool-response.json` 和 `conclusion.json`。结论报告示例：

```json
{
  "schema": "kverif.example.signal-health.v1",
  "language": "csh",
  "gate_pass": true,
  "conclusion": {
    "status": "HEALTHY",
    "reason": "signal activity satisfies all configured gates"
  },
  "evidence": {
    "signal": "tb_kverif_handshake.dut.accepted_count",
    "change_count": 5,
    "unknown_count": 0,
    "truncated": false
  },
  "thresholds": {
    "min_changes": 2,
    "max_unknown": 0,
    "require_complete": true
  }
}
```

脚本参数错误退出 `2`，项目门禁失败退出 `3`。工具执行、后端查询或 JSON response
校验失败返回非零。详细参数默认值见各脚本 `--help` 和开发手册第 9 章。

## Bash 依赖

- Bash 4+
- Python 3 标准库 `json`（以独立进程校验 JSON，不导入 kverif 包）
- 对应的 kverif 工具命令

## Perl 依赖

- Perl 5
- 核心模块 `Getopt::Long`、`File::Path` 和 `FindBin`
- 对应的 kverif 工具命令

## csh 依赖

- `csh` 或 `tcsh`
- Python 3 标准库 `json`，仅作为独立 JSON parser 进程
- 对应的 kverif 工具命令

## Python 依赖

- Python 3.6+
- 只使用 `argparse`、`json`、`os`、`shutil`、`subprocess` 等标准库
- 对应的 kverif 工具命令；不安装、不导入 kverif 包

## 复杂调用示例

```bash
export KVERIF_HOME=/home/host/kverif
export PATH="$KVERIF_HOME/tools:$PATH"
FIXTURE=$KVERIF_HOME/examples/secondary_development/fixtures/fsdb_handshake

# 只有 active-driver 和 connectivity 需要先生成本机 KDB。
bash "$FIXTURE/build_vcs.sh"

bash "$KVERIF_HOME/examples/secondary_development/sh/waveform_window.sh" \
  --fsdb "$FIXTURE/waves.fsdb" \
  --daidir "$FIXTURE/build/simv.daidir" \
  --signal tb_kverif_handshake.dut.req_valid \
  --signal tb_kverif_handshake.dut.req_ready \
  --signal tb_kverif_handshake.dut.req_fire \
  --signal tb_kverif_handshake.dut.rsp_data \
  --begin 0ns --end 125ns \
  --time 45ns --time 95ns \
  --active-signal tb_kverif_handshake.dut.rsp_data --active-time 95ns \
  --max-rows 1000 --min-changes 1 --max-unknown 0 --require-complete \
  --out /data/run/kverif-wave

bash "$KVERIF_HOME/examples/secondary_development/sh/module_connectivity.sh" \
  --daidir "$FIXTURE/build/simv.daidir" \
  --signal tb_kverif_handshake.dut.req_valid \
  --signal tb_kverif_handshake.dut.rsp_data \
  --max-depth 8 --max-items 500 --require-edge --require-complete \
  --out /data/run/kverif-connectivity

bash "$KVERIF_HOME/examples/secondary_development/sh/coverage_convergence.sh" \
  --run smoke=/data/regress/001/simv.vdb \
  --run nightly=/data/regress/002/simv.vdb \
  --run closure=/data/regress/003/simv.vdb \
  --metrics line,toggle,branch --hole-limit 500 \
  --plateau-epsilon 0.05 --fail-under 95 --max-final-holes 100 \
  --max-regression 0.10 --require-growth \
  --out /data/run/kverif-coverage

perl "$KVERIF_HOME/examples/secondary_development/perl/waveform_window.pl" \
  --fsdb "$FIXTURE/waves.fsdb" \
  --signal tb_kverif_handshake.dut.req_valid \
  --signal tb_kverif_handshake.dut.rsp_data \
  --begin 0ns --end 125ns --time 45ns --time 95ns \
  --out /data/run/kverif-wave-perl
```

每个示例都支持用环境变量覆盖工具和 helper 路径：

```bash
export KDEBUG_BIN=/opt/kverif/tools/kdebug
export KCOV_BIN=/opt/kverif/tools/kcov
export KVERIF_JSON_PYTHON=/usr/bin/python3
export KVERIF_JSON_HELPER=/opt/kverif/examples/secondary_development/json_response.py
```

对应的显式参数是 `--kdebug-bin`、`--kcov-bin`、`--json-python` 和
`--json-helper`。显式参数适合 CI 单任务覆盖，环境变量适合一组任务共享配置。

完整跨工具分诊：

```bash
bash "$KVERIF_HOME/examples/secondary_development/sh/regression_triage.sh" \
  --fsdb "$FIXTURE/waves.fsdb" \
  --daidir "$FIXTURE/build/simv.daidir" \
  --vdb /data/run/simv.vdb \
  --signal tb_kverif_handshake.dut.req_valid \
  --signal tb_kverif_handshake.dut.rsp_data \
  --begin 0ns --end 125ns --time 45ns --time 95ns \
  --active-signal tb_kverif_handshake.dut.rsp_data --active-time 95ns \
  --min-changes 1 --fail-under 95 --max-final-holes 100 \
  --out /data/run/kverif-triage
```

完整接口规则、错误处理、并发约束和 VM 命令见
[`../../doc/secondary_development_guide.md`](../../doc/secondary_development_guide.md)。
其中第 9 章逐项解释四个复杂工作流，第 10 章单列 `kdebug`、`kcov`、`kbit`、
`kentry`、`kloc`、`ksva`、`kberif`、`keda-runner` 和 loop client/server 的全部
公开参数、功能和逐子命令例子。

无 EDA 合约及搬迁测试：

```bash
cd /path/to/kverif
make secondary-examples-test
```

测试会把示例复制到仓库外、名称含空格的临时目录，从另一个工作目录启动，并在清空
`KDEBUG_BIN`、`KCOV_BIN`、`KVERIF_HOME` 和 helper 覆盖后，仅通过 `PATH` 查找假
`kdebug/kcov`。Bash、Perl、Python、coverage 和跨工具分诊必须全部生成有效报告；
安装了 csh/tcsh 时还会执行 csh 合同。

有真实 Verdi/VCS 环境时，再运行随库 FSDB 的完整后端测试：

```bash
KVERIF_HOME=/home/host/kverif \
KDEBUG_BIN=/home/host/kverif/tools/kdebug \
bash /home/host/kverif/examples/secondary_development/tests/run_real_fsdb.sh
```

等价的仓库目标是 `make secondary-examples-real-test`。
