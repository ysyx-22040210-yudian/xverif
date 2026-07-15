#!/usr/bin/env python3
"""Process-level JSON helpers for the Shell/Perl CLI examples."""

from __future__ import print_function

import argparse
import json
import sys


def load_object(path):
    try:
        with open(path, "r") as handle:
            value = json.load(handle)
    except (IOError, ValueError) as exc:
        raise SystemExit("invalid JSON file {0}: {1}".format(path, exc))
    if not isinstance(value, dict):
        raise SystemExit("JSON root is not an object: {0}".format(path))
    return value


def command_check_ok(args):
    value = load_object(args.file)
    if value.get("ok") is not True:
        print("tool returned ok=false: {0}".format(args.file), file=sys.stderr)
        return 1
    return 0


def command_coverage_stats(args):
    value = load_object(args.file)
    rows = value.get("data", {}).get("items", [])
    numeric = [
        row for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("covered"), (int, float))
        and not isinstance(row.get("covered"), bool)
        and isinstance(row.get("coverable"), (int, float))
        and not isinstance(row.get("coverable"), bool)
    ]
    if not numeric:
        print("no numeric coverage rows: {0}".format(args.file), file=sys.stderr)
        return 1
    covered = sum(row["covered"] for row in numeric)
    coverable = sum(row["coverable"] for row in numeric)
    percentage = 100.0 if coverable == 0 else covered * 100.0 / coverable
    print("{0:.15g}\t{1:.15g}\t{2:.15g}".format(covered, coverable, percentage))
    return 0


def command_wave_stats(args):
    value = load_object(args.file)
    summary = value.get("summary", {})
    print("{0}\t{1}\t{2}".format(
        int(summary.get("change_count", 0)),
        int(summary.get("unknown_count", 0)),
        "true" if summary.get("truncated") else "false",
    ))
    return 0


def command_wave_row(args):
    value = load_object(args.response)
    summary = value.get("summary", {})
    print(json.dumps({
        "signal": args.signal,
        "response": args.response,
        "change_count": int(summary.get("change_count", 0)),
        "unknown_count": int(summary.get("unknown_count", 0)),
        "truncated": bool(summary.get("truncated")),
    }, separators=(",", ":"), sort_keys=True))
    return 0


def _summary(path):
    if not path:
        return None
    return load_object(path).get("summary", {})


def command_connectivity_row(args):
    driver = _summary(args.driver)
    load = _summary(args.load)
    graph = _summary(args.graph)
    print(json.dumps({
        "signal": args.signal,
        "driver": None if driver is None else {
            "response": args.driver,
            "edge_count": int(driver.get("edge_count", 0)),
            "status": driver.get("status"),
        },
        "load": None if load is None else {
            "response": args.load,
            "edge_count": int(load.get("edge_count", 0)),
            "status": load.get("status"),
        },
        "graph": None if graph is None else {
            "response": args.graph,
            "node_count": int(graph.get("node_count", 0)),
            "edge_count": int(graph.get("edge_count", 0)),
            "truncated": bool(graph.get("truncated")),
        },
    }, separators=(",", ":"), sort_keys=True))
    return 0


def _parse_scalar(text):
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "null":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def command_wrap_report(args):
    records = []
    try:
        with open(args.records, "r") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
    except (IOError, ValueError) as exc:
        raise SystemExit("invalid NDJSON file {0}: {1}".format(args.records, exc))
    report = {"schema": args.schema, "records": records}
    for item in args.meta:
        if "=" not in item or item.startswith("="):
            raise SystemExit("--meta must be key=value: {0}".format(item))
        key, value = item.split("=", 1)
        report[key] = _parse_scalar(value)
    with open(args.output, "w") as handle:
        json.dump(report, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    return 0


def command_holes_count(args):
    value = load_object(args.file)
    summary = value.get("summary", {})
    count = summary.get("matched_count")
    if not isinstance(count, (int, float)) or isinstance(count, bool):
        count = len(value.get("data", {}).get("items", []))
    print(int(count))
    return 0


def command_summary_value(args):
    value = load_object(args.file).get("summary", {}).get(args.key, args.default)
    if isinstance(value, bool):
        print("true" if value else "false")
    elif value is None:
        print("null")
    elif isinstance(value, (dict, list)):
        print(json.dumps(value, separators=(",", ":"), sort_keys=True))
    else:
        print(value)
    return 0


def command_coverage_row(args):
    delta = None if args.delta == "null" else float(args.delta)
    value = {
        "label": args.label,
        "vdb": args.vdb,
        "covered": float(args.covered),
        "coverable": float(args.coverable),
        "coverage_pct": float(args.coverage_pct),
        "delta_pct": delta,
        "plateau": args.plateau == "true",
        "hole_count": int(args.hole_count),
        "summary_response": args.summary_response,
        "holes_response": args.holes_response,
    }
    print(json.dumps(value, separators=(",", ":"), sort_keys=True))
    return 0


def command_coverage_report(args):
    runs = []
    try:
        with open(args.runs, "r") as handle:
            for line in handle:
                if line.strip():
                    runs.append(json.loads(line))
    except (IOError, ValueError) as exc:
        raise SystemExit("invalid NDJSON file {0}: {1}".format(args.runs, exc))
    report = {
        "schema": "kverif.cli.coverage-convergence.v1",
        "metrics": [item for item in args.metrics.split(",") if item],
        "plateau_epsilon_pct": args.plateau_epsilon,
        "fail_under_pct": args.fail_under,
        "max_final_holes": args.max_final_holes,
        "max_regression_pct": args.max_regression,
        "require_growth": args.require_growth,
        "runs": runs,
    }
    with open(args.output, "w") as handle:
        json.dump(report, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    return 0


def command_coverage_gate(args):
    report = load_object(args.report)
    runs = report.get("runs", [])
    percentage = runs[-1].get("coverage_pct", 0) if runs else 0
    failures = []
    if args.target is not None and percentage < args.target:
        failures.append("final coverage {0:.6g} < {1:.6g}".format(percentage, args.target))
    if args.max_final_holes is not None:
        holes = runs[-1].get("hole_count", 0) if runs else 0
        if holes > args.max_final_holes:
            failures.append("final holes {0} > {1}".format(holes, args.max_final_holes))
    if args.max_regression is not None:
        for row in runs:
            delta = row.get("delta_pct")
            if delta is not None and delta < -args.max_regression:
                failures.append("run {0} regressed by {1:.6g}%".format(
                    row.get("label", "?"), -delta))
    if args.require_growth and len(runs) > 1:
        if not any((row.get("delta_pct") or 0) > 0 for row in runs[1:]):
            failures.append("no run increased coverage")
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


def command_triage_report(args):
    report = {
        "schema": "kverif.cli.regression-triage.v1",
        "components": {
            "waveform": load_object(args.waveform),
            "connectivity": load_object(args.connectivity),
            "coverage": load_object(args.coverage),
        },
        "artifacts": {
            "waveform": args.waveform,
            "connectivity": args.connectivity,
            "coverage": args.coverage,
        },
    }
    with open(args.output, "w") as handle:
        json.dump(report, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Validate and summarize kverif CLI JSON")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    child = subparsers.add_parser("check-ok")
    child.add_argument("file")
    child.set_defaults(func=command_check_ok)

    child = subparsers.add_parser("coverage-stats")
    child.add_argument("file")
    child.set_defaults(func=command_coverage_stats)

    child = subparsers.add_parser("wave-stats")
    child.add_argument("file")
    child.set_defaults(func=command_wave_stats)

    child = subparsers.add_parser("wave-row")
    child.add_argument("--signal", required=True)
    child.add_argument("--response", required=True)
    child.set_defaults(func=command_wave_row)

    child = subparsers.add_parser("connectivity-row")
    child.add_argument("--signal", required=True)
    child.add_argument("--driver")
    child.add_argument("--load")
    child.add_argument("--graph")
    child.set_defaults(func=command_connectivity_row)

    child = subparsers.add_parser("wrap-report")
    child.add_argument("--schema", required=True)
    child.add_argument("--records", required=True)
    child.add_argument("--output", required=True)
    child.add_argument("--meta", action="append", default=[])
    child.set_defaults(func=command_wrap_report)

    child = subparsers.add_parser("holes-count")
    child.add_argument("file")
    child.set_defaults(func=command_holes_count)

    child = subparsers.add_parser("summary-value")
    child.add_argument("--file", required=True)
    child.add_argument("--key", required=True)
    child.add_argument("--default", default="")
    child.set_defaults(func=command_summary_value)

    child = subparsers.add_parser("coverage-row")
    child.add_argument("--label", required=True)
    child.add_argument("--vdb", required=True)
    child.add_argument("--covered", required=True)
    child.add_argument("--coverable", required=True)
    child.add_argument("--coverage-pct", required=True)
    child.add_argument("--delta", required=True)
    child.add_argument("--plateau", choices=("true", "false"), required=True)
    child.add_argument("--hole-count", required=True)
    child.add_argument("--summary-response", required=True)
    child.add_argument("--holes-response", required=True)
    child.set_defaults(func=command_coverage_row)

    child = subparsers.add_parser("coverage-report")
    child.add_argument("--metrics", required=True)
    child.add_argument("--plateau-epsilon", type=float, required=True)
    child.add_argument("--fail-under", type=float)
    child.add_argument("--max-final-holes", type=int)
    child.add_argument("--max-regression", type=float)
    child.add_argument("--require-growth", action="store_true")
    child.add_argument("--runs", required=True)
    child.add_argument("--output", required=True)
    child.set_defaults(func=command_coverage_report)

    child = subparsers.add_parser("coverage-gate")
    child.add_argument("--report", required=True)
    child.add_argument("--target", type=float)
    child.add_argument("--max-final-holes", type=int)
    child.add_argument("--max-regression", type=float)
    child.add_argument("--require-growth", action="store_true")
    child.set_defaults(func=command_coverage_gate)

    child = subparsers.add_parser("triage-report")
    child.add_argument("--waveform", required=True)
    child.add_argument("--connectivity", required=True)
    child.add_argument("--coverage", required=True)
    child.add_argument("--output", required=True)
    child.set_defaults(func=command_triage_report)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
