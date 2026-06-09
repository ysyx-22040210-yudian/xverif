"""Backends for xdebug MCP tools."""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from xdebug_lsf.bsub import BsubRunner
from xdebug_lsf.router_client import RouterClient
from xdebug_lsf.session_launcher import SessionInfo, SessionLauncher


Json = Dict[str, Any]


def error_payload(code: str, message: str, **extra: Any) -> Json:
    payload: Json = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        payload["error"].update(extra)
    return payload


def repo_root() -> str:
    return os.environ.get("XVERIF_HOME") or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def default_xdebug_cmd() -> List[str]:
    return [os.path.join(repo_root(), "tools", "xdebug"), "--json", "-"]


class XdebugRunner:
    def __init__(self, cmd: Optional[List[str]] = None, timeout_sec: Optional[float] = None) -> None:
        self.cmd = cmd or default_xdebug_cmd()
        self.timeout_sec = timeout_sec or float(os.environ.get("XDEBUG_MCP_TIMEOUT_SEC", "120"))

    def request(self, request: Json) -> Json:
        try:
            proc = subprocess.run(
                self.cmd,
                input=json.dumps(request, ensure_ascii=False),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return error_payload("XDEBUG_MCP_TIMEOUT", f"xdebug timed out after {self.timeout_sec:g}s")
        except OSError as exc:
            return error_payload("XDEBUG_MCP_EXEC_FAILED", str(exc))
        try:
            payload = json.loads(proc.stdout)
        except Exception as exc:  # noqa: BLE001
            return error_payload(
                "XDEBUG_MCP_BAD_RESPONSE",
                f"xdebug did not return JSON: {exc}",
                exit_code=proc.returncode,
                stdout=proc.stdout[-4096:],
                stderr=proc.stderr[-4096:],
            )
        if isinstance(payload, dict):
            return payload
        return error_payload("XDEBUG_MCP_BAD_RESPONSE", "xdebug JSON response was not an object")


class DirectBackend:
    def __init__(self, runner: Optional[XdebugRunner] = None) -> None:
        self.runner = runner or XdebugRunner()

    def ping(self) -> str:
        return "pong"

    def request(self, request: Json) -> Json:
        request = dict(request)
        request.setdefault("api_version", "xdebug.v1")
        request.setdefault("output", {})
        if isinstance(request["output"], dict):
            request["output"].setdefault("format", "json")
        return self.runner.request(request)


class LsfBackend:
    def __init__(self, fake: Optional[bool] = None) -> None:
        self.fake = fake if fake is not None else os.environ.get("XDEBUG_MCP_FAKE_LSF") == "1"
        bsub_cmd = os.environ.get("XDEBUG_LSF_BSUB")
        if self.fake and not bsub_cmd:
            bsub_cmd = f"{os.sys.executable} -m xdebug_lsf.fake_bsub"
        self.bsub = BsubRunner(bsub_cmd)
        self.router: Optional[RouterClient] = None
        self.sessions: Dict[str, SessionInfo] = {}
        self.default_session: Optional[str] = None
        self.session_launcher = SessionLauncher(self.bsub, fake=self.fake)

    def ping(self) -> str:
        self.ensure_router()
        assert self.router is not None
        rsp = self.router.ping()
        return "pong" if rsp.get("ok") else json.dumps(rsp)

    def ensure_router(self) -> RouterClient:
        if self.router is not None and self.router.process.proc.poll() is None:
            return self.router
        self.router = RouterClient.start(self.bsub)
        seen = set()
        for info in list(self.sessions.values()):
            if id(info) in seen:
                continue
            seen.add(id(info))
            if info.state == "alive":
                self.router.register(self._router_session(info))
        return self.router

    def session_open(
        self,
        name: str,
        fsdb: str,
        daidir: Optional[str] = None,
        queue: Optional[str] = None,
        resource: Optional[str] = None,
        make_default: bool = True,
    ) -> Json:
        router = self.ensure_router()
        info = self.session_launcher.open(name, fsdb, daidir, queue, resource)
        reg = router.register(self._router_session(info))
        if not reg.get("ok"):
            return reg
        self.sessions[name] = info
        self.sessions[info.session_id] = info
        if make_default:
            self.default_session = info.session_id
        return {"ok": True, "session": info.public_json(), "default_session": self.default_session}

    def _router_session(self, info: SessionInfo) -> Json:
        return {"session_id": info.session_id, "host": info.host, "port": info.port, "token": info.token}

    def query(self, session: Optional[str], action: str, args: Optional[Json], output_format: str = "xout") -> Any:
        key = session or self.default_session
        if not key:
            return error_payload("SESSION_REQUIRED", "provide session or call xdebug_session_open")
        info = self.sessions.get(key)
        if not info or info.state != "alive":
            return error_payload("SESSION_DEAD", f"session not alive: {key}")
        request = {"api_version": "xdebug.v1", "action": action, "args": args or {}}
        router = self.ensure_router()
        rsp = router.query(info.session_id, request, output_format)
        if not rsp.get("ok"):
            if rsp.get("error", {}).get("code") == "session_dead":
                info.state = "dead"
            return rsp
        if output_format == "xout":
            return rsp.get("xout", "")
        if output_format == "json":
            return rsp.get("json", rsp)
        return rsp

    def session_close(self, session: str) -> Json:
        info = self.sessions.get(session)
        if not info:
            return error_payload("SESSION_NOT_FOUND", session)
        info.state = "closed"
        if self.router:
            self.router.unregister(info.session_id)
        if info.process:
            info.process.terminate()
        self.sessions.pop(info.alias, None)
        self.sessions.pop(info.session_id, None)
        if self.default_session == info.session_id:
            self.default_session = None
        return {"ok": True, "closed": info.public_json(), "default_session": self.default_session}

    def session_list(self) -> Json:
        seen = set()
        rows = []
        for info in self.sessions.values():
            if id(info) in seen:
                continue
            seen.add(id(info))
            rows.append(info.public_json())
        return {"ok": True, "sessions": rows, "default_session": self.default_session}

    def session_use(self, session: str) -> Json:
        info = self.sessions.get(session)
        if not info or info.state != "alive":
            return error_payload("SESSION_NOT_FOUND", f"session is not alive or unknown: {session}")
        self.default_session = info.session_id
        return {"ok": True, "default_session": self.default_session, "session": info.public_json()}


class XDebugMcpBackend:
    def __init__(self, mode: Optional[str] = None, runner: Optional[XdebugRunner] = None) -> None:
        self.mode = mode or os.environ.get("XDEBUG_MCP_BACKEND", "direct")
        self.direct = DirectBackend(runner)
        self.lsf = LsfBackend() if self.mode == "lsf" else None

    def ping(self) -> str:
        if self.lsf:
            return self.lsf.ping()
        return self.direct.ping()

    def request(self, request: Json) -> Json:
        return self.direct.request(request)
