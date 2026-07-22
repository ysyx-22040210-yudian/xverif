# Public RTL Design Intent Template

This document is model-visible and read-only.  It should explain the correct
design behavior needed to repair the case.  It must not reveal injected fault
locations, trigger thresholds, private patches, or answer-key content.

## Scope

- Case id: `case_XXX`
- Subsystem:
- Benchmark layer:
- Target flow:

## Intended Behavior

Describe the normal behavior of the relevant RTL path.

Examples:

- AXI write response ID must correspond to the accepted write transaction.
- WLAST/RLAST must match the normalized burst length.
- Byte mask bits select the exact byte lanes to update.
- LSU load response data must correspond to the request address, mask, source,
  replay state, and refill beat.
- Branch redirect target must be computed from the branch/jump semantics and
  delivered consistently to frontend and commit checks.
- rfWen/valid/ready/flush must preserve pipeline control invariants across
  redirect and replay.

## Interfaces and Signals

List public signal groups and their meaning.  Avoid naming the injected signal
as "the bug"; describe the whole interface normally.

| Signal or Group | Direction | Meaning |
|---|---|---|
| example_valid | producer -> consumer | Valid handshake bit |
| example_ready | consumer -> producer | Ready handshake bit |

## Invariants

List properties that should hold in the clean design.

- Invariant 1:
- Invariant 2:
- Invariant 3:

## Expected Logs and Pass Criteria

Describe how the normal case passes.

- Build command:
- Run command:
- Judge command:
- Pass markers:

## Useful Debug Pointers

Give legitimate public debug guidance, not the answer.

- Which log sections are useful:
- Which classes of wave/query evidence are meaningful:
- Which module families are relevant:
- Which false leads are common:

## Forbidden Content

Do not include:

- injected file/line/expression
- exact trigger counter or hidden condition
- expected patch
- private answer-key fields
- kdebug-only evidence for without-tool group
- `answer_key`, `private`, `fault_injection`, or `operator_only` material
