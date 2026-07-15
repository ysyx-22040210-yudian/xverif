"""Stateful kdebug adapter for design/wave sessions."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from kverif_mcp.config import (default_kdebug_bin, mcp_backend,
                                startup_timeout, request_timeout)
from kverif_mcp.sessions.session_manager import McpSessionManager

Json = Dict[str, Any]


class KverifDebugAdapter:
    def __init__(self, mode: Optional[str] = None,
                 startup_timeout_sec: Optional[float] = None,
                 request_timeout_sec: Optional[float] = None) -> None:
        if startup_timeout_sec is None:
            startup_timeout_sec = startup_timeout()
        if request_timeout_sec is None:
            request_timeout_sec = request_timeout()
        self.mode = mode or mcp_backend()
        self._sessions = McpSessionManager(
            mode=self.mode, kdebug_bin=default_kdebug_bin(),
            startup_timeout_sec=startup_timeout_sec,
            request_timeout_sec=request_timeout_sec)

    def ping(self) -> str:
        return "pong"

    def actions(self) -> Json:
        return self._one_shot({"api_version": "kdebug.v1", "action": "actions"})

    def schema(self, action: str, kind: str = "request") -> Json:
        return self._one_shot({"api_version": "kdebug.v1", "action": "schema",
                               "args": {"action": action, "kind": kind}})

    def request(self, request: dict, output_format: str = "json") -> Any:
        from kverif_mcp.runner import StatelessCliRunner
        runner = StatelessCliRunner()
        req = dict(request)
        req.setdefault("api_version", "kdebug.v1")
        req.setdefault("output", {})
        wants_json = output_format in ("json", "envelope")
        if isinstance(req["output"], dict):
            if wants_json:
                req["output"].setdefault("format", "json")
            else:
                req["output"].pop("format", None)
        return runner.run_json("kdebug", ["-"], json.dumps(req))

    def _one_shot(self, req: Json) -> Json:
        from kverif_mcp.runner import StatelessCliRunner
        req = dict(req)
        req.setdefault("output", {})
        if isinstance(req["output"], dict):
            req["output"]["format"] = "json"
        return StatelessCliRunner().run_json("kdebug", ["--json", "-"],
                                              json.dumps(req))

    def session_open(self, name: str, **kwargs: Any) -> Json:
        return self._sessions.open_session(name=name, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self._sessions.list_sessions()

    def session_close(self, key: str) -> Json:
        return self._sessions.close_session(key)

    def query(self, **kwargs: Any) -> Any:
        return self._sessions.query(**kwargs)
