"""Shared JSONL process protocol helpers."""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional

from kverif_loop.logging import argv_hash, log_lsf_event, log_stdio_event


Json = Dict[str, Any]


class ProtocolError(RuntimeError):
    pass


@dataclass
class JsonlProcess:
    argv: List[str]
    proc: subprocess.Popen[str]
    stdout_queue: "queue.Queue[str]" = field(default_factory=queue.Queue)
    stderr_tail: Deque[str] = field(default_factory=lambda: deque(maxlen=200))
    pending: Dict[str, Json] = field(default_factory=dict)
    read_lock: threading.Lock = field(default_factory=threading.Lock)
    job_name: Optional[str] = None
    job_id: Optional[str] = None
    log_alias: Optional[str] = None
    log_backend: Optional[str] = None
    log_launcher: Optional[str] = None
    _stdout_thread: Optional[threading.Thread] = None
    _stderr_thread: Optional[threading.Thread] = None

    @classmethod
    def start(cls, argv: Iterable[str], log_context: Optional[Json] = None) -> "JsonlProcess":
        args = list(argv)
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,  # isolate process group for clean kill of children
        )
        item = cls(args, proc)
        if log_context:
            item.log_alias = log_context.get("alias")
            item.log_backend = log_context.get("backend")
            item.log_launcher = log_context.get("launcher")
        item._stdout_thread = threading.Thread(target=item._read_stdout, daemon=True)
        item._stderr_thread = threading.Thread(target=item._read_stderr, daemon=True)
        item._stdout_thread.start()
        item._stderr_thread.start()
        item._log_stdio("process.start", True, argv_hash=argv_hash(args), pid=proc.pid)
        return item

    def _common(self) -> Json:
        return {
            "backend": self.log_backend,
            "launcher": self.log_launcher,
            "pid": self.proc.pid,
            "job_name": self.job_name,
            "job_id": self.job_id,
        }

    def _log_stdio(self, phase: str, ok: bool = True, **fields: Any) -> None:
        data = self._common()
        data.update(fields)
        log_stdio_event(self.log_alias, phase, ok, **data)

    def _log_lsf(self, phase: str, ok: bool = True, **fields: Any) -> None:
        data = self._common()
        data.update(fields)
        log_lsf_event(self.log_alias, phase, ok, **data)

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        from kverif_loop.lsf.bsub import parse_lsf_job_id as _parse
        for line in self.proc.stdout:
            stripped = line.rstrip("\n")
            if not self.job_id:
                jid = _parse(stripped)
                if jid:
                    self.job_id = jid
                    self._log_lsf("job_id.detected", True, job_id=jid)
            self.stdout_queue.put(stripped)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        # Lazy import to avoid circular dependency
        from kverif_loop.lsf.bsub import parse_lsf_job_id as _parse
        for line in self.proc.stderr:
            stripped = line.rstrip("\n")
            self.stderr_tail.append(stripped)
            if not self.job_id:
                jid = _parse(stripped)
                if jid:
                    self.job_id = jid
                    self._log_lsf("job_id.detected", True, job_id=jid)

    def wait_ready(self, protocol: str, timeout_sec: float = 30.0) -> Json:
        self._log_stdio("ready.wait.begin", True, protocol=protocol, timeout_sec=timeout_sec)
        deadline = None if timeout_sec <= 0 else time.time() + timeout_sec
        while deadline is None or time.time() < deadline:
            if self.proc.poll() is not None:
                self._log_stdio("ready.process_exited", False,
                                protocol=protocol, returncode=self.proc.returncode,
                                stderr_tail=list(self.stderr_tail))
                raise ProtocolError(f"process exited before ready: rc={self.proc.returncode}")
            try:
                line = self.stdout_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                self._log_stdio("ready.stdout_non_json", False, line=line[:1000])
                continue
            if msg.get("type") == "ready" and msg.get("protocol") == protocol:
                self._log_stdio("ready.ok", True, protocol=protocol, message=msg)
                return msg
        self._log_stdio("ready.timeout", False, protocol=protocol,
                        timeout_sec=timeout_sec, stderr_tail=list(self.stderr_tail))
        raise ProtocolError(f"timeout waiting for ready protocol {protocol}")

    def request(self, obj: Json, timeout_sec: float = 30.0) -> Json:
        """Send a JSONL request and wait for the matching response."""
        req_id = obj.get("request_id") or obj.get("id") or "unknown"
        self._log_stdio("request.begin", True, request_id=req_id,
                        action=obj.get("action"), timeout_sec=timeout_sec)
        self.write_json(obj)
        try:
            rsp = self.read_json_response(req_id, timeout_sec)
            self._log_stdio("request.end", bool(rsp.get("ok")), request_id=req_id,
                            action=obj.get("action"), response_ok=rsp.get("ok"))
            return rsp
        except Exception as exc:
            self._log_stdio("request.error", False, request_id=req_id,
                            action=obj.get("action"), error=str(exc),
                            stderr_tail=list(self.stderr_tail))
            raise

    def write_json(self, msg: Json) -> None:
        if self.proc.stdin is None:
            self._log_stdio("stdin.closed", False)
            raise ProtocolError("process stdin is closed")
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def read_json_response(self, request_id: str, timeout_sec: float = 30.0) -> Json:
        deadline = None if timeout_sec <= 0 else time.time() + timeout_sec
        with self.read_lock:
            cached = self.pending.pop(request_id, None)
            if cached is not None:
                return cached
            while deadline is None or time.time() < deadline:
                if self.proc.poll() is not None:
                    self._log_stdio("response.process_exited", False,
                                    request_id=request_id,
                                    returncode=self.proc.returncode,
                                    stderr_tail=list(self.stderr_tail))
                    raise ProtocolError(f"process exited while waiting response: rc={self.proc.returncode}")
                try:
                    line = self.stdout_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    msg = json.loads(line)
                except Exception as exc:
                    self._log_stdio("stdout.pollution", False,
                                    request_id=request_id, line=line[:1000])
                    raise ProtocolError(f"stdout protocol pollution after ready: {line!r}") from exc
                msg_id = msg.get("id")
                if msg_id == request_id:
                    return msg
                if isinstance(msg_id, str) and msg_id:
                    self.pending[msg_id] = msg
                    self._log_stdio("response.pending", True,
                                    request_id=request_id, pending_id=msg_id)
        self._log_stdio("response.timeout", False,
                        request_id=request_id, timeout_sec=timeout_sec,
                        stderr_tail=list(self.stderr_tail))
        raise ProtocolError(f"timeout waiting response {request_id}")

    def terminate(self, timeout_sec: float = 5.0) -> None:
        self._log_stdio("process.terminate.begin", True, timeout_sec=timeout_sec)
        if self.proc.poll() is not None:
            self._close_pipes()
            self._log_stdio("process.terminate.end", True, returncode=self.proc.returncode)
            return
        # Kill the entire process group so that child engines (design/waveform)
        # are also terminated, avoiding zombie orphan processes.
        try:
            os.killpg(os.getpgid(self.proc.pid), __import__("signal").SIGTERM)
        except (ProcessLookupError, OSError):
            self.proc.terminate()
        try:
            self.proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self.proc.pid), __import__("signal").SIGKILL)
            except (ProcessLookupError, OSError):
                self.proc.kill()
            self.proc.wait(timeout=timeout_sec)
        self._close_pipes()
        self._log_stdio("process.terminate.end", True, returncode=self.proc.returncode)

    def _close_pipes(self) -> None:
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except Exception:
                pass

    @property
    def stderr_text(self) -> str:
        return "\n".join(self.stderr_tail)
