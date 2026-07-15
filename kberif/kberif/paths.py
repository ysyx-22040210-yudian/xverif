from __future__ import annotations

from pathlib import Path


def config_dir(root: Path) -> Path:
    return root / "kberif"


def state_dir(root: Path) -> Path:
    return root / ".kberif"


def relpath(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
