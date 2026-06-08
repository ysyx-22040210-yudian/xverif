#!/usr/bin/env python3
"""Small stdio MCP server wrapping xdebug JSON requests.

The implementation intentionally avoids third-party dependencies.  It speaks
the JSON-RPC framing used by MCP stdio transports and delegates all xdebug
facts to ``tools/xdebug --json -``.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


Json = Dict[str, Any]


def _repo_root() -> Path:
    env = os.environ.get("XVERIF_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def _default_xdebug_cmd() -> List[str]:
    return [str(_repo_root() / "tools" / "xdebug"), "--json", "-"]


def _json_text(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def _tool_result(payload: Any, is_error: bool = False) -> Json:
    return {
        "content": [{"type": "text", "text": _json_text(payload)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def _error_payload(code: str, message: str, **extra: Any) -> Json:
    payload: Json = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        payload["error"].update(extra)
    return payload


class ManagedSession:
    def __init__(
        self,
        name: str,
        session_id: str,
        mode: str = "",
        daidir: str = "",
        fsdb: str = "",
        last_summary: Optional[Json] = None,
    ) -> None:
        self.name = name
        self.session_id = session_id
        self.mode = mode
        self.daidir = daidir
        self.fsdb = fsdb
        self.last_used_at = time.time()
        self.last_summary = last_summary or {}

    def to_json(self) -> Json:
        out: Json = {
            "name": self.name,
            "session_id": self.session_id,
            "last_used_at": self.last_used_at,
        }
        if self.mode:
            out["mode"] = self.mode
        if self.daidir:
            out["daidir"] = self.daidir
        if self.fsdb:
            out["fsdb"] = self.fsdb
        if self.last_summary:
            out["last_summary"] = self.last_summary
        return out


class XdebugRunner:
    def __init__(self, cmd: Optional[List[str]] = None, timeout_sec: Optional[float] = None) -> None:
        self.cmd = cmd or _default_xdebug_cmd()
        self.timeout_sec = timeout_sec or float(os.environ.get("XDEBUG_MCP_TIMEOUT_SEC", "120"))

    def request(self, request: Json) -> Json:
        text = json.dumps(request, ensure_ascii=False)
        try:
            proc = subprocess.run(
                self.cmd,
                input=text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _error_payload("XDEBUG_MCP_TIMEOUT", f"xdebug timed out after {self.timeout_sec:g}s")
        except OSError as exc:
            return _error_payload("XDEBUG_MCP_EXEC_FAILED", str(exc))

        try:
            payload = json.loads(proc.stdout)
        except Exception as exc:  # noqa: BLE001
            return _error_payload(
                "XDEBUG_MCP_BAD_RESPONSE",
                f"xdebug did not return JSON: {exc}",
                exit_code=proc.returncode,
                stdout=proc.stdout[-4096:],
                stderr=proc.stderr[-4096:],
            )
        if isinstance(payload, dict):
            if proc.stderr:
                payload.setdefault("mcp_stderr", proc.stderr[-4096:])
            return payload
        return _error_payload("XDEBUG_MCP_BAD_RESPONSE", "xdebug JSON response was not an object")


class XdebugMcpServer:
    def __init__(self, runner: Optional[XdebugRunner] = None) -> None:
        self.runner = runner or XdebugRunner()
        self.sessions: Dict[str, ManagedSession] = {}
        self.default_session: Optional[str] = None

    def tools(self) -> List[Json]:
        return [
            {
                "name": "xdebug_request",
                "description": "Run a complete xdebug JSON request. Use this for arbitrary xdebug actions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"request": {"type": "object"}},
                    "required": ["request"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "xdebug_session_open",
                "description": "Open or reuse a named xdebug session and remember it in this MCP server.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "daidir": {"type": "string"},
                        "fsdb": {"type": "string"},
                        "reuse": {"type": "boolean"},
                        "reopen": {"type": "boolean"},
                        "make_default": {"type": "boolean"},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "xdebug_session_list",
                "description": "List sessions known by this MCP server, optionally including xdebug native session.list.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"include_native": {"type": "boolean"}},
                    "additionalProperties": False,
                },
            },
            {
                "name": "xdebug_session_use",
                "description": "Set the default session used by xdebug_query.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "session_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
            {
                "name": "xdebug_session_close",
                "description": "Close one managed xdebug session and remove it from the MCP registry.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "session_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
            {
                "name": "xdebug_query",
                "description": "Run an xdebug action using explicit target, named session, or the default session.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "args": {"type": "object"},
                        "target": {"type": "object"},
                        "session": {"type": "string"},
                        "limits": {"type": "object"},
                        "output": {"type": "object"},
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "xdebug_actions",
                "description": "Return xdebug action catalog.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "xdebug_schema",
                "description": "Return an action-specific xdebug schema.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "kind": {"type": "string", "enum": ["request", "response"]},
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            },
        ]

    def call_tool(self, name: str, arguments: Optional[Json]) -> Json:
        args = arguments or {}
        handlers: Dict[str, Callable[[Json], Json]] = {
            "xdebug_request": self.tool_request,
            "xdebug_session_open": self.tool_session_open,
            "xdebug_session_list": self.tool_session_list,
            "xdebug_session_use": self.tool_session_use,
            "xdebug_session_close": self.tool_session_close,
            "xdebug_query": self.tool_query,
            "xdebug_actions": self.tool_actions,
            "xdebug_schema": self.tool_schema,
        }
        handler = handlers.get(name)
        if not handler:
            return _tool_result(_error_payload("UNKNOWN_TOOL", f"unknown tool: {name}"), True)
        payload = handler(args)
        return _tool_result(payload, bool(isinstance(payload, dict) and payload.get("ok") is False))

    def _run(self, request: Json) -> Json:
        request = dict(request)
        request.setdefault("api_version", "xdebug.v1")
        request.setdefault("output", {})
        if isinstance(request["output"], dict):
            request["output"].setdefault("format", "json")
        return self.runner.request(request)

    def tool_request(self, args: Json) -> Json:
        request = args.get("request")
        if not isinstance(request, dict):
            return _error_payload("INVALID_ARGUMENT", "xdebug_request requires object argument request")
        return self._run(request)

    def tool_session_open(self, args: Json) -> Json:
        name = args.get("name")
        if not isinstance(name, str) or not name:
            return _error_payload("INVALID_ARGUMENT", "xdebug_session_open requires name")
        target: Json = {}
        if isinstance(args.get("daidir"), str):
            target["daidir"] = args["daidir"]
        if isinstance(args.get("fsdb"), str):
            target["fsdb"] = args["fsdb"]
        if not target:
            return _error_payload("INVALID_ARGUMENT", "xdebug_session_open requires daidir and/or fsdb")
        request: Json = {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": target,
            "args": {"name": name},
            "output": {"format": "json"},
        }
        for key in ("reuse", "reopen"):
            if isinstance(args.get(key), bool):
                request["args"][key] = args[key]
        response = self._run(request)
        if response.get("ok"):
            session_id = _extract_session_id(response, name)
            record = ManagedSession(
                name=name,
                session_id=session_id,
                mode=str(response.get("summary", {}).get("mode", "")),
                daidir=str(target.get("daidir", "")),
                fsdb=str(target.get("fsdb", "")),
                last_summary=response.get("summary", {}) if isinstance(response.get("summary"), dict) else {},
            )
            self.sessions[name] = record
            self.sessions[session_id] = record
            if args.get("make_default", True):
                self.default_session = session_id
            response.setdefault("mcp", {})
            response["mcp"].update({"default_session": self.default_session, "managed_session": record.to_json()})
        return response

    def tool_session_list(self, args: Json) -> Json:
        records = []
        seen = set()
        for record in self.sessions.values():
            if id(record) in seen:
                continue
            seen.add(id(record))
            records.append(record.to_json())
        out: Json = {"ok": True, "sessions": records, "default_session": self.default_session}
        if args.get("include_native"):
            out["native"] = self._run({"api_version": "xdebug.v1", "action": "session.list"})
        return out

    def tool_session_use(self, args: Json) -> Json:
        key = args.get("session_id") or args.get("name")
        if not isinstance(key, str) or not key:
            return _error_payload("INVALID_ARGUMENT", "xdebug_session_use requires name or session_id")
        record = self.sessions.get(key)
        if not record:
            return _error_payload("SESSION_NOT_MANAGED", f"session is not known to this MCP server: {key}")
        record.last_used_at = time.time()
        self.default_session = record.session_id
        return {"ok": True, "default_session": self.default_session, "session": record.to_json()}

    def tool_session_close(self, args: Json) -> Json:
        key = args.get("session_id") or args.get("name")
        if not isinstance(key, str) or not key:
            return _error_payload("INVALID_ARGUMENT", "xdebug_session_close requires name or session_id")
        record = self.sessions.get(key)
        session_id = record.session_id if record else key
        response = self._run({"api_version": "xdebug.v1", "action": "session.close", "target": {"session_id": session_id}})
        if response.get("ok") or record:
            self._remove_session(session_id)
            if record:
                self._remove_session(record.name)
        response.setdefault("mcp", {})
        response["mcp"]["default_session"] = self.default_session
        return response

    def tool_query(self, args: Json) -> Json:
        action = args.get("action")
        if not isinstance(action, str) or not action:
            return _error_payload("INVALID_ARGUMENT", "xdebug_query requires action")
        request: Json = {"api_version": "xdebug.v1", "action": action, "output": {"format": "json"}}
        if isinstance(args.get("args"), dict):
            request["args"] = args["args"]
        if isinstance(args.get("limits"), dict):
            request["limits"] = args["limits"]
        if isinstance(args.get("output"), dict):
            request["output"].update(args["output"])
            request["output"]["format"] = "json"

        if isinstance(args.get("target"), dict):
            request["target"] = args["target"]
        else:
            session_key = args.get("session")
            record = self.sessions.get(session_key) if isinstance(session_key, str) else None
            sid = record.session_id if record else (session_key if isinstance(session_key, str) else self.default_session)
            if not sid:
                return _error_payload("SESSION_REQUIRED", "provide target/session or call xdebug_session_open first")
            request["target"] = {"session_id": sid}
            if record:
                record.last_used_at = time.time()
        return self._run(request)

    def tool_actions(self, args: Json) -> Json:
        del args
        return self._run({"api_version": "xdebug.v1", "action": "actions"})

    def tool_schema(self, args: Json) -> Json:
        action = args.get("action")
        if not isinstance(action, str) or not action:
            return _error_payload("INVALID_ARGUMENT", "xdebug_schema requires action")
        kind = args.get("kind", "request")
        return self._run({"api_version": "xdebug.v1", "action": "schema", "args": {"action": action, "kind": kind}})

    def _remove_session(self, key: str) -> None:
        record = self.sessions.pop(key, None)
        if record:
            self.sessions.pop(record.name, None)
            self.sessions.pop(record.session_id, None)
            if self.default_session == record.session_id:
                self.default_session = None
        elif self.default_session == key:
            self.default_session = None

    def handle_jsonrpc(self, message: Json) -> Optional[Json]:
        method = message.get("method")
        msg_id = message.get("id")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "xdebug-mcp", "version": "0.1.0"},
                }
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                params = message.get("params") or {}
                result = self.call_tool(str(params.get("name", "")), params.get("arguments") or {})
            elif method == "notifications/initialized":
                return None
            else:
                return _jsonrpc_error(msg_id, -32601, f"method not found: {method}")
            if msg_id is None:
                return None
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except Exception as exc:  # noqa: BLE001
            return _jsonrpc_error(msg_id, -32603, str(exc))


def _extract_session_id(response: Json, fallback: str) -> str:
    for key in ("summary", "data", "session"):
        value = response.get(key)
        if isinstance(value, dict):
            sid = value.get("session_id") or value.get("id")
            if isinstance(sid, str) and sid:
                return sid
    return fallback


def _jsonrpc_error(msg_id: Any, code: int, message: str) -> Json:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def read_message(stdin: Any) -> Optional[Json]:
    headers: Dict[str, str] = {}
    first = stdin.buffer.readline()
    if not first:
        return None
    if first.lstrip().startswith(b"{"):
        return json.loads(first.decode("utf-8"))
    line = first
    while line and line not in (b"\r\n", b"\n"):
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        headers[key.lower()] = value.strip()
        line = stdin.buffer.readline()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def write_message(stdout: Any, message: Json) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stdout.buffer.write(body)
    stdout.buffer.flush()


def serve_stdio(server: Optional[XdebugMcpServer] = None) -> int:
    srv = server or XdebugMcpServer()
    while True:
        message = read_message(sys.stdin)
        if message is None:
            return 0
        response = srv.handle_jsonrpc(message)
        if response is not None:
            write_message(sys.stdout, response)


def main(argv: Optional[List[str]] = None) -> int:
    del argv
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
