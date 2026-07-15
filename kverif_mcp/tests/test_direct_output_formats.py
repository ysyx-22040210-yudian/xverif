"""Output format tests for kverif-mcp one-shot requests (kout / json / envelope)."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from kverif_mcp.runner import StatelessCliRunner


def _make_fake_kdebug(dirpath: Path,
                      kout_response: str = "@kdebug.fake.v1\n\nsummary:\n  format: kout\n"):
    """Create a fake kdebug executable that returns controlled output."""
    script = dirpath / "kdebug"
    json_response = json.dumps({"ok": True, "action": "fake",
                                "summary": {"format": "json"}})
    script.write_text(
        '#!/usr/bin/env python3\n'
        'import json, sys\n'
        f'KOUT_RESPONSE = {json.dumps(kout_response)}\n'
        f'JSON_RESPONSE = {json.dumps(json_response)}\n'
        'args = sys.argv[1:]\n'
        'if "--json" in args:\n'
        '    print(JSON_RESPONSE)\n'
        'else:\n'
        '    print(KOUT_RESPONSE, end="")\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.fixture
def runner():
    """Return a StatelessCliRunner pointed at a fake kdebug."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        script = _make_fake_kdebug(tmp)
        r = StatelessCliRunner()
        # Override tool_path to use our fake script
        orig_tool_path = r.tool_path
        r.tool_path = lambda tool: str(script)
        yield r
        r.tool_path = orig_tool_path


class TestKverifOutputFormats:
    def test_kout_returns_string(self, runner):
        result = runner.run_text("kdebug", ["-"],
                                  input_text=json.dumps(
                                      {"api_version": "kdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, str)
        assert result.startswith("@kdebug.")

    def test_json_returns_dict(self, runner):
        result = runner.run_json("kdebug", ["--json", "-"],
                                  input_text=json.dumps(
                                      {"api_version": "kdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert result["summary"]["format"] == "json"

    def test_default_output_is_kout(self, runner):
        result = runner.run_text("kdebug", ["-"],
                                  input_text=json.dumps(
                                      {"api_version": "kdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, str)
        assert result.startswith("@kdebug.")

    def test_invalid_output_returns_error(self):
        """Non-existent binary gives CLI_FAILED error."""
        r = StatelessCliRunner()
        result = r.run_json("nonexistent_tool", ["--help"])
        assert not result.get("ok")
        assert result["error"]["code"] == "KVERIF_CLI_FAILED"

    def test_json_keeps_json_default(self, runner):
        """run_json always returns a dict."""
        result = runner.run_json("kdebug", ["--json", "-"],
                                  input_text=json.dumps(
                                      {"api_version": "kdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, dict)
        assert result.get("ok") is True

    def test_runner_kout_text(self, runner):
        """run_text produces raw text string on success."""
        result = runner.run_text("kdebug", ["-"],
                                  input_text=json.dumps(
                                      {"api_version": "kdebug.v1",
                                       "action": "fake"}))
        assert isinstance(result, str)
        assert result.startswith("@kdebug.")

    def test_runner_error_returns_dict(self):
        """run_text returns error dict on failure."""
        r = StatelessCliRunner()
        result = r.run_text("nonexistent_binary", ["--help"])
        assert isinstance(result, dict)
        assert not result.get("ok")
        assert result["error"]["code"] == "KVERIF_CLI_FAILED"


@pytest.mark.parametrize(
    ("runner_timeout", "call_timeout", "expected"),
    [(0, None, None), (-1, None, None), (2.5, None, 2.5), (30, 0, None)],
)
def test_runner_nonpositive_timeout_is_unlimited(
        monkeypatch, runner_timeout, call_timeout, expected):
    observed = []

    def fake_run(cmd, **kwargs):
        observed.append(kwargs["timeout"])
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("kverif_mcp.runner.subprocess.run", fake_run)
    runner = StatelessCliRunner(timeout_sec=runner_timeout)
    runner.tool_path = lambda tool: "fake-tool"
    result = runner._run_raw("kcov", ["--json", "-"], "{}",
                             timeout_sec=call_timeout)
    assert result["exit_code"] == 0
    assert observed == [expected]
