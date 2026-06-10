"""Stateless xberif adapter — project context / summary cards.

Read-only tools are always enabled. Write tools require XVERIF_MCP_ENABLE_WRITE=1.
"""
from __future__ import annotations

from typing import Any, Optional

from xverif_mcp.config import enable_write
from xverif_mcp.errors import error_payload, write_disabled
from xverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


# ------------------------------------------------------------------
# read-only tools
# ------------------------------------------------------------------


def context_status(project_root: Optional[str] = None,
                   output_format: str = "json") -> Any:
    """Check xberif project status."""
    argv = ["--json", "status"] if output_format == "json" else ["status"]
    return runner.run_json("xberif", argv)


def context_list_topics(project_root: Optional[str] = None,
                        output_format: str = "json") -> Any:
    """List all known context topics."""
    argv = ["--json", "list-topics"] if output_format == "json" else ["list-topics"]
    return runner.run_json("xberif", argv)


def context_brief(mode: str = "debug", project_root: Optional[str] = None,
                  output_format: str = "xout") -> Any:
    """Generate a context brief (summary) for the given mode."""
    argv = ["brief", "--mode", mode]
    if output_format == "json":
        argv.insert(0, "--json")
        return runner.run_json("xberif", argv)
    return runner.run_text("xberif", argv)


def context_get(topic: str, detail: bool = False,
                project_root: Optional[str] = None,
                output_format: str = "xout") -> Any:
    """Get a topic card (optionally with detail content)."""
    argv = ["get", topic]
    if detail:
        argv.append("--detail")
    if output_format == "json":
        argv.insert(0, "--json")
        return runner.run_json("xberif", argv)
    return runner.run_text("xberif", argv)


def context_detail(topic: str, project_root: Optional[str] = None,
                   output_format: str = "markdown") -> Any:
    """Get the full detail markdown for a topic."""
    return runner.run_text("xberif", ["detail", topic])


def context_validate(project_root: Optional[str] = None,
                     output_format: str = "json") -> Any:
    """Validate project cards and detail files."""
    argv = ["validate"]
    if output_format == "json":
        argv.insert(0, "--json")
        return runner.run_json("xberif", argv)
    return runner.run_text("xberif", argv)


# ------------------------------------------------------------------
# write tools (protected by XVERIF_MCP_ENABLE_WRITE)
# ------------------------------------------------------------------


def context_config_init(kind: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif kind.toml config for a project kind."""
    if not enable_write():
        return write_disabled("context_config_init")
    return runner.run_json("xberif", ["config", "init", "--kind", kind])


def context_init(model: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif project structure with an external agent model."""
    if not enable_write():
        return write_disabled("context_init")
    return runner.run_json("xberif", ["init", "--model", model])


def context_repair(project_root: Optional[str] = None) -> Any:
    """Repair xberif catalog index."""
    if not enable_write():
        return write_disabled("context_repair")
    return runner.run_json("xberif", ["repair-catalog"])
