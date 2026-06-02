from __future__ import annotations

import argparse
import json
import os
import sys

from .api import dispatch_request
from .config import load_config_file
from .decode import decode_entry, explain_config, validate_entry
from .errors import JsonError
from .format import dumps, error_response
from .fragments import load_fragments_file


HELP_TEXT = """xentry - JSON-first multi-beat entry field decoder

Usage:
  xentry -h
  xentry -help
  xentry -
  xentry request.json
  xentry '{"api_version":"xentry.v1","action":"decode",...}'
  xentry decode --config entry.yaml --input fragments.jsonl --json

JSON request:
  {
    "api_version": "xentry.v1",
    "action": "decode",
    "config": {
      "name": "entry",
      "version": 1,
      "total_bits": 16,
      "fragment_byte_order": "msb_first",
      "bit_numbering": "byte_lsb0",
      "fields": [{"name": "low", "bits": "[7:0]"}]
    },
    "fragments": [
      {"seq": 0, "data": "0x1234", "valid_lsb": 0, "valid_width": 16}
    ]
  }

Actions:
  decode    拼接 fragments 并输出 raw field slices
  explain   解释 config 字段布局
  validate  校验 config 和可选 fragments
"""


def emit(payload: dict, *, pretty: bool) -> int:
    print(dumps(payload, pretty=pretty))
    return 0 if payload.get("ok") else 1


def load_request_arg(arg: str | None) -> dict:
    if arg is None or arg == "-":
        text = sys.stdin.read()
    elif arg.lstrip().startswith("{"):
        text = arg
    else:
        with open(arg, "r", encoding="utf-8") as fh:
            text = fh.read()
    try:
        request = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonError(f"invalid JSON request: {exc}") from exc
    if not isinstance(request, dict):
        raise JsonError("JSON request must be an object")
    return request


def json_main(argv: list[str]) -> int:
    arg = argv[0] if argv else None
    try:
        request = load_request_arg(arg)
        payload = dispatch_request(request)
        pretty = bool(request.get("output", {}).get("pretty", False)) if isinstance(request.get("output"), dict) else False
        return emit(payload, pretty=pretty)
    except Exception as exc:
        action = ""
        request_id = None
        if "request" in locals() and isinstance(request, dict):
            action = str(request.get("action", ""))
            request_id = request.get("request_id")
        return emit(error_response(exc, action=action, request_id=request_id), pretty=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xentry", description="deterministic entry field decoder")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("decode")
    add_common(p)
    p.add_argument("--config", required=True)
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("explain")
    add_common(p)
    p.add_argument("--config", required=True)
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("validate")
    add_common(p)
    p.add_argument("--config", required=True)
    p.add_argument("--input")
    p.set_defaults(func=cmd_validate)
    return parser


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")


def cmd_decode(args: argparse.Namespace) -> dict:
    return decode_entry(load_config_file(args.config), load_fragments_file(args.input))


def cmd_explain(args: argparse.Namespace) -> dict:
    return explain_config(load_config_file(args.config))


def cmd_validate(args: argparse.Namespace) -> dict:
    fragments = load_fragments_file(args.input) if args.input else None
    return validate_entry(load_config_file(args.config), fragments)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 1 and argv[0] in {"-h", "-help"}:
        print(HELP_TEXT)
        return 0
    if not argv or argv[0] == "-" or (len(argv) == 1 and (argv[0].lstrip().startswith("{") or os.path.exists(argv[0]))):
        return json_main(argv[:1])
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        return emit(payload, pretty=args.pretty)
    except Exception as exc:
        return emit(error_response(exc, action=args.command), pretty=True)


if __name__ == "__main__":
    sys.exit(main())
