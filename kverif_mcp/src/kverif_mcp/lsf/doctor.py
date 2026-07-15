"""Doctor command for kdebug loop-session integration (direct + LSF)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from typing import Dict, List, Optional

from kverif_mcp.config import default_kdebug_bin
from kverif_mcp.sessions.launchers import DirectLauncher, LaunchConfig
from kverif_mcp.lsf.bsub import parse_lsf_job_id
from kverif_mcp.lsf.protocol import JsonlProcess


def _check_mcp_sdk() -> str:
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
        return "ok"
    except Exception as exc:
        return f"missing: {exc}"


def _check_kdebug_bin() -> str:
    xbin = default_kdebug_bin()
    if os.path.isfile(xbin) and os.access(xbin, os.X_OK):
        return xbin
    # Also try PATH
    found = shutil.which("kdebug")
    return found or f"missing: {xbin}"


def run(fake: bool = False) -> Dict[str, object]:
    started = time.time()
    mode = "lsf" if (fake or os.environ.get("KVERIF_MCP_BACKEND") == "lsf") else "direct"
    out: Dict[str, object] = {
        "python_version": sys.version.split()[0],
        "mcp_sdk_import": _check_mcp_sdk(),
        "mode": mode,
        "kdebug_bin": _check_kdebug_bin(),
    }

    old_fake = os.environ.get("KVERIF_MCP_FAKE_LSF")
    if fake:
        os.environ["KVERIF_MCP_FAKE_LSF"] = "1"

    try:
        if mode == "lsf":
            from kverif_mcp.sessions.launchers import LsfLauncher
            launcher = LsfLauncher()
            out["bsub"] = "fake" if fake else ("ok" if shutil.which("bsub") else "missing")
        else:
            launcher = DirectLauncher()

        cfg = LaunchConfig(
            alias="doctor",
            kdebug_bin=default_kdebug_bin(),
            queue=os.environ.get("KVERIF_LSF_SESSION_QUEUE"),
            job_name=f"kverif_doctor_{os.getpid()}" if mode == "lsf" else None,
            startup_timeout_sec=30.0,
        )

        handle = launcher.start(cfg)
        try:
            out["process_started"] = True

            # Wait for ready
            ready = handle.wait_ready("kdebug-stdio-loop", 30.0)
            out["ready_pid"] = int(ready.get("pid") or 0)

            if mode == "lsf":
                # Collect job_id from stderr/stdout
                time.sleep(0.5)
                for line in list(handle.stderr_tail):
                    jid = parse_lsf_job_id(line)
                    if jid:
                        out["job_id"] = jid
                        break
                out["job_name"] = cfg.job_name

            # Send one request
            rsp = handle.request({
                "request_id": "doctor-actions",
                "api_version": "kdebug.v1",
                "action": "actions",
            }, timeout_sec=30.0)
            out["actions_ok"] = rsp.get("ok", False)

            # Quit
            rsp2 = handle.request({
                "request_id": "doctor-quit",
                "api_version": "kdebug.v1",
                "action": "stdio.quit",
            }, timeout_sec=10.0)
            out["quit_ok"] = rsp2.get("ok", False)
            out["stderr_tail"] = list(handle.stderr_tail)[-5:]
        finally:
            launcher.terminate(handle)

    except Exception as exc:
        out["error"] = str(exc)
    finally:
        if old_fake is None:
            os.environ.pop("KVERIF_MCP_FAKE_LSF", None)
        else:
            os.environ["KVERIF_MCP_FAKE_LSF"] = old_fake

    out["elapsed_ms"] = int((time.time() - started) * 1000)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    fake = "--fake" in (argv or sys.argv[1:])
    result = run(fake=fake)
    print("kverif_lsf_doctor:")
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        print(f"  {key}: {value}")
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
