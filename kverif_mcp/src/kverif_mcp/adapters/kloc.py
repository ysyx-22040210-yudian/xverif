"""Stateless kloc adapter — UVM log location resolver.

kloc does NOT support JSON-on-stdin. Each call uses subprocess + CLI args.
"""
from __future__ import annotations

from typing import Any, Optional

from kverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


def loc_resolve(loc_id: str, map_path: str,
                output_format: str = "json") -> Any:
    """Resolve a loc_id (L_XXXXXXXX) to source file:line."""
    argv = ["resolve", loc_id, "--map", map_path]
    if output_format == "json":
        argv.append("--json")
        return runner.run_json("kloc", argv)
    return runner.run_text("kloc", argv)


def loc_context(loc_id: str, map_path: str, before: int = 20,
                after: int = 20, output_format: str = "kout") -> Any:
    """Resolve a loc_id and show surrounding source lines."""
    argv = ["context", loc_id, "--map", map_path,
            "--before", str(before), "--after", str(after)]
    if output_format == "json":
        argv.append("--json")
        return runner.run_json("kloc", argv)
    return runner.run_text("kloc", argv)


def loc_stats(log_path: str, map_path: Optional[str] = None,
              top: int = 20, output_format: str = "json") -> Any:
    """Count loc_id frequency in a simulation log."""
    argv = ["stats", log_path, "--top", str(top)]
    if map_path:
        argv.extend(["--map", map_path])
    if output_format == "json":
        argv.append("--json")
        return runner.run_json("kloc", argv)
    return runner.run_text("kloc", argv)


def loc_annotate(log_path: str, map_path: Optional[str] = None,
                 output_format: str = "kout") -> Any:
    """Insert location hints into a simulation log."""
    argv = ["annotate", log_path]
    if map_path:
        argv.extend(["--map", map_path])
    return runner.run_text("kloc", argv)
