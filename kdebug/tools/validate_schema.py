#!/usr/bin/env python3
"""Parse and sanity-check kdebug JSON schema files.

This intentionally avoids third-party dependencies. It validates schema files
well enough to catch malformed JSON and common authoring mistakes before the
runtime contract tests run.
"""

import json
import sys
from pathlib import Path
from typing import Any, List


ALLOWED_TYPES = {
    "array",
    "boolean",
    "integer",
    "null",
    "number",
    "object",
    "string",
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def check_schema_node(node: Any, path: str) -> None:
    if not isinstance(node, dict):
        return
    if "type" in node:
        types = node["type"]
        if isinstance(types, str):
            types = [types]
        if not isinstance(types, list) or not all(t in ALLOWED_TYPES for t in types):
            fail(f"{path}: invalid type {node['type']!r}")
    if "required" in node:
        required = node["required"]
        if not isinstance(required, list) or not all(isinstance(v, str) for v in required):
            fail(f"{path}: required must be a string array")
    if "enum" in node:
        enum = node["enum"]
        if not isinstance(enum, list) or not enum:
            fail(f"{path}: enum must be a non-empty array")
    if "properties" in node:
        props = node["properties"]
        if not isinstance(props, dict):
            fail(f"{path}: properties must be an object")
        for name, child in props.items():
            check_schema_node(child, f"{path}.properties.{name}")
    if "items" in node:
        check_schema_node(node["items"], f"{path}.items")


def main(argv: List[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("kdebug/schemas/v1")
    if not root.exists():
        fail(f"schema root does not exist: {root}")
    files = sorted(root.rglob("*.schema.json"))
    if not files:
        fail(f"no schema files found under {root}")
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as fh:
                schema = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            fail(f"{path}: cannot parse JSON: {exc}")
        if not isinstance(schema, dict):
            fail(f"{path}: top-level schema must be an object")
        if "$schema" not in schema:
            fail(f"{path}: missing $schema")
        if "title" not in schema:
            fail(f"{path}: missing title")
        check_schema_node(schema, str(path))
    print(f"validated {len(files)} schema files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
