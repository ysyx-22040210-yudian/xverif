import os
import sys

from .mapfile import load_map, resolve_loc
from .kout import TextResponseBuilder


def resolve_payload(loc_id: str, map_path: str) -> dict:
    entries = load_map(map_path)
    entry = resolve_loc(entries, loc_id)
    if entry is None:
        return {"ok": False, "action": "resolve", "error": {"code": "LOC_ID_NOT_FOUND", "message": f"{loc_id}: not found in {map_path}"}, "loc_id": loc_id}
    payload = {"ok": True, "action": "resolve", "loc_id": loc_id}
    payload.update(entry)
    return payload


def context_payload(loc_id: str, map_path: str, before: int = 20, after: int = 20) -> dict:
    payload = resolve_payload(loc_id, map_path)
    payload["action"] = "context"
    if not payload.get("ok"):
        return payload
    filepath = payload.get('file', '')
    line_num = payload.get('line', 0)
    payload["context"] = []
    if not filepath or not os.path.exists(filepath):
        payload["warning"] = f"source file not found: {filepath}"
        return payload
    with open(filepath, 'r') as f:
        lines = f.readlines()
    start = max(0, line_num - before - 1)
    end = min(len(lines), line_num + after)
    for i in range(start, end):
        payload["context"].append({"line": i + 1, "hit": i == line_num - 1, "text": lines[i].rstrip()})
    return payload


def render_payload(payload: dict) -> str:
    out = TextResponseBuilder("kloc")
    out.emit_header(payload.get("action", "resolve"))
    if not payload.get("ok"):
        out.emit_error(payload.get("error", {}))
        return out.render()
    out.emit_section("target")
    out.emit_kv("loc_id", payload.get("loc_id"))
    out.emit_section("summary")
    out.emit_kv("file", payload.get("file"))
    out.emit_kv("line", payload.get("line"))
    out.emit_kv("msg_id", payload.get("msg_id"))
    out.emit_section("evidence")
    if payload.get("file") and payload.get("line"):
        out.emit_row(f"{payload.get('file')}:{payload.get('line')}")
    if payload.get("context"):
        out.emit_section("data")
        for row in payload["context"]:
            marker = ">>>" if row.get("hit") else "..."
            out.emit_row(marker, row.get("line"), row.get("text"))
    if payload.get("warning"):
        out.emit_warning("SOURCE_NOT_FOUND", payload["warning"])
    return out.render()


def cmd_resolve(loc_id: str, map_path: str) -> None:
    """resolve <loc_id> — print file, line, msg_id for a loc_id."""
    payload = resolve_payload(loc_id, map_path)
    if not payload.get("ok"):
        print(payload["error"]["message"], file=sys.stderr)
        sys.exit(1)
    print(render_payload(payload), end="")


def cmd_context(loc_id: str, map_path: str, before: int = 20, after: int = 20) -> None:
    """context <loc_id> — resolve then print surrounding source lines."""
    payload = context_payload(loc_id, map_path, before, after)
    if not payload.get("ok"):
        print(payload["error"]["message"], file=sys.stderr)
        sys.exit(1)
    print(render_payload(payload), end="")


def _print_entry(loc_id: str, entry: dict) -> None:
    filepath = entry.get('file', '?')
    line = entry.get('line', '?')
    msg_id = entry.get('msg_id', '?')
    print(f"loc_id:  {loc_id}")
    print(f"file:    {filepath}")
    print(f"line:    {line}")
    print(f"msg_id:  {msg_id}")
