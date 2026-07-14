from __future__ import annotations

import pytest

from xverif_sdk import (CallbackTransport, CoverageRun, XcovClient, XdebugClient,
                        analyze_coverage_convergence, analyze_wave_window,
                        trace_module_connections)


def test_wave_window_keeps_summaries_samples_and_raw_responses():
    def handler(request):
        if request["action"] == "signal.changes":
            signal = request["args"]["signal"]
            return {
                "ok": True, "action": "signal.changes",
                "summary": {"actual_transition_count": 2,
                            "first_change": {"time": "10ns", "value": "0"},
                            "last_change": {"time": "20ns", "value": "1"}},
                "data": {"signal": signal, "changes": []}, "warnings": [],
            }
        return {"ok": True, "action": "value.batch_at",
                "data": {"items": [{"signal": name, "value": "1"}
                                     for name in request["args"]["signals"]]}}

    transport = CallbackTransport(handler)
    report = analyze_wave_window(
        XdebugClient(transport), ["top.valid", "top.ready"],
        start="0ns", end="100ns", sample_times=["50ns"])
    assert report["schema"] == "xverif.sdk.wave-window.v1"
    assert report["summary"]["total_transition_count"] == 4
    assert len(report["signals"]) == 2
    assert report["samples"][0]["response"]["data"]["items"][0]["value"] == "1"
    assert [request["action"] for request in transport.requests] == [
        "signal.changes", "signal.changes", "value.batch_at"]


def test_wave_window_supports_verdi_2018_change_count_shape():
    response = {
        "ok": True, "action": "signal.changes",
        "summary": {"change_count": 3},
        "data": {"changes": [
            {"time": 0, "raw": "0"},
            {"time": 5, "raw": "1"},
            {"time": 10, "raw": "0"},
        ]},
    }
    report = analyze_wave_window(
        XdebugClient(CallbackTransport(lambda request: response)),
        ["tb.clk"], start="0ns", end="10ns")
    signal = report["signals"][0]
    assert signal["returned_change_rows"] == 3
    assert signal["transition_count"] == 2
    assert signal["first_change"]["time"] == 0
    assert signal["last_change"]["time"] == 10


def test_module_connectivity_normalizes_and_deduplicates_edges():
    def handler(request):
        if request["action"] == "trace.driver":
            signal = request["args"]["signal"]
            return {"ok": True, "action": "trace.driver", "data": {"drivers": [{
                "signal": signal,
                "rhs_signals": ["top.src.data", "top.src.data"],
                "condition_signals": ["top.ctrl.enable"],
                "file": "rtl/integration.sv", "line": 42, "confidence": "high",
            }]}}
        return {"ok": True, "action": "trace.graph", "data": {"edges": [
            {"source": "top.upstream.valid", "target": "top.dst.ready", "kind": "dependency"}
        ]}}

    report = trace_module_connections(
        XdebugClient(CallbackTransport(handler)), ["top.dst.data"], max_depth=5)
    assert report["schema"] == "xverif.sdk.module-connections.v1"
    assert report["summary"]["edge_count"] == 3
    assert {edge["kind"] for edge in report["edges"]} == {"data", "control", "dependency"}
    assert report["module_scopes"] == ["top.ctrl", "top.dst", "top.src", "top.upstream"]


def test_module_connectivity_supports_verdi_2018_dependency_graph_shape():
    edge = {
        "from": "tb_top.core_clock",
        "to": "tb_top.sim.clock",
        "relation": "driver",
        "object_type": "npiNet",
        "location": {"file": "top.v", "line": 152},
        "source": "core_clock",
    }

    def handler(request):
        if request["action"] == "trace.driver":
            return {"ok": True, "action": "trace.driver",
                    "data": {"dependency_edges": [edge]}}
        return {"ok": True, "action": "trace.graph",
                "data": {"graph": {"edges": [edge]},
                         "dependency_edges": [edge]}}

    report = trace_module_connections(
        XdebugClient(CallbackTransport(handler)), ["tb_top.sim.clock"])
    assert report["summary"]["edge_count"] == 1
    assert report["edges"] == [{
        "from": "tb_top.core_clock",
        "to": "tb_top.sim.clock",
        "kind": "driver",
        "evidence": {
            "file": "top.v",
            "line": 152,
            "object_type": "npiNet",
            "source_text": "core_clock",
        },
    }]
    assert report["module_scopes"] == ["tb_top", "tb_top.sim"]


def test_module_connectivity_excludes_constant_handles_from_module_scopes():
    edge = {"from": "819993224", "to": "tb_top.clock", "relation": "driver"}

    def handler(request):
        data = ({"dependency_edges": [edge]}
                if request["action"] == "trace.driver" else {})
        return {"ok": True, "action": request["action"], "data": data}

    report = trace_module_connections(
        XdebugClient(CallbackTransport(handler)), ["tb_top.clock"])
    assert report["summary"]["edge_count"] == 1
    assert report["module_scopes"] == ["tb_top"]


def test_coverage_convergence_uses_weighted_totals_and_deltas():
    sessions = {}

    def handler(request):
        action = request["action"]
        if action == "session.open":
            session_id = request["args"]["name"]
            sessions[session_id] = request["target"]["vdb"]
            return {"ok": True, "action": action, "summary": {"session_id": session_id}}
        if action == "session.close":
            return {"ok": True, "action": action}
        vdb = sessions[request["target"]["session_id"]]
        if action == "cov.summary":
            rows = ([{"metric": "line", "covered": 50, "coverable": 100,
                      "coverage_pct": 50.0},
                     {"metric": "toggle", "covered": 25, "coverable": 50,
                      "coverage_pct": 50.0}]
                    if vdb == "run1.vdb" else
                    [{"metric": "line", "covered": 90, "coverable": 100,
                      "coverage_pct": 90.0},
                     {"metric": "toggle", "covered": 40, "coverable": 50,
                      "coverage_pct": 80.0}])
            return {"ok": True, "action": action, "data": {"items": rows}}
        return {"ok": True, "action": action,
                "data": {"items": [{"metric": "toggle", "name": "missing"}]}}

    transport = CallbackTransport(handler)
    report = analyze_coverage_convergence(
        XcovClient(transport),
        [CoverageRun("base", "run1.vdb"), CoverageRun("fixed", "run2.vdb")],
        metrics=["line", "toggle"], target_pct=85.0)
    assert report["schema"] == "xverif.sdk.coverage-convergence.v1"
    assert report["runs"][0]["coverage_pct"] == 50.0
    assert report["runs"][1]["coverage_pct"] == pytest.approx(86.6666667)
    assert report["runs"][1]["delta_pct"] == pytest.approx(36.6666667)
    assert report["summary"]["target_met"] is True
    assert report["summary"]["best_run"] == "fixed"
    assert [request["action"] for request in transport.requests] == [
        "session.open", "cov.summary", "cov.holes", "session.close",
        "session.open", "cov.summary", "cov.holes", "session.close"]


def test_coverage_convergence_rejects_duplicate_labels():
    client = XcovClient(CallbackTransport(lambda request: {"ok": True}))
    with pytest.raises(ValueError, match="unique"):
        analyze_coverage_convergence(
            client, [CoverageRun("same", "a.vdb"), CoverageRun("same", "b.vdb")])
