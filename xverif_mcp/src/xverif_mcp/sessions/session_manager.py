"""McpSessionManager — multi-session lifecycle for stdio-loop backends."""

from __future__ import annotations

import getpass
import os
import re
import uuid as _uuid
from typing import Any, Dict, Optional

from xverif_mcp.lsf.bsub import BsubRunner

from xverif_mcp.config import default_xdebug_bin, startup_timeout, request_timeout
from xverif_mcp.sessions.launchers import DirectLauncher, Launcher, LsfLauncher
from xverif_mcp.sessions.loop_session import XdebugLoopSession

Json = Dict[str, Any]


def _safe_name(s: str, max_len: int = 64) -> str:
    x = re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_")
    return (x or "unnamed")[:max_len]


def _valid_session_name(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", s or ""))


def _error(code: str, message: str) -> Json:
    return {"ok": False, "error": {"code": code, "message": message}}


class McpSessionManager:
    def __init__(self, mode: Optional[str] = None, xdebug_bin: Optional[str] = None,
                 startup_timeout_sec: Optional[float] = None,
                 request_timeout_sec: Optional[float] = None,
                 backend: str = "xdebug", api_version: str = "xdebug.v1",
                 ready_protocol: str = "xdebug-stdio-loop",
                 target_key: str = "fsdb",
                 recovery_tool: str = "xverif_debug_session_open") -> None:
        if startup_timeout_sec is None:
            startup_timeout_sec = startup_timeout()
        if request_timeout_sec is None:
            request_timeout_sec = request_timeout()
        self.mode = mode or os.environ.get("XVERIF_MCP_BACKEND", "direct")
        self.xdebug_bin = xdebug_bin or default_xdebug_bin()
        self.backend = backend
        self.api_version = api_version
        self.ready_protocol = ready_protocol
        self.target_key = target_key
        self.recovery_tool = recovery_tool
        self.startup_timeout_sec = startup_timeout_sec
        self.request_timeout_sec = request_timeout_sec
        self._session_queue = os.environ.get("XVERIF_LSF_SESSION_QUEUE", "interactive")
        self._session_resource = os.environ.get("XVERIF_LSF_SESSION_RESOURCE")
        if self.mode == "direct":
            self.launcher: Launcher = DirectLauncher()
        elif self.mode == "lsf":
            bsub_cmd = os.environ.get("XVERIF_LSF_BSUB")
            if os.environ.get("XVERIF_MCP_FAKE_LSF") == "1" and not bsub_cmd:
                import sys
                bsub_cmd = f"{sys.executable} -m xverif_mcp.lsf.fake_bsub"
            self.launcher = LsfLauncher(BsubRunner(bsub_cmd))
        else:
            raise ValueError(f"unsupported XVERIF_MCP_BACKEND: {self.mode}")
        self._job_prefix = (
            f"xverif_{_safe_name(getpass.getuser())}_{os.getpid()}_"
            f"{_uuid.uuid4().hex[:8]}"
        )
        self.sessions: Dict[str, XdebugLoopSession] = {}

    def open_session(self, name: str, fsdb: Optional[str] = None,
                     daidir: Optional[str] = None,
                     queue: Optional[str] = None, resource: Optional[str] = None,
                     **kwargs: Any) -> Json:
        if not _valid_session_name(name):
            return _error(
                "INVALID_SESSION_NAME",
                "session name must start with an ASCII letter and contain only "
                "ASCII letters, digits, and underscores, with maximum length 64",
            )
        if not fsdb and not daidir:
            return _error("RESOURCE_REQUIRED", "provide fsdb or daidir")
        if name in self.sessions:
            existing = self.sessions[name]
            if existing.state == "alive":
                if existing.process_alive():
                    return _error("SESSION_ID_EXISTS",
                                  f"session id already exists: {name}")
                return _error("SESSION_STALE",
                              "session id exists but is stale: "
                              f"{name}; close it explicitly before opening again")
        job_name = None
        actual_queue = queue or (self._session_queue if self.mode == "lsf" else None)
        actual_resource = resource or (self._session_resource if self.mode == "lsf" else None)
        if self.mode == "lsf":
            job_name = f"{self._job_prefix}_{_safe_name(self.backend)}_{_safe_name(name)}"
        session = XdebugLoopSession(
            alias=name, fsdb=fsdb, daidir=daidir, launcher=self.launcher,
            xdebug_bin=self.xdebug_bin, queue=actual_queue,
            resource=actual_resource, job_name=job_name,
            startup_timeout_sec=self.startup_timeout_sec,
            request_timeout_sec=self.request_timeout_sec,
            backend=self.backend, api_version=self.api_version,
            ready_protocol=self.ready_protocol, target_key=self.target_key,
            recovery_tool=self.recovery_tool)
        result = session.open()
        if not result.get("ok"):
            return result
        self.sessions[name] = session
        if session.session_id:
            self.sessions[session.session_id] = session
        return {"ok": True, "session": session.public_json()}

    def query(self, session: Optional[str], action: str,
              args: Optional[Json] = None, output_format: str = "xout",
              **kwargs: Any) -> Any:
        if not session:
            return _error("SESSION_REQUIRED",
                          "explicit session is required")
        key = session
        s = self.sessions.get(key)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {key}")
        rsp = s.query(action=action, args=args,
                       limits=kwargs.get("limits"), output=kwargs.get("output"),
                       output_format=output_format)
        if s.state == "dead":
            self._evict_session(s)
        return rsp

    def close_session(self, session: str) -> Json:
        s = self.sessions.get(session)
        if not s:
            return _error("SESSION_NOT_FOUND", f"session not found: {session}")
        old_state = s.state
        if s.state == "alive":
            s.close()
        else:
            s.abort(f"close requested for non-alive session: {old_state}",
                    source="close_dead")
        self._evict_session(s)
        return {"ok": True, "closed": s.public_json(),
                "previous_state": old_state}

    def list_sessions(self) -> Json:
        seen = set()
        rows = []
        for s in self.sessions.values():
            if id(s) in seen:
                continue
            seen.add(id(s))
            rows.append(s.public_json())
        return {"ok": True, "sessions": rows}

    def _evict_session(self, s: XdebugLoopSession) -> None:
        self.sessions.pop(s.alias, None)
        if s.session_id:
            self.sessions.pop(s.session_id, None)
        for key, value in list(self.sessions.items()):
            if value is s:
                self.sessions.pop(key, None)

    def session_open(self, name: str, fsdb: Optional[str] = None,
                     **kwargs: Any) -> Json:
        return self.open_session(name=name, fsdb=fsdb, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self.list_sessions()

    def session_close(self, session: str) -> Json:
        return self.close_session(session)

    def close_all(self) -> None:
        seen = set()
        for s in list(self.sessions.values()):
            if id(s) in seen:
                continue
            seen.add(id(s))
            try:
                if s.state == "alive":
                    s.close()
                else:
                    s.abort(
                        f"manager shutdown for non-alive session: {s.state}",
                        source="manager_close_all",
                    )
            except Exception:
                try:
                    s.abort("manager shutdown cleanup failed",
                            source="manager_close_all")
                except Exception:
                    pass
        self.sessions.clear()
