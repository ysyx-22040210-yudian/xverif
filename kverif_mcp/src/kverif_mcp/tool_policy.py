"""Tool exposure policy for kverif MCP."""

from __future__ import annotations

import os
from typing import Any, Iterable, Optional


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}

GROUP_ENV = {
    "common": ("KVERIF_MCP_ENABLE_COMMON", True),
    "debug": ("KVERIF_MCP_ENABLE_DEBUG", True),
    "cov": ("KVERIF_MCP_ENABLE_COV", True),
    "bit": ("KVERIF_MCP_ENABLE_BIT", True),
    "entry": ("KVERIF_MCP_ENABLE_ENTRY", True),
    "loc": ("KVERIF_MCP_ENABLE_LOC", True),
    "context": ("KVERIF_MCP_ENABLE_CONTEXT", True),
    "context_write": ("KVERIF_MCP_ENABLE_CONTEXT_WRITE", False),
    "sva": ("KVERIF_MCP_ENABLE_SVA", True),
}


def _parse_bool(raw: Optional[str], default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def env_bool(name: str, default: bool = True) -> bool:
    return _parse_bool(os.environ.get(name), default)


def _invalid_bool_warning(name: str, default: bool) -> Optional[str]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in TRUE_VALUES or value in FALSE_VALUES:
        return None
    return f"{name}={raw!r} is not a boolean; using default {int(default)}"


def policy_warnings() -> list[str]:
    warnings: list[str] = []
    for name, default in GROUP_ENV.values():
        warning = _invalid_bool_warning(name, default)
        if warning:
            warnings.append(warning)
    warning = _invalid_bool_warning("KVERIF_MCP_ENABLE_WRITE", False)
    if warning:
        warnings.append(warning)
    return warnings


def group_enabled(group: str) -> bool:
    if group == "context_write":
        name, default = GROUP_ENV[group]
        return (
            group_enabled("context")
            and env_bool(name, default)
            and env_bool("KVERIF_MCP_ENABLE_WRITE", False)
        )
    item = GROUP_ENV.get(group)
    if item is None:
        return False
    name, default = item
    return env_bool(name, default)


def tool_enabled(group: str, write: bool = False) -> bool:
    if write:
        return group_enabled("context_write")
    return group_enabled(group)


def policy_summary() -> dict[str, Any]:
    groups = {group: group_enabled(group) for group in GROUP_ENV}
    return {
        "groups": groups,
        "write_enabled": env_bool("KVERIF_MCP_ENABLE_WRITE", False),
        "warnings": policy_warnings(),
    }


def filtered_catalog(
    catalog: Iterable[dict[str, Any]],
    category: Optional[str] = None,
    include_write: bool = False,
) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for item in catalog:
        if category and item.get("category") != category:
            continue
        write = bool(item.get("write"))
        if write and not include_write:
            continue
        group = str(item.get("group") or item.get("category") or "")
        if not tool_enabled(group, write=write):
            continue
        tools.append(dict(item))
    return tools
