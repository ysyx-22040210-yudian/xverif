#!/usr/bin/env python3
"""Invoke kdebug as a subprocess and derive a signal-health conclusion."""

from __future__ import print_function

import argparse
import json
import os
import shutil
import subprocess
import sys


def parser():
    result = argparse.ArgumentParser(
        description="Run kdebug signal.scan and derive a project-level conclusion"
    )
    result.add_argument("--fsdb", required=True)
    result.add_argument("--signal", required=True)
    result.add_argument("--begin", "--start", dest="begin", required=True)
    result.add_argument("--end", "--stop", dest="end", required=True)
    result.add_argument("--max-rows", type=int, default=200)
    result.add_argument("--min-changes", type=int, default=1)
    result.add_argument("--max-unknown", type=int, default=0)
    result.add_argument("--require-complete", action="store_true")
    result.add_argument("--kdebug-bin")
    result.add_argument("--out", required=True)
    return result


def integer_summary(summary, name):
    value = summary.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("summary.{0} is not numeric".format(name))
    return int(value)


def classify(change_count, unknown_count, truncated, args):
    if args.require_complete and truncated:
        return (
            "INCOMPLETE",
            "signal.scan was truncated, so the complete window was not evaluated",
        )
    if unknown_count > args.max_unknown:
        return "UNKNOWN_VALUES", "unknown_count exceeds the configured maximum"
    if change_count < args.min_changes:
        return "INACTIVE", "change_count is below the configured minimum"
    return "HEALTHY", "signal activity satisfies all configured gates"


def tool_prefix(path):
    if os.name != "nt":
        return [path]
    try:
        with open(path, "rb") as handle:
            is_script = handle.read(2) == b"#!"
    except OSError:
        is_script = False
    if not is_script:
        return [path]
    bash = os.environ.get("BASH") or shutil.which("bash")
    if not bash:
        raise OSError("bash is required to launch the kdebug wrapper on Windows")
    return [bash, path]


def executable_path(command):
    if not command:
        return None
    expanded = os.path.expanduser(command)
    if os.path.isfile(expanded) and (os.name == "nt" or os.access(expanded, os.X_OK)):
        return os.path.abspath(expanded)
    resolved = shutil.which(command)
    if resolved:
        return resolved
    if os.path.basename(command) == command:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(directory, command)
            if os.path.isfile(candidate) and (os.name == "nt" or os.access(candidate, os.X_OK)):
                return os.path.abspath(candidate)
    return None


def resolve_kdebug(explicit):
    configured = explicit or os.environ.get("KDEBUG_BIN")
    if configured:
        resolved = executable_path(configured)
        if not resolved:
            raise OSError("configured kdebug is not executable: {0}".format(configured))
        return resolved

    home = os.environ.get("KVERIF_HOME")
    candidates = []
    if home:
        candidates.append(os.path.join(home, "tools", "kdebug"))
    candidates.append(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools", "kdebug"))
    )
    for candidate in candidates:
        resolved = executable_path(candidate)
        if resolved:
            return resolved
    resolved = executable_path("kdebug")
    if resolved:
        return resolved
    raise OSError("cannot find kdebug; use --kdebug-bin, KDEBUG_BIN, KVERIF_HOME, or PATH")


def main(argv=None):
    args = parser().parse_args(argv)
    for name in ("max_rows", "min_changes", "max_unknown"):
        if getattr(args, name) < 0:
            parser().error("--{0} must be non-negative".format(name.replace("_", "-")))

    try:
        kdebug = resolve_kdebug(args.kdebug_bin)
    except OSError as exc:
        print("ERROR: {0}".format(exc), file=sys.stderr)
        return 2

    os.makedirs(args.out, exist_ok=True)
    response_path = os.path.join(args.out, "tool-response.json")
    stderr_path = os.path.join(args.out, "tool-response.stderr")
    report_path = os.path.join(args.out, "conclusion.json")
    command = tool_prefix(kdebug) + [
        "--json",
        "action",
        "signal.scan",
        "--fsdb",
        args.fsdb,
        "--arg",
        "signal={0}".format(args.signal),
        "--arg",
        "begin={0}".format(args.begin),
        "--arg",
        "end={0}".format(args.end),
        "--arg",
        "format=hex",
        "--max-rows",
        str(args.max_rows),
    ]
    try:
        with open(response_path, "w", encoding="utf-8") as stdout_handle, open(
            stderr_path, "w", encoding="utf-8"
        ) as stderr_handle:
            completed = subprocess.run(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                universal_newlines=True,
            )
    except OSError as exc:
        print("ERROR: cannot start kdebug: {0}".format(exc), file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("ERROR: kdebug failed; see {0}".format(stderr_path), file=sys.stderr)
        return 1

    try:
        with open(response_path, "r", encoding="utf-8") as handle:
            response = json.load(handle)
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise ValueError("tool response is not an ok=true object")
        summary = response.get("summary", {})
        if not isinstance(summary, dict):
            raise ValueError("summary is not an object")
        change_count = integer_summary(summary, "change_count")
        unknown_count = integer_summary(summary, "unknown_count")
        truncated = bool(summary.get("truncated", False))
    except (OSError, ValueError, TypeError) as exc:
        print("ERROR: invalid kdebug JSON: {0}".format(exc), file=sys.stderr)
        return 1

    conclusion, reason = classify(change_count, unknown_count, truncated, args)
    report = {
        "schema": "kverif.example.signal-health.v1",
        "language": "python",
        "gate_pass": conclusion == "HEALTHY",
        "conclusion": {"status": conclusion, "reason": reason},
        "evidence": {
            "signal": args.signal,
            "change_count": change_count,
            "unknown_count": unknown_count,
            "truncated": truncated,
        },
        "thresholds": {
            "min_changes": args.min_changes,
            "max_unknown": args.max_unknown,
            "require_complete": args.require_complete,
        },
        "artifacts": {"tool_response": response_path, "tool_stderr": stderr_path},
    }
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        handle.write("\n")

    print("signal health: {0} ({1})".format(conclusion, reason))
    print("report: {0}".format(report_path))
    return 0 if conclusion == "HEALTHY" else 3


if __name__ == "__main__":
    sys.exit(main())
