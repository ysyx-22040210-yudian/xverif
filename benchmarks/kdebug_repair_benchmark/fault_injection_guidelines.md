# Fault Injection Guidelines v2

## Naming and Leakage Rules

Use anonymous case directories:

```text
case_001
case_002
case_003
```

Do not put the bug class in:

- directory names
- file names
- comments
- signal names
- localparam names
- scripts visible to the model

Forbidden visible strings include:

```text
kverif_fault
fault
bug
inject
answer
late_pipeline
branch_redirect
rfWen_force0
```

The private answer key may use descriptive labels, but it must live outside the
model-visible case and repair directories.

## Bug Domains

### RTL bug

The injected fault is in RTL.  The correct repair must modify `rtl/`.

Examples:

- AXI AW/W/B response pairing error
- burst length or last-beat error
- memory address, mask, or data beat corruption
- peripheral decode or response ordering error
- late pipeline bug after thousands of cycles
- valid/ready/rfWen/flush control corruption
- LSU/cache address, mask, data beat, or response order error
- branch/redirect PC error
- cache/MMU/refill/permission interaction error

### Environment bug

The injected fault is in the build/run/test environment.  The correct repair
must modify scripts or configuration, not RTL.

Examples:

- `scripts/run.sh` drops `+diff` or uses the wrong `REF_SO`.
- UVM run dispatch selects the wrong case or seed.
- build/run path uses stale `simv` or an unwritable output directory.
- generated filelist order is wrong.
- executable bit is missing on `simv` or helper scripts.
- run timeout is too short for the selected workload.
- required plusarg or environment variable is missing.

### Mixed bug

The case has both RTL and environment faults.  The correct repair must change
both RTL and environment files.

Examples:

- memory mask/data beat RTL error plus run/judge log path mismatch
- branch/redirect RTL error plus wrong `REF_SO` or missing run option
- LSU/cache RTL error plus timeout/workload configuration error
- stale build cache masking an RTL fix

## Generated UVM UT/IT Faults

Use generated wrapper cases only for protocol or generated harness coverage.
Do not present generated wrapper results as evidence of full-chip debug ability.

Suggested target cases:

```text
ut_axi_burst_outstanding
ut_axi_error_backpressure
it_memory_mixed_burst
it_peripheral_mmio_storm
it_peripheral_error_interrupt
```

The repair judge should use:

```bash
kdebug_repair_benchmark/scripts/judge_uvm_generated.sh run/run.log <case_name>
```

## Real RTL and Full-Chip Faults

Use VM-native XiangShan build artifacts under:

```text
/root/XiangShan-build
```

Do not build full-chip XiangShan under VMware shared folders.

Suggested workloads:

```text
flash_recursion_test.bin
microbench.bin
```

Use `microbench.bin` only when the host can finish within the 3600 second
per-trial timeout.

The repair judge should use:

```bash
kdebug_repair_benchmark/scripts/judge_fullchip.sh run/run.log 0
```

For MicroBench:

```bash
kdebug_repair_benchmark/scripts/judge_fullchip.sh run/run.log 1
```

## Tool Evidence Requirements

After injection and the original failing run, give every case its own plan and
real KDebug inputs:

```text
evidence/kdebug_plan.json
evidence/requests/*.json
inputs/waves.fsdb and/or inputs/simv.daidir/
```

Run `scripts/kdebug_evidence.py collect` separately for every case. Only the
collector may create `evidence/with_kdebug/`. The matrix must stop before model
scheduling unless all selected manifests and collection UUIDs pass
`validate-suite`. See
[`benchmark_evidence_gate.md`](benchmark_evidence_gate.md).

Recommended evidence by bug class:

- RTL data/control bug: first bad signal window, driver chain, mismatch summary
- late pipeline bug: commit/writeback window around first divergence
- branch/redirect bug: redirect producer, frontend target, commit PC
- LSU/cache bug: request address/mask, source ID, beat, response data
- environment bug: a KDebug observation tied to the actual failed runtime,
  plus ordinary command/filelist/build fingerprints available equally to both
  groups; do not relabel copied run logs as KDebug output
- mixed bug: separate plan requests covering the observable RTL symptom and
  the actual failed runtime where KDebug can observe it

If declared evidence is absent, `with_kdebug` is
`TOOL_EVIDENCE_MISSING`. If the manifest, current input, runtime hash,
invocation, raw stdout, parsed response, freshness, or case uniqueness check
fails, it is `TOOL_EVIDENCE_INVALID`. Neither is a valid model outcome.

## Repair Directory Safety

Each repair copy must be independent.  If hard links are used to save disk, the
trial wrapper must replace mutable trees with private copies:

```text
rtl/
scripts/
env/
config/
filelists/
tb/
cases/
out/
run/
simv*
```

Edited files should not have a link count greater than 1.

## Private Answer Key

Keep a private file outside model-visible paths, for example:

```text
/home/host/kverif_runs/<suite>/answer_key_private.json
```

It may contain:

- case id
- hidden bug class
- injected file/line
- injected expression
- expected fix
- expected fail marker
- expected kdebug evidence files
- expected RTL/environment repair class

The model must never read this file during benchmark trials.
