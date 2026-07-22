# KDebug Repair Benchmark for XiangShan

This benchmark measures whether a model can debug and repair anonymous
XiangShan fail cases with and without the current kdebug tool.

v2 is designed to avoid the previous benchmark's main ambiguity: a
`with_kdebug` trial is valid only when an independent pre-trial KDebug
collection produces a machine-validated manifest. The complete gate is defined
in [`benchmark_evidence_gate.md`](benchmark_evidence_gate.md); pass rules depend
on whether the injected problem is RTL, environment, or mixed.

## 下一轮最低合格门禁

每个 case 必须先完成注错和原始失败运行，再由
`scripts/kdebug_evidence.py collect` 真实执行 `/home/host/kverif/tools/kdebug`。
所有 case 的 manifest 通过单 case 校验和 suite collection UUID 去重后，runner 才会查询 API
key 或启动模型。只有非空文件不再合格。

采集器会保存并校验：

- 当前 case 的 metadata、plan、fail logs 和 source request；
- 规范化后的实际 request、完整 command argv、raw stdout、stderr 和 parsed response；
- FSDB 全文件 SHA-256，或 daidir 的确定性全目录 SHA-256；
- KDebug wrapper、Tcl runtime、工具 Git commit、版本、时间戳和独立 collection UUID；
- parsed response 与 raw stdout、自定义 summary 与 invocation 的可复算一致性；
- evidence 与 fail log 的复制/高相似度，以及跨 case collection UUID 复用。

缺文件是 `TOOL_EVIDENCE_MISSING`；manifest 或任一来源检查失败是
`TOOL_EVIDENCE_INVALID`。两种状态都不计为模型失败，也不能证明 KDebug 有效。

## Strict Pass Rule

```text
A failing case counts as debug-pass only if the model modifies the required
repair-scope files, rebuilds, reruns the original failing workload, and the
judge observes PASS within 3600 seconds.
```

Bug-domain specific requirements:

- `rtl`: at least one RTL file must change.
- `env`: at least one environment/script/config/build file must change; an
  RTL-only workaround is a rule violation.
- `mixed`: both RTL and environment files must change.

## Scope

The benchmark covers four layers:

- `generated_wrapper`: generated RTL wrapper UT cases.
- `real_rtl_ut`: UT-style checks that still exercise real repair-scope RTL.
- `real_rtl_it`: integration checks for memory/peripheral subsystems.
- `fullchip`: full-chip XiangShan VCS cases.

Bug domains:

- `rtl`
- `env`
- `mixed`

The current case matrix includes:

- RTL protocol/data/control bugs: AXI, memory, peripheral, pipeline, control,
  LSU/cache, branch/redirect, cache/MMU.
- Environment bugs: dropped `+diff`/`REF_SO`, wrong case or seed dispatch,
  stale or unwritable `simv`/build output.
- Mixed bugs: RTL fault plus environment fault, requiring both sides to be
  repaired.

## Groups

Each case is run twice:

- `with_kdebug`: model may use kdebug Tcl/NPI/wave/query evidence, run logs,
  repair-scope files, and public metadata for that case.
- `without_kdebug`: model may use only the case fail logs, repair-scope files,
  build/run scripts, compiler diagnostics, and ordinary text search.

Both groups work only inside their own repair workdir.

`with_kdebug` is valid only when `evidence/with_kdebug/manifest.json` and every
declared output pass `kdebug_evidence.py`. Missing evidence is reported as
`TOOL_EVIDENCE_MISSING`; invalid or reused evidence is
`TOOL_EVIDENCE_INVALID`.

## Models

Every case is evaluated across three models:

```text
gpt-5.5
glm-4.7
qwen3.6-35b
```

All three models use OpenAI-compatible API endpoints. API keys must be supplied
at runtime through environment variables and must not be written into scripts,
reports, or logs:

```bash
export GPT55_BASE_URL=http://165.154.147.120:8080/v1
export GPT55_API_KEY=<provided key>
export MAAS_BASE_URL=https://maas-coding-api.cn-huabei-1.xf-yun.com/v2
export MAAS_API_KEY=<provided key>
```

Model ID mapping:

```text
gpt-5.5       -> gpt-5.5
glm-4.7       -> xopglmv47flash
qwen3.6-35b   -> xopqwen36v35b
```

## Directory Contract

Each benchmark instance must be writable by the ordinary VM user `host`. Use a
host-owned VM-native directory, for example:

```text
/home/host/kverif_runs/<suite>/
  public_manifest.csv
  case_001/
    case_meta.json
    fail/
      run.log
      run.rc
    rtl/
    scripts/
      build.sh
      run.sh
      judge.sh
    design_refs/
      public_design_intent.md
    env/
    config/
    filelists/
    evidence/
      kdebug_plan.json
      requests/
        failure_value.json
      with_kdebug/
        manifest.json
        manifest.sha256
        kdebug_failure_value.json
        _requests/
        _raw/
        _stderr/
  repair/
    gpt-5.5/with_kdebug/case_001/
    gpt-5.5/without_kdebug/case_001/
    glm-4.7/with_kdebug/case_001/
    qwen3.6-35b/without_kdebug/case_001/
```

Rules:

- Case names must be anonymous: `case_001`, `case_002`, ...
- RTL must not contain bug-revealing names or comments such as `fault`, `bug`,
  `inject`, `kverif_fault`, or the private scenario label.
- `answer_key_private.json` must exist only outside model-visible workdirs.
- The judge must run from the repair workdir and decide pass/fail from logs,
  not from the model's written claim.
- `scripts/judge.sh`, pass markers, fail logs, evidence, and `case_meta.json`
  are protected from model edits.
- Public RTL design intent belongs in read-only directories such as `docs/`,
  `design_docs/`, `design_refs/`, or `spec/`.  These files may explain the
  intended behavior of AXI, MMU, cache, LSU, branch redirect, pipeline control,
  and case-local harnesses, but must not contain injected fault locations,
  trigger thresholds, answer-key patches, or operator notes.
- Prefer per-case `public_design_refs` in `case_meta.json` so each UT/IT/full
  chip case receives only its relevant design documents.

## Case Metadata

`case_meta.json` controls the repair scope:

```json
{
  "bug_domain": "mixed",
  "public_design_refs": [
    "design_refs/common/rtl_debug_common.md",
    "design_refs/fullchip/branch_redirect/branch_redirect_fullchip_design.md"
  ],
  "repair_scope": {
    "allowed_roots": ["rtl", "scripts", "env", "config"],
    "requires_rtl_change": true,
    "requires_env_change": true,
    "forbidden_files": ["answer_key_private.json", "scripts/judge.sh"]
  },
  "tool_evidence": {
    "required_for_with_kdebug": true,
    "plan": "evidence/kdebug_plan.json",
    "expected_files": ["kdebug_failure_value.json"],
    "minimum_nonempty_files": 1
  }
}
```

Recommended public design reference layout:

```text
design_refs/
  common/rtl_debug_common.md
  ut/axi/axi_ut_design.md
  ut/cache/cache_ut_design.md
  ut/mmu/mmu_ut_design.md
  it/memory/memory_it_design.md
  it/peripheral/peripheral_it_design.md
  fullchip/pipeline/pipeline_fullchip_design.md
  fullchip/control/control_fullchip_design.md
  fullchip/lsu_cache/lsu_cache_fullchip_design.md
  fullchip/branch_redirect/branch_redirect_fullchip_design.md
  fullchip/memory_subsystem/memory_subsystem_fullchip_design.md
```

Examples:

- AXI UT: common + `design_refs/ut/axi/axi_ut_design.md`
- Cache UT: common + `design_refs/ut/cache/cache_ut_design.md`
- MMU UT: common + `design_refs/ut/mmu/mmu_ut_design.md`
- Memory IT: common + `design_refs/it/memory/memory_it_design.md`
- Peripheral IT: common + `design_refs/it/peripheral/peripheral_it_design.md`
- Full-chip branch case: common +
  `design_refs/fullchip/branch_redirect/branch_redirect_fullchip_design.md`
- Full-chip LSU/cache case: common +
  `design_refs/fullchip/lsu_cache/lsu_cache_fullchip_design.md`

## Benchmark Flow

The suite performs collection once per case before creating any model trial:

1. Execute every case's plan through real KDebug.
2. Validate each manifest and reject cross-case collection UUID reuse.
3. Copy the failing case into a model/group-specific repair workdir.
4. Revalidate evidence in the copied `with_kdebug` workdir before API lookup.
5. Give the model the group rules, repair workdir, case metadata, fail logs,
   and allowed files/evidence.
6. Start a 3600 second wall-clock repair timer.
7. The model returns an allowed unified diff.
8. The harness applies the diff and runs:
   - `scripts/build.sh`
   - `scripts/run.sh`
   - `scripts/judge.sh`
9. The model may iterate until pass or timeout.
10. Record locate time, edit time, build/run/judge time, iterations, tokens,
   modified RTL files, modified environment files, evidence availability,
   final status, and pass marker.

## Pass Markers

Generated RTL UVM:

```text
XS_BENCH_PASS case=<case-name>
UVM_ERROR :    0
ALL_PASS
```

Full-chip XiangShan:

```text
HIT GOOD TRAP
DIFFTEST WORKLOAD DONE
```

Some long workloads may also require:

```text
MicroBench PASS
```

## Scripts

```text
models.csv
case_matrix.csv
agent_rules_with_kdebug.md
agent_rules_without_kdebug.md
benchmark_protocol.md
benchmark_evidence_gate.md
metrics_schema.csv
fault_injection_guidelines.md
scripts/run_repair_trial.sh
scripts/run_matrix.sh
scripts/api_model_runner.py
scripts/kdebug_evidence.py
scripts/test_kdebug_evidence.py
scripts/collect_results.py
scripts/capture_terminal_screenshots.py
scripts/judge_uvm_generated.sh
scripts/judge_fullchip.sh
scripts/summarize_results.py
scripts/generate_word_reports.py
scripts/generate_fault_detail_docx.py
scripts/generate_design_docx.py
templates/case_meta.template.json
templates/kdebug_evidence_plan.template.json
templates/kdebug_request.value_at.template.json
templates/result_row.template.csv
templates/final_report_template.md
schemas/kdebug_evidence_plan.schema.json
schemas/kdebug_evidence_manifest.schema.json
```

The API runner:

- loads allowed roots/files from `case_meta.json`;
- sends only sanitized public metadata to the model prompt, not raw
  `case_meta.json` fields such as detailed `bug_class`, private evidence
  expectations, or answer-shaped labels;
- sends read-only public RTL design references from `docs/`, `design_docs/`,
  `design_refs/`, and `spec/` to both groups, so both with-tool and without-tool
  models have the same architectural/design-intent background;
- accepts unified diffs only inside the allowed repair scope;
- rejects protected files and private answer material;
- tracks RTL and environment changes separately;
- enforces required repair class after judge pass;
- validates KDebug evidence before API-key lookup and records
  `TOOL_EVIDENCE_MISSING` or `TOOL_EVIDENCE_INVALID` before any model call;
- returns `RETRY_LATER` with exit code 75 for API rate limits or temporary
  throttling; `run_matrix.sh` keeps the trial workdir, pauses that model for
  1800 seconds by default, continues other models, then retries the same
  model/group/case instead of counting it as a model failure.
- treats ordinary unfinished repair as `TIMEOUT` only after the one hour budget
  is exhausted. Intermediate no-patch, build, run, and judge failures are fed
  back into the next repair iteration.
- reports runner crashes, missing metrics, and non-recoverable environment
  issues as `INFRA_ERROR`, which makes the trial invalid rather than
  model-failed.

## Example Run

```bash
su - host

export MAAS_BASE_URL=https://maas-coding-api.cn-huabei-1.xf-yun.com/v2
export MAAS_API_KEY=<provided key>
export GPT55_BASE_URL=http://165.154.147.120:8080/v1
export GPT55_API_KEY=<provided key>
export KDEBUG_RATE_LIMIT_SLEEP_SEC=1800
export KDEBUG_BIN=/home/host/kverif/tools/kdebug
export KDEBUG_PYTHON=/usr/local/bin/python3.8
export KDEBUG_REPORT_PYTHON=/bin/python3

bash /home/host/kverif/benchmarks/kdebug_repair_benchmark/scripts/run_matrix.sh \
  --suite-root /home/host/kverif_runs/<suite> \
  --bench-root /home/host/kverif/benchmarks/kdebug_repair_benchmark \
  --timeout 3600 \
  --evidence-mode collect
```

只验证证据、不调用模型时：

```bash
/usr/local/bin/python3.8 /home/host/kverif/benchmarks/kdebug_repair_benchmark/scripts/kdebug_evidence.py \
  validate-suite \
  --suite-root /home/host/kverif_runs/<suite>
```

## Reports and Screenshots

Final reports must be Chinese Word documents (`.docx`), not only Markdown or
plain text.

For each model and each case/group trial, the report must include a terminal
screenshot showing debug/build/run/judge evidence.  When GUI capture is not
practical, `scripts/capture_terminal_screenshots.py` renders the actual trial
log tail into terminal-style PNG files. `run_matrix.sh` passes `--require-logs`;
if any log is absent, a diagnostic placeholder may be rendered but the final
delivery step fails and the placeholder cannot satisfy the screenshot gate.

Expected outputs:

```text
results.csv
summary.md
screenshots/
docx_out/gpt-5.5_benchmark_report.docx
docx_out/glm-4.7_benchmark_report.docx
docx_out/qwen3.6-35b_benchmark_report.docx
docx_out/three_model_summary_report.docx
```
