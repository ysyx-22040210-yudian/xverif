"""JSONL router running inside the LSF cluster."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from .session_connection import SessionConnection


Json = Dict[str, Any]


class Router:
    def __init__(self, max_workers: int = 64, request_timeout_sec: float = 30.0) -> None:
        self.sessions: Dict[str, SessionConnection] = {}
        self.request_timeout_sec = request_timeout_sec
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.write_lock = threading.Lock()

    def ready(self) -> Json:
        return {
            "type": "ready",
            "protocol": "xdebug-router-jsonl",
            "version": 1,
            "host": socket.gethostname(),
            "pid": os.getpid(),
        }

    def serve(self) -> int:
        self._write(self.ready())
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception as exc:  # noqa: BLE001
                self._write({"id": None, "ok": False, "error": {"code": "protocol_error", "message": str(exc)}})
                continue
            self.executor.submit(self._dispatch_and_write, msg)
        return 0

    def _dispatch_and_write(self, msg: Json) -> None:
        self._write(self.handle(msg))

    def _write(self, msg: Json) -> None:
        with self.write_lock:
            sys.stdout.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()

    def handle(self, msg: Json) -> Json:
        req_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "router.ping":
            return {"id": req_id, "ok": True, "result": "pong", "sessions": list(self.sessions)}
        if method == "session.register":
            return self._register(req_id, params)
        if method == "session.unregister":
            sid = params.get("session_id")
            if isinstance(sid, str):
                self.sessions.pop(sid, None)
            return {"id": req_id, "ok": True}
        if method == "xdebug.query":
            return self._query(req_id, params)
        return {"id": req_id, "ok": False, "error": {"code": "unknown_method", "message": str(method)}}

    def _register(self, req_id: Any, params: Json) -> Json:
        sid = str(params.get("session_id") or "")
        host = str(params.get("host") or "")
        port = int(params.get("port") or 0)
        token = str(params.get("token") or "")
        if not sid or not host or not port or not token:
            return {"id": req_id, "ok": False, "error": {"code": "invalid_session", "message": "missing endpoint"}}
        self.sessions[sid] = SessionConnection(sid, host, port, token)
        return {"id": req_id, "ok": True, "session_id": sid}

    def _query(self, req_id: Any, params: Json) -> Json:
        sid = str(params.get("session_id") or "")
        conn = self.sessions.get(sid)
        if not conn or not conn.alive:
            return {"id": req_id, "ok": False, "error": {"code": "session_dead", "message": f"session not alive: {sid}"}}
        request = params.get("request") if isinstance(params.get("request"), dict) else {}
        payload_format = str(params.get("payload_format") or "xout")
        rsp = conn.query(str(req_id), payload_format, request, self.request_timeout_sec)
        rsp.setdefault("id", req_id)
        return rsp

