"""Standard-library transports for kdebug/kcov JSON APIs."""

from __future__ import annotations

import copy
import json
import os
import queue
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import (Any, Callable, Deque, Dict, List, Mapping, Optional,
                    Sequence, Union)

from .errors import ProtocolError, ToolInvocationError

Json = Dict[str, Any]
Command = Union[str, os.PathLike, Sequence[Union[str, os.PathLike]]]


def resolve_tool(name: str, root: Optional[Union[str, os.PathLike]] = None) -> Path:
    """Resolve a repository tool while allowing KVERIF_HOME overrides."""
    if root is None:
        configured = os.environ.get("KVERIF_HOME")
        root_path = Path(configured) if configured else Path(__file__).resolve().parents[1]
    else:
        root_path = Path(root)
    return root_path / "tools" / name


def _command_list(command: Command) -> List[str]:
    if isinstance(command, (str, os.PathLike)):
        return [str(command)]
    return [str(part) for part in command]


def _subprocess_timeout(timeout_sec: Optional[float]) -> Optional[float]:
    if timeout_sec is None or timeout_sec <= 0:
        return None
    return timeout_sec


class CallbackTransport:
    """Inject a custom request handler for tests or site-specific adapters."""

    def __init__(self, handler: Callable[[Json], Json], *, persistent: bool = True) -> None:
        self.handler = handler
        self.persistent = persistent
        self.requests: List[Json] = []

    def request(self, request: Json, timeout_sec: Optional[float] = None) -> Json:
        del timeout_sec
        copied = copy.deepcopy(request)
        self.requests.append(copied)
        response = self.handler(copied)
        if not isinstance(response, dict):
            raise ProtocolError("callback transport must return a JSON object")
        return copy.deepcopy(response)


class CliTransport:
    """Execute one complete JSON request through a tool's raw CLI."""

    persistent = False

    def __init__(self, command: Command, *, timeout_sec: Optional[float] = None,
                 env: Optional[Mapping[str, str]] = None,
                 cwd: Optional[Union[str, os.PathLike]] = None) -> None:
        self.command = _command_list(command)
        self.timeout_sec = timeout_sec
        self.env = dict(env or {})
        self.cwd = str(cwd) if cwd is not None else None

    def request(self, request: Json, timeout_sec: Optional[float] = None) -> Json:
        command = self.command + ["--json", "-"]
        environment = dict(os.environ)
        environment.update(self.env)
        effective_timeout = self.timeout_sec if timeout_sec is None else timeout_sec
        try:
            process = subprocess.run(
                command,
                input=json.dumps(request, ensure_ascii=False, separators=(",", ":")),
                text=True,
                capture_output=True,
                check=False,
                timeout=_subprocess_timeout(effective_timeout),
                env=environment,
                cwd=self.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolInvocationError(
                "tool request timed out", command=command,
                stderr_tail=str(exc.stderr or "")[-4000:]) from exc
        except OSError as exc:
            raise ToolInvocationError(str(exc), command=command) from exc

        stdout = process.stdout.strip()
        try:
            response = json.loads(stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ToolInvocationError(
                "tool did not return a JSON object",
                command=command,
                returncode=process.returncode,
                stderr_tail=process.stderr[-4000:],
            ) from exc
        if not isinstance(response, dict):
            raise ProtocolError("tool JSON response is not an object")
        return response


class StdioTransport:
    """Maintain one SDK-free JSONL process for stateful kdebug/kcov work."""

    persistent = True

    def __init__(self, command: Command, *, protocol: str, api_version: str,
                 startup_timeout_sec: Optional[float] = 180.0,
                 request_timeout_sec: Optional[float] = None,
                 env: Optional[Mapping[str, str]] = None,
                 cwd: Optional[Union[str, os.PathLike]] = None) -> None:
        self.command = _command_list(command) + ["--json", "--stdio-loop"]
        self.protocol = protocol
        self.api_version = api_version
        self.startup_timeout_sec = startup_timeout_sec
        self.request_timeout_sec = request_timeout_sec
        self.env = dict(env or {})
        self.cwd = str(cwd) if cwd is not None else None
        self.proc: Optional[subprocess.Popen] = None
        self.stdout_queue = queue.Queue()  # type: queue.Queue[str]
        self.stderr_tail = deque(maxlen=500)  # type: Deque[str]
        self._stdout_thread = None  # type: Optional[threading.Thread]
        self._stderr_thread = None  # type: Optional[threading.Thread]
        self._lock = threading.Lock()
        self._seq = 0

    def start(self) -> Json:
        if self.proc is not None:
            raise ProtocolError("stdio transport is already started")
        environment = dict(os.environ)
        environment.update(self.env)
        try:
            self.proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=environment,
                cwd=self.cwd,
                start_new_session=(os.name != "nt"),
            )
        except OSError as exc:
            raise ToolInvocationError(str(exc), command=self.command) from exc
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        try:
            ready = self._read_message(self.startup_timeout_sec, allow_noise=True)
        except Exception:
            self.terminate()
            raise
        if ready.get("type") != "ready" or ready.get("protocol") != self.protocol:
            self.terminate()
            raise ProtocolError("unexpected ready envelope: %r" % ready)
        return ready

    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            self.stdout_queue.put(line.rstrip("\r\n"))

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for line in self.proc.stderr:
            self.stderr_tail.append(line.rstrip("\r\n"))

    def _read_message(self, timeout_sec: Optional[float], *, allow_noise: bool = False) -> Json:
        if self.proc is None:
            raise ProtocolError("stdio transport is not started")
        deadline = None
        if timeout_sec is not None and timeout_sec > 0:
            deadline = time.monotonic() + timeout_sec
        while deadline is None or time.monotonic() < deadline:
            wait_sec = 0.05
            if deadline is not None:
                wait_sec = max(0.001, min(wait_sec, deadline - time.monotonic()))
            try:
                line = self.stdout_queue.get(timeout=wait_sec)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise ProtocolError(
                        "stdio process exited with rc=%s; stderr=%s"
                        % (self.proc.returncode, self.stderr_text[-4000:]))
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                if allow_noise:
                    continue
                raise ProtocolError("stdout protocol pollution: %r" % line) from exc
            if not isinstance(message, dict):
                raise ProtocolError("stdio message is not a JSON object")
            return message
        raise ProtocolError("timeout waiting for stdio response")

    def request(self, request: Json, timeout_sec: Optional[float] = None) -> Json:
        if self.proc is None or self.proc.stdin is None:
            raise ProtocolError("stdio transport is not started")
        with self._lock:
            self._seq += 1
            outgoing = copy.deepcopy(request)
            request_id = outgoing.get("request_id") or outgoing.get("id")
            if not isinstance(request_id, str) or not request_id:
                request_id = "sdk-%d" % self._seq
                outgoing["request_id"] = request_id
            encoded = json.dumps(outgoing, ensure_ascii=False, separators=(",", ":"))
            try:
                self.proc.stdin.write(encoded + "\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise ProtocolError("stdio request write failed") from exc
            effective_timeout = self.request_timeout_sec if timeout_sec is None else timeout_sec
            try:
                envelope = self._read_message(effective_timeout)
            except ProtocolError as exc:
                if "timeout" in str(exc).lower():
                    # A late response cannot be correlated safely with the next request.
                    self.terminate()
                raise
            if envelope.get("id") != request_id:
                raise ProtocolError(
                    "stdio response id mismatch: expected=%r actual=%r"
                    % (request_id, envelope.get("id")))
            response = envelope.get("json")
            if isinstance(response, dict):
                return response
            if not envelope.get("ok"):
                error = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
                return {
                    "api_version": outgoing.get("api_version", self.api_version),
                    "request_id": request_id,
                    "action": outgoing.get("action", ""),
                    "ok": False,
                    "error": error,
                }
            raise ProtocolError("stdio response does not contain a JSON payload")

    @property
    def stderr_text(self) -> str:
        return "\n".join(self.stderr_tail)

    def close(self, timeout_sec: float = 5.0) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                self.request({"api_version": self.api_version, "action": "stdio.quit"},
                             timeout_sec=timeout_sec)
            except Exception:
                pass
        if self.proc.poll() is None:
            try:
                self.proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                self.terminate()
                return
        self._close_streams()

    def terminate(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                if os.name != "nt":
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                else:
                    self.proc.terminate()
            except (OSError, ProcessLookupError):
                self.proc.terminate()
            try:
                self.proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    if os.name != "nt":
                        os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                    else:
                        self.proc.kill()
                except (OSError, ProcessLookupError):
                    self.proc.kill()
                self.proc.wait(timeout=2.0)
        self._close_streams()

    def _close_streams(self) -> None:
        if self.proc is None:
            return
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def __enter__(self) -> "StdioTransport":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.close()
        else:
            self.terminate()
