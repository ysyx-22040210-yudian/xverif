from __future__ import annotations

import shutil
from pathlib import Path

from ..errors import KberifError
from ..io import write_text, write_toml
from ..paths import config_dir
from ..templates import KINDS, default_views, kind_config, template_prompt_path, topics_config, topics_for


def init_config(root: Path, kind: str, force: bool = False, merge: bool = False, dry_run: bool = False) -> list[Path]:
    if kind not in KINDS:
        raise KberifError("KIND_MISMATCH", f"unsupported env_kind {kind}")
    xdir = config_dir(root)
    kind_path = xdir / "kind.toml"
    if kind_path.exists() and not force and not merge:
        raise KberifError("VALIDATION_FAILED", "kberif/kind.toml already exists; use --force or --merge")
    if force and xdir.exists() and not dry_run:
        shutil.rmtree(xdir)

    files: dict[Path, object] = {
        kind_path: kind_config(kind),
        xdir / "topics.toml": topics_config(kind),
    }
    prompt_copies: dict[Path, Path] = {}
    for _topic, _title, prompt, _required in topics_for(kind):
        source = template_prompt_path(kind, prompt)
        if not source.exists():
            raise KberifError("VALIDATION_FAILED", f"missing builtin prompt template: {source}")
        prompt_copies[xdir / "prompts" / prompt] = source
    for name, view in default_views(kind).items():
        files[xdir / "views" / f"{name}.toml"] = view

    written = []
    for path, data in {**files, **prompt_copies}.items():
        if merge and path.exists() and not force:
            continue
        written.append(path)
        if dry_run:
            continue
        if isinstance(data, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(data, path)
        elif isinstance(data, str):
            write_text(path, data)
        else:
            write_toml(path, data)
    return written
