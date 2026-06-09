#!/usr/bin/env python3
"""Compatibility shim for the xdebug MCP server."""

from xdebug_mcp.server import (  # noqa: F401
    ManagedSession,
    XdebugMcpServer,
    XdebugRunner,
    main,
    read_message,
    serve_stdio,
    write_message,
)


if __name__ == "__main__":
    raise SystemExit(main())
