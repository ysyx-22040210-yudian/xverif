import os
import shutil
import subprocess
from collections import Counter
from typing import Dict, List, Tuple

from .mapfile import load_map, find_map_file
from .kout import TextResponseBuilder

LOC_ID_PATTERN = r'L_[0-9A-F]{8}'


def _find_searcher() -> str:
    """Return 'rg', 'grep', or None depending on what is available."""
    if shutil.which('rg'):
        return 'rg'
    if shutil.which('grep'):
        return 'grep'
    return None


def _extract_loc_ids(log_path: str) -> List[str]:
    """Extract loc_ids from log_path using rg/grep (streaming, mem-efficient).

    Returns lines of raw matches; caller should count/parse.
    """
    searcher = _find_searcher()
    if not searcher:
        raise RuntimeError('Neither rg nor grep found in PATH')

    if searcher == 'rg':
        cmd = ['rg', '--no-filename', '--no-line-number', '-o', LOC_ID_PATTERN, log_path]
    else:  # grep
        cmd = ['grep', '-oP', LOC_ID_PATTERN, log_path]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode not in (0, 1):  # 1 = no matches (ok), others = error
        raise RuntimeError(f'{searcher} failed: {proc.stderr.strip()}')
    return [line for line in proc.stdout.splitlines() if line.strip()]


def stats_payload(log_path: str, map_path=None, top: int = 20) -> dict:
    if map_path is None:
        map_path = find_map_file(log_path)
    entries = load_map(map_path) if map_path else {}

    loc_ids = _extract_loc_ids(log_path)
    counts = Counter(loc_ids)

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
    out = TextResponseBuilder("kloc")
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
