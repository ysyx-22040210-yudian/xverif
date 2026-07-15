"""Stateless kentry adapter — deterministic entry field decoder.

kentry natively supports JSON-on-stdin: just pass a JSON request string.
No subcommand parsing needed — kentry reads {"api_version": "kentry.v1", ...}
and dispatches internally.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from kverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


def _kentry_request(action: str, config_path: Optional[str] = None,
                    input_path: Optional[str] = None,
                    config: Optional[dict] = None,
                    fragments: Optional[list] = None,
                    output_format: str = "json") -> Any:
    req: dict = {"api_version": "kentry.v1", "action": action}
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
    return runner.run_json("kentry", ["-"], json.dumps(req))


def entry_decode(config_path: str = "", input_path: str = "",
                 config: Optional[dict] = None,
                 fragments: Optional[list] = None,
                 output_format: str = "json") -> Any:
    """Decode multi-beat fragments into raw field slices per config."""
    return _kentry_request("decode", config_path=config_path or None,
                           input_path=input_path or None,
                           config=config, fragments=fragments,
                           output_format=output_format)


def entry_explain(config_path: str, output_format: str = "json") -> Any:
    """Explain the field layout defined by a config."""
    return _kentry_request("explain", config_path=config_path,
                           output_format=output_format)


def entry_validate(config_path: str = "", input_path: Optional[str] = None,
                   config: Optional[dict] = None,
                   fragments: Optional[list] = None,
                   output_format: str = "json") -> Any:
    """Validate a config (and optionally an input) without decoding."""
    return _kentry_request("validate", config_path=config_path or None,
                           input_path=input_path,
                           config=config, fragments=fragments,
                           output_format=output_format)
