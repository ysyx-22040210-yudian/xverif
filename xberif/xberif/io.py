from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def read_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def write_toml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import tomli_w
    except ModuleNotFoundError:
        path.write_text(_dump_toml(data), encoding="utf-8")
        return
    with path.open("wb") as fh:
        tomli_w.dump(data, fh)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _dump_toml(data: dict) -> str:
    lines: list[str] = []

    def emit_table(table: dict, prefix: list[str]) -> None:
        scalars: list[tuple[str, Any]] = []
        subtables: list[tuple[str, dict]] = []
        for key, value in table.items():
            if isinstance(value, dict):
                subtables.append((key, value))
            else:
                scalars.append((key, value))

        if prefix:
            lines.append(f"[{'.'.join(prefix)}]")
        for key, value in scalars:
            lines.append(f"{key} = {_toml_value(value)}")
        if scalars and subtables:
            lines.append("")

        for index, (key, value) in enumerate(subtables):
            emit_table(value, [*prefix, key])
            if index != len(subtables) - 1:
                lines.append("")

    emit_table(data, [])
    return "\n".join(lines).rstrip() + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if value is None:
        return '""'
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")
