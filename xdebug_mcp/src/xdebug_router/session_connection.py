"""TCP connection to one xdebug session."""

from __future__ import annotations

import json
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict


Json = Dict[str, Any]


@dataclass
class SessionConnection:
    session_id: str
    host: str
    port: int
    token: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    alive: bool = True

    def query(self, request_id: str, payload_format: str, request: Json, timeout_sec: float) -> Json:
        with self.lock:
            msg = {
                "id": request_id,
                "token": self.token,
                "payload_format": payload_format,
                "request": request,
            }
            try:
                with socket.create_connection((self.host, self.port), timeout=timeout_sec) as sock:
                    sock.settimeout(timeout_sec)
                    f = sock.makefile("rwb")
                    f.write((json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
                    f.flush()
                    line = f.readline()
                    if not line:
                        raise RuntimeError("empty session response")
                    rsp = json.loads(line.decode("utf-8"))
                    return rsp if isinstance(rsp, dict) else {"id": request_id, "ok": False}
            except Exception as exc:  # noqa: BLE001
                self.alive = False
                return {"id": request_id, "ok": False, "error": {"code": "session_dead", "message": str(exc)}}

