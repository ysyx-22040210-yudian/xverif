from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .cards import append_key_items, upsert_card, upsert_detail
from .errors import WRITE_DISABLED, XberifError
from .query import brief_result, get_topic, get_topic_detail, list_topics, status


def _result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: str, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(root: Path, request: dict, write: bool = False) -> dict:
    method = request.get("method")
    params = request.get("params") or {}
    req_id = request.get("id")
    if method == "xberif.status":
        return _result(req_id, status(root))
    if method == "xberif.list_topics":
        return _result(req_id, list_topics(root))
    if method in {"xberif.get_topic", "xberif.card.get"}:
        return _result(req_id, get_topic(root, params["topic"]))
    if method == "xberif.get_topic_detail":
        return _result(req_id, get_topic_detail(root, params["topic"]))
    if method == "xberif.brief":
        return _result(req_id, brief_result(root, params["mode"]))
    if method == "xberif.card.upsert":
        if not write:
            raise XberifError(WRITE_DISABLED, "write methods are disabled")
        upsert_card(root, params["card"])
        return _result(req_id, {"ok": True})
    if method == "xberif.card.append_key_items":
        if not write:
            raise XberifError(WRITE_DISABLED, "write methods are disabled")
        append_key_items(root, params["card_id"], params["key_items"])
        return _result(req_id, {"ok": True})
    if method == "xberif.detail.upsert":
        if not write:
            raise XberifError(WRITE_DISABLED, "write methods are disabled")
        upsert_detail(root, params["topic"], params["content"])
        return _result(req_id, {"ok": True})
    raise XberifError("METHOD_NOT_FOUND", f"unknown method {method}")


def serve_stdio(root: Path, write: bool = False) -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        try:
            resp = handle(root, req, write=write)
        except XberifError as exc:
            resp = _error(req.get("id"), exc.code, exc.message)
        print(json.dumps(resp, ensure_ascii=False), flush=True)
