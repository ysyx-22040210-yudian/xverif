"""Stateless xentry adapter — deterministic entry field decoder.

xentry natively supports JSON-on-stdin: just pass a JSON request string.
No subcommand parsing needed — xentry reads {"api_version": "xentry.v1", ...}
and dispatches internally.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from xverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


def _xentry_request(action: str, config_path: Optional[str] = None,
                    input_path: Optional[str] = None,
                    config: Optional[dict] = None,
                    fragments: Optional[list] = None,
                    output_format: str = "json") -> Any:
    req: dict = {"api_version": "xentry.v1", "action": action}
    if config_path:
        req["config_path"] = config_path
    if input_path:
        req["input_path"] = input_path
    if config:
        req["config"] = config
    if fragments:
        req["fragments"] = fragments
    if output_format == "json":
        req["output"] = {"format": "json"}
    return runner.run_json("xentry", ["-"], json.dumps(req))


def entry_decode(config_path: str, input_path: str,
                 output_format: str = "json") -> Any:
    """Decode multi-beat fragments into raw field slices per config."""
    return _xentry_request("decode", config_path=config_path,
                           input_path=input_path, output_format=output_format)


def entry_explain(config_path: str, output_format: str = "json") -> Any:
    """Explain the field layout defined by a config."""
    return _xentry_request("explain", config_path=config_path,
                           output_format=output_format)


def entry_validate(config_path: str, input_path: Optional[str] = None,
                   output_format: str = "json") -> Any:
    """Validate a config (and optionally an input) without decoding."""
    return _xentry_request("validate", config_path=config_path,
                           input_path=input_path, output_format=output_format)
