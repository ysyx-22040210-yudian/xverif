# Benchmark Protocol v2

## Objective

Compare model debug-and-repair performance on anonymous XiangShan benchmark
fail cases in two modes:

- `with_kdebug`
- `without_kdebug`

Each mode is tested across three models:

- `gpt-5.5`
- `glm-4.7`
- `qwen3.6-35b`

The measured task is complete repair closure: locate the root cause, modify the
allowed repair-scope files, rebuild, rerun the original failing workload, and
pass the judge within one hour.

## What Changed in v2

v2 fixes the previous benchmark's weak points:

- Every case must execute KDebug in an independent pre-trial collection step.
  A nonempty file alone is not evidence.
- `with_kdebug` requires a valid `kdebug-evidence-manifest.v1` under
  `evidence/with_kdebug/`. Missing evidence is `TOOL_EVIDENCE_MISSING`;
  provenance, hash, input, invocation, response, freshness, or uniqueness
  failures are `TOOL_EVIDENCE_INVALID`.
- Cases are tagged by bug domain:
  - `rtl`
  - `env`
  - `mixed`
- Pass validation depends on the bug domain:
  - `rtl`: requires RTL change.
  - `env`: requires environment/script/config change; RTL-only workarounds are
    rule violations.
  - `mixed`: requires both RTL and environment changes.
- Reports are grouped by `bug_domain` and `benchmark_layer`, so generated
  wrapper results cannot hide real RTL or environment results.

## Mandatory Pre-Trial KDebug Gate

The normative Chinese specification, complete directory example, JSON request,
manifest fields, rejection rules, and commands are in
[`benchmark_evidence_gate.md`](benchmark_evidence_gate.md).

The required order is:

1. Inject the case-local fault.
2. Run the original failing workload and finalize `case_meta.json` and
   `fail/*.log`.
3. Execute every case's declared KDebug requests independently with
   `scripts/kdebug_evidence.py collect`.
4. Rehash and validate every case, then run `validate-suite` to reject a reused
   collection UUID.
5. Only after the suite gate passes may any model API call start.

Collection must directly target the current case's FSDB and/or daidir. The
collector preserves the source request, canonical request, raw stdout, stderr,
parsed response, input fingerprints, KDebug runtime hashes, timestamps, and
command argv. It also proves that the parsed response is the response contained
in raw KDebug stdout. Evidence copied from `fail/run.log`, inherited from
another case, or assembled without a self-consistent invocation is invalid.

## Hard Timeout

Each `(model_id, case_id, group)` trial has a hard wall-clock timeout:

```text
3600 seconds
```

The timeout includes evidence reading, localization, edits, build, run, judge,
and all iterations.  The model may continue repairing and rerunning until the
judge passes or the 3600 second wall-clock budget is exhausted.  Intermediate
no-patch, invalid-patch, build-fail, run-fail, and judge-fail outcomes are
feedback for the next repair iteration, not final trial failures.

## Case Preparation

Every case must have:

```text
case_<NNN>/
  case_meta.json
  fail/run.log
  fail/run.rc
  rtl/                  # present for rtl and mixed cases
  scripts/build.sh
  scripts/run.sh
  scripts/judge.sh      # protected; not repairable by the model
  design_refs/           # optional read-only public RTL design intent
  inputs/                 # current FSDB and/or daidir, or references to them
  evidence/
    kdebug_plan.json
    requests/
      <request>.json
    with_kdebug/          # collector-generated only
      manifest.json
      manifest.sha256
      <validated-response>.json
      _requests/
      _raw/
      _stderr/
```

Environment and mixed cases may additionally have:

```text
  env/
  config/
  filelists/
  tb/
  cases/
  Makefile
  filelist.f
  vcs_args.f
  run_args.txt
```

`case_meta.json` must define `repair_scope`, including allowed roots/files and
whether RTL and environment changes are required.

## Public RTL Design References

Models need normal design intent to make a correct repair.  Each suite may
include read-only public design references under:

```text
docs/
design_docs/
design_refs/
spec/
```

These files are visible to both `with_kdebug` and `without_kdebug` groups.  They
may describe:

- intended AXI ready/valid/ID/beat/response behavior
- memory mask/data beat/address semantics
- MMU/TLB/PTW/cache/refill behavior
- LSU load/store/replay/response ordering
- branch/redirect/PC update behavior
- pipeline valid/ready/flush/writeback control
- case-local build/run harness architecture

They must not contain:

- injected fault locations or line numbers
- hidden trigger thresholds
- answer-key patches
- operator-only notes
- kdebug-only dynamic evidence
- strings such as `answer_key`, `private`, `fault_injection`, or
  `operator_only`

The value of kdebug should come from dynamic localization and signal causality,
not from giving only one group the RTL design specification.

Design references should be split by verification scope.  Do not feed every RTL
design document to every case; each case should receive only common references
plus the relevant UT/IT/full-chip subsystem document.  The recommended layout is:

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

Each `case_meta.json` should explicitly list `public_design_refs`, for example:

```json
{
  "public_design_refs": [
    "design_refs/common/rtl_debug_common.md",
    "design_refs/fullchip/lsu_cache/lsu_cache_fullchip_design.md"
  ]
}
```

If `public_design_refs` is absent, the runner falls back to a conservative
lookup under `common`, `benchmark_layer`, `level`, and `subsystem` directories.
Explicit per-case references are preferred for reproducibility.

The model-visible case directory must not include:

- private answer key
- bug label in directory/file names
- injected-bug comments
- suspicious marker names such as `kverif_fault`, `bug`, `fault`, `inject`,
  or `answer`

## Repair Workdir

For each model and group:

```text
repair/<model_id>/<group>/<case_id>/
```

The workdir is copied from the public failing case.  Mutable trees such as
`rtl/`, `scripts/`, `env/`, `config/`, `filelists/`, `tb/`, `cases/`, `out/`,
and `simv` artifacts must be private copies, not shared hardlinks.

## Trial Procedure

1. Select the suite cases and independently collect KDebug evidence for each
   case after its failing run is finalized.
2. Run suite-wide manifest validation before model scheduling.
3. Select `(model_id, case_id, group)` and create the repair workdir.
4. For `with_kdebug`, revalidate the copied manifest and all current inputs
   before API-key lookup or any model call.
5. Start the model's 3600 second repair timer.
6. Give the model the group rules, repair workdir, sanitized case metadata,
   public RTL design references, fail logs, and allowed files/evidence.
7. The runner sends only sanitized public metadata to the model. Raw
   `case_meta.json` fields that can reveal the answer, such as detailed
   `bug_class`, private evidence expectations, and operator notes, must not be
   included in the model prompt.
8. For `with_kdebug`, every proposed diff must cite one plan-declared response
   and a concrete observed fact using
   `KDEBUG_EVIDENCE_USED: <file> | <fact>`. The harness rejects uncited,
   undeclared, or generic citations before applying the patch.
9. The model proposes an allowed-scope unified diff.
10. The harness applies the diff, then runs:
   - `scripts/build.sh`
   - `scripts/run.sh`
   - `scripts/judge.sh`
11. If judge fails and time remains, the model may iterate.
12. Stop when judge passes or timeout expires. If the workload passes but the
    required RTL/environment repair-scope rule is not satisfied, feed that rule
    violation back to the model and continue repairing within the same timeout.
13. Record metrics, manifest identity, accepted evidence citations, and
    terminal screenshot evidence.

## Judgement

`PASS` requires all of:

- required file class changed according to `bug_domain`
- build command exited 0 after the final change
- original failing workload or UVM case was rerun
- judge command exited 0
- pass occurred within 3600 seconds

Ordinary model failure is reserved for `TIMEOUT`: the one hour budget elapsed
before the case passed.  Other non-pass terminal conditions are invalid or
infrastructure outcomes, not model debug failures.  For ordinary repair
attempts, the model must be allowed to keep repairing until pass or timeout.

The following are intermediate repair feedback classes and must not terminate a
trial by themselves:

- only localization, no repair
- repair claim without rerun
- no effective patch
- build failure
- run failure
- judge failure
- recoverable API/model failure

Special statuses:

- `TIMEOUT`: 3600 seconds elapsed before pass.  In normal repair-loop runs this
  is the expected final failure status for an unfixed case.
- `TOOL_EVIDENCE_MISSING`: with_kdebug trial lacked required tool evidence.
- `TOOL_EVIDENCE_INVALID`: the manifest or its case/tool/input/request/stdout/
  response/hash/freshness/uniqueness checks failed. It is an invalid trial, not
  a model failure.
- `RULE_VIOLATION`: model changed protected files, used wrong repair class, or
  otherwise violated benchmark rules.
- `INFRA_ERROR`: runner crash, missing metrics, wrapper inconsistency, or other
  environment failure that makes the trial invalid rather than model-failed.
- `RETRY_LATER`: API rate limit or temporary throttle.  This is a scheduling
  pause, not a model failure.  The trial workdir is kept, no final result is
  appended, and `run_matrix.sh` pauses that model for 1800 seconds while
  continuing other models.  When the pause expires, it retries the same
  `(model, group, case)`.

## Metrics

Required fields are defined in `metrics_schema.csv`.

Important derived metrics:

- success rate per model/group
- success rate split by `bug_domain`
- success rate split by `benchmark_layer`
- median locate time and time-to-pass
- build/run time
- iteration count
- token usage
- repair class: `rtl_only`, `env_only`, `mixed`, `no_effective_patch`
- failure class: final or latest diagnostic class, such as `infrastructure_error`,
  `invalid_patch`, `build_fail`, `run_fail`, `judge_fail`, `timeout`,
  `evidence_missing`, `evidence_invalid`, `rule_violation`,
  `api_rate_limited`, `no_patch`.
  These classes explain why an unfinished trial failed to pass; they are not
  separate early-stop conditions.
- evidence presence, validity, manifest path, collection UUID, and validator result

## Fairness Controls

- Same failing case and workload for both groups.
- Same failing case and workload for all three models.
- Same 3600 second budget.
- Same host and build options.
- Same pass/fail judge.
- No cross-case leakage.
- No private answer key.
- Case names are anonymous.
- The without-tool group receives only current-case logs and files.
- KDebug collection happens before model timing and is identical for every
  model assigned to the same case.
- The with-tool prompt receives only plan-declared validated response files;
  the without-tool prompt cannot read `evidence/`.

## Required Reports

Each suite should produce:

```text
results.csv
summary.md
screenshots/
docx_out/gpt-5.5_benchmark_report.docx
docx_out/glm-4.7_benchmark_report.docx
docx_out/qwen3.6-35b_benchmark_report.docx
docx_out/three_model_summary_report.docx
```

All reports must be Chinese Word documents.  Every per-case section must include
a terminal screenshot.  A result without screenshot evidence does not satisfy
the final delivery requirement even if the CSV row says PASS. A generated
"log unavailable" placeholder is diagnostic output, not screenshot evidence;
matrix generation uses `capture_terminal_screenshots.py --require-logs` and
must fail when any source trial log is missing.
