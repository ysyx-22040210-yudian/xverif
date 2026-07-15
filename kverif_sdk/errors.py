"""Public SDK exceptions with machine-usable context."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

Json = Dict[str, Any]


class KverifSdkError(RuntimeError):
    """Base class for SDK errors."""


class ToolInvocationError(KverifSdkError):
    """The tool process could not be started or did not return JSON."""

    def __init__(self, message: str, *, command: Sequence[str] = (),
                 returncode: Optional[int] = None, stderr_tail: str = "") -> None:
        super().__init__(message)
        self.command = list(command)
        self.returncode = returncode
        self.stderr_tail = stderr_tail


class ProtocolError(KverifSdkError):
    """The JSON/JSONL transport contract was violated."""


class ToolResponseError(KverifSdkError):
    """The tool returned a valid structured error response."""

    def __init__(self, response: Json) -> None:
        error = response.get("error") if isinstance(response.get("error"), dict) else {}
        self.response = response
        self.code = str(error.get("code", "TOOL_ERROR"))
        self.action = str(response.get("action", ""))
        self.detail = error
        message = str(error.get("message", "kverif tool request failed"))
        super().__init__("%s: %s" % (self.code, message))
