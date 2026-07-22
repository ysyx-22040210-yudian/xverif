# XiangShan KDebug Repair Benchmark v2 Report

## Scope

- Suite:
- Cases:
- Date:
- Host:
- XiangShan config:
- VCS version:

## Rules

- Each `(case, model, group)` trial has a 3600 second timeout.
- A trial passes only when the model modifies the required repair-scope files,
  rebuilds, reruns the original failing workload, and the judge returns pass.
- `with_kdebug` must have all plan-declared KDebug response files under
  `evidence/with_kdebug/` and a validated case-specific manifest; absent
  response files are `TOOL_EVIDENCE_MISSING`.
  A manifest, input, hash, invocation, raw-response, freshness, or uniqueness
  failure is `TOOL_EVIDENCE_INVALID`. Neither status is a model failure or a
  valid tool-group observation.
- `without_kdebug` may not use kdebug, FSDB, KDB, Verdi, NPI, Tcl queries, or
  cross-case majority diff.
- Private answer material is forbidden for both groups.

## Bug Domains

- RTL bug: requires RTL change.
- Environment bug: requires script/config/environment change; RTL-only pass is
  a rule violation.
- Mixed bug: requires both RTL and environment changes.

## Summary by Model and Group

| Model | Group | Trial | PASS | Unrepaired (= Timeout) | Evidence Missing | Rule Violation | Invalid/Infra | Effective Success Rate | Median Time To Pass | Median Tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gpt-5.5 | with_kdebug | 0 | 0 | 0 | 0 | 0 | 0 | 0% | 0 s | 0 |
| gpt-5.5 | without_kdebug | 0 | 0 | 0 | 0 | 0 | 0 | 0% | 0 s | 0 |

## Summary by Bug Domain

| Bug Domain | Model | Group | Trial | PASS | Success Rate | Notes |
|---|---|---|---:|---:|---:|---|
| rtl | TBD | TBD | 0 | 0 | 0% | TBD |
| env | TBD | TBD | 0 | 0 | 0% | TBD |
| mixed | TBD | TBD | 0 | 0 | 0% | TBD |

## Case Results

| Case | Bug Domain | Benchmark Layer | Subsystem | Model | with_kdebug | without_kdebug | Delta |
|---|---|---|---|---|---|---|---|
| case_001 | rtl | generated_wrapper | axi | gpt-5.5 | TBD | TBD | TBD |

## Evidence Quality

Describe whether each result was supported by:

- dynamic signal/time/driver evidence
- environment command/build/run audit
- failure log only
- static source suspicion
- final repair pass

## Notes

- Token counts must be labelled as actual or estimated.
- Long full-chip workloads should be reported separately if run time dominates.
- Rule violations and evidence-missing trials must be listed explicitly.
