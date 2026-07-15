"""Stateless kberif adapter — project context / summary cards.

Read-only tools are always enabled. Write tools require KVERIF_MCP_ENABLE_WRITE=1.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from kverif_mcp.config import enable_write
from kverif_mcp.errors import write_disabled
from kverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


def _cwd(project_root: Optional[str]) -> str:
    return project_root or os.getcwd()


# ------------------------------------------------------------------
# read-only tools
# ------------------------------------------------------------------


def context_status(project_root: Optional[str] = None,
                   output_format: str = "json") -> Any:
    """Check kberif project status."""
    cwd = _cwd(project_root)
    argv = ["--json", "status"] if output_format == "json" else ["status"]
    return runner.run_json("kberif", argv, cwd=cwd)


def context_list_topics(project_root: Optional[str] = None,
                        output_format: str = "json") -> Any:
    """List all known context topics."""
    cwd = _cwd(project_root)
    argv = (["--json", "list-topics"] if output_format == "json"
            else ["list-topics"])
    return runner.run_json("kberif", argv, cwd=cwd)


def context_brief(mode: str = "debug", project_root: Optional[str] = None,
                  output_format: str = "kout") -> Any:
    """Generate a context brief (summary) for the given mode."""
    cwd = _cwd(project_root)
    argv = ["brief", "--mode", mode]
    if output_format == "json":
        argv.insert(0, "--json")
        return runner.run_json("kberif", argv, cwd=cwd)
    return runner.run_text("kberif", argv, cwd=cwd)


def context_get(topic: str, detail: bool = False,
                project_root: Optional[str] = None,
                output_format: str = "kout") -> Any:
    """Get a topic card (optionally with detail content)."""
    cwd = _cwd(project_root)
    argv = ["get", topic]
    if detail:
        argv.append("--detail")
    if output_format == "json":
        argv.insert(0, "--json")
        return runner.run_json("kberif", argv, cwd=cwd)
    return runner.run_text("kberif", argv, cwd=cwd)


def context_detail(topic: str, project_root: Optional[str] = None,
                   output_format: str = "markdown") -> Any:
    """Get the full detail markdown for a topic."""
    cwd = _cwd(project_root)
    return runner.run_text("kberif", ["detail", topic], cwd=cwd)


def context_validate(project_root: Optional[str] = None,
                     output_format: str = "json") -> Any:
    """Validate project cards and detail files."""
    cwd = _cwd(project_root)
    argv = ["validate"]
    if output_format == "json":
        argv.insert(0, "--json")
        return runner.run_json("kberif", argv, cwd=cwd)
    return runner.run_text("kberif", argv, cwd=cwd)


# ------------------------------------------------------------------
# write tools (protected by KVERIF_MCP_ENABLE_WRITE)
# ------------------------------------------------------------------


def context_config_init(kind: str, project_root: Optional[str] = None) -> Any:
    """Initialize kberif kind.toml config for a project kind."""
    if not enable_write():
        return write_disabled("context_config_init")
    cwd = _cwd(project_root)
    return runner.run_json("kberif", ["config", "init", "--kind", kind],
                           cwd=cwd)


def context_init(model: str, project_root: Optional[str] = None) -> Any:
    """Initialize kberif project structure with an external agent model."""
    if not enable_write():
        return write_disabled("context_init")
    cwd = _cwd(project_root)
    return runner.run_json("kberif", ["init", "--model", model], cwd=cwd)


def context_repair(project_root: Optional[str] = None) -> Any:
    """Repair kberif catalog index."""
    if not enable_write():
        return write_disabled("context_repair")
    cwd = _cwd(project_root)
    return runner.run_json("kberif", ["repair-catalog"], cwd=cwd)
