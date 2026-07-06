from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .errors import XcovError
from .logging import log_lifecycle_event
from .query import coverage_pct

Json = Dict[str, Any]

METRICS = ["line", "toggle", "branch", "condition", "fsm", "assert", "functional"]


def _missing(covered: Any, coverable: Any) -> int | None:
    try:
        return int(coverable) - int(covered)
    except Exception:
        return None


class CoverageBackend:
    def close(self) -> None:
        pass

    def tests(self) -> List[Json]:
        raise NotImplementedError

    def summary(self) -> Json:
        tests = self.tests()
        top_scopes = self.top_scopes()
        return {"test_count": len(tests), "top_scope_count": len(top_scopes)}

    def top_scopes(self) -> List[Json]:
        scopes = self.scopes()
        return [s for s in scopes if "." not in str(s.get("full_name", ""))] or scopes

    def scopes(self) -> List[Json]:
        raise NotImplementedError

    def metrics_for_scope(self, scope: Optional[str], test: str) -> List[Json]:
        raise NotImplementedError

    def items(self, metrics: Optional[List[str]] = None,
              scope: Optional[str] = None, test: str = "merged",
              functional_only: bool = False) -> List[Json]:
        raise NotImplementedError


class FakeCoverageBackend(CoverageBackend):
    def __init__(self, vdb: str = "fake.vdb") -> None:
        self.vdb = vdb
        self._items = [
            {"metric": "line", "type": "npiCovStmtBin", "scope": "top.u_dut",
             "name": "stmt_12", "full_name": "top.u_dut.stmt_12",
             "covered": 1, "coverable": 1, "missing": 0, "count": 5,
             "coverage_pct": 100.0, "status": ["covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 12}},
            {"metric": "toggle", "type": "npiCovToggleBin", "scope": "top.u_dut.u_fifo",
             "name": "0 -> 1", "full_name": "top.u_dut.u_fifo.credit[0].0 -> 1",
             "toggle_signal": "top.u_dut.u_fifo.credit",
             "toggle_bit": "top.u_dut.u_fifo.credit[0]",
             "toggle_transition": "0 -> 1",
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/fifo.sv", "line": 44}},
            {"metric": "branch", "type": "npiCovBranchBin", "scope": "top.u_dut.u_ctrl",
             "name": "else", "full_name": "top.u_dut.u_ctrl.branch_8.else",
             "branch": "if (enable)",
             "branch_bin": "else",
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 88}},
            {"metric": "branch", "type": "npiCovBranchBin", "scope": "top.u_dut.u_ctrl",
             "name": "000000100", "full_name": "top.u_dut.u_ctrl.branch_9.000000100",
             "branch": "case (filter)",
             "branch_bin": "000000100",
             "branch_mask": {"encoding": "one_hot", "branch_arm_index": 2},
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 95}},
            {"metric": "condition", "type": "npiCovConditionBin", "scope": "top.u_dut.u_ctrl",
             "name": "10", "full_name": "top.u_dut.u_ctrl.cond_9.10",
             "condition": "(enable && ready)",
             "condition_bin": "10",
             "condition_terms": "enable;ready",
             "covered": 0, "coverable": 1, "missing": 1, "count": 0,
             "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "rtl/ctrl.sv", "line": 91},
             "evidence_source": {"inherited": True, "type": "npiCovCondition",
                                 "name": "(enable && ready)",
                                 "full_name": "top.u_dut.u_ctrl.cond_9"}},
            {"metric": "functional", "type": "npiCovCovergroup", "scope": "top.u_dut",
             "name": "cg_credit", "full_name": "top.u_dut.cg_credit",
             "covergroup": "cg_credit", "covered": 0, "coverable": 1, "missing": 1,
             "count": -1, "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "verif/env/uart_coverage.sv", "line": 21}},
            {"metric": "functional", "type": "npiCovCoverpoint", "scope": "top.u_dut",
             "name": "cp_level", "full_name": "top.u_dut.cg_credit.cp_level",
             "covergroup": "cg_credit", "coverpoint": "cp_level", "covered": 0,
             "coverable": 1, "missing": 1, "count": -1, "coverage_pct": 0.0,
             "status": ["not_covered"],
             "evidence": {"file": "verif/env/uart_coverage.sv", "line": 22}},
            {"metric": "functional", "type": "npiCovCoverBin", "scope": "top.u_dut",
             "name": "zero_credit", "full_name": "top.u_dut.cg_credit.cp_level.zero_credit",
             "covergroup": "cg_credit", "coverpoint": "cp_level", "cross": None,
             "bin": "zero_credit", "covered": 0, "coverable": 1, "missing": 1,
             "count": 0, "coverage_pct": 0.0, "status": ["not_covered"],
             "evidence": {"file": "verif/env/uart_coverage.sv", "line": 22},
             "evidence_source": {"inherited": True, "type": "npiCovCoverpoint",
                                 "name": "cp_level",
                                 "full_name": "top.u_dut.cg_credit.cp_level"}},
        ]

    def tests(self) -> List[Json]:
        return [{"name": f"{self.vdb}/test"}]

    def summary(self) -> Json:
        return {"test_count": 1, "top_scope_count": len(self.top_scopes())}

    def top_scopes(self) -> List[Json]:
        top_names = sorted({str(i["scope"]).split(".")[0] for i in self._items})
        return [_scope_row(n) for n in top_names]

    def scopes(self) -> List[Json]:
        names = sorted(_scope_closure(i["scope"] for i in self._items))
        return [_scope_row(n) for n in names]

    def metrics_for_scope(self, scope: Optional[str], test: str) -> List[Json]:
        self._check_test(test)
        rows = self.items(scope=scope, test=test)
        out = []
        for metric in sorted({r["metric"] for r in rows}):
            subset = [r for r in rows if r["metric"] == metric]
            coverable = sum(int(r.get("coverable") or 0) for r in subset)
            covered = sum(int(r.get("covered") or 0) for r in subset)
            out.append({"metric": metric, "coverable": coverable, "covered": covered,
                        "missing": coverable - covered,
                        "coverage_pct": coverage_pct(covered, coverable)})
        return out

    def items(self, metrics: Optional[List[str]] = None,
              scope: Optional[str] = None, test: str = "merged",
              functional_only: bool = False) -> List[Json]:
        self._check_test(test)
        rows = list(self._items)
        if metrics:
            rows = [r for r in rows if r.get("metric") in metrics]
        if scope:
            rows = [r for r in rows if str(r.get("scope", "")).startswith(scope)]
        if functional_only:
            rows = [r for r in rows if r.get("metric") == "functional"]
        return [dict(r) for r in rows]

    def _check_test(self, test: str) -> None:
        if test == "each":
            raise XcovError("TEST_MODE_NOT_SUPPORTED",
                            'test="each" is not implemented yet; use test="merged" or a concrete test name')


@dataclass
class NpiCoverageBackend(CoverageBackend):
    vdb: str
    timeout_sec: float = 180.0
    _tests: Optional[List[Json]] = None
    _scopes: Optional[List[Json]] = None

    def __post_init__(self) -> None:
        self.timeout_sec = float(os.environ.get("XVERIF_XCOV_TCL_TIMEOUT_SEC", self.timeout_sec))
        log_lifecycle_event("adhoc", "npi.tcl.backend.ready", True, {"vdb": self.vdb})
        self._tests = self._run_tcl("tests.list").get("items", [])

    def close(self) -> None:
        log_lifecycle_event("adhoc", "npi.tcl.backend.closed", True, {"vdb": self.vdb})

    def tests(self) -> List[Json]:
        if self._tests is None:
            self._tests = self._run_tcl("tests.list").get("items", [])
        return [dict(row) for row in self._tests]

    def _check_test(self, test: str) -> None:
        if test in ("merged", "", None):
            return
        if test == "each":
            raise XcovError("TEST_MODE_NOT_SUPPORTED",
                            'test="each" is not implemented yet; use test="merged" or a concrete test name')
        if any(row.get("name") == test for row in self.tests()):
            return
        raise XcovError("TEST_NOT_FOUND", "test not found", test=test)

    def summary(self) -> Json:
        return {"test_count": len(self.tests()), "top_scope_count": None}

    def top_scopes(self) -> List[Json]:
        rows = self.scopes()
        return [s for s in rows if "." not in str(s.get("full_name", ""))] or rows

    def scopes(self) -> List[Json]:
        if self._scopes is None:
            self._scopes = self._run_tcl("scope.list").get("items", [])
        return [dict(row) for row in self._scopes]

    def metrics_for_scope(self, scope: Optional[str], test: str) -> List[Json]:
        self._check_test(test)
        items = self.items(scope=scope, test=test)
        rows: List[Json] = []
        for metric in METRICS:
            subset = [r for r in items if r.get("metric") == metric]
            if not subset:
                continue
            coverable = sum(int(r.get("coverable") or 0) for r in subset)
            covered = sum(int(r.get("covered") or 0) for r in subset)
            rows.append({"metric": metric, "coverable": coverable, "covered": covered,
                         "missing": coverable - covered,
                         "coverage_pct": coverage_pct(covered, coverable)})
        return rows

    def items(self, metrics: Optional[List[str]] = None,
              scope: Optional[str] = None, test: str = "merged",
              functional_only: bool = False) -> List[Json]:
        self._check_test(test)
        wanted = list(metrics or METRICS)
        if functional_only and "functional" not in wanted:
            wanted = ["functional"]
        data = self._run_tcl("items", {
            "metrics": wanted,
            "scope": scope,
            "test": test,
            "functional_only": functional_only,
        })
        rows = [dict(row) for row in data.get("items", [])]
        for row in rows:
            row.setdefault("missing", _missing(row.get("covered"), row.get("coverable")))
            row.setdefault("coverage_pct", coverage_pct(row.get("covered"), row.get("coverable")))
            row.setdefault("status", _status_flags_from_values(row.get("covered"), row.get("coverable"),
                                                               row.get("status")))
            if (row.get("metric") == "branch" and row.get("type") == "npiCovBranchBin"
                    and _branch_mask_hint_enabled() and isinstance(row.get("branch_bin"), str)):
                hint = _branch_mask_hint(str(row.get("branch_bin")))
                if hint is not None:
                    row.setdefault("branch_mask", hint)
        return rows

    def _run_tcl(self, action: str, args: Optional[Json] = None) -> Json:
        verdi = _find_verdi()
        if not verdi:
            log_lifecycle_event("adhoc", "npi.tcl.verdi_not_found", False, {"vdb": self.vdb})
            raise XcovError("VERDI_NOT_FOUND", "verdi is not in PATH; set VERDI_HOME")
        script = _tcl_script_path()
        request = {"action": action, "vdb": self.vdb, "args": args or {}}
        tmpdir = tempfile.mkdtemp(prefix="xcov-tcl-npi-")
        try:
            req_path = os.path.join(tmpdir, "request.json")
            rsp_path = os.path.join(tmpdir, "response.json")
            with open(req_path, "w", encoding="utf-8") as fp:
                json.dump(request, fp, ensure_ascii=True)
            env = dict(os.environ)
            env["XCOV_TCL_REQUEST_JSON"] = req_path
            env["XCOV_TCL_RESPONSE_JSON"] = rsp_path
            env["XCOV_TCL_ACTION"] = action
            env["XCOV_TCL_VDB"] = self.vdb
            action_args = args or {}
            metrics = action_args.get("metrics") if isinstance(action_args.get("metrics"), list) else []
            env["XCOV_TCL_METRICS"] = "\n".join(str(metric) for metric in metrics)
            env["XCOV_TCL_SCOPE"] = "" if action_args.get("scope") is None else str(action_args.get("scope"))
            env["XCOV_TCL_TEST"] = str(action_args.get("test", "merged"))
            env["XCOV_TCL_FUNCTIONAL_ONLY"] = "1" if action_args.get("functional_only") else "0"
            if os.environ.get("XVERIF_XCOV_VERDI_HOME"):
                env["VERDI_HOME"] = os.environ["XVERIF_XCOV_VERDI_HOME"]
            if env.get("VERDI_HOME") and not env.get("NPIL1_PATH"):
                env["NPIL1_PATH"] = os.path.join(env["VERDI_HOME"], "share", "NPI", "L1", "TCL")
            cmd = [verdi, "-batch", "-nologo", "-play", str(script)]
            log_lifecycle_event("adhoc", "npi.tcl.invoke.begin", True,
                                {"vdb": self.vdb, "action": action})
            try:
                proc = subprocess.run(cmd, text=True, capture_output=True, cwd=tmpdir,
                                      env=env, timeout=self.timeout_sec, check=False)
            except subprocess.TimeoutExpired as exc:
                log_lifecycle_event("adhoc", "npi.tcl.invoke.timeout", False,
                                    {"vdb": self.vdb, "action": action})
                raise XcovError("TCL_NPI_TIMEOUT", "Verdi Tcl coverage action timed out",
                                action=action, timeout_sec=self.timeout_sec) from exc
            except OSError as exc:
                log_lifecycle_event("adhoc", "npi.tcl.invoke.failed", False,
                                    {"vdb": self.vdb, "action": action, "error": str(exc)})
                raise XcovError("VERDI_EXEC_FAILED", str(exc)) from exc
            try:
                with open(rsp_path, encoding="utf-8") as fp:
                    payload = json.load(fp)
            except Exception as exc:
                log_lifecycle_event("adhoc", "npi.tcl.no_response", False,
                                    {"vdb": self.vdb, "action": action, "exit_code": proc.returncode})
                raise XcovError("TCL_NPI_NO_RESPONSE",
                                "Verdi Tcl coverage action did not produce a valid JSON response",
                                action=action, exit_code=proc.returncode,
                                stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:]) from exc
            if not payload.get("ok"):
                err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                code = err.get("code", "TCL_NPI_ERROR")
                message = err.get("message", "Tcl coverage action failed")
                log_lifecycle_event("adhoc", "npi.tcl.invoke.error", False,
                                    {"vdb": self.vdb, "action": action, "code": code})
                raise XcovError(str(code), str(message), tcl_action=action,
                                stdout=proc.stdout[-2000:], stderr=proc.stderr[-2000:])
            log_lifecycle_event("adhoc", "npi.tcl.invoke.ok", True,
                                {"vdb": self.vdb, "action": action, "exit_code": proc.returncode})
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            return data
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _scope_parent(full_name: str) -> str | None:
    if "." not in full_name:
        return None
    return full_name.rsplit(".", 1)[0]


def _scope_depth(full_name: str) -> int:
    return full_name.count(".")


def _scope_row(full_name: str) -> Json:
    return {
        "name": full_name.rsplit(".", 1)[-1],
        "full_name": full_name,
        "parent": _scope_parent(full_name),
        "depth": _scope_depth(full_name),
        "type": "npiCovInstance",
    }


def _scope_closure(scopes: Iterable[str]) -> List[str]:
    names = set()
    for scope in scopes:
        parts = str(scope).split(".")
        for idx in range(1, len(parts) + 1):
            names.add(".".join(parts[:idx]))
    return sorted(names)


def _find_verdi() -> Optional[str]:
    verdi_home = os.environ.get("XVERIF_XCOV_VERDI_HOME") or os.environ.get("VERDI_HOME")
    if verdi_home:
        candidate = os.path.join(verdi_home, "bin", "verdi")
        if os.path.exists(candidate):
            return candidate
    return shutil.which("verdi")


def _tcl_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "tcl_engine" / "xcov_npi.tcl"


def _status_flags_from_values(covered: Any, coverable: Any,
                              raw: Any = None) -> List[str]:
    flags = list(raw or []) if isinstance(raw, list) else []
    flags = [str(flag) for flag in flags if flag not in (None, "")]
    try:
        if int(covered or 0) >= int(coverable or 0) and int(coverable or 0) > 0:
            base = "covered"
        else:
            base = "not_covered"
    except Exception:
        base = "not_covered"
    flags = [flag for flag in flags if flag not in {"covered", "not_covered"}]
    flags.insert(0, base)
    return flags


def _branch_mask_hint_enabled() -> bool:
    return str(os.environ.get("XVERIF_XCOV_BRANCH_MASK_HINT", "1")).lower() not in {
        "0", "false", "no", "off",
    }


def _branch_mask_hint(mask: str) -> dict | None:
    """Decode branch bin bitmask into human-readable hints.

    Returns None when *mask* is empty or contains characters other than
    ``0``, ``1``, or ``-``.

    Encoding classifications:

    * ``path``      — mask contains ``-`` (don't-care) positions; used for
                      FSM always-block branches.
    * ``one_hot``   — exactly one ``1``, no ``-``; bit position (LSB=0)
                      indexes the case item or branch arm.
    * ``multi_bit`` — multiple ``1`` positions, no ``-``; encodes a path
                      through nested if-else chains.
    """
    if not mask or not all(c in "01-" for c in mask):
        return None
    ones = [i for i, ch in enumerate(reversed(mask)) if ch == "1"]
    zeros = [i for i, ch in enumerate(reversed(mask)) if ch == "0"]
    dontcares = sum(1 for ch in mask if ch == "-")
    hint: dict = {}
    if dontcares > 0:
        hint["encoding"] = "path"
        hint["active_bits"] = len(ones) + len(zeros)
        hint["dontcare_bits"] = dontcares
    elif len(ones) == 1:
        hint["encoding"] = "one_hot"
        hint["branch_arm_index"] = ones[0]
    else:
        hint["encoding"] = "multi_bit"
        hint["one_positions"] = ones
    return hint
