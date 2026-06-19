from __future__ import annotations

import json
import os
import signal
import socket
import threading
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


def _write_registry_session(isolated_home: Path, record: dict) -> None:
    path = isolated_home / ".xdebug" / "engine" / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sessions": [record]}, indent=2), encoding="utf-8")


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
def test_session_duplicate_stale_and_advisory_contract(
    resource_targets: dict,
    cli_runner: CliRunner,
    isolated_home: Path,
) -> None:
    name = "strict_open"
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

        old_reuse = cli_runner.run(
            _request(
                "session.open",
                target=target,
                args={"name": name, "reuse": True},
            )
        )
        assert not old_reuse.ok
        assert old_reuse.response["error"]["code"] == "INVALID_REQUEST"

        ensured = cli_runner.run(
            _request("session.ensure", target=target, args={"name": name})
        )
        assert not ensured.ok
        assert ensured.response["error"]["code"] == "UNKNOWN_ACTION"

        same_resource = cli_runner.run(
            _request(
                "session.open",
                target=target,
                args={"name": "strict_open_b"},
            )
        )
        assert same_resource.ok
        advisories = same_resource.response.get("advisories", [])
        assert advisories
        assert advisories[0]["code"] == "RESOURCE_SESSION_ALREADY_ALIVE"
        assert advisories[0]["existing_session_id"] == name

        os.kill(first["server_pid"], signal.SIGKILL)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(first["server_pid"], 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        stale = cli_runner.run(
            _request("session.open", target=target, args={"name": name})
        )
        assert not stale.ok
        assert stale.response["error"]["code"] == "SESSION_STALE"
    finally:
        _kill_all(cli_runner)


@pytest.mark.session
@pytest.mark.parametrize("name", ["", "1case", "_case", "case-a", "case.a", "case a", "A" * 65])
def test_session_open_rejects_invalid_name(
    name: str,
    resource_targets: dict,
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.run(
        _request("session.open", target=resource_targets["design"], args={"name": name})
    )
    assert not result.ok
    assert result.response["error"]["code"] in ("MISSING_FIELD", "INVALID_SESSION_NAME")


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


@pytest.mark.session
@pytest.mark.waveform
def test_session_file_transport_open_query_doctor_and_close(
    resource_targets: dict,
    cli_runner: CliRunner,
    isolated_home: Path,
) -> None:
    name = "file_transport_wave"
    try:
        opened = cli_runner.run(
            _request(
                "session.open",
                target=resource_targets["waveform"],
                args={"name": name, "transport": "file"},
            )
        )
        assert opened.ok
        assert opened.response["session"]["transport"] == "file"
        file_dir = Path(opened.response["session"]["file_dir"])
        assert file_dir.is_dir()
        assert {
            "requests",
            "claims",
            "responses",
            "done",
            "failed",
            "tmp",
            "heartbeat",
        } <= {child.name for child in file_dir.iterdir() if child.is_dir()}

        native = _registry_session(isolated_home, name)
        assert native["transport"] == "file"
        assert Path(native["file_dir"]) == file_dir

        queried = cli_runner.run(
            _request(
                "value.at",
                target={"session_id": name},
                args={
                    "signal": "ai_complex_top.sig_a",
                    "time": "75ns",
                    "format": "hex",
                },
            )
        )
        assert queried.ok
        assert queried.response["session"]["transport"] == "file"
        assert queried.response["data"]["value"]["known"] is True

        doctor = cli_runner.run(
            _request("session.doctor", target={"session_id": name})
        )
        assert doctor.ok
        assert doctor.response["session"]["transport"] == "file"
        assert doctor.response["session"]["file_dir"] == str(file_dir)
        assert doctor.response["summary"]["healthy"] is True

        closed = cli_runner.run(
            _request("session.close", target={"session_id": name})
        )
        assert closed.ok
        assert closed.response["summary"]["removed"] is True
        assert not any(
            item["session_id"] == name
            for item in _registry(isolated_home).get("sessions", [])
        )
    finally:
        _kill_all(cli_runner)


@pytest.mark.session
@pytest.mark.waveform
def test_session_uds_direct_query_times_out_without_spawn_fallback(
    resource_targets: dict,
    cli_runner: CliRunner,
    isolated_home: Path,
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "hung-engine.sock"
    ready = threading.Event()
    accepted = threading.Event()
    stop = threading.Event()
    server_error: list[BaseException] = []

    def serve_hung_socket() -> None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(socket_path))
                server.listen(1)
                server.settimeout(5.0)
                ready.set()
                conn, _ = server.accept()
                with conn:
                    accepted.set()
                    conn.settimeout(1.0)
                    try:
                        conn.recv(65536)
                    except socket.timeout:
                        pass
                    stop.wait(timeout=2.0)
        except BaseException as exc:
            server_error.append(exc)
            ready.set()

    thread = threading.Thread(target=serve_hung_socket, daemon=True)
    thread.start()
    assert ready.wait(timeout=2.0)
    assert not server_error

    _write_registry_session(
        isolated_home,
        {
            "session_id": "hung_uds",
            "transport": "uds",
            "fsdb_file": resource_targets["waveform"]["fsdb"],
            "socket_path": str(socket_path),
            "server_pid": os.getpid(),
        },
    )

    try:
        started_at = time.monotonic()
        result = cli_runner.run(
            {
                **_request(
                    "value.at",
                    target={"session_id": "hung_uds"},
                    args={
                        "signal": "ai_complex_top.sig_a",
                        "time": "75ns",
                        "format": "hex",
                    },
                ),
                "limits": {"timeout_ms": 100},
            },
            timeout_sec=5.0,
        )
        elapsed = time.monotonic() - started_at

        assert accepted.wait(timeout=1.0)
        assert not result.timed_out
        assert result.returncode != 0
        assert isinstance(result.response, dict)
        assert result.response["ok"] is False
        assert result.response["error"]["code"] == "SESSION_TRANSPORT_FAILED"
        assert "direct session socket timed out" in result.response["error"]["message"]
        assert result.response["summary"]["transport"] == "uds"
        assert result.response["summary"]["timeout_ms"] == 100
        assert elapsed < 2.0
    finally:
        stop.set()
        thread.join(timeout=2.0)
        _kill_all(cli_runner)
