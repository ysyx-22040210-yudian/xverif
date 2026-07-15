from __future__ import annotations

import pytest

from runner import CliRunner, StdioLoopRunner


@pytest.mark.contract
@pytest.mark.stdio_loop
def test_cli_and_stdio_loop_json_are_equivalent(
    cli_runner: CliRunner, kdebug_bin, repo_root, isolated_home
) -> None:
    request = {
        "request_id": "equivalence-actions",
        "api_version": "kdebug.v1",
        "action": "actions",
        "output": {"format": "json"},
    }
    cli_result = cli_runner.run(request, output_format="json")
    loop = StdioLoopRunner(
        kdebug_bin,
        cwd=repo_root,
        env={"HOME": str(isolated_home), "KVERIF_HOME": str(repo_root)},
    )
    try:
        loop.start()
        loop_result = loop.request(request)
        assert loop_result.ok
        assert loop_result.normalized_response == cli_result.normalized_response
    finally:
        loop.terminate()


@pytest.mark.contract
@pytest.mark.stdio_loop
def test_cli_and_stdio_loop_kout_are_equivalent(
    cli_runner: CliRunner, kdebug_bin, repo_root, isolated_home
) -> None:
    request = {
        "request_id": "equivalence-kout",
        "api_version": "kdebug.v1",
        "action": "schema",
        "args": {"action": "actions", "kind": "request"},
    }
    cli_result = cli_runner.run(request, output_format="kout")
    loop = StdioLoopRunner(
        kdebug_bin,
        cwd=repo_root,
        env={"HOME": str(isolated_home), "KVERIF_HOME": str(repo_root)},
    )
    try:
        loop.start()
        loop_result = loop.request(request)
        assert loop_result.ok
        assert loop_result.response == cli_result.response
        assert loop_result.response.startswith("@kdebug.schema.v1")
    finally:
        loop.terminate()
