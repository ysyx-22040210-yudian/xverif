#!/usr/bin/env python3
"""Repeated native active trace chain builder.

Calls xdebug trace.active_driver repeatedly, following next_signal at
active_time, to build a manual trace chain.  Does not modify xdebug — it
only interprets the existing JSON response.

Usage:
  python3 run_xdebug_chain.py <session_id> <signal> <time> <output_dir>
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
XDEBUG = os.environ.get("XDEBUG", str(REPO_ROOT / "tools" / "xdebug"))
# fallback to local build
if not Path(XDEBUG).exists():
    XDEBUG = str(Path(__file__).resolve().parent.parent.parent.parent / "xdebug")


def call_xdebug(session_id: str, signal: str, time: str,
                include_trace: bool = True) -> dict:
    """Call trace.active_driver and return parsed JSON response."""
    req = json.dumps({
        "api_version": "xdebug.v1",
        "action": "trace.active_driver",
        "target": {"session_id": session_id},
        "args": {
            "signal": signal,
            "requested_time": time,
            "include_trace": include_trace,
        },
        "output": {"format": "json", "verbosity": "compact"},
    })
    proc = subprocess.run(
        [XDEBUG, "--json", "-"],
        input=req, capture_output=True, text=True, timeout=120,
    )
    raw = proc.stdout + proc.stderr

    # bracket-match the outermost JSON object
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"no JSON in xdebug output: {raw[-500:]}")
    depth, end = 0, -1
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        raise RuntimeError(f"unmatched braces in xdebug output: {raw[-500:]}")
    resp = json.loads(raw[start:end + 1])
    if not resp.get("ok"):
        err = resp.get("error", {})
        raise RuntimeError(f"xdebug error: {err.get('code')} - {err.get('message')}")
    return resp


def extract_next_signal(trace_nodes: list, current_signal: str) -> str:
    """Extract the next signal to trace from the trace nodes.

    Priority:
    1. An assignment node with next_signal (pass-through)
    2. An alias node with next_signal
    3. First signal in the first assignment node that differs from current
    """
    for node in trace_nodes:
        role = node.get("role", "")
        ns = node.get("next_signal", "")
        if ns and role in ("assignment", "alias"):
            return ns

    # fallback: first signal from assignment node that isn't current_signal
    for node in trace_nodes:
        if node.get("role") == "assignment":
            for s in node.get("signals", []):
                if s != current_signal:
                    return s
    return ""


def extract_branch_evidence(resp: dict, current_signal: str,
                            current_time: str) -> dict:
    """Extract branch evidence from a trace.active_driver response.

    Captures multi-signal RHS, controls, and alias candidates.
    """
    data = resp.get("data", {})
    trace = data.get("trace", {})
    nodes = trace.get("nodes", [])
    alias_candidates = data.get("alias_candidates", [])

    evidence = {
        "target": current_signal,
        "time": current_time,
        "candidates": [],
        "decision": {"auto_continue": False, "next": "", "reason": ""},
    }

    has_multi = False
    for node in nodes:
        role = node.get("role", "")
        kind = node.get("kind", "")
        signals = node.get("signals", [])
        ns = node.get("next_signal", "")

        if role == "assignment" and ns:
            # unique pass-through → auto continue
            evidence["decision"]["auto_continue"] = True
            evidence["decision"]["next"] = ns
            evidence["decision"]["reason"] = "native_unique"
            evidence["candidates"].append({
                "path": ns,
                "role": "data",
                "native_active": True,
            })
            break

        if role == "assignment" and len(signals) > 1:
            has_multi = True
            for s in signals:
                if s != current_signal:
                    evidence["candidates"].append({
                        "path": s, "role": "data", "native_active": True,
                    })

        if role in ("control", "event"):
            evidence["candidates"].append({
                "path": node.get("signal", ""),
                "role": "control",
                "kind": kind,
                "native_active": True,
            })

    if alias_candidates:
        for ac in alias_candidates:
            evidence["candidates"].append({
                "path": ac.get("to", ""),
                "role": "alias",
                "confidence": ac.get("confidence", ""),
                "native_active": False,
            })
        if not evidence["decision"]["auto_continue"] and len(alias_candidates) == 1:
            evidence["decision"]["auto_continue"] = True
            evidence["decision"]["next"] = alias_candidates[0].get("to", "")
            evidence["decision"]["reason"] = "alias_unique"

    if not evidence["decision"]["auto_continue"]:
        if has_multi:
            evidence["decision"]["reason"] = "multiple_data_candidates"
        elif alias_candidates:
            evidence["decision"]["reason"] = "multiple_alias_candidates"
        else:
            evidence["decision"]["reason"] = "no_clear_next"

    return evidence


def run_chain(session_id: str, signal: str, time: str,
              max_hops: int = 20, output_dir: str = None) -> dict:
    """Build a trace chain by repeatedly calling trace.active_driver.

    Returns a dict with 'chain', 'branch_evidence', 'limitations',
    'termination', 'temporal_boundary_count'.
    """
    chain = []
    branch_evidence_list = []
    limitations = []
    visited = set()
    temporal_count = 0
    termination = "unresolved"
    current_signal, current_time = signal, time

    for hop in range(max_hops):
        key = f"{current_signal}@{current_time}"
        if key in visited:
            termination = "loop_detected"
            limitations.append(f"loop detected: {key}")
            break
        visited.add(key)

        # ── call native active trace ──
        resp = call_xdebug(session_id, current_signal, current_time,
                           include_trace=True)

        # save raw response
        if output_dir:
            hop_file = os.path.join(output_dir, f"native_trace_hop_{hop}.json")
            with open(hop_file, "w") as f:
                json.dump(resp, f, indent=2)

        summary = resp.get("summary", {})
        data = resp.get("data", {})
        trace = data.get("trace", {})
        nodes = trace.get("nodes", [])
        active_time = summary.get("active_time", current_time)
        driver_status = summary.get("driver_status", "unresolved")
        root_driver = summary.get("root_driver", {})

        # detect temporal boundary
        is_temporal = (active_time != current_time)
        if is_temporal:
            temporal_count += 1

        # extract values
        values = data.get("values", {})
        active_values = values.get("active", {})
        requested_values = values.get("requested", {})
        node_value = (active_values.get(current_signal) or
                      requested_values.get(current_signal))

        # determine next signal
        next_signal = extract_next_signal(nodes, current_signal)

        node = {
            "hop": hop,
            "signal": current_signal,
            "requested_time": current_time,
            "active_time": active_time,
            "value": node_value,
            "driver_status": driver_status,
            "driver_kind": root_driver.get("kind", ""),
            "root_file": root_driver.get("file", ""),
            "root_line": root_driver.get("line", 0),
            "hop_type": "temporal_boundary" if is_temporal else "same_time",
            "next_signal": next_signal,
            "next_time": active_time,
        }
        chain.append(node)

        # check termination
        if driver_status != "resolved":
            termination = driver_status
            # capture branch evidence for non-resolved stops
            be = extract_branch_evidence(resp, current_signal, current_time)
            if be["candidates"]:
                branch_evidence_list.append(be)
            break

        if not next_signal:
            termination = root_driver.get("kind", "unresolved")
            if termination == "primary_input":
                pass  # natural stop
            elif not termination or termination == "unknown":
                # check for branch evidence
                be = extract_branch_evidence(resp, current_signal, current_time)
                if be["candidates"] and not be["decision"]["auto_continue"]:
                    branch_evidence_list.append(be)
            break

        # prepare next hop
        current_signal = next_signal
        current_time = active_time

    # add resp limitations
    for lim in data.get("limitations", []):
        limitations.append(str(lim))

    return {
        "chain": chain,
        "branch_evidence": branch_evidence_list,
        "limitations": limitations,
        "termination": termination,
        "temporal_boundary_count": temporal_count,
        "total_hops": len(chain),
        "visited_count": len(visited),
    }


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <session_id> <signal> <time> [output_dir]",
              file=sys.stderr)
        sys.exit(1)

    session_id = sys.argv[1]
    signal = sys.argv[2]
    time = sys.argv[3]
    output_dir = sys.argv[4] if len(sys.argv) > 4 else None

    result = run_chain(session_id, signal, time, output_dir=output_dir)

    # write trace_chain.json
    if output_dir:
        chain_file = os.path.join(output_dir, "trace_chain.json")
        with open(chain_file, "w") as f:
            json.dump(result, f, indent=2)

    # print summary to stdout
    print(json.dumps({
        "signal": signal,
        "start_time": time,
        "total_hops": result["total_hops"],
        "temporal_boundaries": result["temporal_boundary_count"],
        "termination": result["termination"],
        "branch_evidence_count": len(result["branch_evidence"]),
    }, indent=2))


if __name__ == "__main__":
    main()
