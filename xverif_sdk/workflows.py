"""Reusable verification workflows built only on public client methods."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .clients import XcovClient, XdebugClient

Json = Dict[str, Any]


def _items(response: Json) -> List[Json]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    rows = data.get("items")
    return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _warnings(response: Json) -> List[Any]:
    warnings = response.get("warnings")
    return list(warnings) if isinstance(warnings, list) else []


def analyze_wave_window(client: XdebugClient, signals: Iterable[str], *,
                        start: str, end: str,
                        sample_times: Iterable[str] = (),
                        value_format: str = "hex",
                        max_changes: int = 100,
                        include_changes: bool = True) -> Json:
    """Collect transition summaries and optional multi-signal samples."""
    selected = [str(signal) for signal in signals if str(signal)]
    if not selected:
        raise ValueError("at least one signal is required")
    signal_reports = []
    total_transitions = 0
    for signal_name in selected:
        response = client.signal_changes(
            signal_name, start, end,
            include_rows=include_changes,
            aggregate_only=not include_changes,
            limit=max_changes,
        )
        summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        changes = data.get("changes") if isinstance(data.get("changes"), list) else []
        returned_rows = summary.get("returned_change_rows", summary.get("change_count", len(changes)))
        transitions = summary.get("actual_transition_count", summary.get("transition_count"))
        if transitions is None:
            try:
                transitions = max(int(returned_rows or 0) - 1, 0)
            except (TypeError, ValueError):
                transitions = 0
        try:
            total_transitions += int(transitions or 0)
        except (TypeError, ValueError):
            pass
        signal_reports.append({
            "signal": signal_name,
            "transition_count": transitions,
            "returned_change_rows": returned_rows,
            "first_change": summary.get("first_change") or (changes[0] if changes else None),
            "last_change": summary.get("last_change") or (changes[-1] if changes else None),
            "warnings": _warnings(response),
            "response": response,
        })

    samples = []
    for time_value in sample_times:
        response = client.value_batch_at(selected, str(time_value), value_format=value_format)
        samples.append({"time": str(time_value), "response": response})

    return {
        "schema": "xverif.sdk.wave-window.v1",
        "summary": {
            "signal_count": len(selected),
            "sample_count": len(samples),
            "total_transition_count": total_transitions,
            "start": start,
            "end": end,
        },
        "signals": signal_reports,
        "samples": samples,
    }


def _edge_value(edge: Json, names: Sequence[str]) -> Optional[str]:
    for name in names:
        value = edge.get(name)
        if value is not None and str(value):
            return str(value)
    return None


def _scope_name(signal_name: str) -> str:
    base = re.sub(r"\[[^]]+\]$", "", signal_name)
    return base.rsplit(".", 1)[0] if "." in base else base


def _edge_evidence(edge: Json) -> Optional[Json]:
    evidence = dict(edge.get("evidence")
                    if isinstance(edge.get("evidence"), dict) else {})
    location = edge.get("location") if isinstance(edge.get("location"), dict) else {}
    for key in ("file", "line"):
        value = edge.get(key, location.get(key))
        if value is not None and str(value):
            evidence[key] = value
    for key in ("confidence", "object_type"):
        if edge.get(key) is not None:
            evidence[key] = edge[key]
    if edge.get("from") is not None and edge.get("source") is not None:
        evidence["source_text"] = edge["source"]
    return evidence or None


def _dependency_edges(data: Json) -> List[Json]:
    """Return edges from both current and Verdi 2018 response layouts."""
    rows = []  # type: List[Json]
    for key in ("edges", "dependency_edges"):
        value = data.get(key)
        if isinstance(value, list):
            rows.extend(dict(row) for row in value if isinstance(row, dict))
    graph = data.get("graph") if isinstance(data.get("graph"), dict) else {}
    value = graph.get("edges")
    if isinstance(value, list):
        rows.extend(dict(row) for row in value if isinstance(row, dict))
    return rows


def trace_module_connections(client: XdebugClient, signals: Iterable[str], *,
                             max_depth: int = 4,
                             include_source: bool = True) -> Json:
    """Trace integration wiring and normalize data/control edges."""
    selected = [str(signal) for signal in signals if str(signal)]
    if not selected:
        raise ValueError("at least one signal is required")
    traces = []
    edges = []
    seen = set()

    def append_edge(source: Optional[str], target: Optional[str], kind: str,
                    evidence: Optional[Json] = None) -> None:
        if not source or not target:
            return
        key = (source, target, kind)
        if key in seen:
            return
        seen.add(key)
        row = {"from": source, "to": target, "kind": kind}
        if evidence:
            row["evidence"] = evidence
        edges.append(row)

    for signal_name in selected:
        driver_response = client.trace_driver(
            signal_name, include_source=include_source,
            limits={"max_depth": max_depth},
        )
        graph_response = client.trace_graph(
            signal_name, max_depth=max_depth, include_source=include_source)
        driver_data = (driver_response.get("data")
                       if isinstance(driver_response.get("data"), dict) else {})
        drivers = driver_data.get("drivers") if isinstance(driver_data.get("drivers"), list) else []
        for driver in drivers:
            if not isinstance(driver, dict):
                continue
            target = str(driver.get("signal") or signal_name)
            evidence = {}
            for key in ("file", "line", "confidence"):
                if driver.get(key) is not None:
                    evidence[key] = driver[key]
            for source in driver.get("rhs_signals", []) or []:
                append_edge(str(source), target, "data", evidence)
            for source in driver.get("condition_signals", []) or []:
                append_edge(str(source), target, "control", evidence)

        for dependency_edge in _dependency_edges(driver_data):
            source = _edge_value(
                dependency_edge, ("from", "source", "src", "from_signal"))
            target = _edge_value(
                dependency_edge, ("to", "target", "dst", "to_signal"))
            kind = _edge_value(
                dependency_edge, ("kind", "type", "relation")) or "driver"
            append_edge(source, target, kind, _edge_evidence(dependency_edge))

        graph_data = (graph_response.get("data")
                      if isinstance(graph_response.get("data"), dict) else {})
        for graph_edge in _dependency_edges(graph_data):
            source = _edge_value(graph_edge, ("from", "source", "src", "from_signal"))
            target = _edge_value(graph_edge, ("to", "target", "dst", "to_signal"))
            kind = _edge_value(graph_edge, ("kind", "type", "relation")) or "graph"
            append_edge(source, target, kind, _edge_evidence(graph_edge))
        traces.append({
            "signal": signal_name,
            "driver_response": driver_response,
            "graph_response": graph_response,
        })

    scopes = sorted({
        _scope_name(edge[side])
        for edge in edges
        for side in ("from", "to")
        if "." in edge[side]
    })
    return {
        "schema": "xverif.sdk.module-connections.v1",
        "summary": {
            "root_signal_count": len(selected),
            "edge_count": len(edges),
            "scope_count": len(scopes),
            "max_depth": max_depth,
        },
        "root_signals": selected,
        "module_scopes": scopes,
        "edges": edges,
        "traces": traces,
    }


@dataclass(frozen=True)
class CoverageRun:
    """One ordered coverage result used by the convergence workflow."""

    label: str
    vdb: str
    scope: Optional[str] = None
    test: str = "merged"
    fake: bool = False


def _coverage_totals(rows: Iterable[Json]) -> Tuple[Optional[float], float, float]:
    covered = 0.0
    coverable = 0.0
    for row in rows:
        try:
            row_coverable = float(row.get("coverable") or 0)
            row_covered = float(row.get("covered") or 0)
        except (TypeError, ValueError):
            continue
        if row_coverable > 0:
            covered += row_covered
            coverable += row_coverable
    percentage = None if coverable <= 0 else 100.0 * covered / coverable
    return percentage, covered, coverable


def _session_alias(index: int, label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    if not safe or not safe[0].isalpha():
        safe = "run_" + safe
    return ("sdk_cov_%d_%s" % (index, safe))[:64]


def analyze_coverage_convergence(client: XcovClient, runs: Sequence[CoverageRun], *,
                                 metrics: Iterable[str] = ("line", "toggle", "branch", "condition"),
                                 hole_limit: int = 20,
                                 target_pct: float = 100.0,
                                 plateau_epsilon: float = 0.01) -> Json:
    """Compare ordered regression VDBs and detect progress or a plateau."""
    if not runs:
        raise ValueError("at least one coverage run is required")
    labels = [run.label for run in runs]
    if len(set(labels)) != len(labels):
        raise ValueError("coverage run labels must be unique")
    selected_metrics = [str(metric) for metric in metrics]
    results = []
    previous_pct = None  # type: Optional[float]
    consecutive_plateau = 0

    for index, run in enumerate(runs, 1):
        with client.session(_session_alias(index, run.label), run.vdb, fake=run.fake):
            summary_response = client.coverage_summary(
                metrics=selected_metrics, scope=run.scope, test=run.test)
            holes_response = client.coverage_holes(
                metrics=selected_metrics, scope=run.scope, test=run.test,
                max_items=hole_limit)
        summary_rows = _items(summary_response)
        percentage, covered, coverable = _coverage_totals(summary_rows)
        delta = None if percentage is None or previous_pct is None else percentage - previous_pct
        plateau = delta is not None and abs(delta) <= plateau_epsilon
        consecutive_plateau = consecutive_plateau + 1 if plateau else 0
        metric_pct = {
            str(row.get("metric") or row.get("name")): row.get("coverage_pct")
            for row in summary_rows
            if row.get("metric") is not None or row.get("name") is not None
        }
        results.append({
            "label": run.label,
            "vdb": run.vdb,
            "scope": run.scope,
            "test": run.test,
            "coverage_pct": percentage,
            "covered": covered,
            "coverable": coverable,
            "delta_pct": delta,
            "plateau": plateau,
            "target_met": percentage is not None and percentage >= target_pct,
            "metric_pct": metric_pct,
            "holes": _items(holes_response),
            "responses": {"summary": summary_response, "holes": holes_response},
        })
        if percentage is not None:
            previous_pct = percentage

    valid_results = [row for row in results if row["coverage_pct"] is not None]
    best = max(valid_results, key=lambda row: row["coverage_pct"]) if valid_results else None
    first_pct = valid_results[0]["coverage_pct"] if valid_results else None
    latest_pct = valid_results[-1]["coverage_pct"] if valid_results else None
    improvement = None if first_pct is None or latest_pct is None else latest_pct - first_pct
    return {
        "schema": "xverif.sdk.coverage-convergence.v1",
        "summary": {
            "run_count": len(results),
            "metrics": selected_metrics,
            "first_coverage_pct": first_pct,
            "latest_coverage_pct": latest_pct,
            "improvement_pct": improvement,
            "best_run": best["label"] if best else None,
            "best_coverage_pct": best["coverage_pct"] if best else None,
            "target_pct": target_pct,
            "target_met": latest_pct is not None and latest_pct >= target_pct,
            "plateau": consecutive_plateau > 0,
            "consecutive_plateau_runs": consecutive_plateau,
        },
        "runs": results,
    }
