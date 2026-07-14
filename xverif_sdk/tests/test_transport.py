from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from xverif_sdk import (CallbackTransport, CliTransport, ProtocolError,
                        StdioTransport, ToolInvocationError)


def test_callback_transport_records_isolated_requests():
    transport = CallbackTransport(lambda request: {"ok": True, "data": request})
    request = {"action": "future.action", "args": {"value": 1}}
    response = transport.request(request)
    request["args"]["value"] = 2
    assert response["data"]["args"]["value"] == 1
    assert transport.requests[0]["args"]["value"] == 1


@pytest.mark.parametrize(("configured", "expected"), [(None, None), (0, None), (3, 3)])
def test_cli_transport_timeout_and_json(monkeypatch, configured, expected):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["request"] = json.loads(kwargs["input"])
        observed["timeout"] = kwargs["timeout"]
        return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")

    monkeypatch.setattr("xverif_sdk.transport.subprocess.run", fake_run)
    transport = CliTransport("xdebug", timeout_sec=configured)
    response = transport.request({"api_version": "xdebug.v1", "action": "actions"})
    assert response["ok"] is True
    assert observed["command"] == ["xdebug", "--json", "-"]
    assert observed["request"]["action"] == "actions"
    assert observed["timeout"] == expected


def test_cli_transport_rejects_non_json(monkeypatch):
    monkeypatch.setattr(
        "xverif_sdk.transport.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="noise", stderr="bad"),
    )
    with pytest.raises(ToolInvocationError) as caught:
        CliTransport("xdebug").request({"action": "actions"})
    assert caught.value.returncode == 1
    assert caught.value.stderr_tail == "bad"


def _fake_loop(path: Path) -> Path:
    path.write_text(
        """import json, os, sys, time
print(json.dumps({"type":"ready","protocol":"xdebug-stdio-loop","version":1,"pid":os.getpid()}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    request_id = request.get("request_id", request.get("id", "missing"))
    action = request.get("action", "")
    if action == "stdio.quit":
        print(json.dumps({"id":request_id,"ok":True,"payload_format":"json","json":{"ok":True,"action":action}}), flush=True)
        raise SystemExit(0)
    delay = float(request.get("args", {}).get("sleep", 0))
    if delay:
        time.sleep(delay)
    if action == "fail":
        print(json.dumps({"id":request_id,"ok":False,"error":{"code":"EXPECTED","message":"failed"}}), flush=True)
    else:
        response = {"ok":True,"api_version":"xdebug.v1","action":action,"data":{"request":request}}
        print(json.dumps({"id":request_id,"ok":True,"payload_format":"json","json":response}), flush=True)
""",
        encoding="utf-8",
    )
    return path


def test_stdio_transport_delayed_request_and_structured_error(tmp_path):
    command = [sys.executable, "-u", str(_fake_loop(tmp_path / "fake_loop.py"))]
    transport = StdioTransport(
        command, protocol="xdebug-stdio-loop", api_version="xdebug.v1",
        startup_timeout_sec=2, request_timeout_sec=0,
    )
    with transport:
        response = transport.request({
            "api_version": "xdebug.v1", "action": "value.at",
            "args": {"sleep": 0.05},
        })
        assert response["ok"] is True
        assert response["data"]["request"]["request_id"].startswith("sdk-")
        failed = transport.request({"api_version": "xdebug.v1", "action": "fail"})
        assert failed["ok"] is False
        assert failed["error"]["code"] == "EXPECTED"
    assert transport.proc is not None and transport.proc.poll() == 0


def test_stdio_timeout_terminates_uncorrelatable_stream(tmp_path):
    command = [sys.executable, "-u", str(_fake_loop(tmp_path / "slow_loop.py"))]
    transport = StdioTransport(
        command, protocol="xdebug-stdio-loop", api_version="xdebug.v1",
        startup_timeout_sec=2, request_timeout_sec=0.01,
    )
    transport.start()
    with pytest.raises(ProtocolError, match="timeout"):
        transport.request({
            "api_version": "xdebug.v1", "action": "value.at",
            "args": {"sleep": 0.2},
        })
    assert transport.proc is not None and transport.proc.poll() is not None
