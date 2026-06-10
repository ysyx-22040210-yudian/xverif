"""Verify backend wiring — XverifDebugAdapter uses McpSessionManager."""

from xverif_mcp.adapters.xdebug import XverifDebugAdapter
from xverif_mcp.sessions.session_manager import McpSessionManager


def test_backend_uses_session_manager():
    backend = XverifDebugAdapter(mode="direct")
    assert isinstance(backend._sessions, McpSessionManager)


def test_lsf_mode_rejected():
    import pytest
    from xverif_mcp.sessions.session_manager import McpSessionManager
    with pytest.raises(ValueError, match="unsupported"):
        McpSessionManager(mode="invalid")
