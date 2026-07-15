from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from .errors import KcovError

Json = Dict[str, Any]

API_VERSION = "kcov.v1"


def parse_request(text: str) -> Json:
    try:
        req = json.loads(text)
    except Exception as exc:
        raise KcovError("INVALID_JSON", str(exc)) from exc
    if not isinstance(req, dict):
        raise KcovError("SCHEMA_INVALID", "request must be a JSON object")
    if req.get("api_version") != API_VERSION:
        raise KcovError("API_VERSION_UNSUPPORTED", "api_version must be kcov.v1")
    action = req.get("action")
    if not isinstance(action, str) or not action:
        raise KcovError("SCHEMA_INVALID", "action is required")
    target = req.setdefault("target", {})
    if not isinstance(target, dict):
        raise KcovError("SCHEMA_INVALID", "target must be an object")
    args = req.setdefault("args", {})
    if not isinstance(args, dict):
        raise KcovError("SCHEMA_INVALID", "args must be an object")
    req.setdefault("request_id", "req-unknown")
    return req


def response_format(req: Json) -> str:
    out = req.get("output")
    if isinstance(out, dict):
        return str(out.get("response_format") or "kout")
    args = req.get("args", {})
    if isinstance(args, dict):
        output = args.get("output", {})
        if isinstance(output, dict):
            return str(output.get("response_format") or "kout")
    return "kout"


def ok_response(req: Json, summary: Optional[Json] = None, data: Optional[Json] = None,
                warnings: Optional[List[str]] = None) -> Json:
    s = dict(summary or {})
    s.setdefault("matched_count", 0)
    s.setdefault("returned", 0)
    s.setdefault("truncated", False)
    s.setdefault("output_path", None)
    return {
        "ok": True,
        "api_version": API_VERSION,
        "request_id": req.get("request_id", "req-unknown"),
        "action": req.get("action", ""),
        "summary": s,
        "data": data or {},
        "warnings": warnings or [],
    }


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(_scalar(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _keyvals(item: Json) -> str:
    flat: List[str] = []
    evidence = item.get("evidence")
    for key, value in item.items():
        if key == "evidence" and isinstance(evidence, dict):
            if evidence.get("file") is not None:
                flat.append(f"file={_scalar(evidence.get('file'))}")
            if evidence.get("line") is not None:
                flat.append(f"line={_scalar(evidence.get('line'))}")
            continue
        if key == "evidence_source" and isinstance(value, dict):
            for src_key, src_value in value.items():
                flat.append(f"evidence_source.{src_key}={_scalar(src_value)}")
            continue
        if key == "branch_mask" and isinstance(value, dict):
            for mk, mv in value.items():
                flat.append(f"branch_mask.{mk}={_scalar(mv)}")
            continue
        flat.append(f"{key}={_scalar(value)}")
    return " ".join(flat)


def render_kout(rsp: Json) -> str:
    rid = rsp.get("request_id", "req-unknown")
    action = rsp.get("action", "")
    status = "ok" if rsp.get("ok") else "error"
    lines = [
        f"KOUT_BEGIN request_id={rid} action={action}",
        f"@kcov.v1 {status} action={action} request_id={rid}",
        "",
    ]
    if rsp.get("ok"):
        lines.append("summary:")
        for key, value in rsp.get("summary", {}).items():
            lines.append(f"  {key}: {_scalar(value)}")
        data = rsp.get("data", {})
        filters = data.get("filters") if isinstance(data, dict) else None
        if isinstance(filters, dict):
            lines.extend(["", "filters:"])
            for key, value in filters.items():
                lines.append(f"  {key}: {_scalar(value)}")
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list):
            lines.extend(["", "items:"])
            for item in items:
                if isinstance(item, dict):
                    lines.append(f"  - {_keyvals(item)}")
                else:
                    lines.append(f"  - {_scalar(item)}")
    else:
        lines.append("error:")
        for key, value in rsp.get("error", {}).items():
            lines.append(f"  {key}: {_scalar(value)}")
    warnings = rsp.get("warnings") or []
    if warnings:
        lines.extend(["", "warnings:"])
        for warning in warnings:
            lines.append(f"  - {_scalar(warning)}")
    lines.extend(["", f"KOUT_END request_id={rid}"])
    return "\n".join(lines) + "\n"


def json_dumps(obj: Json) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
