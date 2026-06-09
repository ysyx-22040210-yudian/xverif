"""Client for a router JSONL process."""

from __future__ import annotations

import itertools
import sys
from typing import Any, Dict, Iterable, Optional

from .bsub import BsubOptions, BsubRunner
from .protocol import JsonlProcess


Json = Dict[str, Any]


class RouterClient:
    def __init__(self, process: JsonlProcess, ready: Json, timeout_sec: float = 30.0) -> None:
        self.process = process
        self.ready = ready
        self.timeout_sec = timeout_sec
        self._counter = itertools.count()

    @classmethod
    def start(cls, bsub: BsubRunner, opts: Optional[BsubOptions] = None, timeout_sec: float = 30.0) -> "RouterClient":
        cmd = [sys.executable, "-m", "xdebug_router.main"]
        opts = opts or BsubOptions(job_name="xdebug_router")
        if not opts.job_name:
            opts.job_name = "xdebug_router"
        proc = bsub.start(cmd, opts)
        ready = proc.wait_ready("xdebug-router-jsonl", timeout_sec)
        return cls(proc, ready, timeout_sec)

    def call(self, method: str, params: Optional[Json] = None, timeout_sec: Optional[float] = None) -> Json:
        req_id = f"ctl-{next(self._counter)}"
        self.process.write_json({"id": req_id, "method": method, "params": params or {}})
        return self.process.read_json_response(req_id, timeout_sec or self.timeout_sec)

    def ping(self) -> Json:
        return self.call("router.ping")

    def register(self, session: Json) -> Json:
        return self.call("session.register", session)

    def unregister(self, session_id: str) -> Json:
        return self.call("session.unregister", {"session_id": session_id})

    def query(self, session_id: str, request: Json, payload_format: str = "xout", timeout_sec: Optional[float] = None) -> Json:
        req_id = f"req-{next(self._counter)}"
        self.process.write_json({
            "id": req_id,
            "method": "xdebug.query",
            "params": {
                "session_id": session_id,
                "payload_format": payload_format,
                "request": request,
            },
        })
        return self.process.read_json_response(req_id, timeout_sec or self.timeout_sec)

    def close(self) -> None:
        self.process.terminate()

