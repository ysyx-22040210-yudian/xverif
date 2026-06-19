from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

import pytest

from runner import CliRunner


def _request(action: str, *, target=None, args=None):
    request = {"api_version": "xdebug.v1", "action": action}
    if target is not None:
        request["target"] = target
    if args is not None:
        request["args"] = args
    return request


def _registry(isolated_home: Path) -> dict:
    path = isolated_home / ".xdebug" / "engine" / "registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _registry_session(isolated_home: Path, session_id: str) -> dict:
    sessions = _registry(isolated_home).get("sessions", [])
    return next(item for item in sessions if item["session_id"] == session_id)


def _kill_all(cli_runner: CliRunner) -> None:
    cli_runner.run(_request("session.kill", args={"id": "all"}))


@pytest.fixture
def resource_targets(xdebug_root: Path):
    return {
        "design": {
            "daidir": str(xdebug_root / "testdata" / "design" / "uart" / "simv.daidir")
        },
        "waveform": {
            "fsdb": str(
                xdebug_root
                / "testdata"
                / "waveform"
                / "ai_complex_wave"
                / "out"
                / "waves.fsdb"
            )
        },
        "combined": {
            "daidir": str(
                xdebug_root
                / "testdata"
                / "combined"
                / "active_driver"
                / "out"
                / "simv.daidir"
            ),
            "fsdb": str(
                xdebug_root
                / "testdata"
                / "combined"
                / "active_driver"
                / "out"
                / "waves.fsdb"
            ),
        },
    }


@pytest.mark.session
@pytest.mark.parametrize("mode", ["design", "waveform", "combined"])
def test_session_open_list_doctor_close_for_each_resource_mode(
    mode: str,
    resource_targets: dict,
    cli_runner: CliRunner,
    isolated_home: Path,
) -> None:
    name = "lifecycle_%s" % mode
    try:
        opened = cli_runner.run(
            _request(
                "session.open",
                target=resource_targets[mode],
                args={"name": name},
            )
        )
        assert opened.ok
        assert opened.response["summary"]["mode"] == mode

        listed = cli_runner.run(_request("session.list"))
        records = listed.response["data"]["sessions"]
        assert any(item["session_id"] == name and item["mode"] == mode for item in records)

        doctor = cli_runner.run(
            _request("session.doctor", target={"session_id": name})
        )
        assert doctor.ok
        assert doctor.response["summary"]["healthy"] is True

        native = _registry_session(isolated_home, name)
        assert native["session_id"] == name
        assert native["server_pid"] > 0
        assert Path(native["socket_path"]).exists()

        closed = cli_runner.run(
            _request("session.close", target={"session_id": name})
        )
        assert closed.ok
        assert closed.response["summary"]["removed"] is True
        assert not Path(native["socket_path"]).exists()
        assert not any(
            item["session_id"] == name
            for item in _registry(isolated_home).get("sessions", [])
        )
    finally:
        _kill_all(cli_runner)

@pytest.mark.session
def test_session_duplicate_reuse_ensure_and_reopen_contract(
    resource_targets: dict,
    cli_runner: CliRunner,
    isolated_home: Path,
) -> None:
    name = "reuse_reopen"
    target = resource_targets["design"]
    try:
        opened = cli_runner.run(
            _request("session.open", target=target, args={"name": name})
        )
        assert opened.ok
        first = _registry_session(isolated_home, name)

        duplicate = cli_runner.run(
            _request("session.open", target=target, args={"name": name})
        )
        assert not duplicate.ok
        assert duplicate.response["error"]["code"] == "SESSION_ID_EXISTS"

        reused = cli_runner.run(
            _request(
                "session.open",
                target=target,
                args={"name": name, "reuse": True},
            )
        )
        assert reused.ok
        assert reused.response["summary"]["reused"] is True
        assert _registry_session(isolated_home, name)["server_pid"] == first["server_pid"]

        ensured = cli_runner.run(
            _request("session.ensure", target=target, args={"name": name})
        )
        assert ensured.ok
        assert ensured.response["summary"]["reused"] is True

        reopened = cli_runner.run(
            _request(
                "session.open",
                target=target,
                args={"name": name, "reopen": True},
            )
        )
        assert reopened.ok
        assert reopened.response["summary"]["reopened"] is True
        second = _registry_session(isolated_home, name)
        assert second["server_pid"] != first["server_pid"]
        with pytest.raises(ProcessLookupError):
            os.kill(first["server_pid"], 0)
    finally:
        _kill_all(cli_runner)


@pytest.mark.session
def test_session_gc_removes_crashed_engine(
    resource_targets: dict,
    cli_runner: CliRunner,
    isolated_home: Path,
) -> None:
    name = "crash_gc"
    try:
        opened = cli_runner.run(
            _request(
                "session.open",
                target=resource_targets["design"],
                args={"name": name},
            )
        )
        assert opened.ok
        native = _registry_session(isolated_home, name)
        os.kill(native["server_pid"], signal.SIGKILL)

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(native["server_pid"], 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)

        gc = cli_runner.run(_request("session.gc"))
        assert gc.ok
        assert gc.response["summary"]["removed_count"] == 1
        assert gc.response["data"]["removed"][0]["session_id"] == name
        assert not Path(native["socket_path"]).exists()
    finally:
        _kill_all(cli_runner)
