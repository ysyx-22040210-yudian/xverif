"""Trace module-level signal integration wiring from a Verdi elab database."""

from __future__ import annotations

import argparse

from kverif_sdk import (StdioTransport, KdebugClient, resolve_tool,
                        trace_module_connections)

from ._common import emit_report, split_values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trace module signal connectivity")
    parser.add_argument("--tool", default=str(resolve_tool("kdebug")))
    parser.add_argument("--daidir", required=True)
    parser.add_argument("--signal", action="append", required=True,
                        help="integration signal; repeat or pass a comma-separated list")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--session", default="sdk_module_connectivity")
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--request-timeout", type=float, default=0.0)
    parser.add_argument("--output")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    signals = split_values(args.signal)
    with StdioTransport(
        args.tool, protocol="kdebug-stdio-loop", api_version="kdebug.v1",
        startup_timeout_sec=args.startup_timeout,
        request_timeout_sec=args.request_timeout,
    ) as transport:
        client = KdebugClient(transport)
        with client.session(args.session, daidir=args.daidir):
            report = trace_module_connections(
                client, signals, max_depth=args.max_depth, include_source=True)
    emit_report(report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
