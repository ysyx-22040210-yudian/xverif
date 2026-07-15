import sys
from typing import Set

from .mapfile import iter_loc_ids, load_map, find_map_file


def cmd_annotate(log_path: str, map_path=None) -> None:
    """annotate <sim.log> — insert resolution lines before first occurrence of each loc_id."""
    if map_path is None:
        map_path = find_map_file(log_path)

    entries = load_map(map_path) if map_path else {}
    seen: Set[str] = set()

    with open(log_path, 'r') as f:
        for line in f:
            for loc_id in iter_loc_ids(line):
                if loc_id not in seen:
                    seen.add(loc_id)
                    entry = entries.get(loc_id, {})
                    filepath = entry.get('file', '?')
                    line_num = entry.get('line', '?')
                    print(f"[loc] {loc_id} -> {filepath}:{line_num}")
            sys.stdout.write(line)
