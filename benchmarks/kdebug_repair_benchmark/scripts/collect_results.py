#!/usr/bin/env python3
"""Collect repair trial directories into the benchmark results CSV."""

import argparse
import csv
import json
import re
from pathlib import Path

from kdebug_evidence import validate_case_evidence


FIELDS = [
    "suite", "model_id", "case_id", "group", "benchmark_layer", "layer",
    "level", "subsystem", "bug_domain", "bug_class", "env_fault_class",
    "target_flow", "repair_scope", "requires_rtl_change",
    "requires_env_change", "tool_evidence_required",
    "tool_evidence_present", "tool_evidence_valid", "tool_evidence_files",
    "tool_evidence_manifest", "tool_evidence_collection_id",
    "tool_evidence_validation", "public_design_refs",
    "timeout_sec",
    "start_time", "end_time", "elapsed_sec", "locate_sec", "edit_sec",
    "build_sec", "run_sec", "judge_sec", "iterations", "token_input",
    "token_output", "token_total", "token_is_estimate", "rtl_changed",
    "env_changed", "modified_files", "modified_rtl_files",
    "modified_env_files", "final_build_rc", "final_run_rc",
    "final_judge_rc", "final_status", "repair_class", "failure_class",
    "pass_marker", "evidence_used", "rule_violation", "notes",
]


def read_env(path):
    data = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def read_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def find_api_metrics(repair_dir):
    log_dir = repair_dir / "agent_logs"
    if not log_dir.exists():
        return {}
    metrics = sorted(log_dir.glob("*_metrics.json"))
    if not metrics:
        return {}
    return read_json(metrics[-1])


def find_transcript_metrics(repair_dir):
    log_dir = repair_dir / "agent_logs"
    if not log_dir.exists():
        return {}
    transcripts = sorted(log_dir.glob("*_transcript.jsonl"))
    if not transcripts:
        return {}

    data = {
        "iterations": 0,
        "token_input": 0,
        "token_output": 0,
        "token_total": 0,
        "token_is_estimate": False,
        "model_id": "",
        "notes": f"transcript={transcripts[-1].name}",
    }
    api_model_name = ""
    for line in transcripts[-1].read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        data["iterations"] = max(int(data["iterations"]), int(item.get("iteration") or 0))
        data["model_id"] = item.get("model_id") or data["model_id"]
        response = item.get("response") or {}
        api_model_name = response.get("model") or api_model_name
        usage = response.get("usage") or {}
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or 0)
        data["token_input"] += prompt
        data["token_output"] += completion
        data["token_total"] += total if total else prompt + completion
    if api_model_name:
        data["notes"] += f"; api_model_name={api_model_name}"
    if not data["iterations"] and not data["token_total"]:
        return {}
    return data


def discover_trial_dirs(root):
    for path in Path(root).rglob("trial_metrics.env"):
        if "_retry_later_archive" in path.parts:
            continue
        yield path.parent


def parse_seconds_from_log(text, label):
    pattern = re.compile(rf"{re.escape(label)}[_ ]sec(?:onds)?[=:]\s*([0-9.]+)", re.I)
    match = pattern.search(text)
    return match.group(1) if match else "0"


def normalize_bool(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "false"
    return "true" if str(value).strip().lower() in {"1", "true", "yes", "y", "on"} else "false"


def repair_class(rtl_changed, env_changed):
    rtl = normalize_bool(rtl_changed) == "true"
    env = normalize_bool(env_changed) == "true"
    if rtl and env:
        return "mixed"
    if rtl:
        return "rtl_only"
    if env:
        return "env_only"
    return "no_effective_patch"


def split_modified_files(value):
    files = [x for x in str(value or "").split(";") if x]
    rtl = [x for x in files if x.replace("\\", "/").startswith("rtl/")]
    env = [x for x in files if not x.replace("\\", "/").startswith("rtl/")]
    return rtl, env


def meta_repair_scope(meta):
    scope = meta.get("repair_scope") or {}
    if isinstance(scope, str):
        return scope
    roots = list(scope.get("allowed_roots") or [])
    files = list(scope.get("allowed_files") or [])
    return ";".join(roots + files)


def meta_requires(meta, key):
    scope = meta.get("repair_scope") or {}
    if isinstance(scope, dict):
        return scope.get(key)
    return None


def meta_tool_evidence_files(meta, group):
    if group != "with_kdebug":
        return ""
    files = meta.get("tool_evidence_files") or meta.get("kdebug_evidence_files") or []
    if not files:
        tool = meta.get("tool_evidence") or {}
        files = tool.get("expected_files") or []
    if isinstance(files, str):
        return files
    return ";".join(str(x) for x in files)


def evidence_status_from_files(repair_dir, meta, group):
    if group != "with_kdebug":
        return False, False, ""
    tool = meta.get("tool_evidence") or {}
    required = normalize_bool(tool.get("required_for_with_kdebug", True)) == "true"
    expected = [str(x) for x in (tool.get("expected_files") or [])]
    min_files = int(tool.get("minimum_nonempty_files") or 1)
    evidence_dir = repair_dir / "evidence" / "with_kdebug"
    found = []
    if evidence_dir.exists():
        for path in sorted(evidence_dir.rglob("*")):
            if not path.is_file() or path.stat().st_size <= 0:
                continue
            rel = str(path.relative_to(evidence_dir)).replace("\\", "/")
            if "answer_key_private" in rel:
                continue
            if not expected or rel in expected or Path(rel).name in expected:
                found.append(rel)
    found_names = {Path(item).name for item in found}
    all_expected = all(
        item in found
        or ("/" not in item.replace("\\", "/") and Path(item).name in found_names)
        for item in expected
    )
    present = (all_expected and len(found) >= min_files) if expected else len(found) >= min_files
    if not required:
        present = bool(found)
    return required, present, ";".join(found)


def meta_public_design_refs(meta):
    refs = meta.get("public_design_refs") or meta.get("design_refs") or []
    if isinstance(refs, str):
        return refs
    return ";".join(str(x) for x in refs)


def first_value(*values, default=""):
    for value in values:
        if value not in (None, ""):
            return value
    return default


def collect_one(repair_dir):
    repair_dir = Path(repair_dir)
    env = read_env(repair_dir / "trial_metrics.env")
    meta = read_json(repair_dir / "case_meta.json")
    api = find_api_metrics(repair_dir)
    transcript = find_transcript_metrics(repair_dir)
    trial_log = repair_dir / "trial.log"
    log_text = trial_log.read_text(encoding="utf-8", errors="replace") if trial_log.exists() else ""

    model = api.get("model_id") or transcript.get("model_id") or env.get("model") or repair_dir.parents[1].name
    group = api.get("group") or env.get("group") or repair_dir.parent.name
    case_id = api.get("case_id") or env.get("case_id") or meta.get("case_id") or repair_dir.name
    final_status = api.get("final_status") or env.get("final_status", "INFRA_ERROR")
    evidence_required, evidence_present, evidence_files = evidence_status_from_files(repair_dir, meta, group)
    evidence_validation = {}
    if group == "with_kdebug" and evidence_present:
        evidence_validation = validate_case_evidence(repair_dir, verify_inputs=True)
        if not evidence_validation.get("valid") and final_status in {"PASS", "TIMEOUT", ""}:
            final_status = "TOOL_EVIDENCE_INVALID"

    modified = api.get("modified_files", "")
    rtl_files = api.get("modified_rtl_files", "")
    env_files = api.get("modified_env_files", "")
    if modified and not rtl_files and not env_files:
        rtl_split, env_split = split_modified_files(modified)
        rtl_files = ";".join(rtl_split)
        env_files = ";".join(env_split)

    rtl_changed = api.get("rtl_changed")
    env_changed = api.get("env_changed")
    if rtl_changed is None:
        rtl_changed = bool(rtl_files)
    if env_changed is None:
        env_changed = bool(env_files)

    repair_kind = api.get("repair_class") or repair_class(rtl_changed, env_changed)

    row = {
        "suite": api.get("suite") or env.get("suite") or meta.get("suite", "xiangshan_repair_benchmark_v2"),
        "model_id": model,
        "case_id": case_id,
        "group": group,
        "benchmark_layer": api.get("benchmark_layer") or meta.get("benchmark_layer") or meta.get("layer", ""),
        "layer": api.get("layer") or meta.get("layer", ""),
        "level": api.get("level") or meta.get("level", ""),
        "subsystem": api.get("subsystem") or meta.get("subsystem", ""),
        "bug_domain": api.get("bug_domain") or meta.get("bug_domain", ""),
        "bug_class": api.get("bug_class") or meta.get("bug_class", ""),
        "env_fault_class": api.get("env_fault_class") or meta.get("env_fault_class", ""),
        "target_flow": api.get("target_flow") or meta.get("target_flow", ""),
        "repair_scope": api.get("repair_scope") or meta_repair_scope(meta),
        "requires_rtl_change": normalize_bool(first_value(api.get("requires_rtl_change"), meta_requires(meta, "requires_rtl_change"), default=False)),
        "requires_env_change": normalize_bool(first_value(api.get("requires_env_change"), meta_requires(meta, "requires_env_change"), default=False)),
        "tool_evidence_required": normalize_bool(first_value(api.get("tool_evidence_required"), evidence_required, default=False)),
        "tool_evidence_present": normalize_bool(first_value(api.get("tool_evidence_present"), evidence_present, default=False)),
        "tool_evidence_valid": normalize_bool(first_value(api.get("tool_evidence_valid"), evidence_validation.get("valid"), default=False)),
        "tool_evidence_files": api.get("tool_evidence_files", "") or evidence_files or meta_tool_evidence_files(meta, group),
        "tool_evidence_manifest": api.get("tool_evidence_manifest", "") or (
            "evidence/with_kdebug/manifest.json" if evidence_validation.get("manifest") else ""
        ),
        "tool_evidence_collection_id": api.get("tool_evidence_collection_id", "") or evidence_validation.get("collection_id", ""),
        "tool_evidence_validation": api.get("tool_evidence_validation", "") or (
            "valid" if evidence_validation.get("valid") else "; ".join(evidence_validation.get("errors") or [])
        ) if group == "with_kdebug" else "not_required",
        "public_design_refs": api.get("public_design_refs", "") or meta_public_design_refs(meta),
        "timeout_sec": api.get("timeout_sec") or env.get("timeout_sec", "3600"),
        "start_time": api.get("start_time") or env.get("start_time", ""),
        "end_time": api.get("end_time") or env.get("end_time", ""),
        "elapsed_sec": api.get("elapsed_sec") or env.get("elapsed_sec", ""),
        "locate_sec": api.get("locate_sec") or parse_seconds_from_log(log_text, "locate"),
        "edit_sec": api.get("edit_sec") or parse_seconds_from_log(log_text, "edit"),
        "build_sec": api.get("build_sec") or parse_seconds_from_log(log_text, "build"),
        "run_sec": api.get("run_sec") or parse_seconds_from_log(log_text, "run"),
        "judge_sec": api.get("judge_sec") or parse_seconds_from_log(log_text, "judge"),
        "iterations": first_value(api.get("iterations"), transcript.get("iterations"), default="0"),
        "token_input": first_value(api.get("token_input"), transcript.get("token_input"), default="0"),
        "token_output": first_value(api.get("token_output"), transcript.get("token_output"), default="0"),
        "token_total": first_value(api.get("token_total"), transcript.get("token_total"), default="0"),
        "token_is_estimate": normalize_bool(first_value(api.get("token_is_estimate"), transcript.get("token_is_estimate"), default=True)),
        "rtl_changed": normalize_bool(rtl_changed),
        "env_changed": normalize_bool(env_changed),
        "modified_files": modified,
        "modified_rtl_files": rtl_files,
        "modified_env_files": env_files,
        "final_build_rc": api.get("final_build_rc") or "",
        "final_run_rc": api.get("final_run_rc") or "",
        "final_judge_rc": api.get("final_judge_rc") or env.get("final_judge_rc", ""),
        "final_status": final_status,
        "repair_class": repair_kind,
        "failure_class": api.get("failure_class", "") or (
            "evidence_invalid" if final_status == "TOOL_EVIDENCE_INVALID" else ""
        ),
        "pass_marker": api.get("pass_marker") or ("PASS marker observed" if final_status == "PASS" and "PASS" in log_text else ""),
        "evidence_used": api.get("evidence_used") or (
            (
                "validated kdebug manifest evidence + logs + repair-scope files"
                if evidence_validation.get("valid")
                else "no valid kdebug evidence; model was not called"
            )
            if group == "with_kdebug"
            else "logs + repair-scope files + text search"
        ),
        "rule_violation": api.get("rule_violation", ""),
        "notes": api.get("notes") or transcript.get("notes") or f"repair_dir={repair_dir}",
    }
    return {k: row.get(k, "") for k in FIELDS}


def write_rows(rows, out):
    rows = sorted(rows, key=lambda r: (r["case_id"], r["model_id"], r["group"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--single", type=Path, default=None)
    args = parser.parse_args()

    if args.single:
        existing = []
        if args.out.exists():
            existing = list(csv.DictReader(args.out.open(newline="", encoding="utf-8")))
        row = collect_one(args.single)
        key = (row["case_id"], row["model_id"], row["group"])
        new_status = row.get("final_status", "")
        filtered = [
            r for r in existing
            if (
                (r.get("case_id"), r.get("model_id"), r.get("group")) != key
                or (
                    new_status != "RETRY_LATER"
                    and r.get("final_status") == "RETRY_LATER"
                )
            )
        ]
        filtered.append(row)
        write_rows(filtered, args.out)
    else:
        rows = [collect_one(path) for path in discover_trial_dirs(args.repair_root)]
        write_rows(rows, args.out)
    print(args.out)


if __name__ == "__main__":
    main()
