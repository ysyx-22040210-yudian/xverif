"""TCP session endpoint used by the LSF MCP backend."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional


Json = Dict[str, Any]


def _host() -> str:
    return socket.gethostname()


def _default_xdebug_cmd() -> List[str]:
    root = os.environ.get("XVERIF_HOME")
    if root:
        return [os.path.join(root, "tools", "xdebug")]
    return ["xdebug"]


def _make_xout(action: str, args: Json, delay_ms: int = 0) -> str:
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    lines = [f"@xdebug.{action}.v1", "", "summary:"]
    lines.append(f"  action: {action}")
    for key in ("signal", "time"):
        if key in args:
            lines.append(f"  {key}: {args[key]}")
    return "\n".join(lines) + "\n"


class SessionTcpServer:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.token = args.token or secrets.token_hex(16)
        self.session_id = args.session_id or f"xdebug-session-{os.getpid()}"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lock = threading.Lock()

    def serve(self) -> int:
        host, port = self._parse_bind(self.args.tcp)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(64)
        actual_host, actual_port = self.sock.getsockname()
        ready = {
            "type": "ready",
            "protocol": "xdebug-session-tcp",
            "version": 1,
            "session_id": self.session_id,
            "host": self.args.host or self._advertise_host(host),
            "port": actual_port,
            "pid": os.getpid(),
            "token": self.token,
            "output_formats": ["xout", "json", "envelope"],
        }
        print(json.dumps(ready, ensure_ascii=False), flush=True)
        while True:
            conn, _ = self.sock.accept()
            thread = threading.Thread(target=self._handle_conn, args=(conn,), daemon=True)
            thread.start()

    def _parse_bind(self, spec: str) -> tuple[str, int]:
        if ":" not in spec:
            return spec, 0
        host, port_s = spec.rsplit(":", 1)
        return host or "0.0.0.0", int(port_s or "0")

    def _advertise_host(self, bind_host: str) -> str:
        """返回真实可连接的 hostname，而非 127.0.0.1。"""
        env_host = os.environ.get("XDEBUG_LSF_ADVERTISE_HOST")
        if env_host:
            return env_host
        if bind_host in ("0.0.0.0", "::", ""):
            return socket.getfqdn() or socket.gethostname()
        if bind_host == "127.0.0.1":
            if os.environ.get("XDEBUG_LSF_ALLOW_LOOPBACK_SESSION") == "1":
                return bind_host
            return socket.getfqdn() or socket.gethostname()
        return bind_host

    def _handle_conn(self, conn: socket.socket) -> None:
        with conn:
            f = conn.makefile("rwb")
            line = f.readline()
            if not line:
                return
            try:
                req = json.loads(line.decode("utf-8"))
                rsp = self._handle_request(req)
            except Exception as exc:  # noqa: BLE001
                rsp = {"id": None, "ok": False, "error": {"code": "session_server_error", "message": str(exc)}}
            f.write((json.dumps(rsp, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            f.flush()

    def _handle_request(self, msg: Json) -> Json:
        req_id = msg.get("id")
        if msg.get("token") != self.token:
            return {"id": req_id, "ok": False, "error": {"code": "auth_failed", "message": "invalid token"}}
        payload_format = msg.get("payload_format", "xout")
        request = msg.get("request")
        if not isinstance(request, dict):
            return {"id": req_id, "ok": False, "error": {"code": "invalid_request", "message": "request must be object"}}
        with self.lock:
            if self.args.fake:
                return self._fake_response(req_id, payload_format, request)
            return self._run_xdebug(req_id, payload_format, request)

    def _fake_response(self, req_id: str, payload_format: str, request: Json) -> Json:
        action = str(request.get("action", "unknown"))
        args = request.get("args") if isinstance(request.get("args"), dict) else {}
        delay_ms = int(args.get("sleep_ms", self.args.fake_delay_ms or 0))
        if payload_format == "json":
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)
            return {"id": req_id, "ok": True, "payload_format": "json", "json": {"ok": True, "action": action, "args": args}}
        xout = _make_xout(action, args, delay_ms)
        if payload_format == "envelope":
            return {
                "id": req_id,
                "ok": True,
                "payload_format": "envelope",
                "xout": xout,
                "session": {"session_id": self.session_id, "host": _host()},
            }
        return {"id": req_id, "ok": True, "payload_format": "xout", "xout": xout}

    def _run_xdebug(self, req_id: str, payload_format: str, request: Json) -> Json:
        request = dict(request)
        request.setdefault("api_version", "xdebug.v1")
        if "target" not in request:
            target: Json = {}
            if self.args.fsdb:
                target["fsdb"] = self.args.fsdb
                target["auto_open"] = True
            if self.args.daidir:
                target["daidir"] = self.args.daidir
                target["auto_open"] = True
            request["target"] = target
        cmd = list(self.args.xdebug_cmd or _default_xdebug_cmd())
        if payload_format in {"json", "envelope"}:
            request.setdefault("output", {})
            if isinstance(request["output"], dict):
                request["output"]["format"] = "json"
            cmd = cmd + ["--json", "-"]
        else:
            cmd = cmd + ["-"]
        proc = subprocess.run(
            cmd,
            input=json.dumps(request, ensure_ascii=False),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.args.request_timeout_sec,
            check=False,
        )
        if payload_format == "json":
            try:
                return {"id": req_id, "ok": proc.returncode == 0, "payload_format": "json", "json": json.loads(proc.stdout)}
            except Exception:
                return {"id": req_id, "ok": False, "error": {"code": "bad_xdebug_json", "message": proc.stdout[-4096:]}}
        if payload_format == "envelope":
            return {
                "id": req_id,
                "ok": proc.returncode == 0,
                "payload_format": "envelope",
                "xout": proc.stdout,
                "stderr_tail": proc.stderr[-4096:],
                "session": {"session_id": self.session_id, "pid": os.getpid()},
            }
        return {"id": req_id, "ok": proc.returncode == 0, "payload_format": "xout", "xout": proc.stdout}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tcp", default="0.0.0.0:0")
    parser.add_argument("--host", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--fsdb", default="")
    parser.add_argument("--daidir", default="")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--fake-delay-ms", type=int, default=0)
    parser.add_argument("--request-timeout-sec", type=float, default=120.0)
    parser.add_argument("--xdebug-cmd", nargs="*")
    args = parser.parse_args(argv)
    return SessionTcpServer(args).serve()


if __name__ == "__main__":
    raise SystemExit(main())
