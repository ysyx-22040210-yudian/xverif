from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from kcov.actions import Dispatcher
from kcov.backend import CoverageBackend, NpiCoverageBackend
from kcov.errors import KcovError
from kcov.logging import sanitize_for_log
from kcov.protocol import render_kout
from kcov.schemas import schema_actions
from kcov.session import KcovSession

ROOT = Path(__file__).resolve().parents[2]
KCOV = ROOT / "tools" / "kcov"


def _kcov_cmd() -> list[str]:
    if os.name == "nt":
        return [sys.executable, "-m", "kcov.cli"]
    return [str(KCOV)]


def _test_env(env: dict | None = None) -> dict:
    merged_env = os.environ.copy()
    pythonpath = str(ROOT / "kcov")
    if merged_env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + merged_env["PYTHONPATH"]
    merged_env["PYTHONPATH"] = pythonpath
    if env:
        merged_env.update(env)
    return merged_env


def _run(req: dict) -> dict:
    req.setdefault("output", {})["response_format"] = "json"
    proc = subprocess.run([*_kcov_cmd(), "--json", "-"], input=json.dumps(req),
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT), env=_test_env())
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return json.loads(proc.stdout)


def _run_proc(req: dict, args: list[str] | None = None, env: dict | None = None):
    return subprocess.run([*_kcov_cmd(), *(args or ["-"])], input=json.dumps(req),
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT), env=_test_env(env))


def _read_last_json_line(path: Path) -> dict:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    return json.loads(lines[-1])


def test_cli_json_flag_outputs_json_not_kout(tmp_path):
    proc = _run_proc({
        "api_version": "kcov.v1",
        "request_id": "actions",
        "action": "actions",
    }, ["--json", "-"], {"KVERIF_KCOV_LOG_DIR": str(tmp_path / "logs")})
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.lstrip().startswith("{")
    assert "KOUT_BEGIN" not in proc.stdout
    assert json.loads(proc.stdout)["ok"] is True


def test_output_response_format_json_outputs_json(tmp_path):
    proc = _run_proc({
        "api_version": "kcov.v1",
        "request_id": "actions",
        "action": "actions",
        "output": {"response_format": "json"},
    }, ["-"], {"KVERIF_KCOV_LOG_DIR": str(tmp_path / "logs")})
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.lstrip().startswith("{")
    assert "KOUT_BEGIN" not in proc.stdout


def test_session_open_fake_json():
    rsp = _run({
        "api_version": "kcov.v1",
        "request_id": "open",
        "action": "session.open",
        "target": {"vdb": "fake"},
        "args": {"name": "cov0", "fake": True},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["session_id"] == "cov0"
    assert rsp["summary"]["worker"] == "fake"


def test_real_backend_does_not_use_python_npi_bindings():
    backend_py = (ROOT / "kcov" / "kcov" / "backend.py").read_text(encoding="utf-8")
    forbidden_terms = [
        "py" + "npi",
        "npi" + "sys",
        "share/NPI/" + "python",
        "NPI/" + "python",
    ]
    for forbidden in forbidden_terms:
        assert forbidden not in backend_py


def test_tcl_status_iteration_and_raw_nulls_are_json_safe():
    tcl = (ROOT / "kcov" / "tcl_engine" / "kcov_npi.tcl").read_text(
        encoding="utf-8")
    assert "foreach {status label} {" in tcl
    assert "lassign $pair status label" not in tcl
    assert 'if {$value eq ""} {return "null"}' in tcl
    assert 'set pct "null"' in tcl


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(None, None), ("0", None), ("-1", None), ("2.5", 2.5)],
)
def test_tcl_backend_timeout_configuration(monkeypatch, configured, expected):
    monkeypatch.setattr("kcov.backend._find_verdi", lambda: "verdi")
    if configured is None:
        monkeypatch.delenv("KVERIF_KCOV_TCL_TIMEOUT_SEC", raising=False)
    else:
        monkeypatch.setenv("KVERIF_KCOV_TCL_TIMEOUT_SEC", configured)
    observed = []

    def fake_run(cmd, text, capture_output, cwd, env, timeout, check):
        observed.append(timeout)
        Path(env["KCOV_TCL_RESPONSE_JSON"]).write_text(
            json.dumps({"ok": True, "data": {"items": []}}),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("kcov.backend.subprocess.run", fake_run)
    backend = NpiCoverageBackend("fake.vdb")
    assert backend.timeout_sec == expected
    assert observed == [expected]


@pytest.mark.parametrize("configured", [0, -1])
def test_tcl_backend_nonpositive_constructor_timeout_is_unlimited(monkeypatch, configured):
    monkeypatch.delenv("KVERIF_KCOV_TCL_TIMEOUT_SEC", raising=False)
    monkeypatch.setattr(NpiCoverageBackend, "_run_tcl", lambda self, action: {"items": []})
    backend = NpiCoverageBackend("fake.vdb", timeout_sec=configured)
    assert backend.timeout_sec is None


def test_tcl_backend_success_response_returns_data(monkeypatch):
    monkeypatch.setattr("kcov.backend._find_verdi", lambda: "verdi")

    def fake_run(cmd, text, capture_output, cwd, env, timeout, check):
        Path(env["KCOV_TCL_RESPONSE_JSON"]).write_text(
            json.dumps({"ok": True, "data": {"items": [{"name": "t0"}]}}),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("kcov.backend.subprocess.run", fake_run)
    backend = object.__new__(NpiCoverageBackend)
    backend.vdb = "fake.vdb"
    backend.timeout_sec = 1.0
    assert backend._run_tcl("tests.list") == {"items": [{"name": "t0"}]}


def test_tcl_backend_error_response_keeps_structured_error(monkeypatch):
    monkeypatch.setattr("kcov.backend._find_verdi", lambda: "verdi")

    def fake_run(cmd, text, capture_output, cwd, env, timeout, check):
        Path(env["KCOV_TCL_RESPONSE_JSON"]).write_text(
            json.dumps({"ok": False, "error": {"code": "VDB_OPEN_FAILED", "message": "missing"}}),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="out", stderr="err")

    monkeypatch.setattr("kcov.backend.subprocess.run", fake_run)
    backend = object.__new__(NpiCoverageBackend)
    backend.vdb = "missing.vdb"
    backend.timeout_sec = 1.0
    try:
        backend._run_tcl("tests.list")
    except KcovError as exc:
        assert exc.code == "VDB_OPEN_FAILED"
        assert exc.detail["tcl_action"] == "tests.list"
    else:
        raise AssertionError("expected KcovError")


def test_schema_registry_covers_all_p0_actions():
    dispatcher = Dispatcher()
    for action in schema_actions():
        rsp = dispatcher.dispatch({
            "api_version": "kcov.v1",
            "request_id": f"schema-{action}",
            "action": "schema",
            "args": {"action": action},
            "output": {"response_format": "json"},
        })
        assert rsp["ok"] is True, action
        schema = rsp["data"]["schema"]
        assert schema["properties"]["action"]["const"] == action


def test_schema_required_fields_are_action_specific():
    dispatcher = Dispatcher()
    source = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "schema-source",
        "action": "schema", "args": {"action": "source.map"},
        "output": {"response_format": "json"},
    })["data"]["schema"]
    session_open = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "schema-open",
        "action": "schema", "args": {"action": "session.open"},
        "output": {"response_format": "json"},
    })["data"]["schema"]
    object_get = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "schema-object",
        "action": "schema", "args": {"action": "cov.object.get"},
        "output": {"response_format": "json"},
    })["data"]["schema"]
    assert set(source["properties"]["args"]["required"]) == {"file", "line"}
    assert session_open["properties"]["target"]["required"] == ["vdb"]
    assert object_get["properties"]["args"]["required"] == ["name"]


def test_logging_sanitize_omits_heavy_fields():
    sanitized = sanitize_for_log({"data": {"items": [{"x": i} for i in range(100)]},
                                  "small": True})
    assert sanitized["data"] == "<omitted:large-field>"
    assert sanitized["small"] is True
    assert sanitized["log_truncated"] is True


def test_stdio_loop_fake_holes():
    lines = [
        {"api_version": "kcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "kcov.v1", "request_id": "holes",
         "action": "cov.holes", "target": {"session_id": "cov0"},
         "args": {"metrics": ["toggle", "branch"]}},
    ]
    proc = subprocess.run([*_kcov_cmd(), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in lines) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT), env=_test_env())
    assert proc.returncode == 0, proc.stderr
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    assert out[0]["protocol"] == "kcov-stdio-loop"
    assert out[2]["id"] == "holes"
    assert out[2]["ok"] is True
    assert "@kcov.v1 ok action=cov.holes" in out[2]["kout"]
    assert out[2]["json"]["summary"]["matched_count"] == 3


def test_logging_writes_action_manifest_lifecycle_and_transport(tmp_path):
    log_dir = tmp_path / "kcov_logs"
    reqs = [
        {"api_version": "kcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "kcov.v1", "request_id": "holes",
         "action": "cov.holes", "target": {"session_id": "cov0"},
         "args": {"metrics": ["toggle"]}},
        {"api_version": "kcov.v1", "request_id": "close",
         "action": "session.close", "target": {"session_id": "cov0"}},
    ]
    proc = subprocess.run([*_kcov_cmd(), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT),
                          env=_test_env({"KVERIF_KCOV_LOG_DIR": str(log_dir)}))
    assert proc.returncode == 0
    action_log = log_dir / "sessions" / "cov0" / "logs" / "actions.ndjson"
    manifest = log_dir / "sessions" / "cov0" / "session.json"
    lifecycle = log_dir / "backend" / "sessions" / "cov0" / "logs" / "lifecycle.ndjson"
    transport = log_dir / "backend" / "sessions" / "cov0" / "logs" / "transport.ndjson"
    assert action_log.exists()
    assert manifest.exists()
    assert lifecycle.exists()
    assert transport.exists()
    assert _read_last_json_line(action_log)["component"] == "kcov"
    assert json.loads(manifest.read_text(encoding="utf-8"))["session_id"] == "cov0"


def test_logging_can_be_disabled(tmp_path):
    log_dir = tmp_path / "disabled_logs"
    proc = _run_proc({
        "api_version": "kcov.v1",
        "request_id": "open",
        "action": "session.open",
        "target": {"vdb": "fake"},
        "args": {"name": "cov0", "fake": True},
    }, ["--json", "-"], {"KVERIF_KCOV_LOG_DIR": str(log_dir), "KVERIF_KCOV_LOG": "0"})
    assert proc.returncode == 0
    assert not log_dir.exists()


def test_regex_rejected():
    reqs = [
        {"api_version": "kcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "kcov.v1", "request_id": "bad",
         "action": "cov.holes", "target": {"session_id": "cov0"},
         "args": {"query": {"include_patterns": ["^top.*"]}}},
    ]
    proc = subprocess.run([*_kcov_cmd(), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT), env=_test_env())
    out = [json.loads(line) for line in proc.stdout.splitlines()]
    assert out[2]["ok"] is False
    assert out[2]["json"]["error"]["code"] == "REGEX_NOT_SUPPORTED"


def test_export_writes_file(tmp_path):
    path = tmp_path / "holes.ndjson"
    reqs = [
        {"api_version": "kcov.v1", "request_id": "open",
         "action": "session.open", "target": {"vdb": "fake"},
         "args": {"name": "cov0", "fake": True}},
        {"api_version": "kcov.v1", "request_id": "export",
         "action": "export.holes", "target": {"session_id": "cov0"},
         "args": {"output": {"mode": "file", "artifact_format": "ndjson",
                              "path": str(path), "allow_absolute_path": True}}},
    ]
    proc = subprocess.run([*_kcov_cmd(), "--stdio-loop"],
                          input="\n".join(json.dumps(x) for x in reqs) + "\n",
                          text=True, capture_output=True, check=False,
                          cwd=str(ROOT), env=_test_env())
    assert proc.returncode == 0
    assert path.exists()
    assert "npiCovToggleBin" in path.read_text()


def _dispatch_opened() -> Dispatcher:
    dispatcher = Dispatcher()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "open",
        "action": "session.open", "target": {"vdb": "fake"},
        "args": {"name": "cov0", "fake": True},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    return dispatcher


def test_top_level_limits_output_are_merged_for_mcp_queries():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "holes",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["toggle", "branch"]},
        "limits": {"max_items": 1},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 3
    assert rsp["summary"]["returned"] == 1


def test_args_limits_take_precedence_over_top_level_limits():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "holes",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["toggle", "branch"], "limits": {"max_items": 2}},
        "limits": {"max_items": 1},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["returned"] == 2


def test_scope_summary_returns_one_requested_scope():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "scope",
        "action": "scope.summary", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 1
    item = rsp["data"]["items"][0]
    assert item["full_name"] == "top.u_dut"
    assert item["coverable"] == 6


def test_scope_children_direct_vs_recursive():
    dispatcher = _dispatch_opened()
    direct = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "children",
        "action": "scope.children", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut"},
        "output": {"format": "json"},
    })
    recursive = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "children-rec",
        "action": "scope.children", "target": {"session_id": "cov0"},
        "args": {"scope": "top", "recursive": True},
        "output": {"format": "json"},
    })
    assert {i["full_name"] for i in direct["data"]["items"]} == {
        "top.u_dut.u_ctrl", "top.u_dut.u_fifo"
    }
    assert "top.u_dut.u_fifo" in {i["full_name"] for i in recursive["data"]["items"]}


def test_scope_search_does_not_enrich_coverage():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "search",
        "action": "scope.search", "target": {"session_id": "cov0"},
        "args": {"query": {"include_patterns": ["*u_fifo"], "match_field": "full_name"}},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["data"]["items"][0]["full_name"] == "top.u_dut.u_fifo"
    assert "coverage_pct" not in rsp["data"]["items"][0]


def test_export_scope_tree_contains_coverage_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "tree",
        "action": "export.scope_tree", "target": {"session_id": "cov0"},
        "args": {"scope": "top.u_dut", "output": {"mode": "both", "path": "tree.json"}},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["output_path"].replace("\\", "/") == ".kverif/kcov_exports/tree.json"
    item = next(i for i in rsp["data"]["items"] if i["full_name"] == "top.u_dut")
    assert item["coverable"] == 6
    assert item["metrics"]
    assert (tmp_path / ".kverif/kcov_exports/tree.json").exists()


def test_functional_levels_filter():
    dispatcher = _dispatch_opened()
    bins = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "func-bin",
        "action": "functional.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["bin"]},
        "output": {"format": "json"},
    })
    cps = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "func-cp",
        "action": "functional.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["coverpoint"]},
        "output": {"format": "json"},
    })
    assert bins["summary"]["matched_count"] == 1
    assert cps["summary"]["matched_count"] == 1


def test_functional_summary_uses_requested_level_only():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "func-summary",
        "action": "functional.summary", "target": {"session_id": "cov0"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    assert rsp["summary"]["matched_count"] == 1
    assert rsp["data"]["items"][0]["coverable"] == 1


def test_functional_bin_evidence_is_inherited_from_parent():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "func-bin-evidence",
        "action": "functional.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["bin"]},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    item = rsp["data"]["items"][0]
    assert item["evidence"] == {"file": "verif/env/uart_coverage.sv", "line": 22}
    assert item["evidence_source"]["inherited"] is True
    assert item["evidence_source"]["type"] == "npiCovCoverpoint"


def test_code_coverage_holes_include_detail_fields():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "code-details",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["toggle", "branch", "condition"]},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    rows = rsp["data"]["items"]
    toggle = next(row for row in rows if row["metric"] == "toggle")
    branch = next(row for row in rows if row["metric"] == "branch")
    condition = next(row for row in rows if row["metric"] == "condition")
    assert toggle["toggle_signal"] == "top.u_dut.u_fifo.credit"
    assert toggle["toggle_bit"] == "top.u_dut.u_fifo.credit[0]"
    assert toggle["toggle_transition"] == "0 -> 1"
    assert branch["branch"] == "if (enable)"
    assert branch["branch_bin"] == "else"
    assert condition["condition"] == "(enable && ready)"
    assert condition["condition_bin"] == "10"
    assert condition["condition_terms"] == "enable;ready"
    assert condition["evidence_source"]["type"] == "npiCovCondition"


def test_kout_flattens_evidence_source():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "func-bin-kout",
        "action": "functional.holes", "target": {"session_id": "cov0"},
        "args": {"levels": ["bin"]},
    })
    kout = render_kout(rsp)
    assert "evidence_source={" not in kout
    assert "evidence_source.inherited=true" in kout
    assert "evidence_source.type=npiCovCoverpoint" in kout


def test_kout_contains_code_coverage_detail_fields():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "code-detail-kout",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["condition"], "limits": {"max_items": 1}},
    })
    kout = render_kout(rsp)
    assert "condition=(enable && ready)" in kout
    assert "condition_bin=10" in kout
    assert "condition_terms=enable;ready" in kout
    assert "evidence_source.type=npiCovCondition" in kout


def test_branch_mask_hint_decoding():
    from kcov.backend import _branch_mask_hint
    # one_hot: single '1' bit, no '-'
    assert _branch_mask_hint("000000100") == {"encoding": "one_hot",
                                               "branch_arm_index": 2}
    assert _branch_mask_hint("1") == {"encoding": "one_hot",
                                       "branch_arm_index": 0}
    assert _branch_mask_hint("1000000") == {"encoding": "one_hot",
                                             "branch_arm_index": 6}
    # multi_bit: multiple '1's or all zeros
    assert _branch_mask_hint("001001000") == {"encoding": "multi_bit",
                                               "one_positions": [3, 6]}
    assert _branch_mask_hint("000000000") == {"encoding": "multi_bit",
                                               "one_positions": []}
    # path: contains '-'
    result = _branch_mask_hint("---001-1--")
    assert result["encoding"] == "path"
    assert result["dontcare_bits"] > 0
    assert result["active_bits"] > 0
    # invalid
    assert _branch_mask_hint("") is None
    assert _branch_mask_hint("else") is None
    assert _branch_mask_hint("0b1010") is None


def test_branch_mask_hint_enabled(monkeypatch):
    from kcov.backend import _branch_mask_hint_enabled
    monkeypatch.delenv("KVERIF_KCOV_BRANCH_MASK_HINT", raising=False)
    assert _branch_mask_hint_enabled() is True
    for v in ("1", "true", "yes", "on"):
        monkeypatch.setenv("KVERIF_KCOV_BRANCH_MASK_HINT", v)
        assert _branch_mask_hint_enabled() is True
    for v in ("0", "false", "no", "off"):
        monkeypatch.setenv("KVERIF_KCOV_BRANCH_MASK_HINT", v)
        assert _branch_mask_hint_enabled() is False


def test_branch_mask_in_response():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "branch-mask",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["branch"]},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is True
    rows = rsp["data"]["items"]
    # one-hot item: "000000100" -> branch_mask
    bin_item = next(row for row in rows
                    if row.get("branch_bin") == "000000100")
    assert "branch_mask" in bin_item
    assert bin_item["branch_mask"]["encoding"] == "one_hot"
    assert bin_item["branch_mask"]["branch_arm_index"] == 2
    # non-bitmask item: "else" -> no branch_mask
    else_item = next(row for row in rows
                     if row.get("branch_bin") == "else")
    assert "branch_mask" not in else_item


def test_branch_mask_in_kout():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "branch-mask-kout",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"metrics": ["branch"]},
    })
    kout = render_kout(rsp)
    assert "branch_mask={" not in kout
    assert "branch_mask.encoding=one_hot" in kout
    assert "branch_mask.branch_arm_index=2" in kout


def test_test_each_is_explicitly_unsupported():
    dispatcher = _dispatch_opened()
    rsp = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "each",
        "action": "cov.holes", "target": {"session_id": "cov0"},
        "args": {"test": "each"},
        "output": {"format": "json"},
    })
    assert rsp["ok"] is False
    assert rsp["error"]["code"] == "TEST_MODE_NOT_SUPPORTED"


def test_export_path_safety(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatcher = _dispatch_opened()
    bad_parent = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "bad-parent",
        "action": "export.holes", "target": {"session_id": "cov0"},
        "args": {"output": {"mode": "file", "path": "../holes.json"}},
        "output": {"format": "json"},
    })
    bad_abs = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "bad-abs",
        "action": "export.holes", "target": {"session_id": "cov0"},
        "args": {"output": {"mode": "file", "path": str(tmp_path / "holes.json")}},
        "output": {"format": "json"},
    })
    ok = dispatcher.dispatch({
        "api_version": "kcov.v1", "request_id": "ok-rel",
        "action": "export.holes", "target": {"session_id": "cov0"},
        "args": {"output": {"mode": "file", "path": "holes.json"}},
        "output": {"format": "json"},
    })
    assert bad_parent["error"]["code"] == "OUTPUT_PATH_UNSAFE"
    assert bad_abs["error"]["code"] == "OUTPUT_PATH_UNSAFE"
    assert ok["ok"] is True
    assert (tmp_path / ".kverif/kcov_exports/holes.json").exists()


class CountingBackend(CoverageBackend):
    def __init__(self) -> None:
        self.scopes_called = 0

    def tests(self):
        return [{"name": "t0"}]

    def summary(self):
        return {"test_count": 1, "top_scope_count": 1}

    def scopes(self):
        self.scopes_called += 1
        raise AssertionError("session public_json must not scan scopes")

    def metrics_for_scope(self, scope, test):
        return []

    def items(self, metrics=None, scope=None, test="merged", functional_only=False):
        return []


def test_session_public_json_does_not_scan_scopes():
    backend = CountingBackend()
    session = KcovSession("cov0", "fake", backend, "fake")
    assert session.public_json()["top_scope_count"] == 1
    assert backend.scopes_called == 0
