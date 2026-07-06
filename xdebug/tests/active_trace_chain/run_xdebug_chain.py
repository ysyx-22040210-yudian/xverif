#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path


def usage():
    print(
        "usage: run_xdebug_chain.py XDEBUG SESSION DAIDIR FSDB SIGNAL TIME OUT_DIR",
        file=sys.stderr,
    )


def extract_json(text):
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in xdebug output")
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : idx + 1])
    raise ValueError("unterminated JSON object in xdebug output")


def run_xdebug(xdebug, request, timeout_sec=180):
    proc = subprocess.run(
        [xdebug, "--json", "-"],
        input=json.dumps(request) + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_sec,
    )
    combined = proc.stdout + proc.stderr
    response = extract_json(combined)
    if proc.returncode != 0 or not response.get("ok", False):
        err = response.get("error") or {}
        raise RuntimeError(
            "%s failed rc=%s code=%s message=%s"
            % (
                request.get("action", ""),
                proc.returncode,
                err.get("code", ""),
                err.get("message", combined[-1000:]),
            )
        )
    return response


def main(argv):
    if len(argv) != 7:
        usage()
        return 2
    xdebug, session, daidir, fsdb, signal, time_spec, out_dir = argv
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    open_req = {
        "api_version": "xdebug.v1",
        "action": "session.open",
        "target": {"daidir": daidir, "fsdb": fsdb},
        "args": {"name": session},
        "output": {"format": "json", "verbosity": "compact"},
    }
    open_resp = run_xdebug(xdebug, open_req)
    sess = open_resp.get("session") or (open_resp.get("data") or {}).get("session") or {}
    session_id = sess.get("session_id") or sess.get("id") or session

    try:
        chain_req = {
            "api_version": "xdebug.v1",
            "action": "trace.active_driver_chain",
            "target": {"session_id": session_id},
            "args": {"signal": signal, "requested_time": time_spec, "clk_period": "10ns"},
            "limits": {"max_depth": 16, "max_nodes": 64},
            "output": {"format": "json", "verbosity": "compact"},
        }
        chain_resp = run_xdebug(xdebug, chain_req)
        (out_path / "trace_chain.json").write_text(
            json.dumps(chain_resp, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(chain_resp.get("summary", {}), sort_keys=True))
    finally:
        close_req = {
            "api_version": "xdebug.v1",
            "action": "session.kill",
            "args": {"id": session_id},
            "output": {"format": "json", "verbosity": "compact"},
        }
        try:
            run_xdebug(xdebug, close_req, timeout_sec=30)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
