import json
import re
from typing import Any


def _key(key: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]", "_", str(key))
    return text or "field"


def _value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    text = text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", " ")
    return text[:4096] + ("..." if len(text) > 4096 else "")


class TextResponseBuilder:
    def __init__(self, tool: str):
        self.tool = tool
        self.lines = []
        self.pending = None
        self.in_section = False
        self.wrote_content = False

    def emit_header(self, action: str) -> None:
        self.lines.append(f"@{self.tool}.{action}.v1")

    def emit_section(self, name: str) -> None:
        self.pending = _key(name)

    def _ensure(self) -> bool:
        nested = self.in_section or self.pending is not None
        if self.pending is not None:
            if self.wrote_content:
                self.lines.append("")
            self.lines.append(f"{self.pending}:")
            self.pending = None
            self.in_section = True
            self.wrote_content = True
        elif not self.wrote_content:
            self.lines.append("")
            self.wrote_content = True
        return nested

    def emit_kv(self, key: str, value: Any) -> None:
        if value is None or value == {} or value == []:
            return
        nested = self._ensure()
        self.lines.append(f"{'  ' if nested else ''}{_key(key)}: {_value(value)}")

    def emit_row(self, *columns: Any) -> None:
        row = " ".join(" ".join(_value(col).split()) for col in columns if _value(col))
        if not row:
            return
        nested = self._ensure()
        self.lines.append(f"{'  ' if nested else ''}{row}")

    def emit_warning(self, code: str, message: str) -> None:
        self.emit_section("warnings")
        self.emit_row(code, message)

    def emit_error(self, error: dict) -> None:
        self.emit_kv("code", error.get("code"))
        self.emit_kv("message", error.get("message"))

    def render(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
