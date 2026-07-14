# xcov

`xcov` is an AI/MCP-oriented query engine for VCS/Verdi coverage databases.
Human users can call it with parameter-style subcommands such as
`cov-holes`, `cov-summary`, `scope-children`, and `source-map`. The JSON
`xcov.v1` request protocol remains available for scripts, MCP, stdio-loop,
schema tests, and reproducible bug reports. Compact `xout` is the default;
use `--json` for machine JSON responses.

xcov follows the same stateful split as xdebug: `tools/xcov --stdio-loop`
hosts the real coverage database session. Python owns the JSON protocol,
filtering, caching, export, and MCP-facing lifecycle; direct VDB/NPI traversal
is delegated to `xcov/tcl_engine/xcov_npi.tcl` running inside Verdi batch Tcl.
`xverif_mcp` only starts/stops the loop process, keeps alias/default mappings,
forwards JSON requests, and handles direct/LSF launcher cleanup.

## Quick Start

One-shot parameter CLI:

```bash
tools/xcov cov-holes --vdb fake --fake --metrics toggle,branch --max-items 3
tools/xcov cov-holes --vdb fake --fake --metrics toggle,branch --max-items 3 --json
tools/xcov cov-summary --vdb /path/to/simv.vdb --metrics line,toggle,branch
tools/xcov source-map --vdb /path/to/simv.vdb --file rtl/ctrl.sv --line 88 --window 5
```

Reusable session CLI:

```bash
tools/xcov open --vdb /path/to/simv.vdb --name cov0
tools/xcov tests --session cov0
tools/xcov metrics --session cov0 --scope top.u_dut
tools/xcov cov-holes --session cov0 --metrics branch,condition --include "*ctrl*" --max-items 20
tools/xcov close --session cov0
```

JSON protocol remains supported:

```bash
printf '%s\n' '{"api_version":"xcov.v1","action":"session.open","target":{"vdb":"fake"},"args":{"name":"cov0","fake":true}}' \
  | tools/xcov --json -
```

Loop mode for MCP:

```bash
tools/xcov --stdio-loop
```

The loop emits a JSON ready line with `protocol:"xcov-stdio-loop"` and then
JSONL envelopes containing `xout` and `json` payloads. NPI diagnostic output is
routed to stderr so stdout remains machine-readable.

## Real Tcl NPI Smoke

The verified runtime shape is:

```text
Python 3.11
verdi -batch -nologo -play xcov/tcl_engine/xcov_npi.tcl
```

Verified database shape:

```text
<project>/sim/merged.vdb
```

Observed smoke results:

```text
session.open: ok, test_count=1, top_scope_count=null (lazy; scope actions scan hierarchy)
tests.list: ok, matched_count=1
metrics.list: ok, matched_count=4
scope.summary: ok, matched_count=1 for uart_tb
scope.children: ok, direct children returned with limits
export.scope_tree: ok, writes .xverif/xcov_exports/<name>
cov.holes: ok with metric/limit filtering
```

Real Tcl NPI commands need access to Verdi/VCS coverage libraries and the local
Synopsys license server. In sandboxed execution, run them outside the sandbox.
Do not add another direct NPI implementation path; keep direct coverage NPI
calls in `tcl_engine/xcov_npi.tcl`.

## Timeout Policy

Real coverage traversal can take a long time on large VDBs or Verdi 2018.
xcov therefore waits indefinitely by default for the Tcl NPI process, session
startup, and coverage queries. Unset values, zero, and negative values mean
"no timeout". A positive value opts back into a finite limit:

```bash
# Explicitly unlimited (also the default)
export XVERIF_XCOV_TCL_TIMEOUT_SEC=0
export XVERIF_XCOV_STARTUP_TIMEOUT_SEC=0
export XVERIF_XCOV_REQUEST_TIMEOUT_SEC=0

# Optional CI protection
export XVERIF_XCOV_TCL_TIMEOUT_SEC=600
export XVERIF_XCOV_STARTUP_TIMEOUT_SEC=600
export XVERIF_XCOV_REQUEST_TIMEOUT_SEC=900
```

`xverif-loop-client` also defaults `cov.*` methods to unlimited socket wait.
Use `--timeout-sec 0` to request that behavior explicitly, or a positive value
to bound one client call. xdebug keeps its existing defaults. Session close and
process cleanup remain bounded so interrupted jobs do not leave child tools
running.

## MCP Tools

`xverif_mcp` exposes xcov as a stateful backend:

```text
xverif_cov_session_open
xverif_cov_session_list
xverif_cov_session_use
xverif_cov_session_close
xverif_cov_query
xverif_cov_raw_request
xverif_cov_list_actions
xverif_cov_get_schema
```

Use `XVERIF_MCP_ENABLE_COV=0` to hide coverage tools. `XVERIF_XCOV_BIN` and
`XVERIF_XCOV_PYTHON` override the xcov executable and Python runtime.

MCP `xverif_cov_query` accepts `limits` and `output` as top-level tool
arguments. xcov merges those into action args unless `args.limits` or
`args.output` is already set; action-local args win.

`xverif_cov_get_schema` returns action-specific request/response schemas for
all current P0 actions. The schema is meant for agent/tool guidance; runtime
validation still uses xcov's explicit checks.

## Logs

xcov writes diagnostic logs without touching stdout protocol output:

```text
~/.xverif/xcov/sessions/<session_id>/session.json
~/.xverif/xcov/sessions/<session_id>/logs/actions.ndjson
~/.xverif/xcov/backend/sessions/<session_id>/logs/lifecycle.ndjson
~/.xverif/xcov/backend/sessions/<session_id>/logs/transport.ndjson
```

Use `XVERIF_XCOV_LOG_DIR` to override the log root. Use
`XVERIF_XCOV_LOG=0` to disable logging. Log events follow the xdebug-style
fields `ts/event_id/pid/layer/component/session_id/action/phase/ok/context`
and omit large coverage payloads such as full `items` arrays.

## Scope Semantics

- `scope.summary(scope="top.u_dut")` returns one aggregate row for that scope.
- `scope.summary` without `scope` returns aggregate rows for top scopes.
- `scope.children(scope="top.u_dut")` returns direct children only.
- `scope.children(..., recursive=true)` returns descendants.
- `scope.search` only searches scope names/paths and does not attach coverage
  aggregation fields.
- `export.scope_tree` exports scope rows enriched with coverage totals and
  per-metric summaries.

Session open/status/close are lightweight: they do not recursively scan the
whole VDB. Recursive scope/item traversal is triggered by coverage actions such
as `scope.children`, `scope.summary`, `export.scope_tree`, and `cov.holes`.

## Coverage Evidence Fields

Coverage item rows always keep the common fields
`metric/type/name/full_name/covered/coverable/missing/count/status/evidence`.
For code coverage bins that do not carry their own source location, xcov
inherits `evidence.file/line` from the nearest parent coverage object and adds
`evidence_source.*` fields to show where that location came from.

Additional code coverage detail fields:

- Toggle holes use `toggle_signal`, `toggle_bit`, and `toggle_transition` to
  identify the uncovered signal, bit, and transition direction.
- Condition holes use `condition`, `condition_bin`, and, when NPI exposes it,
  `condition_terms` to identify the expression, uncovered truth-value
  combination, and term order.
- Branch holes use `branch`, `branch_bin`, and, when NPI exposes it,
  `branch_terms` to identify the branch object/expression and uncovered arm.

Functional bin rows use `covergroup`, `coverpoint` or `cross`, and `bin`.
For cross bins, a value like `bin=[write|err]` means one uncovered cross
combination, not two independent bins.

## Export Safety

For MCP safety, relative `output.path` values are written under
`.xverif/xcov_exports/`. Paths containing `..` are rejected. Absolute paths are
rejected unless `output.allow_absolute_path=true` is set explicitly.

## Current Limits

- `test="each"` is not implemented; use `test="merged"` or a concrete test name.
- `cov.object.get` is an exact lookup with optional `include_children` and
  `max_children`; it is not a general object index yet.
- `functional.summary` and `functional.holes` support
  `levels=["covergroup","coverpoint","cross","bin"]`.

## Python Extension SDK

See [`../xverif_sdk/README.md`](../xverif_sdk/README.md) for the public
`XcovClient`, stdio transport, and the multi-VDB coverage convergence example.
Downstream scripts should use that JSON API instead of importing xcov backend
internals or calling NPI directly.
