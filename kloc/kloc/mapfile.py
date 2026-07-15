import json
import os
import re
from typing import Dict, Iterator, Optional

LOC_ID_RE = re.compile(r'L_[0-9A-F]{8}')


def load_map(map_path: str) -> Dict[str, dict]:
    """Load a JSONL sidecar map into a dict keyed by loc_id."""
    entries = {}
    if not os.path.exists(map_path):
        return entries
    with open(map_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            loc_id = entry.get('loc_id')
            if loc_id:
                entries[loc_id] = entry
    return entries


def resolve_loc(entries: Dict[str, dict], loc_id: str) -> Optional[dict]:
    """Look up a single loc_id in the loaded map."""
    return entries.get(loc_id)


def iter_loc_ids(text: str) -> Iterator[str]:
    """Yield all loc_ids found in text in order of first occurrence."""
    for m in LOC_ID_RE.finditer(text):
        yield m.group()


def find_map_file(log_path: str) -> Optional[str]:
    """Find the sidecar map file for a given log file.

    Looks for <log>.kloc.jsonl in the same directory.
    """
    candidate = log_path + '.kloc.jsonl'
    if os.path.exists(candidate):
        return candidate
    return None
