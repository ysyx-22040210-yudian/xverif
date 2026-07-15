"""kverif-mcp — unified MCP server for all kverif tools."""

import inspect
import json
import time
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from kverif_mcp.adapters.kdebug import KverifDebugAdapter
from kverif_mcp.adapters.kcov import KverifCoverageAdapter
from kverif_mcp.adapters.kbit import bit_conv, bit_eval, bit_slice, bit_check
from kverif_mcp.adapters.kentry import entry_decode, entry_explain, entry_validate
from kverif_mcp.adapters.kloc import loc_resolve, loc_context, loc_stats, loc_annotate
from kverif_mcp.adapters.kberif import (context_status, context_list_topics, context_brief,
                                         context_get, context_detail, context_validate,
                                         context_config_init, context_init, context_repair)
from kverif_mcp.adapters.ksva import sva_list, sva_scan, sva_parse, sva_explain
from kverif_mcp.errors import error_payload
from kverif_mcp.tool_policy import filtered_catalog, policy_summary, tool_enabled

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

INSTRUCTIONS = """
kverif-mcp — https://github.com/BLANK2077/kverif

Exposes deterministic local tools for chip verification debug agents.
The kdebug and kcov backends are stateful and may run locally or through LSF.
Other tools (kbit, kentry, kloc, kberif, ksva) are stateless CLI adapters.

Typical workflow:
1. Call kverif_tools to discover available tools.
2. For debug queries: kverif_debug_session_open → kverif_debug_query.
3. For coverage queries: kverif_cov_session_open → kverif_cov_query.
4. For stateless queries: call the tool directly (e.g., kverif_bit_eval).

If kverif_debug_query returns error.code=SESSION_LOST:
  - check error.terminal_source: "transport" means subprocess/LSF crash or timeout
  - if timeout: inform user of possible causes (large data, LSF queue delay)
    and let user decide — narrow query scope or increase timeout env vars
  - the MCP server has already cleaned up the subprocess/LSF job
  - the session mapping has been evicted
  - the agent must explicitly call kverif_debug_session_open before retrying
No automatic retry or reopen is performed by the server.

Batch execution (kverif_batch):
  Use kverif_batch when you need to run multiple tools in strict serial order,
  especially for stateful workflows like session.open → query → session.close.
  This avoids race conditions where a query might execute before the session is
  ready.

  IMPORTANT — nested args: tools like kverif_debug_query and kverif_cov_query
  have their own "args" parameter.  In a batch line, the outer "args" maps to
  the tool's MCP parameters, and the inner "args" maps to the action's arguments:
    {"tool":"kverif_debug_query","args":{"action":"value.at","args":{"signal":"top.clk","time":"10ns"}}}

  Step 1 — write the batch file (bash inline):
    cat > /tmp/batch.ndjson << 'EOF'
    {"tool": "kverif_cov_session_open", "args": {"name": "s0", "vdb": "/path/to/merged.vdb"}}
    {"tool": "kverif_cov_query", "args": {"session": "s0", "action": "cov.holes", "args": {"metrics": ["line"], "limits": {"max_items": 5}}, "output_format": "json"}}
    {"tool": "kverif_cov_session_close", "args": {"name": "s0"}}
    EOF

  Or Python inline:
    import json
    reqs = [
        {"tool": "kverif_cov_session_open", "args": {"name": "s0", "vdb": "/path/to/merged.vdb"}},
        {"tool": "kverif_cov_query", "args": {"session": "s0", "action": "cov.holes", "args": {"metrics": ["line"], "limits": {"max_items": 5}}, "output_format": "json"}},
        {"tool": "kverif_cov_session_close", "args": {"name": "s0"}},
    ]
    with open("/tmp/batch.ndjson", "w") as f:
        for r in reqs: f.write(json.dumps(r) + "\\n")

  Step 2 — call kverif_batch(batch_file="/tmp/batch.ndjson", output_file="/tmp/batch_results.ndjson").
  Returns {total, ok_count, failed_count, output_file}.

  Step 3 — read results (Python inline):
    import json
    with open("/tmp/batch_results.ndjson") as f:
        for line in f:
            r = json.loads(line)
            # r["tool"], r["ok"], r["elapsed_ms"], r["error"]
  Format errors (invalid JSON, missing tool field) appear as tool=null with ok=false.

Output format: all tools default to output_format="kout" (compact AI-readable
structured text, saves tokens vs JSON). Use output_format="json" only when you
need structured data for programmatic analysis.
"""

mcp = FastMCP(
    name="kverif",
    instructions=INSTRUCTIONS,
)

debug = KverifDebugAdapter()
cov = KverifCoverageAdapter()


def _tool_error(code: str, message: str) -> dict:
    return error_payload(code, message)


def _write_output(result: Any, path: str, append: bool) -> None:
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        if isinstance(result, str):
            f.write(result)
        else:
            f.write(str(result))


def _wrap_with_output(fn):
    """Wrap a tool function so it accepts ``kverif_output_path`` and
    ``kverif_output_append`` keyword arguments.  When *output_path* is
    given the raw return value is also written to that file."""
    sig = inspect.signature(fn)
    new_params = list(sig.parameters.values()) + [
        inspect.Parameter("kverif_output_path", inspect.Parameter.KEYWORD_ONLY,
                          default=None),
        inspect.Parameter("kverif_output_append", inspect.Parameter.KEYWORD_ONLY,
                          default=False),
    ]
    new_sig = sig.replace(parameters=new_params)

    if inspect.iscoroutinefunction(fn):
        async def wrapper(*args, **kwargs):
            output_path = kwargs.pop("kverif_output_path", None)
            output_append = kwargs.pop("kverif_output_append", False)
            result = await fn(*args, **kwargs)
            if output_path:
                try:
                    _write_output(result, output_path, output_append)
                except Exception:
                    pass
            return result
    else:
        def wrapper(*args, **kwargs):
            output_path = kwargs.pop("kverif_output_path", None)
            output_append = kwargs.pop("kverif_output_append", False)
            result = fn(*args, **kwargs)
            if output_path:
                try:
                    _write_output(result, output_path, output_append)
                except Exception:
                    pass
            return result

    wrapper.__signature__ = new_sig
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.__annotations__ = {}
    return wrapper


def kverif_tool(group: str, write: bool = False):
    """Conditionally register a FastMCP tool according to env policy."""
    def decorator(fn):
        fn = _wrap_with_output(fn)
        if tool_enabled(group, write=write):
            return mcp.tool()(fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


@kverif_tool("common")
def kverif_ping() -> str:
    """Ping the kverif MCP server. Use this to check whether the server is alive."""
    return debug.ping()


def _append_result(output_file: str, tool: str | None, ok: bool,
                   error: str | None, elapsed_ms: int,
                   response: str | None = None) -> None:
    entry: dict = {
        "tool": tool,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }
    if response is not None:
        entry["response"] = response
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


async def _execute_one(name: str, args: dict) -> tuple[bool, str | None, int, str | None]:
    t0 = time.monotonic()
    try:
        result = await mcp.call_tool(name, args)
        content = result[0] if isinstance(result, tuple) else result
        text = content[0].text if content else ""
        try:
            j = json.loads(text)
            return j.get("ok", False), None, int((time.monotonic() - t0) * 1000), text
        except (json.JSONDecodeError, AttributeError):
            ok = ("pong" in str(text).lower()
                  or "KOUT_BEGIN" in text
                  or (text.startswith("@") and ".error." not in text))
            return ok, None, int((time.monotonic() - t0) * 1000), text
    except Exception as e:
        return False, str(e), int((time.monotonic() - t0) * 1000), None


@kverif_tool("common")
async def kverif_batch(batch_file: str, output_file: str) -> dict:
    """Execute multiple MCP tool requests from an NDJSON batch file serially.

    Each line is a JSON object with ``tool`` (tool name) and ``args``
    (arguments dict passed to that tool).  Results are written to
    ``output_file`` as NDJSON, one line per request (including parse errors).

    For tools that have their own nested ``args`` parameter (e.g.
    kverif_debug_query, kverif_cov_query), the inner args must be nested:
    ``{"tool":"kverif_debug_query","args":{"action":"value.at","args":{"signal":"top.clk","time":"10ns"}}}``

    Returns ``{total, ok_count, failed_count, output_file}``.
    """
    stats = {"total": 0, "ok": 0, "failed": 0}

    try:
        with open(batch_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    req = json.loads(line)
                except json.JSONDecodeError as e:
                    _append_result(output_file, None, False,
                                   f"INVALID_JSON: {e}", 0)
                    stats["failed"] += 1
                    stats["total"] += 1
                    continue

                tool_name = req.get("tool")
                if not tool_name:
                    _append_result(output_file, None, False,
                                   "MISSING_TOOL_FIELD", 0)
                    stats["failed"] += 1
                    stats["total"] += 1
                    continue

                tool_args = req.get("args", {})
                if not isinstance(tool_args, dict):
                    tool_args = {}

                ok, error, elapsed_ms, response = await _execute_one(tool_name, tool_args)
                _append_result(output_file, tool_name, ok, error, elapsed_ms, response)
                if ok:
                    stats["ok"] += 1
                else:
                    stats["failed"] += 1
                stats["total"] += 1
    except FileNotFoundError:
        return _tool_error("FILE_NOT_FOUND",
                           f"batch file not found: {batch_file}")
    except Exception as e:
        return _tool_error("BATCH_FAILED", str(e))

    return {
        "ok": True,
        "total": stats["total"],
        "ok_count": stats["ok"],
        "failed_count": stats["failed"],
        "output_file": output_file,
    }


# ---------------------------------------------------------------------------
# Debug tools (kdebug)
# ---------------------------------------------------------------------------


@kverif_tool("debug")
def kverif_debug_list_actions() -> dict:
    """Return the kdebug action catalog.

    Call this before kverif_debug_query when you are unsure which action to use.
    Returns the list of all available kdebug actions with brief descriptions.
    """
    return debug.actions()


@kverif_tool("debug")
def kverif_debug_get_schema(action: str, kind: str = "request") -> dict:
    """Return an action-specific kdebug JSON schema.

    Args:
        action: The kdebug action name (e.g. "value.at", "trace.drivers").
        kind: "request" for input schema, "response" for output schema.
    """
    if kind not in ("request", "response"):
        return _tool_error("INVALID_ARGUMENT", "kind must be 'request' or 'response'")
    return debug.schema(action, kind)


@kverif_tool("debug")
def kverif_debug_raw_request(request: dict, output_format: str = "kout") -> dict:
    """Run a complete kdebug JSON request (one-shot, no session).

    This tool does NOT use sessions. For session-based queries, use
    kverif_debug_query instead.

    Args:
        request: A full kdebug JSON request object with api_version, action, args, etc.
        output_format: "json" (default), "kout", or "envelope".
    """
    if not isinstance(request, dict):
        return _tool_error("INVALID_ARGUMENT", "request must be a JSON object")
    return debug.request(request, output_format)


@kverif_tool("debug")
def kverif_debug_session_open(
    name: str,
    daidir: Optional[str] = None,
    fsdb: Optional[str] = None,
    queue: Optional[str] = None,
    resource: Optional[str] = None,
) -> dict:
    """Open a loop-backed kdebug session."""
    return debug.session_open(
        name=name, daidir=daidir, fsdb=fsdb, queue=queue,
        resource=resource,
    )


@kverif_tool("debug")
def kverif_debug_session_list(include_native: bool = False) -> dict:
    """List kdebug sessions managed by this server."""
    return debug.session_list(include_native=include_native)


@kverif_tool("debug")
def kverif_debug_session_close(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Close and cleanup a kdebug session."""
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return debug.session_close(key)


@kverif_tool("debug")
def kverif_debug_query(
    session: str,
    action: str,
    args: Optional[dict] = None,
    limits: Optional[dict] = None,
    output: Optional[dict] = None,
    output_format: str = "kout",
) -> Any:
    """Run a kdebug action through a loop session.

    Recommended workflow:
    1. Call kverif_debug_list_actions if you don't know available actions.
    2. Call kverif_debug_get_schema(action) if you need the exact request shape.
    3. Call kverif_debug_session_open first for FSDB/daidir queries.
    4. Call kverif_debug_query with action + args.

    Args:
        action: The kdebug action name (e.g. "value.at", "trace.drivers").
        session: Explicit session alias or session_id returned by session_open.
        args: Action-specific arguments dict.
        limits: Query limits dict (max_rows, timeout, etc.).
        output: Output control dict (rarely needed).
        output_format:
            "kout" (default) — AI-readable structured text.
            "json" — raw kdebug JSON dict.
            "envelope" — wrapper envelope for debugging.
    """
    if output_format not in ("kout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'kout', 'json', or 'envelope'")
    return debug.query(
        action=action,
        args=args or {},
        session=session,
        limits=limits,
        output=output,
        output_format=output_format,
    )


# ---------------------------------------------------------------------------
# Coverage tools (kcov — stateful backend)
# ---------------------------------------------------------------------------


@kverif_tool("cov")
def kverif_cov_list_actions() -> dict:
    """Return the kcov action catalog."""
    return cov.actions()


@kverif_tool("cov")
def kverif_cov_get_schema(action: str, kind: str = "request") -> dict:
    """Return a kcov action schema."""
    if kind not in ("request", "response"):
        return _tool_error("INVALID_ARGUMENT", "kind must be 'request' or 'response'")
    return cov.schema(action, kind)


@kverif_tool("cov")
def kverif_cov_raw_request(request: dict, output_format: str = "kout") -> Any:
    """Run a complete kcov JSON request one-shot."""
    if not isinstance(request, dict):
        return _tool_error("INVALID_ARGUMENT", "request must be a JSON object")
    if output_format not in ("kout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'kout', 'json', or 'envelope'")
    return cov.request(request, output_format)


@kverif_tool("cov")
def kverif_cov_session_open(
    name: str,
    vdb: str,
    queue: Optional[str] = None,
    resource: Optional[str] = None,
) -> dict:
    """Open a loop-backed kcov coverage database session."""
    return cov.session_open(
        name=name, vdb=vdb, queue=queue, resource=resource,
    )


@kverif_tool("cov")
def kverif_cov_session_list() -> dict:
    """List kcov sessions managed by this server."""
    return cov.session_list()


@kverif_tool("cov")
def kverif_cov_session_close(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Close and cleanup a kcov session."""
    key = session_id or name
    if not key:
        return _tool_error("INVALID_ARGUMENT", "provide name or session_id")
    return cov.session_close(key)


@kverif_tool("cov")
def kverif_cov_query(
    session: str,
    action: str,
    args: Optional[dict] = None,
    limits: Optional[dict] = None,
    output: Optional[dict] = None,
    output_format: str = "kout",
) -> Any:
    """Run a kcov action through a coverage session."""
    if output_format not in ("kout", "json", "envelope"):
        return _tool_error("INVALID_ARGUMENT",
                           "output_format must be 'kout', 'json', or 'envelope'")
    return cov.query(
        action=action,
        args=args or {},
        session=session,
        limits=limits,
        output=output,
        output_format=output_format,
    )


# ---------------------------------------------------------------------------
# Bit tools (kbit — stateless CLI adapter)
# ---------------------------------------------------------------------------


@kverif_tool("bit")
def kverif_bit_convert(value: str, width: int = 0, signed: bool = False,
                     unsigned: bool = False, state: str = "2",
                     output_format: str = "kout") -> Any:
    """Convert a value between radices and SV literal formats.

    Args:
        value: The value to convert (hex, binary, SV literal, etc.).
        width: Resize result to N bits (0 = keep original).
        signed: Treat as signed value.
        unsigned: Treat as unsigned value.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "kout".
    """
    return bit_conv(value, width=width, signed=signed, unsigned=unsigned,
                    state=state, output_format=output_format)


@kverif_tool("bit")
def kverif_bit_eval(expr: str, vars: Optional[dict] = None, width: int = 0,
                     signed: bool = False, unsigned: bool = False,
                     state: str = "2", output_format: str = "kout") -> Any:
    """Evaluate a deterministic bit/expression calculation.

    Args:
        expr: Expression string (e.g. "0x10 + 0x1", "sig_a & sig_b").
        vars: Dict of variable name to literal value.
        width: Resize result to N bits.
        signed: Treat as signed value.
        unsigned: Treat as unsigned value.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "kout".
    """
    return bit_eval(expr, vars=vars, width=width, signed=signed,
                    unsigned=unsigned, state=state, output_format=output_format)


@kverif_tool("bit")
def kverif_bit_slice(value: str, msb: int, lsb: int, state: str = "2",
                      output_format: str = "kout") -> Any:
    """Extract a bit slice from a value.

    Args:
        value: The source value.
        msb: Most significant bit index.
        lsb: Least significant bit index.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "kout".
    """
    return bit_slice(value, msb, lsb, state=state, output_format=output_format)


@kverif_tool("bit")
def kverif_bit_check(expr: str, vars: Optional[dict] = None,
                      values: Optional[str] = None, state: str = "2",
                      output_format: str = "kout") -> Any:
    """Check a bit expression against expected values.

    Args:
        expr: Expression to evaluate.
        vars: Dict of variable name to literal value.
        values: Expected values to check against.
        state: 2 or 4 state encoding (default: 2).
        output_format: "json" or "kout".
    """
    return bit_check(expr, vars=vars, values=values, state=state,
                     output_format=output_format)


# ---------------------------------------------------------------------------
# Entry tools (kentry — stateless CLI adapter)
# ---------------------------------------------------------------------------


@kverif_tool("entry")
def kverif_entry_decode(config_path: Optional[str] = None,
                         input_path: Optional[str] = None,
                         config: Optional[dict] = None,
                         fragments: Optional[list] = None,
                         output_format: str = "kout") -> Any:
    """Decode multi-beat byte fragments into raw field slices per config.

    Provide either (config_path + input_path) or (config + fragments).

    Args:
        config_path: Path to YAML/JSON entry config file.
        input_path: Path to JSONL fragments input file.
        config: Inline entry config dict (alternative to config_path).
        fragments: Inline fragments list (alternative to input_path).
        output_format: "json" or "kout".
    """
    if not config_path and not config:
        return _tool_error("INVALID_ARGUMENT",
                           "provide config_path or config")
    return entry_decode(config_path=config_path or "",
                         input_path=input_path or "",
                         config=config, fragments=fragments,
                         output_format=output_format)


@kverif_tool("entry")
def kverif_entry_explain(config_path: str, output_format: str = "kout") -> Any:
    """Explain the field layout defined by an entry config.

    Args:
        config_path: Path to YAML/JSON entry config file.
        output_format: "json" or "kout".
    """
    return entry_explain(config_path, output_format=output_format)


@kverif_tool("entry")
def kverif_entry_validate(config_path: Optional[str] = None,
                           input_path: Optional[str] = None,
                           config: Optional[dict] = None,
                           fragments: Optional[list] = None,
                           output_format: str = "kout") -> Any:
    """Validate an entry config (and optionally an input) without decoding.

    Provide either (config_path + input_path) or (config + fragments).

    Args:
        config_path: Path to YAML/JSON entry config file.
        input_path: Optional path to JSONL fragments for deeper validation.
        config: Inline entry config dict (alternative to config_path).
        fragments: Inline fragments list (alternative to input_path).
        output_format: "json" or "kout".
    """
    if not config_path and not config:
        return _tool_error("INVALID_ARGUMENT",
                           "provide config_path or config")
    return entry_validate(config_path=config_path or "",
                           input_path=input_path,
                           config=config, fragments=fragments,
                           output_format=output_format)


# ---------------------------------------------------------------------------
# Location tools (kloc — stateless CLI adapter)
# ---------------------------------------------------------------------------


@kverif_tool("loc")
def kverif_loc_resolve(loc_id: str, map_path: str,
                        output_format: str = "kout") -> Any:
    """Resolve a compressed loc_id (L_XXXXXXXX) to source file:line.

    Args:
        loc_id: The loc_id to resolve (e.g. L_00000001).
        map_path: Path to JSONL sidecar map file.
        output_format: "json" or "kout".
    """
    return loc_resolve(loc_id, map_path, output_format=output_format)


@kverif_tool("loc")
def kverif_loc_context(loc_id: str, map_path: str, before: int = 20,
                        after: int = 20, output_format: str = "kout") -> Any:
    """Resolve a loc_id and show surrounding source code context.

    Args:
        loc_id: The loc_id to resolve.
        map_path: Path to JSONL sidecar map file.
        before: Lines to show before the target line.
        after: Lines to show after the target line.
        output_format: "json" or "kout".
    """
    return loc_context(loc_id, map_path, before=before, after=after,
                       output_format=output_format)


@kverif_tool("loc")
def kverif_loc_stats(log_path: str, map_path: Optional[str] = None,
                      top: int = 20, output_format: str = "kout") -> Any:
    """Count loc_id frequency in a simulation log (hotspot analysis).

    Args:
        log_path: Path to simulation log.
        map_path: Optional path to JSONL sidecar map file for resolution.
        top: Show top N locations (default: 20).
        output_format: "json" or "kout".
    """
    return loc_stats(log_path, map_path=map_path, top=top,
                     output_format=output_format)


@kverif_tool("loc")
def kverif_loc_annotate(log_path: str, map_path: Optional[str] = None,
                         output_format: str = "kout") -> Any:
    """Insert source location hints into a simulation log.

    Args:
        log_path: Path to simulation log.
        map_path: Optional path to JSONL sidecar map file.
        output_format: "kout" (annotated text).
    """
    return loc_annotate(log_path, map_path=map_path,
                        output_format=output_format)


# ---------------------------------------------------------------------------
# Context tools (kberif — stateless CLI adapter)
# ---------------------------------------------------------------------------


@kverif_tool("context")
def kverif_context_status(project_root: Optional[str] = None,
                           output_format: str = "kout") -> Any:
    """Check kberif project status (which kinds, cards, details exist)."""
    return context_status(project_root=project_root, output_format=output_format)


@kverif_tool("context")
def kverif_context_topics(project_root: Optional[str] = None,
                                output_format: str = "kout") -> Any:
    """List all known context topics."""
    return context_list_topics(project_root=project_root, output_format=output_format)


@kverif_tool("context")
def kverif_context_brief(mode: str = "debug", project_root: Optional[str] = None,
                          output_format: str = "kout") -> Any:
    """Generate a context summary brief for the given mode.

    Args:
        mode: Context mode (e.g. "debug").
        output_format: "json" or "kout".
    """
    return context_brief(mode=mode, project_root=project_root,
                         output_format=output_format)


@kverif_tool("context")
def kverif_context_topic(topic: str, detail: bool = False,
                        project_root: Optional[str] = None,
                        output_format: str = "kout") -> Any:
    """Get a topic summary card, optionally with full detail.

    Args:
        topic: Topic name (e.g. "clk_rst", "memory_map").
        detail: If True, also include full detail content.
        output_format: "json" or "kout".
    """
    return context_get(topic, detail=detail, project_root=project_root,
                       output_format=output_format)


@kverif_tool("context")
def kverif_context_topic_detail(topic: str, project_root: Optional[str] = None,
                           output_format: str = "markdown") -> Any:
    """Get the full detail markdown for a topic.

    Args:
        topic: Topic name.
        output_format: "markdown" (raw detail text).
    """
    return context_detail(topic, project_root=project_root,
                          output_format=output_format)


@kverif_tool("context")
def kverif_context_validate(project_root: Optional[str] = None,
                             output_format: str = "kout") -> Any:
    """Validate project cards and detail files for consistency."""
    return context_validate(project_root=project_root, output_format=output_format)


@kverif_tool("context_write", write=True)
def kverif_context_init_config(kind: str, project_root: Optional[str] = None) -> Any:
    """Initialize kberif kind.toml config. Requires KVERIF_MCP_ENABLE_WRITE=1."""
    return context_config_init(kind, project_root=project_root)


@kverif_tool("context_write", write=True)
def kverif_context_init_project(model: str, project_root: Optional[str] = None) -> Any:
    """Initialize kberif project structure. Requires KVERIF_MCP_ENABLE_WRITE=1."""
    return context_init(model, project_root=project_root)


@kverif_tool("context_write", write=True)
def kverif_context_repair_index(project_root: Optional[str] = None) -> Any:
    """Repair kberif catalog index. Requires KVERIF_MCP_ENABLE_WRITE=1."""
    return context_repair(project_root=project_root)


# ---------------------------------------------------------------------------
# SVA tools (ksva — stateless CLI adapter)
# ---------------------------------------------------------------------------


@kverif_tool("sva")
def kverif_sva_list_properties(file: str, output_format: str = "kout") -> Any:
    """List all property/assertion names in a SVA source file.

    Args:
        file: Path to SVA source file (.sv/.sva/.v).
    """
    return sva_list(file, output_format=output_format)


@kverif_tool("sva")
def kverif_sva_scan_constructs(file: str, output_format: str = "kout") -> Any:
    """Scan syntax constructs used in a SVA source file.

    Args:
        file: Path to SVA source file.
    """
    return sva_scan(file, output_format=output_format)


@kverif_tool("sva")
def kverif_sva_parse_property(file: str, property: str, emit: str = "timeline-ir",
                      output_format: str = "kout") -> Any:
    """Parse a SVA property into IR.

    Args:
        file: Path to SVA source file.
        property: Property/assertion name.
        emit: IR level — "surface-ir", "sequence-ir", or "timeline-ir".
    """
    return sva_parse(file, property, emit=emit, output_format=output_format)


@kverif_tool("sva")
def kverif_sva_explain_property(file: str, property: str, strict: bool = False,
                        output_format: str = "kout") -> Any:
    """Generate a human-readable explanation of a SVA property.

    Args:
        file: Path to SVA source file.
        property: Property/assertion name.
        strict: If True, error on unsupported constructs.
        output_format: "json", "markdown", or "kout".
    """
    return sva_explain(file, property, strict=strict, output_format=output_format)


# ---------------------------------------------------------------------------
# Tool catalog (meta-tools for AI discovery)
# ---------------------------------------------------------------------------

TOOL_CATALOG = [
    {"name": "kverif_ping", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "Ping the kverif MCP server."},
    {"name": "kverif_tools", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "List all available kverif tools."},
    {"name": "kverif_tool_help", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "Get help for a specific tool."},
    {"name": "kverif_batch", "category": "common", "backend": "builtin",
     "stateful": False, "requires_session": False,
     "description": "Execute MCP tools from NDJSON batch file serially. "
                    "Line: {\"tool\":\"<name>\",\"args\":{<params>}}. "
                    "Nested args for debug_query/cov_query: "
                    "{\"tool\":\"kverif_debug_query\",\"args\":"
                    "{\"session\":\"case_a\",\"action\":\"value.at\","
                    "\"args\":{\"signal\":\"top.clk\",\"time\":\"10ns\"}}}"},
    # debug
    {"name": "kverif_debug_list_actions", "category": "debug", "backend": "kdebug",
     "stateful": False, "requires_session": False,
     "description": "Return the kdebug action catalog."},
    {"name": "kverif_debug_get_schema", "category": "debug", "backend": "kdebug",
     "stateful": False, "requires_session": False,
     "description": "Return an action-specific kdebug JSON schema."},
    {"name": "kverif_debug_raw_request", "category": "debug", "backend": "kdebug",
     "stateful": False, "requires_session": False,
     "description": "Run a complete kdebug JSON request (one-shot, no session)."},
    {"name": "kverif_debug_session_open", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": True,
     "description": "Open a loop-backed kdebug session (direct or LSF)."},
    {"name": "kverif_debug_session_list", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": False,
     "description": "List kdebug sessions managed by this server."},
    {"name": "kverif_debug_session_close", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": True,
     "description": "Close and cleanup a kdebug session."},
    {"name": "kverif_debug_query", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": True,
     "description": "Run a kdebug action through a loop session."},
    # coverage
    {"name": "kverif_cov_list_actions", "category": "cov", "backend": "kcov",
     "stateful": False, "requires_session": False,
     "description": "Return the kcov action catalog."},
    {"name": "kverif_cov_get_schema", "category": "cov", "backend": "kcov",
     "stateful": False, "requires_session": False,
     "description": "Return a kcov action schema."},
    {"name": "kverif_cov_raw_request", "category": "cov", "backend": "kcov",
     "stateful": False, "requires_session": False,
     "description": "Run a complete kcov JSON request one-shot."},
    {"name": "kverif_cov_session_open", "category": "cov", "backend": "kcov",
     "stateful": True, "requires_session": True,
     "description": "Open a loop-backed kcov coverage database session."},
    {"name": "kverif_cov_session_list", "category": "cov", "backend": "kcov",
     "stateful": True, "requires_session": False,
     "description": "List kcov sessions managed by this server."},
    {"name": "kverif_cov_session_close", "category": "cov", "backend": "kcov",
     "stateful": True, "requires_session": True,
     "description": "Close and cleanup a kcov session."},
    {"name": "kverif_cov_query", "category": "cov", "backend": "kcov",
     "stateful": True, "requires_session": True,
     "description": "Run a kcov action through a coverage session."},
    # wave aliases
    {"name": "kverif_wave_value_at", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": True,
     "description": "Get signal value at a time (alias for value.at)."},
    {"name": "kverif_wave_changes", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": True,
     "description": "Get all value changes in a time window (alias for signal.changes)."},
    {"name": "kverif_wave_generate_rc", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": True,
     "description": "Generate RC from config (alias for rc.generate)."},
    {"name": "kverif_design_trace_driver", "category": "debug", "backend": "kdebug",
     "stateful": True, "requires_session": True,
     "description": "Trace the driver of a signal (alias for trace.driver)."},
    # bit
    {"name": "kverif_bit_convert", "category": "bit", "backend": "kbit",
     "stateful": False, "requires_session": False,
     "description": "Convert a value between radices and SV literal formats."},
    {"name": "kverif_bit_eval", "category": "bit", "backend": "kbit",
     "stateful": False, "requires_session": False,
     "description": "Evaluate a deterministic bit/expression calculation."},
    {"name": "kverif_bit_slice", "category": "bit", "backend": "kbit",
     "stateful": False, "requires_session": False,
     "description": "Extract a bit slice from a value."},
    {"name": "kverif_bit_check", "category": "bit", "backend": "kbit",
     "stateful": False, "requires_session": False,
     "description": "Check a bit expression against expected values."},
    # entry
    {"name": "kverif_entry_decode", "category": "entry", "backend": "kentry",
     "stateful": False, "requires_session": False,
     "description": "Decode multi-beat fragments into raw field slices."},
    {"name": "kverif_entry_explain", "category": "entry", "backend": "kentry",
     "stateful": False, "requires_session": False,
     "description": "Explain field layout defined by an entry config."},
    {"name": "kverif_entry_validate", "category": "entry", "backend": "kentry",
     "stateful": False, "requires_session": False,
     "description": "Validate an entry config and optionally its input."},
    # loc
    {"name": "kverif_loc_resolve", "category": "loc", "backend": "kloc",
     "stateful": False, "requires_session": False,
     "description": "Resolve a loc_id to source file:line."},
    {"name": "kverif_loc_context", "category": "loc", "backend": "kloc",
     "stateful": False, "requires_session": False,
     "description": "Resolve a loc_id and show surrounding source context."},
    {"name": "kverif_loc_stats", "category": "loc", "backend": "kloc",
     "stateful": False, "requires_session": False,
     "description": "Count loc_id frequency in a simulation log."},
    {"name": "kverif_loc_annotate", "category": "loc", "backend": "kloc",
     "stateful": False, "requires_session": False,
     "description": "Insert source location hints into a simulation log."},
    # context
    {"name": "kverif_context_status", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Check kberif project status."},
    {"name": "kverif_context_topics", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "List all known context topics."},
    {"name": "kverif_context_brief", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Generate a context summary brief."},
    {"name": "kverif_context_topic", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Get a topic summary card, optionally with detail."},
    {"name": "kverif_context_topic_detail", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Get the full detail markdown for a topic."},
    {"name": "kverif_context_validate", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Validate project cards and detail files."},
    {"name": "kverif_context_init_config", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Initialize kberif kind.toml config (write)."},
    {"name": "kverif_context_init_project", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Initialize kberif project structure (write)."},
    {"name": "kverif_context_repair_index", "category": "context", "backend": "kberif",
     "stateful": False, "requires_session": False,
     "description": "Repair kberif catalog index (write)."},
    # sva
    {"name": "kverif_sva_list_properties", "category": "sva", "backend": "ksva",
     "stateful": False, "requires_session": False,
     "description": "List all property/assertion names in a SVA file."},
    {"name": "kverif_sva_scan_constructs", "category": "sva", "backend": "ksva",
     "stateful": False, "requires_session": False,
     "description": "Scan syntax constructs in a SVA file."},
    {"name": "kverif_sva_parse_property", "category": "sva", "backend": "ksva",
     "stateful": False, "requires_session": False,
     "description": "Parse a SVA property into IR."},
    {"name": "kverif_sva_explain_property", "category": "sva", "backend": "ksva",
     "stateful": False, "requires_session": False,
     "description": "Generate a human-readable SVA property explanation."},
]

_WRITE_TOOL_NAMES = {
    "kverif_context_init_config",
    "kverif_context_init_project",
    "kverif_context_repair_index",
}

for _tool in TOOL_CATALOG:
    if _tool["name"] in _WRITE_TOOL_NAMES:
        _tool.setdefault("group", "context_write")
        _tool.setdefault("write", True)
    else:
        _tool.setdefault("group", _tool["category"])
        _tool.setdefault("write", False)


@kverif_tool("common")
def kverif_tools(category: Optional[str] = None,
                  include_write: bool = True) -> dict:
    """List all available kverif tools, optionally filtered by category.

    Args:
        category: Filter by category ("debug", "bit", "entry", "loc", "context", "sva").
        include_write: If False, hide write-protected tools from this catalog view.
    """
    return {
        "ok": True,
        "tools": filtered_catalog(TOOL_CATALOG, category=category, include_write=include_write),
        "policy": policy_summary(),
    }


@kverif_tool("common")
def kverif_tool_help(name: str) -> dict:
    """Get detailed help for a specific kverif tool.

    Args:
        name: Exact tool name (e.g. "kverif_debug_query").
    """
    for t in filtered_catalog(TOOL_CATALOG, include_write=True):
        if t["name"] == name:
            return {"ok": True, "tool": t, "policy": policy_summary()}
    for t in TOOL_CATALOG:
        if t["name"] == name:
            return _tool_error("TOOL_NOT_ENABLED", f"tool is disabled by MCP policy: {name}")
    return _tool_error("TOOL_NOT_FOUND", f"tool not found: {name}")


# ---------------------------------------------------------------------------
# High-frequency debug aliases (shortcuts for kverif_debug_query)
# ---------------------------------------------------------------------------


@kverif_tool("debug")
def kverif_wave_value_at(signal: str, time: str = "0ns",
                          session: str = "",
                          output_format: str = "kout") -> Any:
    """Get a signal value at a specific time (alias for value.at).

    Args:
        signal: Full hierarchical signal path.
        time: Target time string (e.g. "100ns", "1us").
        session: Explicit session alias or session_id.
        output_format: "kout", "json", or "envelope".
    """
    return debug.query(action="value.at", args={"signal": signal, "time": time},
                       session=session, output_format=output_format)


@kverif_tool("debug")
def kverif_wave_changes(signal: str, begin: str = "0ns",
                                end: str = "100ns",
                                session: str = "",
                                output_format: str = "kout") -> Any:
    """Get all value changes for a signal in a time window.

    Args:
        signal: Full hierarchical signal path.
        begin: Start time (e.g. "0ns").
        end: End time (e.g. "100ns").
        session: Explicit session alias or session_id.
        output_format: "kout", "json", or "envelope".
    """
    return debug.query(action="signal.changes",
                       args={"signal": signal, "begin": begin, "end": end},
                       session=session, output_format=output_format)


@kverif_tool("debug")
def kverif_wave_generate_rc(config_path: str, rc_path: str,
                              session: str = "",
                              output_format: str = "kout") -> Any:
    """Generate recovery context from config (alias for rc.generate).

    Args:
        config_path: Path to RC config file.
        rc_path: Output path for generated RC.
        session: Explicit session alias or session_id.
        output_format: "json" or "kout".
    """
    return debug.query(action="rc.generate",
                       args={"config_path": config_path, "rc_path": rc_path},
                       session=session, output_format=output_format)


@kverif_tool("debug")
def kverif_design_trace_driver(signal: str, time: str = "0ns",
                                session: str = "",
                                output_format: str = "kout") -> Any:
    """Trace the active driver of a signal at a specific time.

    Args:
        signal: Full hierarchical signal path.
        time: Target time string.
        session: Explicit session alias or session_id.
        output_format: "kout", "json", or "envelope".
    """
    return debug.query(action="trace.driver",
                       args={"signal": signal, "time": time},
                       session=session, output_format=output_format)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
