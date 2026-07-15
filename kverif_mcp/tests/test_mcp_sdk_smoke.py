"""FastMCP registration tests for kverif-mcp."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import anyio
import pytest

KDEBUG_DIR = Path(__file__).resolve().parents[2] / "kdebug"
sys.path = [
    path for path in sys.path
    if Path(path or os.getcwd()).resolve() != KDEBUG_DIR
]

sys.modules.pop("mcp", None)
pytest.importorskip("mcp")


POLICY_ENV = [
    "KVERIF_MCP_ENABLE_COMMON",
    "KVERIF_MCP_ENABLE_DEBUG",
    "KVERIF_MCP_ENABLE_COV",
    "KVERIF_MCP_ENABLE_BIT",
    "KVERIF_MCP_ENABLE_ENTRY",
    "KVERIF_MCP_ENABLE_LOC",
    "KVERIF_MCP_ENABLE_CONTEXT",
    "KVERIF_MCP_ENABLE_CONTEXT_WRITE",
    "KVERIF_MCP_ENABLE_SVA",
    "KVERIF_MCP_ENABLE_WRITE",
]


def _server(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None):
    for name in POLICY_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in (overrides or {}).items():
        monkeypatch.setenv(name, value)
    if "kverif_mcp.server" in sys.modules:
        return importlib.reload(sys.modules["kverif_mcp.server"])
    return importlib.import_module("kverif_mcp.server")


def _tool_names(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None) -> set[str]:
    server = _server(monkeypatch, overrides)

    async def _run() -> set[str]:
        tools = await server.mcp.list_tools()
        return {tool.name for tool in tools}

    return anyio.run(_run)


def _call_tool(monkeypatch: pytest.MonkeyPatch, name: str, args: dict | None = None,
               overrides: dict[str, str] | None = None):
    server = _server(monkeypatch, overrides)

    async def _run():
        result = await server.mcp.call_tool(name, args or {})
        if isinstance(result, tuple):
            return result
        return result, None

    return anyio.run(_run)


def test_mcp_server_initialize(monkeypatch: pytest.MonkeyPatch):
    server = _server(monkeypatch)
    assert server.mcp.name == "kverif"


def test_mcp_tools_list(monkeypatch: pytest.MonkeyPatch):
    """tools/list must include all expected read-only tool names by default."""
    names = _tool_names(monkeypatch)
    assert "kverif_ping" in names
    assert "kverif_debug_query" in names
    assert "kverif_debug_session_open" in names
    assert "kverif_cov_session_open" in names
    assert "kverif_cov_query" in names
    assert "kverif_debug_list_actions" in names
    assert "kverif_debug_get_schema" in names
    assert "kverif_debug_session_list" in names
    assert "kverif_debug_session_use" not in names
    assert "kverif_debug_session_close" in names
    assert "kverif_session_open" not in names
    assert "kverif_session_list" not in names
    assert "kverif_session_use" not in names
    assert "kverif_session_close" not in names
    assert "kverif_debug_raw_request" in names
    assert "kverif_tools" in names
    assert "kverif_bit_eval" in names
    assert "kverif_entry_decode" in names
    assert "kverif_loc_resolve" in names
    assert "kverif_context_status" in names
    assert "kverif_sva_explain_property" in names
    assert "kverif_context_init_config" not in names


def test_mcp_ping_call(monkeypatch: pytest.MonkeyPatch):
    """Calling kverif_ping should return a string containing 'pong'."""
    content, structured = _call_tool(monkeypatch, "kverif_ping")
    assert "pong" in content[0].text.lower()
    assert structured["result"] == "pong"


def test_tool_group_disable_sva(monkeypatch: pytest.MonkeyPatch):
    env = {"KVERIF_MCP_ENABLE_SVA": "0"}
    names = _tool_names(monkeypatch, env)
    assert "kverif_sva_explain_property" not in names
    assert "kverif_debug_query" in names

    content, _ = _call_tool(monkeypatch, "kverif_tools", {}, env)
    payload = json.loads(content[0].text)
    catalog = {tool["name"] for tool in payload["tools"]}
    assert "kverif_sva_explain_property" not in catalog


def test_tool_group_disable_debug(monkeypatch: pytest.MonkeyPatch):
    names = _tool_names(monkeypatch, {"KVERIF_MCP_ENABLE_DEBUG": "0"})
    assert "kverif_debug_query" not in names
    assert "kverif_debug_session_open" not in names
    assert "kverif_wave_value_at" not in names
    assert "kverif_cov_query" in names
    assert "kverif_bit_eval" in names


def test_tool_group_disable_cov(monkeypatch: pytest.MonkeyPatch):
    names = _tool_names(monkeypatch, {"KVERIF_MCP_ENABLE_COV": "0"})
    assert "kverif_cov_query" not in names
    assert "kverif_cov_session_open" not in names
    assert "kverif_debug_query" in names


def test_cov_session_fake_lifecycle(monkeypatch: pytest.MonkeyPatch):
    overrides = {
        "KVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "KVERIF_MCP_BACKEND": "direct",
    }
    server = _server(monkeypatch, overrides)

    async def _run():
        opened = await server.mcp.call_tool(
            "kverif_cov_session_open",
            {"name": "cov_fake", "vdb": "fake"},
        )
        queried = await server.mcp.call_tool(
            "kverif_cov_query",
            {"session": "cov_fake", "action": "cov.holes",
             "args": {"metrics": ["toggle", "branch"]},
             "limits": {"max_items": 1},
             "output_format": "json"},
        )
        closed = await server.mcp.call_tool(
            "kverif_cov_session_close",
            {"name": "cov_fake"},
        )
        return opened, queried, closed

    opened, queried, _ = anyio.run(_run)
    opened_payload = json.loads(opened[0].text)
    queried_payload = json.loads(queried[0].text)
    assert opened_payload["ok"] is True
    assert queried_payload["summary"]["matched_count"] == 3
    assert queried_payload["summary"]["returned"] == 1


@pytest.mark.parametrize(
    ("env_name", "missing", "present"),
    [
        ("KVERIF_MCP_ENABLE_BIT", "kverif_bit_eval", "kverif_entry_decode"),
        ("KVERIF_MCP_ENABLE_ENTRY", "kverif_entry_decode", "kverif_bit_eval"),
        ("KVERIF_MCP_ENABLE_LOC", "kverif_loc_resolve", "kverif_bit_eval"),
        ("KVERIF_MCP_ENABLE_CONTEXT", "kverif_context_status", "kverif_bit_eval"),
    ],
)
def test_tool_group_disable_stateless_groups(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    missing: str,
    present: str,
):
    names = _tool_names(monkeypatch, {env_name: "0"})
    assert missing not in names
    assert present in names


def test_tool_group_disable_common(monkeypatch: pytest.MonkeyPatch):
    names = _tool_names(monkeypatch, {"KVERIF_MCP_ENABLE_COMMON": "0"})
    assert "kverif_ping" not in names
    assert "kverif_tools" not in names
    assert "kverif_tool_help" not in names
    assert "kverif_debug_query" in names


def test_context_write_requires_both_switches(monkeypatch: pytest.MonkeyPatch):
    assert "kverif_context_init_config" not in _tool_names(monkeypatch)
    assert "kverif_context_init_config" not in _tool_names(
        monkeypatch,
        {"KVERIF_MCP_ENABLE_CONTEXT_WRITE": "1"},
    )
    enabled = {
        "KVERIF_MCP_ENABLE_CONTEXT": "1",
        "KVERIF_MCP_ENABLE_CONTEXT_WRITE": "1",
        "KVERIF_MCP_ENABLE_WRITE": "1",
    }
    names = _tool_names(monkeypatch, enabled)
    assert "kverif_context_init_config" in names

    content, _ = _call_tool(monkeypatch, "kverif_tools", {}, enabled)
    payload = json.loads(content[0].text)
    catalog = {tool["name"] for tool in payload["tools"]}
    assert "kverif_context_init_config" in catalog


def test_invalid_bool_policy_warning(monkeypatch: pytest.MonkeyPatch):
    content, _ = _call_tool(
        monkeypatch,
        "kverif_tools",
        {},
        {"KVERIF_MCP_ENABLE_SVA": "maybe"},
    )
    payload = json.loads(content[0].text)
    assert "kverif_sva_explain_property" in {tool["name"] for tool in payload["tools"]}
    assert payload["policy"]["warnings"]
    assert "KVERIF_MCP_ENABLE_SVA" in payload["policy"]["warnings"][0]


def test_tool_help_disabled_tool_is_hidden(monkeypatch: pytest.MonkeyPatch):
    content, _ = _call_tool(
        monkeypatch,
        "kverif_tool_help",
        {"name": "kverif_sva_explain_property"},
        {"KVERIF_MCP_ENABLE_SVA": "0"},
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TOOL_NOT_ENABLED"


def test_output_path_in_tool_schema(monkeypatch: pytest.MonkeyPatch):
    """kverif_ping schema must expose kverif_output_path and kverif_output_append."""
    server = _server(monkeypatch)

    async def _run():
        tools = await server.mcp.list_tools()
        ping = next(t for t in tools if t.name == "kverif_ping")
        schema = ping.inputSchema
        props = schema.get("properties", {})
        assert "kverif_output_path" in props
        assert "kverif_output_append" in props

    anyio.run(_run)


def test_output_path_writes_response(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Calling a tool with kverif_output_path writes the response to that file."""
    output_file = tmp_path / "rsp.txt"
    content, _ = _call_tool(
        monkeypatch,
        "kverif_ping",
        {"kverif_output_path": str(output_file)},
    )
    assert "pong" in content[0].text.lower()
    assert output_file.exists()
    assert "pong" in output_file.read_text().lower()


def test_output_path_append(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """kverif_output_append=True appends instead of overwriting."""
    output_file = tmp_path / "rsp.txt"
    output_file.write_text("existing\n")
    _call_tool(monkeypatch, "kverif_ping",
               {"kverif_output_path": str(output_file), "kverif_output_append": True})
    text = output_file.read_text()
    assert text.startswith("existing\n")
    assert "pong" in text.lower()


def test_output_path_does_not_affect_response(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Not passing kverif_output_path has no effect on normal response."""
    content, _ = _call_tool(monkeypatch, "kverif_ping", {})
    assert "pong" in content[0].text.lower()


def test_output_path_invalid_dir_no_crash(monkeypatch: pytest.MonkeyPatch):
    """If the output path is invalid, the tool still returns normally."""
    content, _ = _call_tool(
        monkeypatch,
        "kverif_ping",
        {"kverif_output_path": "/nonexistent/dir/rsp.txt"},
    )
    assert "pong" in content[0].text.lower()


def test_batch_fake_lifecycle(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """kverif_batch with fake cov session + ping + bit_eval in one file."""
    batch_file = tmp_path / "batch.ndjson"
    output_file = tmp_path / "results.ndjson"

    overrides = {
        "KVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "KVERIF_MCP_BACKEND": "direct",
    }

    batch_file.write_text("\n".join([
        json.dumps({"tool": "kverif_cov_session_open",
                     "args": {"name": "cov_fake", "vdb": "fake"}}),
        json.dumps({"tool": "kverif_cov_query",
                     "args": {"session": "cov_fake", "action": "cov.holes",
                              "args": {"metrics": ["line"], "limits": {"max_items": 2}},
                              "output_format": "json"}}),
        json.dumps({"tool": "kverif_cov_session_close",
                     "args": {"name": "cov_fake"}}),
        json.dumps({"tool": "kverif_ping", "args": {}}),
        json.dumps({"tool": "kverif_bit_eval",
                     "args": {"expr": "2 + 3"}}),
    ]) + "\n")

    content, _ = _call_tool(
        monkeypatch,
        "kverif_batch",
        {"batch_file": str(batch_file), "output_file": str(output_file)},
        overrides,
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is True
    assert payload["total"] == 5
    assert payload["ok_count"] == 5
    assert payload["failed_count"] == 0

    lines = [json.loads(l) for l in output_file.read_text().splitlines() if l]
    assert len(lines) == 5
    assert all(r["ok"] for r in lines)


def test_batch_format_errors(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Invalid JSON and missing tool field are written as errors, not executed."""
    batch_file = tmp_path / "batch.ndjson"
    output_file = tmp_path / "results.ndjson"

    overrides = {
        "KVERIF_HOME": str(Path(__file__).resolve().parents[2]),
        "KVERIF_MCP_BACKEND": "direct",
    }

    batch_file.write_text("\n".join([
        "not json at all",
        json.dumps({"args": {"expr": "1+1"}}),  # missing tool
        json.dumps({"tool": "kverif_ping", "args": {}}),
    ]) + "\n")

    content, _ = _call_tool(
        monkeypatch,
        "kverif_batch",
        {"batch_file": str(batch_file), "output_file": str(output_file)},
        overrides,
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is True
    assert payload["total"] == 3
    assert payload["ok_count"] == 1
    assert payload["failed_count"] == 2

    lines = [json.loads(l) for l in output_file.read_text().splitlines() if l]
    assert len(lines) == 3
    assert lines[0]["tool"] is None
    assert lines[0]["ok"] is False
    assert "INVALID_JSON" in lines[0]["error"]
    assert lines[1]["tool"] is None
    assert lines[1]["ok"] is False
    assert "MISSING_TOOL_FIELD" in lines[1]["error"]
    assert lines[2]["tool"] == "kverif_ping"
    assert lines[2]["ok"] is True


def test_batch_file_not_found(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """kverif_batch on a nonexistent file returns FILE_NOT_FOUND error."""
    content, _ = _call_tool(
        monkeypatch,
        "kverif_batch",
        {"batch_file": "/nonexistent/batch.ndjson",
         "output_file": str(tmp_path / "out.ndjson")},
    )
    payload = json.loads(content[0].text)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "FILE_NOT_FOUND"
