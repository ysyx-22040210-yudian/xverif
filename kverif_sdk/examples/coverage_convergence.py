"""Compare ordered VDBs and report coverage convergence or a plateau."""

from __future__ import annotations

import argparse

from kverif_sdk import (CoverageRun, StdioTransport, KcovClient,
                        analyze_coverage_convergence, resolve_tool)

from ._common import emit_report, split_values


def _run(value: str, fake: bool) -> CoverageRun:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run must use LABEL=VDB")
    label, vdb = value.split("=", 1)
    if not label or not vdb:
        raise argparse.ArgumentTypeError("--run must use non-empty LABEL=VDB")
    return CoverageRun(label=label, vdb=vdb, fake=fake or vdb == "fake")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze ordered coverage regression results")
    parser.add_argument("--tool", default=str(resolve_tool("kcov")))
    parser.add_argument("--run", action="append", required=True,
                        help="ordered LABEL=VDB entry; repeat for each regression result")
    parser.add_argument("--metrics", action="append")
    parser.add_argument("--hole-limit", type=int, default=20)
    parser.add_argument("--target-pct", type=float, default=100.0)
    parser.add_argument("--plateau-epsilon", type=float, default=0.01)
    parser.add_argument("--fake", action="store_true",
                        help="use kcov's built-in fake backend for all runs")
    parser.add_argument("--startup-timeout", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=float, default=0.0)
    parser.add_argument("--output")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    runs = [_run(value, args.fake) for value in args.run]
    metrics = split_values(args.metrics or ["line,toggle,branch,condition"])
    with StdioTransport(
        args.tool, protocol="kcov-stdio-loop", api_version="kcov.v1",
        startup_timeout_sec=args.startup_timeout,
        request_timeout_sec=args.request_timeout,
    ) as transport:
        client = KcovClient(transport)
        report = analyze_coverage_convergence(
            client, runs, metrics=metrics, hole_limit=args.hole_limit,
            target_pct=args.target_pct, plateau_epsilon=args.plateau_epsilon)
    emit_report(report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
