#!/usr/bin/env python3
"""Audit action-specific xdebug schema/example coverage."""

import json
import sys
from pathlib import Path


def fail(message):
    raise SystemExit("ERROR: " + message)


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path("xdebug")
    specs_path = root / "specs/actions/actions.yaml"
    specs = json.load(open(specs_path, "r", encoding="utf-8"))["actions"]
    missing = []
    generic = []
    non_removed = [item for item in specs if item["status"] != "removed"]
    for item in non_removed:
        name = item["name"]
        schemas = item.get("schemas", {})
        examples = item.get("examples", {})
        for kind in ("request", "response"):
            expected_schema = f"schemas/v1/actions/{name}.{kind}.schema.json"
            if schemas.get(kind) != expected_schema:
                if schemas.get(kind, "").startswith("schemas/v1/xdebug."):
                    generic.append((name, kind, schemas.get(kind)))
                else:
                    missing.append((name, kind, schemas.get(kind)))
            if not (root / expected_schema).exists():
                missing.append((name, kind, expected_schema))
            refs = examples.get(kind)
            if not refs:
                missing.append((name, f"{kind}_example", None))
            else:
                for ref in refs:
                    if not (root / ref).exists():
                        missing.append((name, f"{kind}_example", ref))
    print(f"actions={len(specs)} non_removed={len(non_removed)} generic_refs={len(generic)} missing={len(missing)}")
    if generic:
        for row in generic:
            print("generic", *row)
    if missing:
        for row in missing:
            print("missing", *[str(v) for v in row])
    if generic or missing:
        fail("schema coverage audit failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
