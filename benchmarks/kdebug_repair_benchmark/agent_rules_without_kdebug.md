# Agent Rules: without_kdebug

You are debugging one anonymous XiangShan benchmark fail case without kdebug.

## Allowed

- Use only this case's fail logs, build/run logs, case metadata, and files
  inside the repair scope declared by `case_meta.json`.
- Use read-only public RTL design references under `docs/`, `design_docs/`,
  `design_refs/`, or `spec/`.  These describe intended behavior and are visible
  to both tool and no-tool groups.
- Use ordinary text tools such as `rg`, `sed`, `awk`, `git diff`, and compiler
  diagnostics inside the assigned repair workdir.
- Edit only allowed repair-scope files inside the assigned repair workdir.
  Typical scopes are:
  - RTL case: `rtl/`
  - environment case: `scripts/`, `env/`, `config/`, `filelists/`, selected
    build/run files
  - mixed case: both RTL and environment scope
- Rebuild and rerun the original failing workload as many times as needed,
  within the 3600 second timeout.

## Forbidden

- Do not use kdebug.
- Do not use FSDB, KDB, Verdi, waveform viewers, NPI, Tcl debug queries, or any
  dynamic driver/signal tracing tool.
- Do not read `answer_key_private.json`.
- Do not inspect other cases' RTL, logs, reports, compact evidence, or answer
  material.
- Do not perform cross-case majority diff.
- Do not edit the original failing case directory.
- Do not edit global XiangShan source or generated RTL outside the assigned
  repair workdir.
- Do not modify protected files such as `case_meta.json`, fail logs,
  `evidence/`, `agent_logs/`, pass markers, or `scripts/judge.sh`.
- Do not modify public design reference files under `docs/`, `design_docs/`,
  `design_refs/`, or `spec/`.

## Success Standard

The run is successful only if all conditions are true:

- The required repair class is satisfied:
  - RTL bug: at least one RTL file changed.
  - Environment bug: at least one environment/script/config/build file changed,
    and the pass was not achieved by an RTL-only workaround.
  - Mixed bug: both RTL and environment files changed.
- The case was rebuilt after the modification.
- The original failing workload was rerun.
- `scripts/judge.sh` returns 0.
- The whole debug-repair-rerun loop finishes within 3600 seconds.

If an attempt does not make the case pass, keep repairing in the next
iteration. Ordinary debug failures such as no patch, build failure, run
failure, or judge failure are feedback, not terminal benchmark results. The
only ordinary model failure is exhausting the 3600 second wall-clock budget
without making the original failing case pass.
