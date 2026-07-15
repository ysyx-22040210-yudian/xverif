"""Stateful kcov adapter for VCS/Verdi coverage database queries."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from kverif_mcp.config import (default_kcov_bin, mcp_backend,
                                kcov_startup_timeout, kcov_request_timeout)
from kverif_mcp.sessions.session_manager import McpSessionManager

Json = Dict[str, Any]


class KverifCoverageAdapter:
    def __init__(self, mode: Optional[str] = None,
                 startup_timeout_sec: Optional[float] = None,
                 request_timeout_sec: Optional[float] = None) -> None:
        if startup_timeout_sec is None:
            startup_timeout_sec = kcov_startup_timeout()
        if request_timeout_sec is None:
            request_timeout_sec = kcov_request_timeout()
        self.mode = mode or mcp_backend()
        self._sessions = McpSessionManager(
            mode=self.mode,
            kdebug_bin=default_kcov_bin(),
            startup_timeout_sec=startup_timeout_sec,
            request_timeout_sec=request_timeout_sec,
            backend="kcov",
            api_version="kcov.v1",
            ready_protocol="kcov-stdio-loop",
            target_key="vdb",
            recovery_tool="kverif_cov_session_open",
        )

    def actions(self) -> Json:
        return self._one_shot({"api_version": "kcov.v1", "action": "actions"})

    def schema(self, action: str, kind: str = "request") -> Json:
        return self._one_shot({"api_version": "kcov.v1", "action": "schema",
                               "args": {"action": action, "kind": kind}})

    def request(self, request: dict, output_format: str = "kout") -> Any:
        from kverif_mcp.runner import StatelessCliRunner
        runner = StatelessCliRunner(timeout_sec=kcov_request_timeout())
        req = dict(request)
        req.setdefault("api_version", "kcov.v1")
        req.setdefault("output", {})
        if output_format in ("json", "envelope"):
            req["output"]["response_format"] = "json"
        else:
            req["output"].pop("response_format", None)
        raw = runner._run_raw("kcov", ["-"], json.dumps(req))
        if output_format == "kout":
            return raw["stdout"]
        try:
            return json.loads(raw["stdout"])
        except Exception:
            return {"ok": False, "error": {"code": "BAD_JSON",
                                            "message": raw["stdout"],
                                            "stderr": raw["stderr"]}}

    def _one_shot(self, req: Json) -> Json:
        from kverif_mcp.runner import StatelessCliRunner
        req = dict(req)
        req.setdefault("output", {})["response_format"] = "json"
        return StatelessCliRunner(timeout_sec=kcov_request_timeout()).run_json(
            "kcov", ["--json", "-"], json.dumps(req))

    def session_open(self, name: str, vdb: str, **kwargs: Any) -> Json:
        return self._sessions.open_session(name=name, fsdb=vdb, **kwargs)

    def session_list(self) -> Json:
        return self._sessions.list_sessions()

    def session_close(self, key: str) -> Json:
        return self._sessions.close_session(key)

    def query(self, **kwargs: Any) -> Any:
        return self._sessions.query(**kwargs)
