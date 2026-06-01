import sys
from collections import Counter
from typing import Dict

from .mapfile import iter_loc_ids, load_map, find_map_file


def cmd_stats(log_path: str, map_path=None, top: int = 20) -> None:
    """stats <sim.log> — count loc_id frequency, print top N."""
    if map_path is None:
        map_path = find_map_file(log_path)

    entries = load_map(map_path) if map_path else {}

    with open(log_path, 'r') as f:
        text = f.read()

    counts = Counter(iter_loc_ids(text))

    if not counts:
        print("No loc_ids found in log.")
        return

    print(f"{'loc_id':<14} {'count':>6}  {'file':<40} {'msg_id'}")
    print("-" * 100)
    for loc_id, count in counts.most_common(top):
        entry = entries.get(loc_id, {})
        filepath = entry.get('file', '?')
        msg_id = entry.get('msg_id', '?')
        print(f"{loc_id:<14} {count:>6}  {filepath:<40} {msg_id}")

    total_unique = len(counts)
    total_hits = sum(counts.values())
    print(f"\n{total_unique} unique locations, {total_hits} total occurrences")
