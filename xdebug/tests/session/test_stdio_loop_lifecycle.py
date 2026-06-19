from __future__ import annotations

import json

import pytest

from runner import StdioLoopRunner


@pytest.fixture
def stdio_loop(xdebug_bin, repo_root, isolated_home):
    loop = StdioLoopRunner(
        xdebug_bin,
        cwd=repo_root,
        env={"HOME": str(isolated_home), "XVERIF_HOME": str(repo_root)},
    )
    loop.start()
    try:
        yield loop
    finally:
        loop.terminate()


@pytest.mark.session
@pytest.mark.stdio_loop
def test_stdio_loop_recovers_after_blank_malformed_and_invalid_request(
    stdio_loop: StdioLoopRunner,
) -> None:
    assert stdio_loop.proc is not None and stdio_loop.proc.stdin is not None
    stdio_loop.proc.stdin.write("\n")
    stdio_loop.proc.stdin.flush()

    malformed = stdio_loop.send_raw("{not-json")
    assert malformed["ok"] is False
    assert malformed["error"]["code"] == "INVALID_JSON"

    invalid_version = stdio_loop.request(
        {
            "request_id": "bad-version",
            "api_version": "xdebug.v0",
            "action": "actions",
        }
    )
    assert not invalid_version.ok
    assert invalid_version.envelope["id"] == "bad-version"
    assert invalid_version.envelope["error"]["code"] == "UNSUPPORTED_API_VERSION"

    recovered = stdio_loop.request(
        {
            "request_id": "after-errors",
            "api_version": "xdebug.v1",
            "action": "actions",
            "output": {"format": "json"},
        }
    )
    assert recovered.ok
    assert recovered.envelope["id"] == "after-errors"
    assert recovered.envelope["payload_format"] == "json"


@pytest.mark.session
@pytest.mark.stdio_loop
def test_stdio_loop_multiple_requests_keep_ids_and_output_modes(
    stdio_loop: StdioLoopRunner,
) -> None:
    first = stdio_loop.request(
        {
            "request_id": "json-1",
            "api_version": "xdebug.v1",
            "action": "actions",
            "output": {"format": "json"},
        }
    )
    second = stdio_loop.request(
        {
            "id": "xout-2",
            "api_version": "xdebug.v1",
            "action": "schema",
            "args": {"action": "actions", "kind": "request"},
        }
    )
    third = stdio_loop.request(
        {
            "request_id": "json-3",
            "api_version": "xdebug.v1",
            "action": "schema",
            "args": {"action": "actions", "kind": "response"},
            "output": {"format": "json"},
        }
    )

    assert first.envelope["id"] == "json-1"
    assert first.envelope["payload_format"] == "json"
    assert second.envelope["id"] == "xout-2"
    assert second.envelope["payload_format"] == "xout"
    assert second.response.startswith("@xdebug.schema.v1")
    assert third.envelope["id"] == "json-3"
    assert third.envelope["payload_format"] == "json"


@pytest.mark.session
@pytest.mark.stdio_loop
def test_stdio_loop_quit_closes_process_cleanly(
    stdio_loop: StdioLoopRunner,
) -> None:
    result = stdio_loop.quit()
    assert result is not None and result.ok
    assert result.envelope["json"]["action"] == "stdio.quit"
    assert stdio_loop.proc is not None
    assert stdio_loop.proc.poll() == 0


@pytest.mark.session
@pytest.mark.stdio_loop
def test_stdio_loop_stdout_is_jsonl_only(
    stdio_loop: StdioLoopRunner,
) -> None:
    result = stdio_loop.request(
        {
            "request_id": "clean-stdout",
            "api_version": "xdebug.v1",
            "action": "actions",
            "output": {"format": "json"},
        }
    )
    assert result.ok
    assert not [
        item
        for item in stdio_loop.transcript
        if item.get("direction") == "stdout-noise"
    ]
    json.loads(result.stdout_raw)
