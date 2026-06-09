#!/usr/bin/env python3
"""Compatibility shim for the xdebug MCP server.

Old classes are imported from server_legacy; the new FastMCP app instance is
imported from server.
"""

from xdebug_mcp.server_legacy import (  # noqa: F401
    ManagedSession,
    XdebugMcpServer,
    XdebugRunner,
    main,
    read_message,
    serve_stdio,
    write_message,
)

from xdebug_mcp.server import mcp  # noqa: F401


if __name__ == "__main__":
    from xdebug_mcp.server_legacy import main as legacy_main
    raise SystemExit(legacy_main())
