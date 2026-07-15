from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path

from pathspec.gitignore import GitIgnoreSpec

from .io import write_json
from .paths import relpath, state_dir


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) or GitIgnoreSpec.from_lines([p]).match_file(path) for p in patterns)


def _line_count(data: bytes) -> int:
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def build_manifest(root: Path, kind: str, config: dict) -> dict:
    root = root.resolve()
    deny_paths = config.get("safety", {}).get("deny_paths", [])
    max_files = int(config.get("budgets", {}).get("max_files_for_ai", 120))
    max_bytes = int(config.get("budgets", {}).get("max_bytes_per_file", 120000))
    inputs = config.get("inputs", {})
    files: list[dict] = []
    excluded: list[dict] = []
    seen: set[str] = set()

    for _name, input_cfg in inputs.items():
        role = input_cfg.get("role", _name)
        includes = input_cfg.get("include", [])
        excludes = input_cfg.get("exclude", [])
        candidates: list[Path] = []
        for pattern in includes:
            candidates.extend(p for p in root.glob(pattern) if p.is_file())
        for path in sorted(set(candidates)):
            rel = relpath(root, path)
            if rel in seen:
                continue
            if _matches(rel, deny_paths):
                excluded.append({"path": rel, "reason": "matched deny_paths"})
                continue
            if _matches(rel, excludes):
                excluded.append({"path": rel, "reason": "matched input exclude"})
                continue
            data = path.read_bytes()
            if len(data) > max_bytes:
                excluded.append({"path": rel, "reason": "exceeded max_bytes_per_file"})
                continue
            digest = hashlib.sha256(data).hexdigest()
            files.append(
                {
                    "path": rel,
                    "role": role,
                    "size": len(data),
                    "sha256": digest,
                    "lines": _line_count(data),
                }
            )
            seen.add(rel)
            if len(files) >= max_files:
                excluded.append({"path": "*", "reason": "exceeded max_files_for_ai"})
                break
        if len(files) >= max_files:
            break

    return {
        "schema_version": "kberif.manifest.v1",
        "env_kind": kind,
        "root": str(root),
        "files": files,
        "excluded": excluded,
    }


def write_manifest(root: Path, kind: str, config: dict) -> dict:
    manifest = build_manifest(root, kind, config)
    write_json(state_dir(root) / "manifest.json", manifest)
    return manifest
