from __future__ import annotations

import json
from typing import Any

from .bitvector import BitVector
from .errors import KbitError


SCHEMA_RESULT = "kbit.result.v1"
SCHEMA_ERROR = "kbit.error.v1"


def success(op: str, *, input_value: Any = None, result: Any = None, warnings: list[str] | None = None, **extra) -> dict:
    response = {"ok": True, "schema": SCHEMA_RESULT, "op": op}
    if input_value is not None:
        response["input"] = input_value
    if result is not None:
        response["result"] = result.to_result() if isinstance(result, BitVector) else result
    response.update(extra)
    response["warnings"] = warnings or []
    return response


def failure(error: Exception) -> dict:
    if isinstance(error, KbitError):
        err = error.to_error()
    else:
        err = {"code": "INTERNAL_ERROR", "message": str(error)}
    return {"ok": False, "schema": SCHEMA_ERROR, "error": err}


def dumps(payload: dict, *, pretty: bool = False) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, sort_keys=False)


def human_result(payload: dict) -> str:
    op = payload.get("op", "result")
    if not payload.get("ok"):
        error = payload.get("error", {})
        return f"@kbit.error.v1\n\ncode: {error.get('code', 'ERROR')}\nmessage: {error.get('message', '')}"
    result = payload.get("result")
    lines = [f"@kbit.{op}.v1", ""]
    if isinstance(result, dict) and "sv" in result:
        lines.extend(["summary:", f"  result: {result['sv']}", f"  width: {result['width']}"])
        if result.get("known"):
            lines.append(f"  unsigned: {result.get('unsigned')}")
            lines.append(f"  signed: {result.get('signed_value')}")
        if "bool" in result:
            lines.append(f"  bool: {str(result['bool']).lower()}")
        return "\n".join(lines)
    if result is not None:
        lines.extend(["summary:", f"  result: {result}"])
        return "\n".join(lines)
    if "matched" in payload:
        lines.extend(["summary:", f"  matched: {str(payload['matched']).lower()}"])
        return "\n".join(lines)
    lines.extend(["summary:", "  ok: true"])
    return "\n".join(lines)
