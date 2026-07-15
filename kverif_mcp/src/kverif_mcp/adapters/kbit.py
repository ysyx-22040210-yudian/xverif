"""Stateless kbit adapter — deterministic bit/expression calculator."""
from __future__ import annotations

from typing import Any, Optional

from kverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


def bit_conv(value: str, width: int = 0, signed: bool = False,
             unsigned: bool = False, state: str = "2",
             output_format: str = "json") -> Any:
    """Convert a value between radices and SV literal formats."""
    argv = ["conv", value, "--state", state]
    if width:
        argv.extend(["--width", str(width)])
    if signed:
        argv.append("--signed")
    if unsigned:
        argv.append("--unsigned")
    if output_format == "json":
        argv.append("--json")
        return runner.run_json("kbit", argv)
    return runner.run_text("kbit", argv)


def bit_eval(expr: str, vars: Optional[dict] = None, width: int = 0,
             signed: bool = False, unsigned: bool = False,
             state: str = "2", output_format: str = "json") -> Any:
    """Evaluate a deterministic bit/expression calculation."""
    argv = ["eval", expr, "--state", state]
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
        argv.append("--json")
        return runner.run_json("kbit", argv)
    return runner.run_text("kbit", argv)


def bit_slice(value: str, msb: int, lsb: int, state: str = "2",
              output_format: str = "json") -> Any:
    """Extract a bit slice from a value."""
    argv = ["slice", value, str(msb), str(lsb), "--state", state]
    if output_format == "json":
        argv.append("--json")
        return runner.run_json("kbit", argv)
    return runner.run_text("kbit", argv)


def bit_check(expr: str, vars: Optional[dict] = None,
              values: Optional[str] = None, state: str = "2",
              output_format: str = "json") -> Any:
    """Check a bit expression against expected values."""
    argv = ["check", "--state", state, "--expr", expr]
    if vars:
        for k, v in vars.items():
            argv.extend(["--var", f"{k}={v}"])
    if values:
        argv.extend(["--values", values])
    if output_format == "json":
        argv.append("--json")
        return runner.run_json("kbit", argv)
    return runner.run_text("kbit", argv)
