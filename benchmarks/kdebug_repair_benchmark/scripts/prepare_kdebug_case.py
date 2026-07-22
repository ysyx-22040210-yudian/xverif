#!/usr/bin/env python3
"""Prepare one existing failing case for manifest-gated KDebug collection."""

import argparse
import json
import shutil
from pathlib import Path


PLAN_VERSION = "kdebug-evidence-plan.v1"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_relative(case_dir, raw, label):
    case_dir = Path(case_dir).resolve()
    candidate = Path(raw)
    resolved = candidate.resolve() if candidate.is_absolute() else (case_dir / candidate).resolve()
    try:
        return resolved.relative_to(case_dir).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the case directory: {raw}") from exc


def parse_query(raw):
    parts = raw.split(",", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError("--query must be ID,SIGNAL,OUTPUT")
    request_id, signal, output = (part.strip() for part in parts)
    if not request_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"invalid request id: {request_id}")
    output_path = Path(output)
    if output_path.is_absolute() or ".." in output_path.parts or output_path.suffix.lower() != ".json":
        raise ValueError(f"query output must be a relative JSON path: {output}")
    return request_id, signal, output_path.as_posix()


def prepare_case(case_dir, suite_name, daidir, queries):
    case_dir = Path(case_dir).resolve()
    meta_path = case_dir / "case_meta.json"
    if not meta_path.is_file():
        raise ValueError(f"missing case metadata: {meta_path}")
    fail_dir = case_dir / "fail"
    if not fail_dir.is_dir() or not any(path.is_file() for path in fail_dir.iterdir()):
        raise ValueError(f"missing failing-run logs: {fail_dir}")

    daidir_rel = safe_relative(case_dir, daidir, "daidir")
    daidir_path = case_dir / daidir_rel
    if not daidir_path.is_dir():
        raise ValueError(f"missing case-local daidir: {daidir_path}")

    parsed_queries = [parse_query(raw) for raw in queries]
    ids = [item[0] for item in parsed_queries]
    outputs = [item[2] for item in parsed_queries]
    if len(set(ids)) != len(ids):
        raise ValueError("query ids must be unique")
    if len(set(outputs)) != len(outputs):
        raise ValueError("query outputs must be unique")

    evidence_dir = case_dir / "evidence"
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    requests_dir = evidence_dir / "requests"
    requests_dir.mkdir(parents=True)

    meta = read_json(meta_path)
    case_id = str(meta.get("case_id") or case_dir.name)
    if case_id != case_dir.name:
        raise ValueError(f"case_id mismatch: metadata={case_id} directory={case_dir.name}")
    meta["suite"] = suite_name
    meta["tool_evidence"] = {
        "required_for_with_kdebug": True,
        "plan": "evidence/kdebug_plan.json",
        "expected_files": outputs,
        "minimum_nonempty_files": len(outputs),
    }
    write_json(meta_path, meta)

    plan_requests = []
    for request_id, signal, output in parsed_queries:
        request_rel = f"evidence/requests/{request_id}.json"
        write_json(
            case_dir / request_rel,
            {
                "api_version": "kdebug.v1",
                "action": "trace.driver",
                "target": {"daidir": daidir_rel},
                "args": {
                    "signal": signal,
                    "include_source": True,
                    "include_trace": True,
                },
                "limits": {"max_rows": 64, "max_depth": 8},
                "output": {"format": "json"},
            },
        )
        plan_requests.append(
            {
                "id": request_id,
                "request": request_rel,
                "output": output,
                "diagnostic": True,
                "timeout_sec": 600,
            }
        )

    plan = {
        "schema_version": PLAN_VERSION,
        "case_id": case_id,
        "minimum_successful_invocations": len(plan_requests),
        "minimum_diagnostic_invocations": len(plan_requests),
        "max_fail_log_similarity": 0.80,
        "request_timeout_sec": 600,
        "requests": plan_requests,
    }
    write_json(evidence_dir / "kdebug_plan.json", plan)
    return {
        "case_id": case_id,
        "suite": suite_name,
        "daidir": daidir_rel,
        "requests": plan_requests,
        "legacy_evidence_removed": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--suite-name", required=True)
    parser.add_argument("--daidir", required=True)
    parser.add_argument(
        "--query",
        action="append",
        required=True,
        help="ID,SIGNAL,OUTPUT; repeat for multiple diagnostic queries",
    )
    args = parser.parse_args()
    try:
        result = prepare_case(args.case_dir, args.suite_name, args.daidir, args.query)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
