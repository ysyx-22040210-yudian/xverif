"""Stateless xbit adapter — deterministic bit/expression calculator."""
from __future__ import annotations

from typing import Any, Optional

from xverif_mcp.errors import error_payload
from xverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


def _bit_json(argv: list) -> dict:
    return runner.run_json("xbit", argv)


def _bit_text(argv: list) -> str:
    r = runner.run_text("xbit", argv)
    return r if isinstance(r, str) else str(r)


def bit_conv(value: str, width: int = 0, signed: bool = False,
             unsigned: bool = False, state: str = "2",
             output_format: str = "json") -> Any:
    """Convert a value between radices and SV literal formats."""
    argv = ["conv", value, "--json", "--state", state]
    if width:
        argv.extend(["--width", str(width)])
    if signed:
        argv.append("--signed")
    if unsigned:
        argv.append("--unsigned")
    if output_format == "json":
        return _bit_json(argv)
    return _bit_text(argv)


def bit_eval(expr: str, vars: Optional[dict] = None, width: int = 0,
             signed: bool = False, unsigned: bool = False,
             state: str = "2", output_format: str = "json") -> Any:
    """Evaluate a deterministic bit/expression calculation."""
    argv = ["eval", expr, "--json", "--state", state]
    if vars:
        for k, v in vars.items():
            argv.extend(["--var", f"{k}={v}"])
    if width:
        argv.extend(["--width", str(width)])
    if signed:
        argv.append("--signed")
    if unsigned:
        argv.append("--unsigned")
    if output_format == "json":
        return _bit_json(argv)
    return _bit_text(argv)


def bit_slice(value: str, msb: int, lsb: int, state: str = "2",
              output_format: str = "json") -> Any:
    """Extract a bit slice from a value."""
    argv = ["slice", value, str(msb), str(lsb), "--json", "--state", state]
    if output_format == "json":
        return _bit_json(argv)
    return _bit_text(argv)


def bit_check(expr: str, vars: Optional[dict] = None,
              values: Optional[str] = None, state: str = "2",
              output_format: str = "json") -> Any:
    """Check a bit expression against expected values."""
    argv = ["check", "--json", "--state", state, "--expr", expr]
    if vars:
        for k, v in vars.items():
            argv.extend(["--var", f"{k}={v}"])
    if values:
        argv.extend(["--values", values])
    if output_format == "json":
        return _bit_json(argv)
    return _bit_text(argv)
