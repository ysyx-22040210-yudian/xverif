"""Focused tests for the MCP action smoke script."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "test_actions.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("test_actions_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, args: dict | None = None):
        args = args or {}
        self.calls.append((name, args))
        if name == "kverif_debug_list_actions":
            payload = {
                "ok": True,
                "data": {"implemented": ["counter.statistics", "value.at"]},
            }
        elif name == "kverif_debug_get_schema":
            payload = {
                "ok": True,
                "data": {"action": args["action"], "kind": args["kind"]},
            }
        elif name == "kverif_debug_session_open":
            payload = {"ok": True, "summary": {"mode": "fake"}}
        else:
            payload = {"ok": True}
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])


def test_schema_smoke_uses_runtime_action_catalog():
    script = _load_script()
    session = FakeSession()

    passed, failed = asyncio.run(script.test_all_schemas(session))

    assert (passed, failed) == (4, 0)
    schema_calls = [
        args for name, args in session.calls
        if name == "kverif_debug_get_schema"
    ]
    assert schema_calls == [
        {"action": "counter.statistics", "kind": "request"},
        {"action": "value.at", "kind": "request"},
        {"action": "counter.statistics", "kind": "response"},
        {"action": "value.at", "kind": "response"},
    ]


def test_open_session_does_not_send_removed_reuse_arg():
    script = _load_script()
    session = FakeSession()
    cfg = {
        "session_name": "smoke_session",
        "daidir": "simv.daidir",
        "fsdb": "waves.fsdb",
    }

    assert asyncio.run(script._open_session(session, cfg)) is True

    open_calls = [
        args for name, args in session.calls
        if name == "kverif_debug_session_open"
    ]
    assert open_calls == [{
        "name": "smoke_session",
        "daidir": "simv.daidir",
        "fsdb": "waves.fsdb",
    }]
