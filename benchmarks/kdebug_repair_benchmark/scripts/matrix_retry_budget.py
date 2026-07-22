#!/usr/bin/env python3
"""Track cumulative RETRY_LATER budget for one matrix task.

The matrix runner may retry a model/case after transient API throttling.  Those
attempts still consume the benchmark's one-hour budget for that matrix cell, so
this helper folds repeated RETRY_LATER rows into a final TIMEOUT row once their
active elapsed time reaches the configured timeout.
"""

import argparse
import csv
from pathlib import Path

from collect_results import FIELDS


TERMINAL_STATUSES = {
    "PASS",
    "TIMEOUT",
    "RULE_VIOLATION",
    "TOOL_EVIDENCE_MISSING",
    "TOOL_EVIDENCE_INVALID",
}


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def read_rows(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r.get("case_id", ""), r.get("model_id", ""), r.get("group", "")))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def is_key(row, model, group, case_id):
    return (
        row.get("model_id") == model
        and row.get("group") == group
        and row.get("case_id") == case_id
    )


def merge_semicolon(rows, field):
    seen = []
    for row in rows:
        for item in str(row.get(field, "")).split(";"):
            item = item.strip()
            if item and item not in seen:
                seen.append(item)
    return ";".join(seen)


def repair_class(row):
    rtl = str(row.get("rtl_changed", "")).lower() == "true" or bool(row.get("modified_rtl_files"))
    env = str(row.get("env_changed", "")).lower() == "true" or bool(row.get("modified_env_files"))
    if rtl and env:
        return "mixed"
    if rtl:
        return "rtl_only"
    if env:
        return "env_only"
    return "no_effective_patch"


def timeout_row(rows, attempt_rows, timeout_sec, cumulative_elapsed, reason="cumulative_retry_later_timeout"):
    base = dict(attempt_rows[-1] if attempt_rows else rows[-1])
    for field in ["elapsed_sec", "locate_sec", "edit_sec", "build_sec", "run_sec", "judge_sec"]:
        base[field] = round(sum(as_float(row.get(field)) for row in attempt_rows), 3)
    for field in ["iterations", "token_input", "token_output", "token_total"]:
        base[field] = str(sum(as_int(row.get(field)) for row in attempt_rows))
    base["token_is_estimate"] = (
        "true"
        if any(str(row.get("token_is_estimate", "")).lower() == "true" for row in attempt_rows)
        else "false"
    )
    if attempt_rows:
        base["start_time"] = next((row.get("start_time", "") for row in attempt_rows if row.get("start_time")), "")
        base["end_time"] = next((row.get("end_time", "") for row in reversed(attempt_rows) if row.get("end_time")), "")
    base["timeout_sec"] = str(timeout_sec)
    base["final_status"] = "TIMEOUT"
    base["failure_class"] = "timeout"
    base["final_build_rc"] = base.get("final_build_rc") or "1"
    base["final_run_rc"] = base.get("final_run_rc") or "1"
    base["final_judge_rc"] = "1"
    base["modified_files"] = merge_semicolon(attempt_rows, "modified_files")
    base["modified_rtl_files"] = merge_semicolon(attempt_rows, "modified_rtl_files")
    base["modified_env_files"] = merge_semicolon(attempt_rows, "modified_env_files")
    base["rtl_changed"] = "true" if base["modified_rtl_files"] else "false"
    base["env_changed"] = "true" if base["modified_env_files"] else "false"
    base["repair_class"] = repair_class(base)
    base["rule_violation"] = (
        f"{reason}: "
        f"attempts={len(attempt_rows)}; "
        f"cumulative_elapsed_sec={cumulative_elapsed:.3f}; "
        f"timeout_sec={timeout_sec}"
    )
    notes = base.get("notes", "")
    suffix = f"cumulative_attempts={len(attempt_rows)}"
    base["notes"] = f"{notes}; {suffix}" if notes else suffix
    return {field: base.get(field, "") for field in FIELDS}


def terminal_rollup_row(terminal_row, attempt_rows, timeout_sec, cumulative_elapsed):
    base = dict(terminal_row)
    for field in ["elapsed_sec", "locate_sec", "edit_sec", "build_sec", "run_sec", "judge_sec"]:
        base[field] = round(sum(as_float(row.get(field)) for row in attempt_rows), 3)
    for field in ["iterations", "token_input", "token_output", "token_total"]:
        base[field] = str(sum(as_int(row.get(field)) for row in attempt_rows))
    base["token_is_estimate"] = (
        "true"
        if any(str(row.get("token_is_estimate", "")).lower() == "true" for row in attempt_rows)
        else "false"
    )
    base["timeout_sec"] = str(timeout_sec)
    base["start_time"] = next((row.get("start_time", "") for row in attempt_rows if row.get("start_time")), "")
    base["end_time"] = next((row.get("end_time", "") for row in reversed(attempt_rows) if row.get("end_time")), "")
    base["modified_files"] = merge_semicolon(attempt_rows, "modified_files")
    base["modified_rtl_files"] = merge_semicolon(attempt_rows, "modified_rtl_files")
    base["modified_env_files"] = merge_semicolon(attempt_rows, "modified_env_files")
    base["rtl_changed"] = "true" if base["modified_rtl_files"] else "false"
    base["env_changed"] = "true" if base["modified_env_files"] else "false"
    base["repair_class"] = repair_class(base)
    notes = base.get("notes", "")
    suffix = f"cumulative_attempts={len(attempt_rows)}; cumulative_elapsed_sec={cumulative_elapsed:.3f}"
    base["notes"] = f"{notes}; {suffix}" if notes else suffix
    return {field: base.get(field, "") for field in FIELDS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--timeout", required=True, type=int)
    parser.add_argument("--mark-timeout", action="store_true")
    args = parser.parse_args()

    rows = read_rows(args.results)
    matches = [row for row in rows if is_key(row, args.model, args.group, args.case_id)]
    if not matches:
        print(f"PENDING cumulative_elapsed_sec=0.000 retry_later_attempts=0 remaining_sec={args.timeout}")
        return 0

    retry_rows = [row for row in matches if row.get("final_status") == "RETRY_LATER"]
    cumulative = sum(as_float(row.get("elapsed_sec")) for row in retry_rows)
    terminal = [row for row in matches if row.get("final_status") in TERMINAL_STATUSES]
    if terminal:
        terminal_row = terminal[-1]
        terminal_status = terminal_row.get("final_status", "")
        attempt_rows = retry_rows + [terminal_row]
        total = cumulative + as_float(terminal_row.get("elapsed_sec"))
        if args.mark_timeout and retry_rows:
            kept = [row for row in rows if not is_key(row, args.model, args.group, args.case_id)]
            if total > args.timeout and terminal_status == "PASS":
                kept.append(timeout_row(
                    matches,
                    attempt_rows,
                    args.timeout,
                    total,
                    reason="cumulative_budget_exceeded_before_pass",
                ))
                write_rows(args.results, kept)
                print(
                    "MARKED_TIMEOUT "
                    f"cumulative_elapsed_sec={total:.3f} "
                    f"retry_later_attempts={len(retry_rows)}"
                )
                return 0
            kept.append(terminal_rollup_row(terminal_row, attempt_rows, args.timeout, total))
            write_rows(args.results, kept)
        print(f"DONE status={terminal_status}")
        return 0

    if cumulative >= args.timeout and retry_rows:
        if args.mark_timeout:
            kept = [row for row in rows if not is_key(row, args.model, args.group, args.case_id)]
            kept.append(timeout_row(matches, retry_rows, args.timeout, cumulative))
            write_rows(args.results, kept)
            print(
                "MARKED_TIMEOUT "
                f"cumulative_elapsed_sec={cumulative:.3f} "
                f"retry_later_attempts={len(retry_rows)}"
            )
        else:
            print(
                "WOULD_TIMEOUT "
                f"cumulative_elapsed_sec={cumulative:.3f} "
                f"retry_later_attempts={len(retry_rows)}"
            )
        return 0

    print(
        "PENDING "
        f"cumulative_elapsed_sec={cumulative:.3f} "
        f"retry_later_attempts={len(retry_rows)} "
        f"remaining_sec={max(1, int(args.timeout - cumulative))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
