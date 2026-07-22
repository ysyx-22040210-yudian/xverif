# Agent Rules: with_kdebug

You are debugging one anonymous XiangShan benchmark fail case with kdebug.

## Allowed

- Use only the current case's plan-declared, manifest-validated KDebug response
  files from `evidence/with_kdebug/`.
- Use the current case's fail logs, build/run logs, case metadata, and files
  inside the repair scope declared by `case_meta.json`.
- Use read-only public RTL design references under `docs/`, `design_docs/`,
  `design_refs/`, or `spec/`.  These describe intended behavior and are visible
  to both tool and no-tool groups.
- Edit only allowed repair-scope files inside the assigned repair workdir.
  Typical scopes are:
  - RTL case: `rtl/`
  - environment case: `scripts/`, `env/`, `config/`, `filelists/`, selected
    build/run files
  - mixed case: both RTL and environment scope
- Rebuild and rerun the original failing workload as many times as needed,
  within the 3600 second timeout.

## Required kdebug Evidence

`with_kdebug` is valid only after an independent pre-trial collector has really
executed KDebug for this case and `kdebug_evidence.py` has validated its
manifest. The runner performs that check before the model API call. Missing
evidence is `TOOL_EVIDENCE_MISSING`; a bad manifest, stale input, changed tool,
copied fail log, inconsistent raw stdout/response, or reused collection UUID is
`TOOL_EVIDENCE_INVALID`. Do not claim a tool-assisted result in either state.

Manifest internals, raw stdout, stderr, collector bookkeeping, and other cases'
collections are not model evidence. The model-visible evidence is limited to
the response files declared by this case's collection plan.

When using kdebug, explain the concrete evidence you relied on, for example:

- first divergent signal/time window
- failing transaction ID, beat, mask, PC, redirect, or commit event
- run/build command audit for environment bugs
- relation between tool evidence and the patch

Do not treat the existence of a valid manifest as proof that KDebug helped.
Name the exact case-local signal, time, transaction, driver, or command fact
that affected the diagnosis so the post-run audit can compare it with the
patch and judge result.

## Forbidden

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
