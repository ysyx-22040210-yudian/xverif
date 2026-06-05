import sys
from collections import Counter
from typing import Dict

from .mapfile import iter_loc_ids, load_map, find_map_file
from .xout import TextResponseBuilder


def stats_payload(log_path: str, map_path=None, top: int = 20) -> dict:
    if map_path is None:
        map_path = find_map_file(log_path)
    entries = load_map(map_path) if map_path else {}
    with open(log_path, 'r') as f:
        text = f.read()
    counts = Counter(iter_loc_ids(text))
    rows = []
    for loc_id, count in counts.most_common(top):
        entry = entries.get(loc_id, {})
        rows.append({
            "loc_id": loc_id,
            "count": count,
            "file": entry.get("file", "?"),
            "line": entry.get("line", "?"),
            "msg_id": entry.get("msg_id", "?"),
        })
    return {
        "ok": True,
        "action": "stats",
        "log": log_path,
        "map": map_path,
        "unique_locations": len(counts),
        "total_occurrences": sum(counts.values()),
        "rows": rows,
    }


def render_stats(payload: dict) -> str:
    out = TextResponseBuilder("xloc")
    out.emit_header("stats")
    out.emit_section("target")
    out.emit_kv("log", payload.get("log"))
    out.emit_kv("map", payload.get("map"))
    out.emit_section("summary")
    out.emit_kv("unique_locations", payload.get("unique_locations"))
    out.emit_kv("total_occurrences", payload.get("total_occurrences"))
    out.emit_section("data")
    for row in payload.get("rows", []):
        out.emit_row(row.get("loc_id"), row.get("count"), row.get("file"), row.get("line"), row.get("msg_id"))
    return out.render()


def cmd_stats(log_path: str, map_path=None, top: int = 20) -> None:
    """stats <sim.log> — count loc_id frequency, print top N."""
    payload = stats_payload(log_path, map_path, top)
    if not payload["rows"]:
        print(render_stats(payload), end="")
        return
    print(render_stats(payload), end="")
