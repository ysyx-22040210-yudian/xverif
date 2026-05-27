#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
XDEBUG = os.path.join(ROOT, "tools", "xdebug-env")
FSDB = os.environ.get("XDEBUG_SYSTEM_FSDB", "/home/yian/wave_tmp/waves.fsdb")


def query(home, request):
    env = os.environ.copy()
    env["HOME"] = home
    proc = subprocess.run([XDEBUG, "-"], input=json.dumps(request) + "\n", universal_newlines=True,
                          cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = json.loads(proc.stdout)
    if proc.returncode != 0 or not result.get("ok"):
        raise AssertionError("{}\n{}".format(result, proc.stderr))
    return result


def main():
    if not os.path.isfile(FSDB):
        print("SKIP: system FSDB not found: {}".format(FSDB))
        return 0
    home = tempfile.mkdtemp(prefix="xdebug-system-wave-")
    session = "system_wave"
    query(home, {"api_version": "xdebug.v1", "action": "session.open",
                 "target": {"fsdb": FSDB}, "args": {"name": session}})
    value = query(home, {"api_version": "xdebug.v1", "action": "value.at",
                         "target": {"session_id": session},
                         "args": {"signal": "xring_tb_top.rst_n", "time": "11000ns", "format": "binary"}})
    assert "value" in value["data"]
    changes = query(home, {"api_version": "xdebug.v1", "action": "signal.changes",
                           "target": {"session_id": session},
                           "args": {"signal": "xring_tb_top.clk",
                                    "time_range": {"begin": "100ns", "end": "120ns"}},
                           "limits": {"max_events": 20}})
    assert "changes" in changes["data"]
    query(home, {"api_version": "xdebug.v1", "action": "session.kill",
                 "args": {"id": "all"}})
    print("PASS: xdebug system waveform smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
