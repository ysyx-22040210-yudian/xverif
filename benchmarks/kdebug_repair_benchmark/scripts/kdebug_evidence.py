#!/usr/bin/env python3
"""Collect and validate case-specific KDebug benchmark evidence.

The collector invokes the KDebug CLI directly for every request declared by a
case plan.  The validator treats files as untrusted and recomputes provenance,
input, request, response, and manifest hashes before a with_kdebug trial starts.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_VERSION = "kdebug-evidence-manifest.v1"
PLAN_VERSION = "kdebug-evidence-plan.v1"
COLLECTOR_VERSION = "1.0.0"
DEFAULT_PLAN = Path("evidence/kdebug_plan.json")
DEFAULT_EVIDENCE_DIR = Path("evidence/with_kdebug")
MANIFEST_NAME = "manifest.json"
MANIFEST_HASH_NAME = "manifest.sha256"
FRESHNESS_TOLERANCE_NS = 2_000_000_000
CONTROL_ACTIONS = {
    "actions",
    "schema",
    "session.open",
    "session.close",
    "session.list",
    "session.doctor",
    "session.export",
    "session.import",
    "server.version",
    "server.ping",
    "server.quit",
}


class EvidenceError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_json(path: Path, value: object) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(path, data)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"JSON root must be an object: {path}")
    return value


def safe_relative_path(value: str, label: str) -> Path:
    path = Path(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise EvidenceError(f"{label} must be a case-relative path: {value}")
    return path


def artifact_record(path: Path, root: Path) -> dict:
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def fingerprint_path(path: Path) -> dict:
    resolved = path.resolve()
    if not resolved.exists():
        raise EvidenceError(f"KDebug input does not exist: {resolved}")
    if resolved.is_file():
        return {
            "kind": "file",
            "path": str(resolved),
            "size": resolved.stat().st_size,
            "sha256": sha256_file(resolved),
        }
    if not resolved.is_dir():
        raise EvidenceError(f"unsupported KDebug input type: {resolved}")

    digest = hashlib.sha256()
    file_count = 0
    total_size = 0
    for child in sorted(resolved.rglob("*"), key=lambda p: p.relative_to(resolved).as_posix()):
        rel = child.relative_to(resolved).as_posix()
        if child.is_symlink():
            target = os.readlink(child)
            digest.update(f"L\0{rel}\0{target}\n".encode("utf-8", errors="surrogateescape"))
            continue
        if not child.is_file():
            continue
        size = child.stat().st_size
        child_hash = sha256_file(child)
        digest.update(f"F\0{rel}\0{size}\0{child_hash}\n".encode("utf-8"))
        file_count += 1
        total_size += size
    return {
        "kind": "directory",
        "path": str(resolved),
        "file_count": file_count,
        "size": total_size,
        "sha256": digest.hexdigest(),
    }


def same_fingerprint(expected: dict, actual: dict) -> bool:
    keys = {"kind", "path", "size", "sha256"}
    if expected.get("kind") == "directory":
        keys.add("file_count")
    return all(expected.get(key) == actual.get(key) for key in keys)


def resolve_command_prefix(values: list[str]) -> list[str]:
    if not values:
        raise EvidenceError("KDebug command is empty")
    first = values[0]
    resolved_first = shutil.which(first) if not Path(first).is_absolute() else first
    if not resolved_first:
        raise EvidenceError(f"KDebug executable not found: {first}")
    prefix = [str(Path(resolved_first).resolve())]
    for item in values[1:]:
        candidate = Path(item)
        prefix.append(str(candidate.resolve()) if candidate.exists() else item)
    return prefix


def command_identity(prefix: list[str]) -> list[dict]:
    records = []
    for index, item in enumerate(prefix):
        path = Path(item)
        if path.is_file():
            records.append({
                "argv_index": index,
                "role": "command",
                "path": str(path.resolve()),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    roots = []
    for item in prefix:
        path = Path(item)
        if path.is_file() and path.parent.name == "tools":
            roots.append(path.parent.parent)
    for root in roots:
        for rel in (
            "kdebug/kdebug",
            "kdebug/tcl_engine/kdebug-engine",
            "kdebug/tcl_engine/kdebug_engine.py",
            "kdebug/tcl_engine/kdebug_npi.tcl",
        ):
            path = root / rel
            if not path.is_file() or any(record["path"] == str(path.resolve()) for record in records):
                continue
            records.append({
                "argv_index": None,
                "role": "runtime",
                "path": str(path.resolve()),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return records


def repository_identity(prefix: list[str]) -> dict | None:
    for item in prefix:
        path = Path(item)
        if not path.is_file():
            continue
        for parent in [path.parent, *path.parents]:
            if not (parent / ".git").exists():
                continue
            proc = subprocess.run(
                ["git", "-C", str(parent), "rev-parse", "HEAD"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                text=True,
            )
            if proc.returncode == 0:
                return {"root": str(parent.resolve()), "commit": proc.stdout.strip()}
            break
    return None


def canonicalize_request(request: dict, case_dir: Path, request_id: str | None = None) -> dict:
    canonical = json.loads(json.dumps(request))
    target = canonical.get("target")
    if not isinstance(target, dict):
        raise EvidenceError("KDebug request must contain a target object")
    target_count = 0
    for key in ("fsdb", "daidir"):
        value = target.get(key)
        if not value:
            continue
        path = Path(str(value))
        if not path.is_absolute():
            path = case_dir / path
        resolved = path.resolve()
        target[key] = str(resolved)
        target_count += 1
    if not target_count:
        raise EvidenceError("diagnostic KDebug request must target fsdb and/or daidir directly")
    output = canonical.setdefault("output", {})
    if not isinstance(output, dict):
        raise EvidenceError("request output must be an object")
    output["format"] = "json"
    if request_id is not None:
        canonical["request_id"] = request_id
    return canonical


def resolve_request_targets(
    request: dict,
    case_dir: Path,
    fingerprint_cache: dict[str, dict] | None = None,
) -> tuple[dict, list[dict]]:
    canonical = canonicalize_request(request, case_dir)
    target = canonical["target"]
    inputs = []
    for key in ("fsdb", "daidir"):
        value = target.get(key)
        if not value:
            continue
        resolved = Path(str(value))
        cache_key = str(resolved)
        if fingerprint_cache is not None and cache_key in fingerprint_cache:
            record = dict(fingerprint_cache[cache_key])
        else:
            record = fingerprint_path(resolved)
            if fingerprint_cache is not None:
                fingerprint_cache[cache_key] = dict(record)
        record["target_field"] = key
        inputs.append(record)
    return canonical, inputs


def parse_json_response(stdout: bytes) -> dict:
    text = stdout.decode("utf-8", errors="replace").strip()
    if not text:
        raise EvidenceError("KDebug produced empty stdout")
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    for value in reversed(candidates):
        if "ok" in value and "action" in value:
            return value
    raise EvidenceError("KDebug stdout did not contain a response JSON object")


def normalize_text(value: str) -> str:
    return " ".join(str(value).split()).lower()


def string_leaves(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from string_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from string_leaves(child)


def response_log_similarity(response: dict, fail_logs: list[str]) -> tuple[float, str]:
    response_text = normalize_text(json.dumps(response, ensure_ascii=False, sort_keys=True))
    best_ratio = 0.0
    reason = ""
    for log in fail_logs:
        normalized_log = normalize_text(log)
        if not normalized_log:
            continue
        for leaf in string_leaves(response):
            normalized_leaf = normalize_text(leaf)
            if len(normalized_leaf) >= 128 and normalized_leaf in normalized_log:
                ratio = min(1.0, len(normalized_leaf) / max(1, len(normalized_log)))
                if ratio > best_ratio:
                    best_ratio = ratio
                    reason = "response contains a long string copied from a fail log"
        left = response_text[:100000]
        right = normalized_log[:100000]
        ratio = difflib.SequenceMatcher(None, left, right, autojunk=True).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            reason = "response is textually similar to a fail log"
    return best_ratio, reason


def load_case_configuration(case_dir: Path, plan_path: Path | None = None) -> tuple[dict, dict, Path]:
    meta_path = case_dir / "case_meta.json"
    if not meta_path.is_file():
        raise EvidenceError(f"missing case_meta.json: {case_dir}")
    meta = read_json(meta_path)
    configured = (meta.get("tool_evidence") or {}).get("plan")
    selected = plan_path or (case_dir / safe_relative_path(configured, "tool_evidence.plan") if configured else case_dir / DEFAULT_PLAN)
    if not selected.is_absolute():
        selected = case_dir / selected
    selected = selected.resolve()
    if not selected.is_file():
        raise EvidenceError(f"missing KDebug evidence plan: {selected}")
    plan = read_json(selected)
    return meta, plan, selected


def validate_plan(case_dir: Path, meta: dict, plan: dict) -> None:
    case_id = str(meta.get("case_id") or case_dir.name)
    if plan.get("schema_version") != PLAN_VERSION:
        raise EvidenceError(f"unsupported evidence plan schema: {plan.get('schema_version')}")
    if plan.get("case_id") != case_id:
        raise EvidenceError(f"evidence plan case_id mismatch: expected {case_id}")
    requests = plan.get("requests")
    if not isinstance(requests, list) or not requests:
        raise EvidenceError("evidence plan requests must be a nonempty array")
    ids = set()
    outputs = set()
    for entry in requests:
        if not isinstance(entry, dict):
            raise EvidenceError("each evidence request entry must be an object")
        request_id = str(entry.get("id") or "")
        if not request_id or not request_id.replace("_", "").replace("-", "").isalnum():
            raise EvidenceError(f"invalid evidence request id: {request_id}")
        if request_id in ids:
            raise EvidenceError(f"duplicate evidence request id: {request_id}")
        ids.add(request_id)
        safe_relative_path(entry.get("request", ""), f"request path for {request_id}")
        output = safe_relative_path(entry.get("output", ""), f"output path for {request_id}")
        if output.parts[0].startswith("_") or output.name in {MANIFEST_NAME, MANIFEST_HASH_NAME}:
            raise EvidenceError(f"reserved evidence output path: {output}")
        if output.as_posix() in outputs:
            raise EvidenceError(f"duplicate evidence output path: {output}")
        outputs.add(output.as_posix())

    expected = set(str(item) for item in ((meta.get("tool_evidence") or {}).get("expected_files") or []))
    if not expected:
        raise EvidenceError("case_meta tool_evidence.expected_files must be a nonempty array")
    if outputs != expected:
        raise EvidenceError(
            "plan outputs must exactly match case_meta tool_evidence.expected_files: "
            f"plan={sorted(outputs)} meta={sorted(expected)}"
        )


def fail_log_records(case_dir: Path) -> tuple[list[dict], list[str]]:
    records = []
    texts = []
    fail_dir = case_dir / "fail"
    if fail_dir.is_dir():
        for path in sorted(fail_dir.rglob("*.log")):
            if not path.is_file():
                continue
            records.append(artifact_record(path, case_dir))
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    if not records:
        raise EvidenceError(f"no fail/*.log files found for evidence provenance: {case_dir}")
    return records, texts


def archive_existing_evidence(case_dir: Path, evidence_dir: Path) -> None:
    if not evidence_dir.exists() or not any(evidence_dir.iterdir()):
        return
    resolved_case = case_dir.resolve()
    resolved_evidence = evidence_dir.resolve()
    try:
        resolved_evidence.relative_to(resolved_case)
    except ValueError as exc:
        raise EvidenceError(f"refusing to archive evidence outside case dir: {resolved_evidence}") from exc
    archive_root = case_dir / "evidence" / "_kdebug_archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = archive_root / stamp
    os.replace(evidence_dir, destination)


def collect_case(case_dir: Path, command_prefix: list[str], force: bool = False, plan_path: Path | None = None) -> dict:
    case_dir = case_dir.resolve()
    meta, plan, selected_plan = load_case_configuration(case_dir, plan_path)
    validate_plan(case_dir, meta, plan)
    evidence_dir = case_dir / DEFAULT_EVIDENCE_DIR

    if not force and (evidence_dir / MANIFEST_NAME).is_file():
        current = validate_case_evidence(case_dir, verify_inputs=True)
        if current["valid"]:
            current["reused"] = True
            return current

    prefix = resolve_command_prefix(command_prefix)
    fail_records, fail_texts = fail_log_records(case_dir)
    archive_existing_evidence(case_dir, evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    collection_id = str(uuid.uuid4())
    started_ns = time.time_ns()
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "collection_id": collection_id,
        "case_id": str(meta.get("case_id") or case_dir.name),
        "case_root": str(case_dir),
        "started_at": now_iso(),
        "started_at_epoch_ns": started_ns,
        "collector": {
            "name": "kdebug_evidence.py",
            "version": COLLECTOR_VERSION,
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "policy": {
            "minimum_successful_invocations": int(plan.get("minimum_successful_invocations", 1)),
            "minimum_diagnostic_invocations": int(plan.get("minimum_diagnostic_invocations", 1)),
            "max_fail_log_similarity": float(plan.get("max_fail_log_similarity", 0.80)),
            "require_direct_target": True,
        },
        "case_meta": artifact_record(case_dir / "case_meta.json", case_dir),
        "plan": artifact_record(selected_plan, case_dir),
        "fail_logs": fail_records,
        "tool": {
            "name": "kdebug",
            "command_prefix": prefix,
            "command_artifacts": command_identity(prefix),
            "repository": repository_identity(prefix),
            "reported_versions": [],
        },
        "invocations": [],
    }

    fingerprint_cache: dict[str, dict] = {}
    versions = set()
    for entry in plan["requests"]:
        entry_id = str(entry["id"])
        source_request = case_dir / safe_relative_path(entry["request"], f"request path for {entry_id}")
        request = read_json(source_request)
        action = str(request.get("action") or "")
        if not action:
            raise EvidenceError(f"KDebug request has no action: {source_request}")
        diagnostic = bool(entry.get("diagnostic", True))
        if diagnostic and action in CONTROL_ACTIONS:
            raise EvidenceError(f"control action cannot satisfy diagnostic evidence: {action}")
        canonical, input_records = resolve_request_targets(request, case_dir, fingerprint_cache)
        canonical["request_id"] = f"{manifest['case_id']}:{entry_id}:{collection_id}"

        request_path = evidence_dir / "_requests" / f"{entry_id}.json"
        raw_path = evidence_dir / "_raw" / f"{entry_id}.stdout"
        stderr_path = evidence_dir / "_stderr" / f"{entry_id}.txt"
        response_path = evidence_dir / safe_relative_path(entry["output"], f"output path for {entry_id}")
        atomic_write_json(request_path, canonical)

        command = prefix + ["--json", str(request_path.resolve())]
        invocation_started_ns = time.time_ns()
        invocation_started = now_iso()
        timeout_sec = int(entry.get("timeout_sec", plan.get("request_timeout_sec", 600)))
        timed_out = False
        try:
            proc = subprocess.run(
                command,
                cwd=case_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(1, timeout_sec),
                check=False,
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = (exc.stderr or b"") + f"\nTIMEOUT after {timeout_sec}s\n".encode("utf-8")
            exit_code = 124
            timed_out = True
        invocation_ended_ns = time.time_ns()
        atomic_write_bytes(raw_path, stdout)
        atomic_write_bytes(stderr_path, stderr)

        response = None
        parse_error = ""
        try:
            response = parse_json_response(stdout)
        except EvidenceError as exc:
            parse_error = str(exc)
        if response is not None:
            atomic_write_json(response_path, response)
            tool = response.get("tool")
            if isinstance(tool, dict) and tool.get("version"):
                versions.add(str(tool["version"]))

        invocation = {
            "id": entry_id,
            "diagnostic": diagnostic,
            "action": action,
            "command_argv": command,
            "started_at": invocation_started,
            "started_at_epoch_ns": invocation_started_ns,
            "ended_at": now_iso(),
            "ended_at_epoch_ns": invocation_ended_ns,
            "duration_sec": round((invocation_ended_ns - invocation_started_ns) / 1_000_000_000, 6),
            "timeout_sec": timeout_sec,
            "timed_out": timed_out,
            "exit_code": exit_code,
            "request": artifact_record(request_path, case_dir),
            "source_request": artifact_record(source_request, case_dir),
            "raw_stdout": artifact_record(raw_path, case_dir),
            "stderr": artifact_record(stderr_path, case_dir),
            "inputs": input_records,
            "response": artifact_record(response_path, case_dir) if response_path.is_file() else None,
            "response_ok": bool(response and response.get("ok") is True),
            "parse_error": parse_error,
        }
        if response is not None:
            ratio, reason = response_log_similarity(response, fail_texts)
            invocation["fail_log_similarity"] = round(ratio, 6)
            invocation["fail_log_similarity_reason"] = reason
        manifest["invocations"].append(invocation)

    manifest["tool"]["reported_versions"] = sorted(versions)
    manifest["ended_at"] = now_iso()
    manifest["ended_at_epoch_ns"] = time.time_ns()
    manifest["summary"] = {
        "invocation_count": len(manifest["invocations"]),
        "successful_invocations": sum(
            1 for item in manifest["invocations"] if item["exit_code"] == 0 and item["response_ok"]
        ),
        "successful_diagnostic_invocations": sum(
            1
            for item in manifest["invocations"]
            if item["diagnostic"] and item["exit_code"] == 0 and item["response_ok"]
        ),
    }
    manifest_path = evidence_dir / MANIFEST_NAME
    atomic_write_json(manifest_path, manifest)
    manifest_hash = sha256_file(manifest_path)
    atomic_write_bytes(evidence_dir / MANIFEST_HASH_NAME, f"{manifest_hash}  {MANIFEST_NAME}\n".encode("ascii"))
    result = validate_case_evidence(case_dir, verify_inputs=True)
    result["reused"] = False
    return result


def resolve_artifact(case_dir: Path, record: dict | None, label: str, errors: list[str]) -> Path | None:
    if not isinstance(record, dict):
        errors.append(f"missing {label} artifact record")
        return None
    try:
        rel = safe_relative_path(record.get("path", ""), label)
    except EvidenceError as exc:
        errors.append(str(exc))
        return None
    path = case_dir / rel
    if not path.is_file():
        errors.append(f"missing {label} artifact: {rel.as_posix()}")
        return None
    actual_size = path.stat().st_size
    actual_hash = sha256_file(path)
    if record.get("size") != actual_size:
        errors.append(f"{label} size mismatch: {rel.as_posix()}")
    if record.get("sha256") != actual_hash:
        errors.append(f"{label} sha256 mismatch: {rel.as_posix()}")
    return path


def _validate_case_evidence(case_dir: Path | str, verify_inputs: bool = True) -> dict:
    case_dir = Path(case_dir).resolve()
    errors: list[str] = []
    evidence_dir = case_dir / DEFAULT_EVIDENCE_DIR
    manifest_path = evidence_dir / MANIFEST_NAME
    sidecar_path = evidence_dir / MANIFEST_HASH_NAME
    result = {
        "valid": False,
        "case_id": case_dir.name,
        "manifest": str(manifest_path),
        "collection_id": "",
        "evidence_files": [],
        "errors": errors,
    }
    if not manifest_path.is_file():
        errors.append(f"missing {MANIFEST_NAME}")
        return result
    if not sidecar_path.is_file():
        errors.append(f"missing {MANIFEST_HASH_NAME}")
        return result
    expected_sidecar = sidecar_path.read_text(encoding="ascii", errors="replace").split()
    if not expected_sidecar or expected_sidecar[0] != sha256_file(manifest_path):
        errors.append("manifest.sha256 does not match manifest.json")
    if len(expected_sidecar) < 2 or expected_sidecar[1] != MANIFEST_NAME:
        errors.append("manifest.sha256 does not name manifest.json")
    try:
        manifest = read_json(manifest_path)
    except EvidenceError as exc:
        errors.append(str(exc))
        return result

    result["collection_id"] = str(manifest.get("collection_id") or "")
    if manifest.get("schema_version") != MANIFEST_VERSION:
        errors.append(f"unsupported manifest schema: {manifest.get('schema_version')}")

    try:
        meta, plan, selected_plan = load_case_configuration(case_dir)
        validate_plan(case_dir, meta, plan)
    except EvidenceError as exc:
        errors.append(str(exc))
        return result
    case_id = str(meta.get("case_id") or case_dir.name)
    result["case_id"] = case_id
    if manifest.get("case_id") != case_id:
        errors.append(f"manifest case_id mismatch: expected {case_id}")
    collection_root_value = str(manifest.get("case_root") or "")
    collection_root = Path(collection_root_value) if collection_root_value else None
    if not collection_root or not collection_root.is_absolute():
        errors.append("manifest case_root must be an absolute collection path")
        collection_root = None
    elif collection_root.name != case_id:
        errors.append(f"manifest case_root does not end in {case_id}")
    if not result["collection_id"]:
        errors.append("manifest collection_id is empty")
    else:
        try:
            if str(uuid.UUID(result["collection_id"])) != result["collection_id"]:
                errors.append("manifest collection_id is not a canonical UUID")
        except ValueError:
            errors.append("manifest collection_id is not a UUID")

    resolve_artifact(case_dir, manifest.get("case_meta"), "case_meta", errors)
    plan_record = manifest.get("plan")
    resolved_plan = resolve_artifact(case_dir, plan_record, "plan", errors)
    if resolved_plan and resolved_plan.resolve() != selected_plan.resolve():
        errors.append("manifest plan path does not match configured plan")

    fail_records = manifest.get("fail_logs")
    current_fail_records, fail_texts = fail_log_records(case_dir)
    if not isinstance(fail_records, list) or not fail_records:
        errors.append("manifest fail_logs is empty")
        fail_records = []
    for index, record in enumerate(fail_records):
        resolve_artifact(case_dir, record, f"fail_logs[{index}]", errors)
    current_fail_map = {record["path"]: record["sha256"] for record in current_fail_records}
    manifest_fail_map = {
        record.get("path"): record.get("sha256") for record in fail_records if isinstance(record, dict)
    }
    if current_fail_map != manifest_fail_map:
        errors.append("current fail logs do not match the manifest fail-log set")

    started_ns = int(manifest.get("started_at_epoch_ns") or 0)
    ended_ns = int(manifest.get("ended_at_epoch_ns") or 0)
    if started_ns <= 0 or ended_ns < started_ns:
        errors.append("manifest collection timestamps are invalid")
    provenance_paths = [case_dir / "case_meta.json", selected_plan]
    provenance_paths.extend(case_dir / record["path"] for record in current_fail_records)
    newest_provenance_ns = max((path.stat().st_mtime_ns for path in provenance_paths), default=0)
    # Some shared/Windows filesystems round mtimes slightly into the future.
    # Hash equality still protects content; this tolerance only absorbs clock granularity.
    if started_ns + FRESHNESS_TOLERANCE_NS < newest_provenance_ns:
        errors.append("evidence collection did not start after case metadata, plan, and fail logs were finalized")

    policy = manifest.get("policy") if isinstance(manifest.get("policy"), dict) else {}
    min_success = int(policy.get("minimum_successful_invocations", plan.get("minimum_successful_invocations", 1)))
    min_diagnostic = int(policy.get("minimum_diagnostic_invocations", plan.get("minimum_diagnostic_invocations", 1)))
    max_similarity = float(policy.get("max_fail_log_similarity", plan.get("max_fail_log_similarity", 0.80)))
    if not 0 <= max_similarity < 1:
        errors.append("max_fail_log_similarity must be in [0, 1)")

    tool = manifest.get("tool") if isinstance(manifest.get("tool"), dict) else {}
    if tool.get("name") != "kdebug":
        errors.append("manifest tool.name must be kdebug")
    prefix = tool.get("command_prefix")
    if not isinstance(prefix, list) or not prefix:
        errors.append("manifest tool.command_prefix is empty")
        prefix = []
    for record in tool.get("command_artifacts") or []:
        path = Path(str(record.get("path") or ""))
        if not path.is_file():
            errors.append(f"tool command artifact missing: {path}")
            continue
        if record.get("size") != path.stat().st_size:
            errors.append(f"tool command/runtime artifact size changed: {path}")
        if record.get("sha256") != sha256_file(path):
            errors.append(f"tool command/runtime artifact changed: {path}")
    repository = tool.get("repository")
    if isinstance(repository, dict) and repository.get("root") and repository.get("commit"):
        proc = subprocess.run(
            ["git", "-C", str(repository["root"]), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
        if proc.returncode != 0 or proc.stdout.strip() != repository.get("commit"):
            errors.append("KDebug repository commit differs from the collection manifest")

    invocations = manifest.get("invocations")
    if not isinstance(invocations, list) or not invocations:
        errors.append("manifest invocations is empty")
        invocations = []
    plan_entries = {str(entry["id"]): entry for entry in plan["requests"]}
    seen_ids = set()
    successful = 0
    diagnostic_successful = 0
    observed_versions = set()
    latest_invocation_end_ns = started_ns
    declared_files = {MANIFEST_NAME, MANIFEST_HASH_NAME}
    output_files = []
    validation_fingerprint_cache: dict[str, dict] = {}
    for index, invocation in enumerate(invocations):
        label = f"invocations[{index}]"
        if not isinstance(invocation, dict):
            errors.append(f"{label} must be an object")
            continue
        entry_id = str(invocation.get("id") or "")
        if entry_id not in plan_entries:
            errors.append(f"{label} id is not declared by the plan: {entry_id}")
            continue
        if entry_id in seen_ids:
            errors.append(f"duplicate invocation id: {entry_id}")
        seen_ids.add(entry_id)
        plan_entry = plan_entries[entry_id]
        source_path = resolve_artifact(case_dir, invocation.get("source_request"), f"{label}.source_request", errors)
        request_path = resolve_artifact(case_dir, invocation.get("request"), f"{label}.request", errors)
        raw_path = resolve_artifact(case_dir, invocation.get("raw_stdout"), f"{label}.raw_stdout", errors)
        stderr_path = resolve_artifact(case_dir, invocation.get("stderr"), f"{label}.stderr", errors)
        response_path = resolve_artifact(case_dir, invocation.get("response"), f"{label}.response", errors)
        for record in (invocation.get("source_request"), invocation.get("request"), invocation.get("raw_stdout"), invocation.get("stderr"), invocation.get("response")):
            if isinstance(record, dict) and record.get("path"):
                declared_files.add(str(record["path"]).replace("\\", "/"))

        expected_source = case_dir / safe_relative_path(plan_entry["request"], f"plan request {entry_id}")
        if source_path and source_path.resolve() != expected_source.resolve():
            errors.append(f"{label} source request path does not match the plan")
        expected_output = (DEFAULT_EVIDENCE_DIR / safe_relative_path(plan_entry["output"], f"plan output {entry_id}")).as_posix()
        if isinstance(invocation.get("response"), dict):
            actual_output = str(invocation["response"].get("path") or "").replace("\\", "/")
            if actual_output != expected_output:
                errors.append(f"{label} response path does not match plan output")
            output_files.append(safe_relative_path(plan_entry["output"], f"plan output {entry_id}").as_posix())

        request_obj = None
        if request_path:
            try:
                request_obj = read_json(request_path)
            except EvidenceError as exc:
                errors.append(str(exc))
        source_obj = None
        if source_path:
            try:
                source_obj = read_json(source_path)
            except EvidenceError as exc:
                errors.append(str(exc))
        action = str(invocation.get("action") or "")
        if not request_obj or request_obj.get("action") != action:
            errors.append(f"{label} request action mismatch")
        if not source_obj or action != str(source_obj.get("action") or ""):
            errors.append(f"{label} action differs from source request")
        if source_obj and request_obj:
            try:
                expected_request = canonicalize_request(
                    source_obj,
                    collection_root or case_dir,
                    f"{case_id}:{entry_id}:{result['collection_id']}",
                )
                if request_obj != expected_request:
                    errors.append(f"{label} canonical request differs from the case source request")
            except EvidenceError as exc:
                errors.append(f"{label}: {exc}")
        diagnostic = bool(invocation.get("diagnostic"))
        if diagnostic != bool(plan_entry.get("diagnostic", True)):
            errors.append(f"{label} diagnostic flag differs from plan")
        if diagnostic and action in CONTROL_ACTIONS:
            errors.append(f"{label} control action cannot count as diagnostic evidence")

        command = invocation.get("command_argv")
        if not isinstance(command, list) or command[: len(prefix)] != prefix:
            errors.append(f"{label} command prefix mismatch")
        elif len(command) != len(prefix) + 2 or command[-2] != "--json":
            errors.append(f"{label} command must invoke KDebug as --json <request>")
        elif request_path:
            request_record = invocation.get("request") if isinstance(invocation.get("request"), dict) else {}
            recorded_rel = safe_relative_path(request_record.get("path", ""), f"{label}.request command path")
            expected_command_path = collection_root / recorded_rel if collection_root else None
            actual_command_path = Path(command[-1])
            if not actual_command_path.is_absolute():
                errors.append(f"{label} command request path is not absolute")
            elif expected_command_path and actual_command_path.resolve() != expected_command_path.resolve():
                errors.append(f"{label} command request path does not match the collection root")
            elif actual_command_path.is_file():
                if request_record.get("sha256") != sha256_file(actual_command_path):
                    errors.append(f"{label} original command request changed after collection")
            else:
                errors.append(f"{label} original command request no longer exists")

        invocation_started = int(invocation.get("started_at_epoch_ns") or 0)
        invocation_ended = int(invocation.get("ended_at_epoch_ns") or 0)
        if not (started_ns <= invocation_started <= invocation_ended):
            errors.append(f"{label} invocation timestamps are invalid")
        if invocation_ended > ended_ns:
            errors.append(f"{label} ended after the manifest collection")
        latest_invocation_end_ns = max(latest_invocation_end_ns, invocation_ended)
        exit_code = invocation.get("exit_code")
        if exit_code != 0:
            errors.append(f"{label} KDebug exit code is {exit_code}")

        response = None
        if response_path:
            try:
                response = read_json(response_path)
            except EvidenceError as exc:
                errors.append(str(exc))
        if response:
            if response.get("api_version") != "kdebug.v1":
                errors.append(f"{label} response api_version is not kdebug.v1")
            if response.get("action") != action:
                errors.append(f"{label} response action mismatch")
            if response.get("ok") is not True:
                errors.append(f"{label} response ok is not true")
            if request_obj and response.get("request_id") != request_obj.get("request_id"):
                errors.append(f"{label} response request_id mismatch")
            response_tool = response.get("tool")
            if not isinstance(response_tool, dict) or response_tool.get("name") != "kdebug" or not response_tool.get("version"):
                errors.append(f"{label} response lacks kdebug tool name/version provenance")
            else:
                observed_versions.add(str(response_tool["version"]))
            ratio, reason = response_log_similarity(response, fail_texts)
            if ratio > max_similarity or reason == "response contains a long string copied from a fail log":
                errors.append(f"{label} evidence duplicates fail log: {reason}; similarity={ratio:.3f}")
        if raw_path:
            try:
                raw_response = parse_json_response(raw_path.read_bytes())
            except EvidenceError as exc:
                errors.append(f"{label} raw stdout is not a KDebug response: {exc}")
            else:
                if response != raw_response:
                    errors.append(f"{label} parsed response differs from raw KDebug stdout")
        if bool(invocation.get("response_ok")) != bool(response and response.get("ok") is True):
            errors.append(f"{label} response_ok does not match the response")

        inputs = invocation.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            errors.append(f"{label} has no direct KDebug input fingerprints")
        else:
            expected_target_paths = {}
            if request_obj and isinstance(request_obj.get("target"), dict):
                expected_target_paths = {
                    key: str(request_obj["target"][key])
                    for key in ("fsdb", "daidir")
                    if request_obj["target"].get(key)
                }
            observed_target_paths = {
                str(item.get("target_field") or ""): str(item.get("path") or "")
                for item in inputs
                if isinstance(item, dict)
            }
            if observed_target_paths != expected_target_paths:
                errors.append(f"{label} input fingerprints do not match canonical request targets")
        if isinstance(inputs, list) and verify_inputs:
            for input_index, expected in enumerate(inputs):
                if not isinstance(expected, dict):
                    errors.append(f"{label}.inputs[{input_index}] must be an object")
                    continue
                try:
                    input_path = str(expected.get("path") or "")
                    if input_path in validation_fingerprint_cache:
                        actual = validation_fingerprint_cache[input_path]
                    else:
                        actual = fingerprint_path(Path(input_path))
                        validation_fingerprint_cache[input_path] = actual
                except EvidenceError as exc:
                    errors.append(f"{label}.inputs[{input_index}]: {exc}")
                    continue
                if not same_fingerprint(expected, actual):
                    errors.append(f"{label}.inputs[{input_index}] fingerprint mismatch")

        if exit_code == 0 and response and response.get("ok") is True:
            successful += 1
            if diagnostic and action not in CONTROL_ACTIONS:
                diagnostic_successful += 1

    if seen_ids != set(plan_entries):
        errors.append(f"manifest invocation ids do not match plan ids: manifest={sorted(seen_ids)} plan={sorted(plan_entries)}")
    if successful < min_success:
        errors.append(f"successful KDebug invocations {successful} < required {min_success}")
    if diagnostic_successful < min_diagnostic:
        errors.append(f"successful diagnostic KDebug invocations {diagnostic_successful} < required {min_diagnostic}")
    if latest_invocation_end_ns > ended_ns:
        errors.append("manifest ended before its final KDebug invocation")

    reported_versions = tool.get("reported_versions")
    if not isinstance(reported_versions, list) or sorted(str(item) for item in reported_versions) != sorted(observed_versions):
        errors.append("tool.reported_versions does not match invocation responses")

    expected_summary = {
        "invocation_count": len(invocations),
        "successful_invocations": successful,
        "successful_diagnostic_invocations": diagnostic_successful,
    }
    if manifest.get("summary") != expected_summary:
        errors.append("manifest summary does not match validated invocations")

    actual_files = {
        path.relative_to(evidence_dir).as_posix()
        for path in evidence_dir.rglob("*")
        if path.is_file()
    }
    declared_relative = set()
    prefix_text = DEFAULT_EVIDENCE_DIR.as_posix() + "/"
    for value in declared_files:
        normalized = value.replace("\\", "/")
        if normalized.startswith(prefix_text):
            declared_relative.add(normalized[len(prefix_text):])
        else:
            declared_relative.add(normalized)
    extras = sorted(actual_files - declared_relative)
    if extras:
        errors.append(f"undeclared files exist in evidence/with_kdebug: {extras}")

    expected_files = sorted(str(item) for item in ((meta.get("tool_evidence") or {}).get("expected_files") or []))
    if sorted(output_files) != expected_files:
        errors.append(f"validated response files do not match expected_files: {sorted(output_files)}")
    result["evidence_files"] = sorted(output_files)
    result["successful_invocations"] = successful
    result["successful_diagnostic_invocations"] = diagnostic_successful
    result["valid"] = not errors
    return result


def validate_case_evidence(case_dir: Path | str, verify_inputs: bool = True) -> dict:
    case_dir = Path(case_dir).resolve()
    try:
        return _validate_case_evidence(case_dir, verify_inputs=verify_inputs)
    except (EvidenceError, OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        return {
            "valid": False,
            "case_id": case_dir.name,
            "manifest": str(case_dir / DEFAULT_EVIDENCE_DIR / MANIFEST_NAME),
            "collection_id": "",
            "evidence_files": [],
            "errors": [f"manifest validation error: {exc}"],
        }


def validate_suite(suite_root: Path, case_names: list[str], verify_inputs: bool = True) -> dict:
    rows = []
    collection_ids = {}
    errors = []
    for case_name in case_names:
        result = validate_case_evidence(suite_root / case_name, verify_inputs=verify_inputs)
        rows.append(result)
        if not result["valid"]:
            errors.append(f"{case_name}: " + "; ".join(result["errors"]))
        collection_id = result.get("collection_id")
        if collection_id:
            collection_ids.setdefault(collection_id, []).append(case_name)
    for collection_id, names in collection_ids.items():
        if len(names) > 1:
            errors.append(f"collection_id reused across cases: {collection_id}: {names}")
    return {
        "valid": not errors,
        "suite_root": str(suite_root.resolve()),
        "case_count": len(case_names),
        "cases": rows,
        "errors": errors,
    }


def default_kdebug_command() -> list[str]:
    configured = os.environ.get("KDEBUG_BIN")
    if configured:
        return [configured]
    repo_root = Path(__file__).resolve().parents[3]
    return [str(repo_root / "tools" / "kdebug")]


def parse_cases(value: str, suite_root: Path) -> list[str]:
    if value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return sorted(path.name for path in suite_root.glob("case_[0-9][0-9][0-9]") if path.is_dir())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="execute KDebug requests and write a manifest")
    collect_parser.add_argument("--case-dir", type=Path, required=True)
    collect_parser.add_argument("--plan", type=Path)
    collect_parser.add_argument("--kdebug", nargs="+", default=None, metavar="COMMAND")
    collect_parser.add_argument("--force", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="validate one case manifest")
    validate_parser.add_argument("--case-dir", type=Path, required=True)
    validate_parser.add_argument("--no-input-rehash", action="store_true")

    suite_parser = subparsers.add_parser("validate-suite", help="validate all selected case manifests")
    suite_parser.add_argument("--suite-root", type=Path, required=True)
    suite_parser.add_argument("--cases", default="")
    suite_parser.add_argument("--no-input-rehash", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "collect":
            result = collect_case(
                args.case_dir,
                args.kdebug or default_kdebug_command(),
                force=args.force,
                plan_path=args.plan,
            )
        elif args.command == "validate":
            result = validate_case_evidence(args.case_dir, verify_inputs=not args.no_input_rehash)
        else:
            suite_root = args.suite_root.resolve()
            case_names = parse_cases(args.cases, suite_root)
            if not case_names:
                raise EvidenceError(f"no benchmark cases found under {suite_root}")
            result = validate_suite(suite_root, case_names, verify_inputs=not args.no_input_rehash)
    except EvidenceError as exc:
        result = {"valid": False, "errors": [str(exc)]}

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 3


if __name__ == "__main__":
    raise SystemExit(main())
