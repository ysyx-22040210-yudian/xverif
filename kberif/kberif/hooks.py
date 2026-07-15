from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .cards import reconcile_detail_metadata, update_catalog, validate_all, validate_card_file, validate_detail_file
from .errors import KberifError
from .paths import state_dir


def _hook_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()


def _tool_path(data: dict[str, Any]) -> Path | None:
    return _tool_path_for_root(data, _root())


def _tool_path_for_root(data: dict[str, Any], root: Path) -> Path | None:
    tool_input = data.get("tool_input", {})
    path = tool_input.get("file_path")
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _is_under(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


KBERIF_BASH_RE = re.compile(r"(?:^|[\s'\"=:/])(?:\./)?\.kberif(?:/|[\s'\"()]|$)")


def _bash_mentions_kberif(command: str) -> bool:
    return bool(KBERIF_BASH_RE.search(command))


def _deny_guard() -> int:
    message = (
        "Blocked direct access to .kberif. .kberif is kberif-managed state; "
        "do not read or edit it directly. Use the kberif skill or CLI instead: "
        "read with `kberif status`, `kberif brief`, `kberif list-topics`, "
        "`kberif get <topic>`, or `kberif detail <topic>`; modify with the "
        "kberif card/detail workflow, `kberif repair-catalog`, and `kberif validate`."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                },
                "systemMessage": message,
            },
            ensure_ascii=False,
        )
    )
    return 0


def guard_state_access() -> int:
    root = _root()
    data = _hook_input()
    tool_name = data.get("tool_name", "")
    if tool_name in {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}:
        path = _tool_path_for_root(data, root)
        if path is not None and _is_under(path, state_dir(root)):
            return _deny_guard()
    if tool_name == "Bash":
        command = data.get("tool_input", {}).get("command", "")
        if isinstance(command, str) and _bash_mentions_kberif(command):
            return _deny_guard()
    return 0


def _generated_kind(root: Path, path: Path) -> str | None:
    if path.parent == (state_dir(root) / "cards").resolve() and path.suffix == ".json":
        return "card"
    if path.parent == (state_dir(root) / "details").resolve() and path.suffix == ".md":
        return "detail"
    return None


def validate_card_write() -> int:
    root = _root()
    data = _hook_input()
    path = _tool_path(data)
    kind = _generated_kind(root, path) if path is not None else None
    if path is None or kind is None:
        return 0
    try:
        if kind == "card":
            validate_card_file(root, path)
        else:
            validate_detail_file(root, path)
    except (OSError, json.JSONDecodeError, KberifError) as exc:
        print(f"kberif card validation failed for {path}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"systemMessage": f"kberif validated {kind} {path.name}"}, ensure_ascii=False))
    return 0


def validate_stop() -> int:
    root = _root()
    try:
        reconcile_detail_metadata(root)
        update_catalog(root)
        errors = validate_all(root)
    except Exception as exc:  # noqa: BLE001 - hook must return a clean block reason.
        errors = [str(exc)]
    if errors:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "kberif validation failed: " + "; ".join(errors),
                    "systemMessage": "Fix the invalid kberif cards before stopping.",
                },
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps({"decision": "approve", "systemMessage": "kberif validation passed"}, ensure_ascii=False))
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m kberif.hooks <validate-card-write|validate-stop|guard-state-access>", file=sys.stderr)
        return 2
    if sys.argv[1] == "validate-card-write":
        return validate_card_write()
    if sys.argv[1] == "validate-stop":
        return validate_stop()
    if sys.argv[1] == "guard-state-access":
        return guard_state_access()
    print(f"unknown hook command: {sys.argv[1]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
