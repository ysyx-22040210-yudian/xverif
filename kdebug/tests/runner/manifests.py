from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml


Json = Dict[str, Any]
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class TestManifest:
    path: Path
    name: str
    fsdb: Optional[Path]
    daidir: Optional[Path]
    top: Optional[str]
    tags: List[str]
    timeout_sec: float
    queries: List[Json]
    raw: Json


def _expand_string(value: str, env: Mapping[str, str]) -> str:
    missing = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            missing.append(name)
            return match.group(0)
        return env[name]

    expanded = _ENV_PATTERN.sub(replace, value)
    if missing:
        raise ManifestError(
            "unresolved environment variables: %s" % ", ".join(sorted(set(missing)))
        )
    return expanded


def _expand(value: Any, env: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _expand_string(value, env)
    if isinstance(value, list):
        return [_expand(item, env) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item, env) for key, item in value.items()}
    return value


def _resolve_path(value: Optional[str], base: Path) -> Optional[Path]:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def load_manifest(
    path: Path,
    *,
    env: Optional[Mapping[str, str]] = None,
    require_resource: bool = True,
) -> TestManifest:
    manifest_path = Path(path).resolve()
    try:
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError("failed to load manifest %s: %s" % (manifest_path, exc))
    if not isinstance(loaded, dict):
        raise ManifestError("manifest must be a mapping: %s" % manifest_path)

    data = _expand(loaded, dict(os.environ) if env is None else env)
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ManifestError("manifest.name must be a non-empty string")

    queries = data.get("queries", [])
    if not isinstance(queries, list):
        raise ManifestError("manifest.queries must be a list")
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            raise ManifestError("queries[%d] must be a mapping" % index)
        if not isinstance(query.get("action"), str) or not query["action"]:
            raise ManifestError("queries[%d].action must be a non-empty string" % index)
        if "expect" in query and not isinstance(query["expect"], dict):
            raise ManifestError("queries[%d].expect must be a mapping" % index)

    fsdb = _resolve_path(data.get("fsdb"), manifest_path.parent)
    daidir = _resolve_path(data.get("daidir"), manifest_path.parent)
    if require_resource and fsdb is None and daidir is None:
        raise ManifestError("manifest requires fsdb or daidir")

    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ManifestError("manifest.tags must be a list of strings")

    timeout_sec = data.get("timeout_sec", 600)
    if not isinstance(timeout_sec, (int, float)) or timeout_sec <= 0:
        raise ManifestError("manifest.timeout_sec must be positive")

    top = data.get("top")
    if top is not None and not isinstance(top, str):
        raise ManifestError("manifest.top must be a string")

    return TestManifest(
        path=manifest_path,
        name=name,
        fsdb=fsdb,
        daidir=daidir,
        top=top,
        tags=list(tags),
        timeout_sec=float(timeout_sec),
        queries=list(queries),
        raw=data,
    )
