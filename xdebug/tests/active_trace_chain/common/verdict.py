#!/usr/bin/env python3
"""Compare expected trace chain against actual, produce verdict.json.

Usage:
  python3 verdict.py <expected.json> <actual_chain.json> <verdict.json>
"""

import json
import sys
from pathlib import Path


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def compare(expected: dict, actual: dict) -> dict:
    """Compare expected chain structure against actual."""
    checks = []
    all_pass = True

    expected_chain = expected.get("expected_chain", [])
    actual_chain = actual.get("chain", [])

    # 1. chain length
    exp_len = len(expected_chain)
    act_len = len(actual_chain)
    min_len = min(exp_len, act_len)
    checks.append({
        "check": "chain_length",
        "expected": exp_len,
        "actual": act_len,
        "pass": act_len >= exp_len,
    })
    if act_len < exp_len:
        all_pass = False

    # 2. termination
    exp_term = expected.get("expected_termination", "")
    act_term = actual.get("termination", "")
    checks.append({
        "check": "termination",
        "expected": exp_term,
        "actual": act_term,
        "pass": act_term == exp_term,
    })
    if act_term != exp_term:
        all_pass = False

    # 3. temporal boundaries
    exp_tb = expected.get("expected_temporal_boundaries", 0)
    act_tb = actual.get("temporal_boundary_count", 0)
    checks.append({
        "check": "temporal_boundary_count",
        "expected": exp_tb,
        "actual": act_tb,
        "pass": act_tb >= exp_tb,
    })
    if act_tb < exp_tb:
        all_pass = False

    # 4. per-hop checks
    for i in range(min_len):
        exp_hop = expected_chain[i]
        act_hop = actual_chain[i] if i < act_len else {}

        # signal match (prefix/suffix match, not exact — NPI may return
        # elaborated names)
        exp_sig = exp_hop.get("signal_ends_with", exp_hop.get("signal", ""))
        act_sig = act_hop.get("signal", "")
        sig_ok = exp_sig == "" or act_sig.endswith(exp_sig.replace("top.", ""))
        checks.append({
            "check": f"hop_{i}_signal",
            "expected": exp_sig,
            "actual": act_sig,
            "pass": sig_ok,
        })
        if not sig_ok:
            all_pass = False

        # hop type
        exp_type = exp_hop.get("hop_type", "")
        act_type = act_hop.get("hop_type", "")
        if exp_type:
            type_ok = act_type == exp_type
            checks.append({
                "check": f"hop_{i}_hop_type",
                "expected": exp_type,
                "actual": act_type,
                "pass": type_ok,
            })
            if not type_ok:
                all_pass = False

        # driver kind (if specified)
        exp_kind = exp_hop.get("driver_kind", "")
        act_kind = act_hop.get("driver_kind", "")
        if exp_kind:
            kind_ok = act_kind == exp_kind
            checks.append({
                "check": f"hop_{i}_driver_kind",
                "expected": exp_kind,
                "actual": act_kind,
                "pass": kind_ok,
            })
            if not kind_ok:
                all_pass = False

        # next signal (if specified)
        exp_next = exp_hop.get("next_signal_ends_with", exp_hop.get("next_signal", ""))
        act_next = act_hop.get("next_signal", "")
        if exp_next:
            next_ok = act_next.endswith(exp_next.replace("top.", "")) or act_next == exp_next
            checks.append({
                "check": f"hop_{i}_next_signal",
                "expected": exp_next,
                "actual": act_next,
                "pass": next_ok,
            })
            if not next_ok:
                all_pass = False

    # 5. branch evidence (if expected)
    exp_be = expected.get("expected_branch_evidence", False)
    act_be = len(actual.get("branch_evidence", [])) > 0
    if exp_be:
        checks.append({
            "check": "branch_evidence_present",
            "expected": True,
            "actual": act_be,
            "pass": act_be,
        })
        if not act_be:
            all_pass = False

    # determine overall verdict
    expected_verdict = expected.get("expected_verdict", "PASS")
    if all_pass:
        verdict = "PASS"
    elif any(c.get("check") == "chain_length" and not c["pass"] for c in checks):
        verdict = "FAIL"
    else:
        verdict = "PARTIAL" if expected_verdict == "PARTIAL" else "FAIL"

    return {
        "verdict": verdict,
        "expected_verdict": expected_verdict,
        "checks": checks,
        "all_checks_pass": all_pass,
    }


def main():
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <expected.json> <actual_chain.json> <verdict.json>",
              file=sys.stderr)
        sys.exit(1)

    expected = load_json(sys.argv[1])
    actual = load_json(sys.argv[2])
    verdict = compare(expected, actual)

    with open(sys.argv[3], "w") as f:
        json.dump(verdict, f, indent=2)

    print(f"Verdict: {verdict['verdict']}  (expected: {verdict['expected_verdict']})")
    for c in verdict["checks"]:
        status = "PASS" if c["pass"] else "FAIL"
        print(f"  [{status}] {c['check']}: expected={c['expected']}, actual={c['actual']}")

    if verdict["verdict"] != verdict["expected_verdict"] and verdict["verdict"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
