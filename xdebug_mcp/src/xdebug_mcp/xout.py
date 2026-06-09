"""XOUT helpers."""

from __future__ import annotations


def detect_xout(text: str) -> bool:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        return line.startswith("@xdebug.") and line.endswith(".v1")
    return False

