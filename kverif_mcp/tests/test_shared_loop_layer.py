"""Tests for the SDK-free shared loop backend layer."""

from __future__ import annotations

from pathlib import Path


def test_kverif_loop_imports_without_mcp_sdk() -> None:
    import kverif_loop
    from kverif_loop.lsf.protocol import JsonlProcess, ProtocolError
    from kverif_loop.sessions.session_manager import McpSessionManager

    assert kverif_loop is not None
    assert JsonlProcess is not None
    assert ProtocolError is not None
    assert McpSessionManager is not None


def test_kverif_loop_package_has_no_mcp_sdk_imports() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "kverif_loop"
    offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("from mcp", "import mcp", "kverif_mcp.server"):
            if needle in text:
                offenders.append(f"{path.relative_to(package_root)}:{needle}")
    assert offenders == []
