"""Doctor command for xdebug LSF MCP integration."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from typing import Dict, List, Optional

from xdebug_mcp.backend import LsfBackend


def _check_mcp_sdk() -> str:
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"missing: {exc}"


def run(fake: bool = False) -> Dict[str, object]:
    started = time.time()
    out: Dict[str, object] = {
        "python_version": sys.version.split()[0],
        "mcp_sdk_import": _check_mcp_sdk(),
        "bsub": "fake" if fake else ("ok" if shutil.which("bsub") else "missing"),
    }
    old_fake = os.environ.get("XDEBUG_MCP_FAKE_LSF")
    if fake:
        os.environ["XDEBUG_MCP_FAKE_LSF"] = "1"
    try:
        backend = LsfBackend(fake=fake)
        pong = backend.ping()
        out["router_ready"] = "ok" if pong == "pong" else pong
        opened = backend.session_open("doctor", fsdb="doctor.fsdb")
        out["session_ready"] = "ok" if opened.get("ok") else opened
        query = backend.query("doctor", "value.at", {"signal": "top.clk", "time": "1ns"}, "xout")
        out["xout_passthrough"] = "ok" if isinstance(query, str) and query.startswith("@xdebug.") else query
        closed = backend.session_close("doctor")
        out["shutdown"] = "ok" if closed.get("ok") else closed
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    finally:
        if old_fake is None:
            os.environ.pop("XDEBUG_MCP_FAKE_LSF", None)
        else:
            os.environ["XDEBUG_MCP_FAKE_LSF"] = old_fake
    out["elapsed_ms"] = int((time.time() - started) * 1000)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    fake = "--fake" in (argv or sys.argv[1:])
    result = run(fake=fake)
    print("xdebug_lsf_doctor:")
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        print(f"  {key}: {value}")
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())

