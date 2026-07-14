"""Analyze a waveform window with a persistent xdebug stdio session."""

from __future__ import annotations

import argparse

from xverif_sdk import (StdioTransport, XdebugClient, analyze_wave_window,
                        resolve_tool)

from ._common import emit_report, split_values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze signal activity in an FSDB window")
    parser.add_argument("--tool", default=str(resolve_tool("xdebug")))
    parser.add_argument("--fsdb", required=True)
    parser.add_argument("--signal", action="append", required=True,
                        help="signal name; repeat or pass a comma-separated list")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--sample-time", action="append", default=[])
    parser.add_argument("--format", default="hex")
    parser.add_argument("--max-changes", type=int, default=100)
    parser.add_argument("--session", default="sdk_wave_analysis")
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--request-timeout", type=float, default=0.0)
    parser.add_argument("--output")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    signals = split_values(args.signal)
    sample_times = split_values(args.sample_time)
    with StdioTransport(
        args.tool, protocol="xdebug-stdio-loop", api_version="xdebug.v1",
        startup_timeout_sec=args.startup_timeout,
        request_timeout_sec=args.request_timeout,
    ) as transport:
        client = XdebugClient(transport)
        with client.session(args.session, fsdb=args.fsdb):
            report = analyze_wave_window(
                client, signals, start=args.start, end=args.end,
                sample_times=sample_times, value_format=args.format,
                max_changes=args.max_changes,
            )
    emit_report(report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
