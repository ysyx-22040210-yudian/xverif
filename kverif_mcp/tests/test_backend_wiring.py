"""Verify backend wiring — KverifDebugAdapter uses McpSessionManager."""

from kverif_mcp.adapters.kdebug import KverifDebugAdapter
from kverif_mcp.sessions.session_manager import McpSessionManager


def test_backend_uses_session_manager():
    backend = KverifDebugAdapter(mode="direct")
    assert isinstance(backend._sessions, McpSessionManager)


def test_lsf_mode_rejected():
    import pytest
    from kverif_mcp.sessions.session_manager import McpSessionManager
    with pytest.raises(ValueError, match="unsupported"):
        McpSessionManager(mode="invalid")
