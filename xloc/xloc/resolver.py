import os
import sys

from .mapfile import load_map, resolve_loc


def cmd_resolve(loc_id: str, map_path: str) -> None:
    """resolve <loc_id> — print file, line, msg_id for a loc_id."""
    entries = load_map(map_path)
    entry = resolve_loc(entries, loc_id)
    if entry is None:
        print(f"{loc_id}: not found in {map_path}", file=sys.stderr)
        sys.exit(1)
    _print_entry(loc_id, entry)


def cmd_context(loc_id: str, map_path: str, before: int = 20, after: int = 20) -> None:
    """context <loc_id> — resolve then print surrounding source lines."""
    entries = load_map(map_path)
    entry = resolve_loc(entries, loc_id)
    if entry is None:
        print(f"{loc_id}: not found in {map_path}", file=sys.stderr)
        sys.exit(1)

    _print_entry(loc_id, entry)

    filepath = entry.get('file', '')
    line_num = entry.get('line', 0)
    if not filepath or not os.path.exists(filepath):
        print(f"\n(source file not found: {filepath})")
        return

    with open(filepath, 'r') as f:
        lines = f.readlines()

    start = max(0, line_num - before - 1)
    end = min(len(lines), line_num + after)
    print()
    for i in range(start, end):
        marker = '>>>' if i == line_num - 1 else '   '
        print(f"{marker} {i + 1:6d}: {lines[i].rstrip()}")


def _print_entry(loc_id: str, entry: dict) -> None:
    filepath = entry.get('file', '?')
    line = entry.get('line', '?')
    msg_id = entry.get('msg_id', '?')
    print(f"loc_id:  {loc_id}")
    print(f"file:    {filepath}")
    print(f"line:    {line}")
    print(f"msg_id:  {msg_id}")
