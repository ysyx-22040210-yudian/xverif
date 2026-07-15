from __future__ import annotations

import pytest

from runner import CliRunner


def _batch(mode: str):
    return {
        "api_version": "kdebug.v1",
        "action": "batch",
        "args": {
            "mode": mode,
            "requests": [
                {"api_version": "kdebug.v1", "action": "actions"},
                {"api_version": "kdebug.v1", "action": "does.not.exist"},
                {
                    "api_version": "kdebug.v1",
                    "action": "schema",
                    "args": {"action": "actions", "kind": "request"},
                },
            ],
        },
    }


@pytest.mark.contract
def test_batch_continue_on_error_keeps_later_requests(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.run(_batch("continue_on_error"), output_format="json")
    assert result.returncode == 1
    response = result.response
    assert response["ok"] is False
    assert response["error"]["code"] == "BATCH_PARTIAL_FAILURE"
    assert response["summary"] == {"count": 3, "all_ok": False}
    child_results = response["data"]["results"]
    assert [child["ok"] for child in child_results] == [True, False, True]
    assert child_results[1]["error"]["code"] == "UNKNOWN_ACTION"
    assert child_results[2]["action"] == "schema"


@pytest.mark.contract
def test_batch_stop_on_error_stops_after_first_failure(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.run(_batch("stop_on_error"), output_format="json")
    assert result.returncode == 1
    response = result.response
    assert response["ok"] is False
    assert response["error"]["code"] == "BATCH_PARTIAL_FAILURE"
    assert response["summary"] == {"count": 2, "all_ok": False}
    child_results = response["data"]["results"]
    assert [child["ok"] for child in child_results] == [True, False]
    assert child_results[1]["error"]["code"] == "UNKNOWN_ACTION"


@pytest.mark.contract
def test_batch_requires_requests_array(cli_runner: CliRunner) -> None:
    result = cli_runner.run(
        {
            "api_version": "kdebug.v1",
            "action": "batch",
            "args": {},
        },
        output_format="json",
    )
    assert result.returncode == 1
    assert result.response["ok"] is False
    assert result.response["error"]["code"] == "MISSING_FIELD"
