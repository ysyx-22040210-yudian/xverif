from __future__ import annotations

import argparse
import json
import os
import sys

from .api import dispatch_request
from .config import load_config_file
from .decode import decode_entry, explain_config, validate_entry
from .errors import JsonError
from .format import dumps, error_response, to_xout
from .fragments import load_fragments_file


HELP_TEXT = """xentry - multi-beat entry field decoder

Usage:
  xentry -h
  xentry -help
  xentry decode --config entry.yaml --input fragments.jsonl [--json]
  xentry explain --config entry.yaml [--json]
  xentry validate --config entry.yaml [--input fragments.jsonl]
  xentry -
  xentry request.json
  xentry '{"api_version":"xentry.v1","action":"decode",...}'

Parameter commands are the normal human CLI. JSON request remains available
for scripts, agents, and regression tests:
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


def emit(payload: dict, *, pretty: bool, json_mode: bool = False) -> int:
    print(dumps(payload, pretty=pretty) if json_mode else to_xout(payload), end="" if not json_mode else "\n")
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


def json_main(argv: list[str], *, json_mode: bool = False) -> int:
    arg = argv[0] if argv else None
    try:
        request = load_request_arg(arg)
        payload = dispatch_request(request)
        pretty = bool(request.get("output", {}).get("pretty", False)) if isinstance(request.get("output"), dict) else False
        request_json_mode = bool(
            isinstance(request.get("output"), dict)
            and request["output"].get("format") == "json"
        )
        return emit(payload, pretty=pretty, json_mode=json_mode or request_json_mode)
    except Exception as exc:
        action = ""
        request_id = None
        if "request" in locals() and isinstance(request, dict):
            action = str(request.get("action", ""))
            request_id = request.get("request_id")
        return emit(error_response(exc, action=action, request_id=request_id), pretty=True, json_mode=json_mode)


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
    json_mode = False
    if "--json" in argv:
        json_mode = True
        argv = [arg for arg in argv if arg != "--json"]
    if "--text" in argv or "--xout" in argv:
        argv = [arg for arg in argv if arg not in {"--text", "--xout"}]
    if not argv or argv[0] == "-" or (len(argv) == 1 and (argv[0].lstrip().startswith("{") or os.path.exists(argv[0]))):
        return json_main(argv[:1], json_mode=json_mode)
    parser = build_parser()
    args = parser.parse_args(argv)
    args.json = bool(getattr(args, "json", False) or json_mode)
    try:
        payload = args.func(args)
        return emit(payload, pretty=args.pretty, json_mode=args.json)
    except Exception as exc:
        return emit(error_response(exc, action=args.command), pretty=True, json_mode=args.json)


if __name__ == "__main__":
    sys.exit(main())
