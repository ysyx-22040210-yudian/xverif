from __future__ import annotations

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
        self.lines: list[str] = []
        self.pending: str | None = None
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
        if value is None or value == [] or value == {}:
            return
        nested = self._ensure()
        self.lines.append(f"{'  ' if nested else ''}{_key(key)}: {_value(value)}")

    def emit_row(self, *columns: Any) -> None:
        row = " ".join(part for part in (" ".join(_value(col).split()) for col in columns) if part)
        if not row:
            return
        nested = self._ensure()
        self.lines.append(f"{'  ' if nested else ''}{row}")

    def emit_error(self, code: str, message: str) -> None:
        self.emit_kv("code", code)
        self.emit_kv("message", message)

    def render(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


def render_status(payload: dict) -> str:
    out = TextResponseBuilder("kberif")
    out.emit_header("status")
    out.emit_section("summary")
    for key in ("state", "configured", "state_dir_exists", "catalog_exists", "catalog_card_count", "raw_card_count", "raw_detail_count"):
        out.emit_kv(key, payload.get(key))
    out.emit_section("next")
    out.emit_row(payload.get("next_action"))
    return out.render()


def render_list_topics(payload: dict) -> str:
    out = TextResponseBuilder("kberif")
    out.emit_header("list-topics")
    out.emit_section("summary")
    out.emit_kv("env_kind", payload.get("env_kind"))
    out.emit_kv("topic_count", len(payload.get("topics", [])))
    out.emit_section("data")
    for topic in payload.get("topics", []):
        out.emit_row(topic.get("topic"), topic.get("card_id"), topic.get("key_item_count"), "detail=" + _value(topic.get("detail_available")))
    return out.render()


def render_topic(payload: dict) -> str:
    out = TextResponseBuilder("kberif")
    out.emit_header("get")
    out.emit_section("target")
    out.emit_kv("topic", payload.get("topic"))
    out.emit_kv("env_kind", payload.get("env_kind"))
    out.emit_section("summary")
    out.emit_kv("title", payload.get("title"))
    out.emit_kv("summary", payload.get("summary"))
    out.emit_kv("confidence", payload.get("confidence"))
    out.emit_kv("detail_available", payload.get("detail_available"))
    out.emit_kv("detail_token_estimate", payload.get("detail_token_estimate"))
    out.emit_section("data")
    for item in payload.get("key_items", []):
        out.emit_row(item.get("name", "item"), item.get("one_line", ""))
    out.emit_section("next")
    if payload.get("detail_available"):
        out.emit_row("kberif detail", payload.get("topic"))
    return out.render()


def render_repair(payload: dict) -> str:
    out = TextResponseBuilder("kberif")
    out.emit_header("repair-catalog")
    out.emit_section("summary")
    out.emit_kv("ok", payload.get("ok"))
    out.emit_kv("catalog_card_count", payload.get("catalog_card_count"))
    return out.render()
