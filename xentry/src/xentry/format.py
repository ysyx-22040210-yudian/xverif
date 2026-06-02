from __future__ import annotations

import json
from typing import Any

from .errors import XentryError


def dumps(payload: dict, *, pretty: bool = False) -> str:
    return json.dumps(payload, indent=2 if pretty else None, sort_keys=False)


def error_response(exc: Exception, *, action: str = "", request_id: Any = None) -> dict:
    if isinstance(exc, XentryError):
        error = {"code": exc.code, "message": exc.message}
        if exc.details:
            error["details"] = exc.details
    else:
        error = {"code": "INTERNAL_ERROR", "message": str(exc)}
    payload = {
        "ok": False,
        "api_version": "xentry.v1",
        "action": action,
        "error": error,
        "warnings": [],
        "errors": [error],
    }
    if request_id is not None:
        payload["request_id"] = request_id
    return payload
