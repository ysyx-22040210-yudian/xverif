# kverif CLI 二次开发示例

这里的示例不导入任何 kverif Python 包，也不要求调用方使用某种编程语言。
稳定集成面只有四项：

1. `tools/` 下的可执行命令。
2. 命令行参数或原始 JSON request。
3. `--json` 返回的结构化结果。
4. 进程退出码：`0` 成功，非 `0` 失败。

目录内容：

```text
secondary_development/
  sh/waveform_window.sh        多信号 FSDB scan、批量采样、active-driver 和门禁
  sh/module_connectivity.sh    KDB driver/load/graph 查询和连线门禁
  sh/coverage_convergence.sh   多轮 VDB 趋势、防回退、平台期和准入判断
  sh/regression_triage.sh      FSDB/KDB/VDB 跨工具回归分诊和统一报告
  perl/waveform_window.pl      Perl 直接调用 kdebug 的完整示例
  json_response.py             独立进程式 JSON 校验和聚合器，不是 SDK
  tests/run.sh                 使用假 CLI 的无 EDA 合约测试
```

## 工作流能力

| 示例 | 查询链 | 项目门禁 | 主要产物 |
| --- | --- | --- | --- |
| `waveform_window.sh` | session open -> 每信号 `signal.scan` -> 每时间点 `value.batch_at` -> 可选 active-driver | 最小变化次数、最大未知值、禁止截断 | 原始 response、`signals.ndjson`、`gate-errors.txt`、`report.json` |
| `module_connectivity.sh` | 每信号 driver -> load -> dependency graph | driver edge 必须存在、禁止 graph 截断 | driver/load/graph response、`signals.ndjson`、`report.json` |
| `coverage_convergence.sh` | 每轮 `cov-summary` + `cov-holes` -> 趋势聚合 | 最终覆盖率、最大 hole、最大回退、必须增长 | 每轮 response、`runs.ndjson`、`convergence.json` |
| `regression_triage.sh` | waveform + connectivity + coverage | 三类门禁串联，任一失败即非零退出 | 三个子目录和统一 `report.json` |

脚本参数错误退出 `2`，项目门禁失败退出 `3`。工具执行、后端查询或 JSON response
校验失败返回非零。详细参数默认值见各脚本 `--help` 和开发手册第 9 章。

## Bash 依赖

- Bash 4+
- Python 3 标准库 `json`（以独立进程校验 JSON，不导入 kverif 包）
- Perl 5（只用于浮点增量计算；EDA VM 通常自带）
- 对应的 kverif 工具命令

## Perl 依赖

- Perl 5
- 核心模块 `Getopt::Long`、`File::Path` 和 `FindBin`
- 对应的 kverif 工具命令

## 复杂调用示例

```bash
export KVERIF_HOME=/home/host/kverif
export PATH="$KVERIF_HOME/tools:$PATH"

bash "$KVERIF_HOME/examples/secondary_development/sh/waveform_window.sh" \
  --fsdb /data/run/waves.fsdb \
  --daidir /data/run/simv.daidir \
  --signal tb.dut.valid \
  --signal tb.dut.ready \
  --begin 0ns --end 1us \
  --time 100ns --time 500ns \
  --active-signal tb.dut.ready --active-time 500ns \
  --max-rows 1000 --min-changes 1 --max-unknown 0 --require-complete \
  --out /data/run/kverif-wave

bash "$KVERIF_HOME/examples/secondary_development/sh/module_connectivity.sh" \
  --daidir /data/run/simv.daidir \
  --signal tb.dut.valid --signal tb.dut.ready \
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
  --fsdb /data/run/waves.fsdb \
  --signal tb.dut.valid \
  --begin 0ns --end 1us \
  --out /data/run/kverif-wave-perl
```

每个示例都支持用环境变量覆盖工具绝对路径：

```bash
export KDEBUG_BIN=/opt/kverif/tools/kdebug
export KCOV_BIN=/opt/kverif/tools/kcov
export KVERIF_JSON_PYTHON=/usr/bin/python3
```

完整跨工具分诊：

```bash
bash "$KVERIF_HOME/examples/secondary_development/sh/regression_triage.sh" \
  --fsdb /data/run/waves.fsdb \
  --daidir /data/run/simv.daidir \
  --vdb /data/run/simv.vdb \
  --signal tb.dut.valid --signal tb.dut.ready \
  --begin 0ns --end 1us --time 100ns --time 500ns \
  --active-signal tb.dut.ready --active-time 500ns \
  --min-changes 1 --fail-under 95 --max-final-holes 100 \
  --out /data/run/kverif-triage
```

完整接口规则、错误处理、并发约束和 VM 命令见
[`../../doc/secondary_development_guide.md`](../../doc/secondary_development_guide.md)。
其中第 9 章逐项解释四个复杂工作流，第 10 章单列 `kdebug`、`kcov`、`kbit`、
`kentry`、`kloc`、`ksva`、`kberif`、`keda-runner` 和 loop client/server 的全部
公开参数、功能和逐子命令例子。
