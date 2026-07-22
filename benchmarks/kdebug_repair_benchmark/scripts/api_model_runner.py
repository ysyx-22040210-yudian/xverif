#!/usr/bin/env python3
"""Run an OpenAI-compatible model in a constrained repair loop.

Benchmark v2 supports three bug domains:

* rtl: the repair must change RTL and pass the final judge.
* env: the repair must change environment/script/config files and pass the
  final judge without relying on an RTL-only workaround.
* mixed: the repair must change both RTL and environment files.

The case metadata owns the allowed repair scope.  This prevents the old
benchmark mistake where every case was judged as an RTL-only task and the
with-kdebug group could pass without any actual kdebug evidence.
"""

import argparse
import csv
import hashlib
import json
import multiprocessing
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from kdebug_evidence import validate_case_evidence


DEFAULT_BASE_URL = "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
GPT55_DEFAULT_BASE_URL = "http://165.154.147.120:8080/v1"
RETRY_LATER_EXIT_CODE = 75
API_MODEL_NAMES = {
    "gpt-5.5": "gpt-5.5",
    "glm-4.7": "xopglmv47flash",
    "qwen3.6-35b": "xopqwen36v35b",
}
MODELS = set(API_MODEL_NAMES)


class ApiHardTimeout(RuntimeError):
    pass

RTL_SUFFIXES = {".v", ".sv", ".svh", ".vh"}
ENV_SUFFIXES = {
    ".sh", ".bash", ".py", ".pl", ".tcl", ".mk", ".f", ".flist",
    ".args", ".txt", ".json", ".yaml", ".yml", ".cfg", ".ini", ".env",
    ".conf", ".list", ".log", ".sv", ".svh", ".v", ".vh",
}
TEXT_SUFFIXES = RTL_SUFFIXES | ENV_SUFFIXES | {".md", ".csv"}
DEFAULT_ENV_ROOTS = ["scripts", "env", "config", "filelists", "tb", "cases"]
READONLY_DESIGN_ROOTS = ["docs", "design_docs", "design_refs", "spec"]
MAX_DESIGN_REF_FILES = 20
DEFAULT_ALLOWED_FILES = [
    "Makefile",
    "makefile",
    "filelist.f",
    "vcs_args.f",
    "run_args.txt",
]
DEFAULT_FORBIDDEN_ROOTS = ["fail", "evidence", "agent_logs", ".git"]
DEFAULT_FORBIDDEN_FILES = [
    "answer_key_private.json",
    "scripts/judge.sh",
    "case_meta.json",
]
MAX_CONTEXT_CHARS = 64000
MAX_FILE_CHARS = 12000
MAX_API_PAYLOAD_CHARS = int(os.environ.get("KDEBUG_MAX_API_PAYLOAD_CHARS", "650000"))
MAX_API_MESSAGE_CHARS = int(os.environ.get("KDEBUG_MAX_API_MESSAGE_CHARS", "500000"))
MAX_HISTORY_MESSAGES = int(os.environ.get("KDEBUG_MAX_HISTORY_MESSAGES", "6"))

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


def utc_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_text(path, limit=None):
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    if limit and len(text) > limit:
        head = limit // 2
        tail = limit - head
        return text[:head] + "\n...[truncated]...\n" + text[-tail:]
    return text


def truncate_middle(text, limit, marker="\n...[truncated for API payload budget]...\n"):
    text = str(text)
    if limit <= 0 or len(text) <= limit:
        return text
    if limit <= len(marker) + 20:
        return text[:limit]
    head = (limit - len(marker)) // 2
    tail = limit - len(marker) - head
    return text[:head] + marker + text[-tail:]


def messages_char_count(messages):
    return sum(len(str(m.get("content", ""))) + len(str(m.get("role", ""))) + 32 for m in messages)


def compact_message(message, limit):
    content = truncate_middle(message.get("content", ""), limit)
    return {"role": message.get("role", "user"), "content": content}


def compress_messages_for_api(messages, model_name=""):
    """Keep API payloads below provider limits while preserving repair feedback.

    The transcript and command log remain complete on disk.  This only compacts
    the request body sent to providers with strict message-size limits.
    """
    if not messages:
        return messages

    system = messages[0]
    current = messages[-1]
    history = messages[1:-1]
    max_payload = max(40000, MAX_API_PAYLOAD_CHARS)
    max_current = max(20000, min(MAX_API_MESSAGE_CHARS, max_payload - 20000))

    compressed = [compact_message(system, 12000)]
    if history:
        recent = history[-max(0, MAX_HISTORY_MESSAGES):]
        dropped = max(0, len(history) - len(recent))
        if dropped:
            compressed.append({
                "role": "user",
                "content": (
                    f"[history compacted] {dropped} older repair-loop messages were omitted "
                    "from this API request to stay within provider payload limits. The latest "
                    "case context below contains current build/run/judge logs and repair-scope files."
                ),
            })
        per_history = max(1000, min(12000, (max_payload - max_current - 16000) // max(1, len(recent))))
        compressed.extend(compact_message(m, per_history) for m in recent)

    compressed.append(compact_message(current, max_current))

    while messages_char_count(compressed) > max_payload and len(compressed) > 2:
        del compressed[1]
    if messages_char_count(compressed) > max_payload:
        compressed[-1] = compact_message(compressed[-1], max(20000, max_payload - messages_char_count(compressed[:-1]) - 2000))
    return compressed


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def truthy(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_case_meta(repair):
    meta_path = repair / "case_meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def normalize_rel(raw):
    raw = str(raw).strip()
    raw = raw.split("\t", 1)[0]
    raw = re.sub(r"^[ab]/", "", raw)
    raw = raw.replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def rel_parts(rel):
    return Path(str(rel).replace("\\", "/")).parts


def scope_from_meta(meta):
    scope = meta.get("repair_scope") or {}
    bug_domain = (meta.get("bug_domain") or "rtl").strip().lower()

    if isinstance(scope, str):
        allowed_roots = [p for p in scope.split(";") if p]
        allowed_files = list(DEFAULT_ALLOWED_FILES)
        forbidden_roots = list(DEFAULT_FORBIDDEN_ROOTS)
        forbidden_files = list(DEFAULT_FORBIDDEN_FILES)
        requires_rtl = "rtl" in allowed_roots and bug_domain in {"rtl", "mixed"}
        requires_env = any(p != "rtl" for p in allowed_roots) and bug_domain in {"env", "mixed"}
    else:
        allowed_roots = list(scope.get("allowed_roots") or [])
        if "allowed_files" in scope:
            allowed_files = list(scope.get("allowed_files") or [])
        else:
            allowed_files = list(DEFAULT_ALLOWED_FILES)
        forbidden_roots = list(scope.get("forbidden_roots") or DEFAULT_FORBIDDEN_ROOTS)
        forbidden_files = list(scope.get("forbidden_files") or DEFAULT_FORBIDDEN_FILES)
        requires_rtl = truthy(scope.get("requires_rtl_change"), bug_domain in {"rtl", "mixed"})
        requires_env = truthy(scope.get("requires_env_change"), bug_domain in {"env", "mixed"})

    if not allowed_roots:
        if bug_domain == "env":
            allowed_roots = list(DEFAULT_ENV_ROOTS)
        elif bug_domain == "mixed":
            allowed_roots = ["rtl"] + list(DEFAULT_ENV_ROOTS)
        else:
            allowed_roots = ["rtl"]

    normalized = {
        "allowed_roots": sorted({normalize_rel(p).strip("/") for p in allowed_roots if p}),
        "allowed_files": sorted({normalize_rel(p) for p in allowed_files if p}),
        "forbidden_roots": sorted({normalize_rel(p).strip("/") for p in forbidden_roots if p}),
        "forbidden_files": sorted({normalize_rel(p) for p in forbidden_files if p}),
        "requires_rtl_change": requires_rtl,
        "requires_env_change": requires_env,
        "bug_domain": bug_domain,
    }
    return normalized


def scope_string(scope):
    return ";".join(scope["allowed_roots"] + scope["allowed_files"])


def is_forbidden_rel(rel, scope):
    rel = normalize_rel(rel)
    parts = rel_parts(rel)
    if not parts:
        return True
    if rel in scope["forbidden_files"]:
        return True
    if Path(rel).name == "answer_key_private.json":
        return True
    return parts[0] in scope["forbidden_roots"]


def is_rtl_rel(rel):
    parts = rel_parts(rel)
    return bool(parts) and parts[0] == "rtl"


def is_env_rel(rel):
    parts = rel_parts(rel)
    return bool(parts) and parts[0] != "rtl"


def ensure_allowed_rel(rel, scope):
    rel = normalize_rel(rel)
    if rel == "/dev/null":
        return rel
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError(f"unsafe patch path: {rel}")
    if is_forbidden_rel(rel, scope):
        raise ValueError(f"patch path is protected or forbidden: {rel}")

    root = p.parts[0]
    allowed_by_root = root in scope["allowed_roots"]
    allowed_by_file = rel in scope["allowed_files"] or p.name in scope["allowed_files"]
    if not allowed_by_root and not allowed_by_file:
        raise ValueError(f"patch path is outside repair scope: {rel}")

    suffix = p.suffix.lower()
    if root == "rtl":
        if suffix and suffix not in RTL_SUFFIXES:
            raise ValueError(f"RTL patch suffix is not allowed: {rel}")
        if not suffix:
            raise ValueError(f"RTL patch path must be an RTL file: {rel}")
    else:
        if suffix and suffix not in ENV_SUFFIXES:
            raise ValueError(f"environment patch suffix is not allowed: {rel}")
        if not suffix and not allowed_by_file:
            raise ValueError(f"environment patch path without suffix is not explicitly allowed: {rel}")
    return rel


def allowed_file_candidates(repair, scope):
    roots = [repair / root for root in scope["allowed_roots"]]
    for root in roots:
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                rel = normalize_rel(path.relative_to(repair))
                try:
                    ensure_allowed_rel(rel, scope)
                except ValueError:
                    continue
                yield rel
    for rel in scope["allowed_files"]:
        path = repair / rel
        if path.is_file():
            try:
                ensure_allowed_rel(rel, scope)
            except ValueError:
                continue
            yield normalize_rel(rel)


def resolve_patch_rel(raw, repair, scope):
    rel = normalize_rel(raw)
    try:
        return ensure_allowed_rel(rel, scope)
    except ValueError as first_error:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            raise first_error
        matches = [
            candidate for candidate in sorted(set(allowed_file_candidates(repair, scope)))
            if Path(candidate).name == p.name
        ]
        if len(matches) == 1:
            return ensure_allowed_rel(matches[0], scope)
        raise first_error


def selected_visible_files(repair, scope, include_files):
    selected = []
    if include_files:
        for rel in include_files:
            try:
                selected.append(ensure_allowed_rel(rel, scope))
            except ValueError:
                pass
        return selected[:12]

    candidates = sorted(set(allowed_file_candidates(repair, scope)))
    env_first = [rel for rel in candidates if is_env_rel(rel)]
    rtl_first = [rel for rel in candidates if is_rtl_rel(rel)]
    selected.extend(env_first[:8])
    selected.extend(rtl_first[:8])
    return selected[:16]


def list_evidence_files(repair, group, meta):
    if group != "with_kdebug":
        return False, False, []
    tool = meta.get("tool_evidence") or {}
    required = truthy(tool.get("required_for_with_kdebug"), True)
    expected = [str(x) for x in (tool.get("expected_files") or [])]
    min_files = int(tool.get("minimum_nonempty_files") or 1)
    evidence_dir = repair / "evidence" / "with_kdebug"
    found = []
    if evidence_dir.exists():
        for path in sorted(evidence_dir.rglob("*")):
            if not path.is_file() or path.stat().st_size <= 0:
                continue
            rel = normalize_rel(path.relative_to(evidence_dir))
            if "answer_key_private" in rel:
                continue
            if expected:
                if rel in expected or Path(rel).name in expected:
                    found.append(rel)
            else:
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
    return required, present, found


def is_private_reference(path):
    text = str(path).replace("\\", "/").lower()
    blocked = [
        "answer_key",
        "answer-key",
        "private",
        "fault_injection",
        "injection_detail",
        "operator_only",
    ]
    return any(token in text for token in blocked)


def design_ref_candidates_from_meta(meta):
    explicit = meta.get("public_design_refs")
    if isinstance(explicit, list):
        return [normalize_rel(x) for x in explicit if str(x).strip()]
    if isinstance(explicit, dict):
        refs = []
        for value in explicit.values():
            if isinstance(value, list):
                refs.extend(normalize_rel(x) for x in value if str(x).strip())
        if refs:
            return refs

    benchmark_layer = normalize_rel(meta.get("benchmark_layer") or meta.get("layer") or "")
    level = normalize_rel(meta.get("level") or "").lower()
    subsystem = normalize_rel(meta.get("subsystem") or "").lower()
    candidates = []
    for root in READONLY_DESIGN_ROOTS:
        candidates.extend([
            f"{root}/common",
            f"{root}/{benchmark_layer}",
            f"{root}/{level}",
        ])
        if benchmark_layer and subsystem:
            candidates.append(f"{root}/{benchmark_layer}/{subsystem}")
        if level and subsystem:
            candidates.append(f"{root}/{level}/{subsystem}")
        if subsystem:
            candidates.append(f"{root}/{subsystem}")
    seen = []
    for rel in candidates:
        rel = rel.strip("/")
        if rel and rel not in seen:
            seen.append(rel)
    return seen


def collect_design_references(repair, meta):
    docs = []
    for rel in design_ref_candidates_from_meta(meta):
        if len(docs) >= MAX_DESIGN_REF_FILES:
            return docs
        p = repair / rel
        try:
            resolved = p.resolve().relative_to(repair.resolve())
        except ValueError:
            continue
        if is_private_reference(resolved):
            continue
        if p.is_file():
            if p.suffix.lower() in TEXT_SUFFIXES and not is_private_reference(p):
                docs.append(p)
            continue
        if p.is_dir():
            for path in sorted(p.rglob("*")):
                if len(docs) >= MAX_DESIGN_REF_FILES:
                    return docs
                if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                if is_private_reference(path):
                    continue
                docs.append(path)
    return docs


def public_meta_for_prompt(meta, scope):
    """Return model-visible metadata without private or answer-shaped labels."""
    return {
        "case_id": meta.get("case_id", ""),
        "benchmark_layer": meta.get("benchmark_layer") or meta.get("layer", ""),
        "layer": meta.get("layer", ""),
        "level": meta.get("level", ""),
        "subsystem": meta.get("subsystem", ""),
        "target_flow": meta.get("target_flow", ""),
        "fail_workload_or_case": meta.get("fail_workload_or_case", ""),
        "timeout_sec": meta.get("timeout_sec", ""),
        "bug_domain": meta.get("bug_domain", scope["bug_domain"]),
        "repair_requirements": {
            "requires_rtl_change": scope["requires_rtl_change"],
            "requires_env_change": scope["requires_env_change"],
            "allowed_roots": scope["allowed_roots"],
            "allowed_files": scope["allowed_files"],
            "protected_roots": scope["forbidden_roots"],
            "protected_files": scope["forbidden_files"],
        },
        "commands": {
            "build": meta.get("build_command") or "scripts/build.sh",
            "run": meta.get("fail_command") or meta.get("run_command") or "scripts/run.sh",
            "judge": meta.get("judge_command") or "scripts/judge.sh",
        },
        "read_only_design_reference_roots": READONLY_DESIGN_ROOTS,
        "public_design_refs": design_ref_candidates_from_meta(meta),
    }


def collect_context(repair_dir, group, include_files, scope, meta):
    repair = Path(repair_dir)
    parts = [
        f"REPAIR_DIR={repair}",
        f"GROUP={group}",
        "The private answer key is forbidden. Do not request or infer access to it.",
        "Final success is decided only by the benchmark harness after build/run/judge.",
        "\n--- public case metadata ---\n"
        + json.dumps(public_meta_for_prompt(meta, scope), ensure_ascii=False, indent=2),
    ]
    for rel in [
        "fail/build.log",
        "fail/run.log",
        "fail/run.rc",
        "agent_logs/latest_build.log",
        "agent_logs/latest_run.log",
        "agent_logs/latest_judge.log",
    ]:
        p = repair / rel
        if p.exists():
            parts.append(f"\n--- {rel} ---\n{read_text(p, 10000)}")

    evidence_dir = repair / "evidence" / group
    if group == "with_kdebug" and evidence_dir.exists():
        parts.append(f"\n--- public evidence/{group} ---")
        _, _, evidence_files = list_evidence_files(repair, group, meta)
        validation = validate_case_evidence(repair, verify_inputs=False)
        parts.append(
            "Validated KDebug collection_id="
            + str(validation.get("collection_id", ""))
        )
        for evidence_file in evidence_files:
            p = evidence_dir / evidence_file
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
                rel = p.relative_to(repair)
                parts.append(f"\n--- {rel} ---\n{read_text(p, 8000)}")

    design_docs = collect_design_references(repair, meta)
    if design_docs:
        parts.append("\n--- read-only public RTL design references ---")
        for p in design_docs:
            rel = p.relative_to(repair)
            parts.append(f"\n--- {rel} (read-only) ---\n{read_text(p, 10000)}")

    parts.append("\n--- case-local commands ---")
    for rel in ["scripts/build.sh", "scripts/run.sh", "scripts/judge.sh"]:
        p = repair / rel
        if p.exists():
            protected = " (protected: do not patch)" if normalize_rel(rel) in scope["forbidden_files"] else ""
            parts.append(f"\n--- {rel}{protected} ---\n{read_text(p, 6000)}")

    visible = sorted(set(allowed_file_candidates(repair, scope)))
    parts.append("\n--- repair-scope files visible ---")
    parts.extend(visible[:160])

    for rel in selected_visible_files(repair, scope, include_files):
        p = repair / rel
        if p.exists() and p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            parts.append(f"\n--- {rel} ---\n{read_text(p, MAX_FILE_CHARS)}")

    context = "\n".join(parts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = (
            context[: MAX_CONTEXT_CHARS // 2]
            + "\n...[context truncated]...\n"
            + context[-MAX_CONTEXT_CHARS // 2 :]
        )
    return context


def _api_chat_once_direct(base_url, api_key, model, messages, timeout):
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.1,
    }).encode("utf-8")
    req = request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                ctype = resp.headers.get("content-type", "")
                raise RuntimeError(
                    f"API returned non-JSON response: content_type={ctype}; body={body[:300]!r}"
                ) from exc
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {body}") from exc


def _api_chat_once_worker(queue, base_url, api_key, model, messages, timeout):
    try:
        queue.put(("ok", _api_chat_once_direct(base_url, api_key, model, messages, timeout)))
    except BaseException as exc:
        queue.put(("err", f"{type(exc).__name__}: {exc}"))


def api_chat_once(base_url, api_key, model, messages, timeout):
    use_process_timeout = str(os.environ.get("KDEBUG_API_PROCESS_TIMEOUT", "1")).lower() not in {"0", "false", "no"}
    if use_process_timeout and "fork" in multiprocessing.get_all_start_methods():
        ctx = multiprocessing.get_context("fork")
        queue = ctx.Queue(maxsize=1)
        proc = ctx.Process(
            target=_api_chat_once_worker,
            args=(queue, base_url, api_key, model, messages, timeout),
        )
        proc.daemon = True
        proc.start()
        proc.join(max(1, int(timeout)))
        if proc.is_alive():
            proc.terminate()
            proc.join(5)
            if proc.is_alive() and hasattr(proc, "kill"):
                proc.kill()
                proc.join(5)
            raise RuntimeError(f"API call timed out after {timeout}s")
        if queue.empty():
            raise RuntimeError(f"API worker exited without response: exitcode={proc.exitcode}")
        status, payload = queue.get()
        if status == "ok":
            return payload
        raise RuntimeError(f"API worker error: {payload}")
    return _api_chat_once_direct(base_url, api_key, model, messages, timeout)


def is_retryable_api_error(exc):
    text = str(exc).lower()
    return (
        "api http 429" in text
        or "api http 500" in text
        or "api http 502" in text
        or "api http 503" in text
        or "api http 504" in text
        or "timed out" in text
        or "temporarily unavailable" in text
        or "connection reset" in text
        or "api call timed out" in text
    )


def is_rate_limit_api_error(exc):
    text = str(exc).lower()
    return (
        "api http 429" in text
        or "rate limit" in text
        or "ratelimit" in text
        or "too many requests" in text
        or "quota" in text
        or "throttle" in text
        or "temporarily unavailable" in text
    )


def api_chat(base_url, api_key, model, messages, timeout, retries=None):
    if retries is None:
        retries = int(os.environ.get("KDEBUG_API_RETRIES", "0"))
    last_exc = None
    deadline = time.time() + max(1, int(timeout))
    attempt = 0
    while True:
        remaining = int(deadline - time.time())
        if remaining <= 0:
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("API retry budget exhausted")
        per_try_timeout = max(30, min(remaining, int(os.environ.get("KDEBUG_API_PER_TRY_TIMEOUT_SEC", "300"))))
        try:
            return api_chat_once(base_url, api_key, model, messages, per_try_timeout)
        except Exception as exc:
            last_exc = exc
            if not is_retryable_api_error(exc):
                raise
            if retries is not None and attempt >= retries:
                raise
            sleep_sec = min(60, 5 * (2 ** min(attempt, 5)))
            if time.time() + sleep_sec >= deadline:
                raise
            time.sleep(sleep_sec)
            attempt += 1


def extract_diff_blocks(text):
    fence_pattern = re.compile(r"(?ms)^```\s*([A-Za-z0-9_-]*)[^\n]*\n(.*?)^```\s*$")
    fenced = [(lang.lower(), body) for lang, body in fence_pattern.findall(text)]
    blocks = [body for lang, body in fenced if lang in {"diff", "patch"}]
    if blocks:
        return "\n".join(block.strip() for block in blocks if block.strip()) + "\n"

    def looks_like_unified_diff(candidate):
        return (
            re.search(r"(?m)^---\s+\S+", candidate)
            and re.search(r"(?m)^\+\+\+\s+\S+", candidate)
            and re.search(r"(?m)^@@", candidate)
        )

    blocks = [body for _lang, body in fenced if looks_like_unified_diff(body)]
    if blocks:
        return "\n".join(block.strip() for block in blocks if block.strip()) + "\n"
    if looks_like_unified_diff(text):
        return text.strip() + "\n"
    return ""


def rewrite_patch_token(token, repair, scope, side):
    norm = normalize_rel(token)
    if norm == "/dev/null":
        return "/dev/null"
    rel = resolve_patch_rel(norm, repair, scope)
    prefix = "a/" if side == "old" else "b/"
    return prefix + rel


def rewrite_header_path(line, repair, scope, side):
    prefix = line[:4]
    rest = line[4:].strip()
    match = re.match(r"(\S+)(.*)$", rest)
    if not match:
        return line
    path_token, suffix = match.groups()
    return prefix + rewrite_patch_token(path_token, repair, scope, side) + suffix


def canonicalize_diff_paths(diff_text, repair, scope):
    rewritten = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                parts[2] = rewrite_patch_token(parts[2], repair, scope, "old")
                parts[3] = rewrite_patch_token(parts[3], repair, scope, "new")
                line = " ".join(parts)
        elif line.startswith("--- "):
            line = rewrite_header_path(line, repair, scope, "old")
        elif line.startswith("+++ "):
            line = rewrite_header_path(line, repair, scope, "new")
        rewritten.append(line)
    return "\n".join(rewritten).rstrip() + "\n"


def validate_patch_paths(diff_text, scope):
    paths = []
    for line in diff_text.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            raw = line[4:].strip()
            norm = normalize_rel(raw)
            if norm == "/dev/null":
                continue
            paths.append(ensure_allowed_rel(norm, scope))
    if not paths:
        raise ValueError("no file paths found in unified diff")
    return sorted(set(paths))


def parse_hunk_start(header):
    match = re.match(r"@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", header)
    if not match:
        return 0
    return int(match.group(1))


def header_rel(line):
    raw = line[4:].strip()
    token = raw.split(None, 1)[0] if raw else ""
    return normalize_rel(token)


def parse_tolerant_diff(diff_text, scope):
    files = []
    old_rel = None
    new_rel = None
    hunks = []
    current = None

    def finish_file():
        nonlocal old_rel, new_rel, hunks, current
        current = None
        if old_rel is None and new_rel is None:
            return
        if old_rel == "/dev/null" or new_rel == "/dev/null":
            raise ValueError("tolerant patch does not support file create/delete")
        if not old_rel or not new_rel:
            raise ValueError("incomplete unified diff file header")
        if old_rel != new_rel:
            raise ValueError(f"tolerant patch does not support rename: {old_rel} -> {new_rel}")
        ensure_allowed_rel(old_rel, scope)
        if not hunks:
            raise ValueError(f"no hunks found for {old_rel}")
        files.append({"rel": old_rel, "hunks": hunks})
        old_rel = None
        new_rel = None
        hunks = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            continue
        if line.startswith("--- "):
            finish_file()
            old_rel = header_rel(line)
            continue
        if line.startswith("+++ "):
            if old_rel is None:
                raise ValueError("+++ header appeared before --- header")
            new_rel = header_rel(line)
            continue
        if line.startswith("@@"):
            if old_rel is None or new_rel is None:
                raise ValueError("hunk appeared before file headers")
            current = {"header": line, "old_start": parse_hunk_start(line), "lines": []}
            hunks.append(current)
            continue
        if current is not None:
            if line.startswith((" ", "+", "-", "\\")):
                current["lines"].append(line)
                continue
            raise ValueError(f"malformed hunk line without diff prefix: {line[:80]}")

    finish_file()
    if not files:
        raise ValueError("no file hunks found in unified diff")
    return files


def hunk_old_new_lines(hunk):
    old_lines = []
    new_lines = []
    has_change = False
    for line in hunk["lines"]:
        if line.startswith("\\"):
            continue
        prefix = line[:1]
        value = line[1:]
        if prefix == " ":
            old_lines.append(value)
            new_lines.append(value)
        elif prefix == "-":
            old_lines.append(value)
            has_change = True
        elif prefix == "+":
            new_lines.append(value)
            has_change = True
        else:
            raise ValueError(f"unsupported hunk line prefix: {prefix!r}")
    if not has_change:
        raise ValueError("hunk has no changed lines")
    if not old_lines:
        raise ValueError("tolerant patch requires old context lines")
    return old_lines, new_lines


def find_line_block(lines, needle):
    if not needle or len(needle) > len(lines):
        return []
    width = len(needle)
    return [idx for idx in range(0, len(lines) - width + 1) if lines[idx:idx + width] == needle]


def context_equal(actual, expected):
    if len(actual) != len(expected):
        return False
    if actual == expected:
        return True
    return [line.strip() for line in actual] == [line.strip() for line in expected]


def choose_match(candidates, expected):
    if len(candidates) == 1:
        return candidates[0]
    distances = [(abs(idx - expected), idx) for idx in candidates]
    distances.sort()
    if len(distances) >= 2 and distances[0][0] == distances[1][0]:
        raise ValueError(f"hunk context is not unique; candidates={candidates[:8]}")
    return distances[0][1]


def single_edit_group(hunk):
    before = []
    after = []
    group = []
    seen_group = False
    closed = False
    for line in hunk["lines"]:
        if line.startswith("\\"):
            continue
        prefix = line[:1]
        value = line[1:]
        if prefix in {"-", "+"}:
            if closed:
                raise ValueError("tolerant single-edit fallback supports only one edit group per hunk")
            seen_group = True
            group.append(line)
        elif prefix == " ":
            if seen_group:
                closed = True
                after.append(value)
            else:
                before.append(value)
        else:
            raise ValueError(f"unsupported hunk line prefix: {prefix!r}")
    old = [line[1:] for line in group if line.startswith("-")]
    new = [line[1:] for line in group if line.startswith("+")]
    return before, old, new, after


def context_candidates(lines, before, after):
    positions = []
    max_pos = len(lines)
    for pos in range(max_pos + 1):
        before_ok = True
        after_ok = True
        if before:
            before_ok = pos >= len(before) and context_equal(lines[pos - len(before):pos], before)
        if after:
            after_ok = pos + len(after) <= len(lines) and context_equal(lines[pos:pos + len(after)], after)
        if before_ok and after_ok:
            positions.append(pos)
    return positions


def apply_hunk_by_single_edit(lines, hunk, rel):
    before, old_lines, new_lines, after = single_edit_group(hunk)
    if old_lines:
        candidates = find_line_block(lines, old_lines)
        if not candidates:
            raise ValueError(f"edit block not found in {rel}: {hunk['header']}")
    else:
        candidates = context_candidates(lines, before, after)
        if not candidates:
            raise ValueError(f"insert context not found in {rel}: {hunk['header']}")
    valid = []
    for idx in candidates:
        before_ok = True
        after_ok = True
        if before:
            before_ok = idx >= len(before) and context_equal(lines[idx - len(before):idx], before)
        if after:
            start = idx + len(old_lines)
            after_ok = start + len(after) <= len(lines) and context_equal(lines[start:start + len(after)], after)
        if before_ok and after_ok:
            valid.append(idx)
    if not valid and len(candidates) == 1:
        valid = candidates
    if not valid:
        raise ValueError(f"edit block context mismatch in {rel}: {hunk['header']}")
    idx = choose_match(valid, max(0, hunk.get("old_start", 1) - 1))
    lines[idx:idx + len(old_lines)] = new_lines
    return len(new_lines) - len(old_lines)


def apply_patch_tolerant(diff_text, repair, scope):
    parsed = parse_tolerant_diff(diff_text, scope)
    originals = {}
    changed = []
    try:
        for file_patch in parsed:
            rel = file_patch["rel"]
            path = repair / rel
            if not path.is_file():
                raise ValueError(f"patch target is not a file: {rel}")
            original = path.read_text(encoding="utf-8", errors="replace")
            originals[rel] = original
            final_newline = original.endswith("\n")
            lines = original.splitlines()
            offset = 0
            for hunk in file_patch["hunks"]:
                old_lines, new_lines = hunk_old_new_lines(hunk)
                candidates = find_line_block(lines, old_lines)
                expected = max(0, hunk.get("old_start", 1) - 1 + offset)
                if candidates:
                    idx = choose_match(candidates, expected)
                    lines[idx:idx + len(old_lines)] = new_lines
                    offset += len(new_lines) - len(old_lines)
                else:
                    offset += apply_hunk_by_single_edit(lines, hunk, rel)
            new_text = "\n".join(lines)
            if final_newline:
                new_text += "\n"
            if new_text != original:
                path.write_text(new_text, encoding="utf-8")
                changed.append(rel)
    except Exception:
        for rel, text in originals.items():
            (repair / rel).write_text(text, encoding="utf-8")
        raise
    if not changed:
        raise ValueError("tolerant patch made no changes")
    return changed


def apply_patch_with_git(diff_text, repair, scope, log_path):
    diff_text = canonicalize_diff_paths(diff_text, repair, scope)
    validate_patch_paths(diff_text, scope)
    patch_path = Path(log_path).with_suffix(".patch")
    patch_path.write_text(diff_text, encoding="utf-8")
    with open(log_path, "ab") as log:
        log.write(b"\n===== APPLY PATCH =====\n")
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(patch_path)],
            cwd=repair,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        if proc.returncode != 0:
            log.write(b"\n===== TOLERANT PATCH APPLY =====\n")
            try:
                changed = apply_patch_tolerant(diff_text, repair, scope)
            except Exception as exc:
                log.write(f"fallback failed: {exc}\n".encode("utf-8", errors="replace"))
            else:
                log.write(
                    ("fallback applied changed files: " + ";".join(changed) + "\n").encode(
                        "utf-8", errors="replace"
                    )
                )
                return 0, str(patch_path)
    return proc.returncode, str(patch_path)


def record_invalid_patch(diff_text, log_dir, log_path, model, iteration, error_text):
    patch_path = Path(log_dir) / f"{model}_invalid_patch_iter{iteration}.patch"
    patch_path.write_text(diff_text, encoding="utf-8")
    with open(log_path, "ab") as log:
        log.write(b"\n===== INVALID PATCH =====\n")
        log.write(str(patch_path).encode("utf-8", errors="replace") + b"\n")
        log.write(str(error_text).encode("utf-8", errors="replace") + b"\n")
    return str(patch_path)


def run_cmd(cmd, cwd, log_path, timeout, title):
    start = time.time()
    latest_path = Path(cwd) / "agent_logs" / f"latest_{title}.log"
    with open(log_path, "ab") as log, open(latest_path, "wb") as latest:
        banner = f"\n===== {title.upper()} {utc_now()} :: {cmd} =====\n".encode("utf-8")
        log.write(banner)
        latest.write(banner)
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            out, _ = proc.communicate(timeout=max(1, int(timeout)))
            log.write(out)
            latest.write(out)
            rc = proc.returncode
        except subprocess.TimeoutExpired as exc:
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    out, _ = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    out, _ = proc.communicate()
            else:
                out = exc.stdout or b""
            msg = f"\nTIMEOUT after {timeout}s\n".encode("utf-8")
            log.write(out + msg)
            latest.write(out + msg)
            rc = 124
    return rc, time.time() - start


def snapshot_allowed_files(repair, scope):
    snap = {}
    for rel in sorted(set(allowed_file_candidates(repair, scope))):
        path = repair / rel
        if path.is_file():
            snap[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


def changed_files(repair, scope, baseline):
    current = snapshot_allowed_files(repair, scope)
    changed = sorted(rel for rel, digest in current.items() if baseline.get(rel) != digest)
    deleted = sorted(rel for rel in baseline if rel not in current)
    return changed + deleted


def parse_requested_files(answer, scope):
    files = []
    path_re = r"[A-Za-z0-9_./\\-]+\.(?:sv|svh|v|vh|sh|py|tcl|mk|f|args|txt|json|yaml|yml|cfg|ini|env|md|csv)"
    patterns = [
        rf"(?i)(?:need|read|open|include|inspect)\s+({path_re})",
        rf"`({path_re})`",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, answer):
            try:
                files.append(ensure_allowed_rel(match, scope))
            except ValueError:
                pass
    seen = []
    for rel in files:
        if rel not in seen:
            seen.append(rel)
    return seen[:12]


def token_usage(response):
    usage = response.get("usage") or {}
    return {
        "token_input": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "token_output": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        "token_total": int(usage.get("total_tokens") or 0),
        "token_is_estimate": False if usage else True,
    }


def default_base_url(model):
    if model == "gpt-5.5":
        return (
            os.environ.get("GPT55_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or GPT55_DEFAULT_BASE_URL
        )
    return os.environ.get("MAAS_BASE_URL") or os.environ.get("AIAPI_BASE_URL") or DEFAULT_BASE_URL


def normalize_base_url(model, base_url):
    base = (base_url or "").rstrip("/")
    if model == "gpt-5.5" and re.fullmatch(r"https?://[^/]+:8080", base):
        return base + "/v1"
    return base


def default_api_key_env(model):
    if model == "gpt-5.5":
        return "GPT55_API_KEY"
    return "MAAS_API_KEY"


def resolve_api_key(primary_env, model):
    candidates = []
    fallback = ["MAAS_API_KEY", "AIAPI_API_KEY"]
    if model == "gpt-5.5":
        fallback = ["GPT55_API_KEY", "OPENAI_API_KEY", "MAAS_API_KEY", "AIAPI_API_KEY"]
    for name in [primary_env] + fallback:
        if name and name not in candidates:
            candidates.append(name)
    for name in candidates:
        value = os.environ.get(name)
        if value:
            return value, name
    raise KeyError(" or ".join(candidates))


def repair_class(rtl_changed, env_changed):
    if rtl_changed and env_changed:
        return "mixed"
    if rtl_changed:
        return "rtl_only"
    if env_changed:
        return "env_only"
    return "no_effective_patch"


def classify_failure(status, build_rc, run_rc, judge_rc, rule_violation):
    if status == "PASS":
        return ""
    if status == "RETRY_LATER":
        return "api_rate_limited"
    if status == "TIMEOUT":
        return "timeout"
    if status == "TOOL_EVIDENCE_MISSING":
        return "evidence_missing"
    if status == "TOOL_EVIDENCE_INVALID":
        return "evidence_invalid"
    if status == "RULE_VIOLATION":
        return "rule_violation"
    if status == "INFRA_ERROR":
        return "infrastructure_error"
    if rule_violation:
        if "api_rate_limited" in rule_violation:
            return "api_rate_limited"
        if "api_error" in rule_violation:
            return "infrastructure_error"
        if "invalid_patch" in rule_violation:
            return "invalid_patch"
        if "no_patch" in rule_violation:
            return "no_patch"
    if build_rc not in (0, "0"):
        return "build_fail"
    if run_rc not in (0, "0"):
        return "run_fail"
    if judge_rc not in (0, "0"):
        return "judge_fail"
    return "unknown_fail"


def append_trial_csv(path, row):
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in FIELDS})


def make_metrics(
    args, meta, scope, start_time, start_wall, token_in=0, token_out=0,
    token_total=0, token_is_estimate=True, locate_sec=0.0, edit_sec=0.0,
    build_sec=0.0, run_sec=0.0, judge_sec=0.0, iterations=0,
    final_build_rc=1, final_run_rc=1, final_judge_rc=1, final_status="TIMEOUT",
    rule_violation="", pass_marker="", evidence_files=None, modified=None,
    notes="", evidence_validation=None,
):
    evidence_files = evidence_files or []
    modified = modified or []
    rtl_files = sorted(rel for rel in modified if is_rtl_rel(rel))
    env_files = sorted(rel for rel in modified if is_env_rel(rel))
    required, present, _ = list_evidence_files(Path(args.repair_dir), args.group, meta)
    if evidence_validation is None and args.group == "with_kdebug" and present:
        evidence_validation = validate_case_evidence(Path(args.repair_dir), verify_inputs=True)
    evidence_validation = evidence_validation or {}
    evidence_valid = bool(evidence_validation.get("valid")) if args.group == "with_kdebug" else False
    manifest_path = evidence_validation.get("manifest", "") if args.group == "with_kdebug" else ""
    if manifest_path:
        try:
            manifest_path = normalize_rel(Path(manifest_path).resolve().relative_to(Path(args.repair_dir).resolve()))
        except ValueError:
            manifest_path = str(manifest_path)
    design_refs = [
        normalize_rel(path.relative_to(Path(args.repair_dir)))
        for path in collect_design_references(Path(args.repair_dir), meta)
    ]
    elapsed = time.time() - start_wall
    repair_kind = repair_class(bool(rtl_files), bool(env_files))
    failure = classify_failure(final_status, final_build_rc, final_run_rc, final_judge_rc, rule_violation)
    return {
        "suite": meta.get("suite", "xiangshan_repair_benchmark_v2"),
        "model_id": args.model,
        "case_id": meta.get("case_id", Path(args.repair_dir).name),
        "group": args.group,
        "benchmark_layer": meta.get("benchmark_layer") or meta.get("layer", ""),
        "layer": meta.get("layer", ""),
        "level": meta.get("level", ""),
        "subsystem": meta.get("subsystem", ""),
        "bug_domain": meta.get("bug_domain", scope["bug_domain"]),
        "bug_class": meta.get("bug_class", ""),
        "env_fault_class": meta.get("env_fault_class", ""),
        "target_flow": meta.get("target_flow", ""),
        "repair_scope": scope_string(scope),
        "requires_rtl_change": scope["requires_rtl_change"],
        "requires_env_change": scope["requires_env_change"],
        "tool_evidence_required": required,
        "tool_evidence_present": present,
        "tool_evidence_valid": evidence_valid,
        "tool_evidence_files": ";".join(evidence_files),
        "tool_evidence_manifest": manifest_path,
        "tool_evidence_collection_id": evidence_validation.get("collection_id", ""),
        "tool_evidence_validation": (
            "valid" if evidence_valid else "; ".join(evidence_validation.get("errors") or [])
        ) if args.group == "with_kdebug" else "not_required",
        "public_design_refs": ";".join(design_refs),
        "timeout_sec": args.timeout,
        "start_time": start_time,
        "end_time": utc_now(),
        "elapsed_sec": round(elapsed, 3),
        "locate_sec": round(locate_sec, 3),
        "edit_sec": round(edit_sec, 3),
        "build_sec": round(build_sec, 3),
        "run_sec": round(run_sec, 3),
        "judge_sec": round(judge_sec, 3),
        "iterations": iterations,
        "token_input": token_in,
        "token_output": token_out,
        "token_total": token_total,
        "token_is_estimate": token_is_estimate,
        "rtl_changed": bool(rtl_files),
        "env_changed": bool(env_files),
        "modified_files": ";".join(modified),
        "modified_rtl_files": ";".join(rtl_files),
        "modified_env_files": ";".join(env_files),
        "final_build_rc": final_build_rc,
        "final_run_rc": final_run_rc,
        "final_judge_rc": final_judge_rc,
        "final_status": final_status,
        "repair_class": repair_kind,
        "failure_class": failure,
        "pass_marker": pass_marker,
        "evidence_used": (
            (
                "validated kdebug manifest evidence + logs + repair-scope files"
                if evidence_valid
                else "no valid kdebug evidence; model was not called"
            )
            if args.group == "with_kdebug"
            else "logs + repair-scope files + text search"
        ),
        "rule_violation": rule_violation,
        "notes": notes,
    }


def system_prompt_for(scope):
    allowed = ", ".join(scope["allowed_roots"] + scope["allowed_files"])
    req = []
    if scope["requires_rtl_change"]:
        req.append("at least one effective RTL change")
    if scope["requires_env_change"]:
        req.append("at least one effective environment/script/config change")
    req_text = " and ".join(req) if req else "an effective repair"
    return f"""You are a hardware debug-and-repair agent in a benchmark.
Follow the rules exactly:
- You may modify only repair-scope paths: {allowed}.
- Do not read answer_key_private.json or any private answer key.
- Do not inspect other cases or cross-case answer material.
- Do not modify protected files such as case_meta.json, fail logs, evidence, agent_logs, or scripts/judge.sh.
- A case succeeds only after {req_text}, rebuild, rerun of the original failing workload, and final judge pass.
- Return exactly one unified diff in a fenced ```diff block when you want to edit.
"""


def finalize_status(final_status, scope, meta, modified, final_judge_rc, rule_violation):
    rtl_changed = any(is_rtl_rel(rel) for rel in modified)
    env_changed = any(is_env_rel(rel) for rel in modified)
    bug_domain = (meta.get("bug_domain") or scope["bug_domain"]).lower()

    if final_status == "PASS":
        if scope["requires_rtl_change"] and not rtl_changed:
            return "RULE_VIOLATION", "judge passed but required RTL change was not detected"
        if scope["requires_env_change"] and not env_changed:
            return "RULE_VIOLATION", "judge passed but required environment change was not detected"
        if bug_domain == "env" and rtl_changed:
            return "RULE_VIOLATION", "env-only case passed with RTL changes; repair is not a clean environment fix"
        if final_judge_rc != 0:
            return "INFRA_ERROR", rule_violation or "inconsistent PASS state: final_judge_rc was nonzero"
    return final_status, rule_violation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--repair-dir", default=os.environ.get("REPAIR_DIR"))
    parser.add_argument("--group", default=os.environ.get("GROUP", "without_kdebug"))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("TIMEOUT_SEC", "3600")))
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=int(os.environ.get("MAX_ITERATIONS", "0")),
        help="Safety cap for model turns; 0 means keep repairing until timeout.",
    )
    parser.add_argument("--results-csv", type=Path, default=None)
    args = parser.parse_args()

    if args.model not in MODELS:
        print(f"ERROR: unsupported API model {args.model}", file=sys.stderr)
        return 2
    if not args.repair_dir:
        print("ERROR: --repair-dir or REPAIR_DIR is required", file=sys.stderr)
        return 2
    if args.group not in {"with_kdebug", "without_kdebug"}:
        print("ERROR: group must be with_kdebug or without_kdebug", file=sys.stderr)
        return 2

    repair = Path(args.repair_dir).resolve()
    if not repair.exists():
        print(f"ERROR: repair dir does not exist: {repair}", file=sys.stderr)
        return 2
    args.repair_dir = str(repair)

    meta = load_case_meta(repair)
    scope = scope_from_meta(meta)
    log_dir = repair / "agent_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    command_log = log_dir / f"{args.model}_commands.log"
    transcript = log_dir / f"{args.model}_transcript.jsonl"
    metrics_path = log_dir / f"{args.model}_metrics.json"
    baseline = snapshot_allowed_files(repair, scope)

    start_wall = time.time()
    start_time = utc_now()

    evidence_required, evidence_present, evidence_files = list_evidence_files(repair, args.group, meta)
    evidence_validation = None
    if evidence_required and args.group == "with_kdebug" and not evidence_present:
        rule = "with_kdebug requested but required plan-declared KDebug response files are missing"
        metrics = make_metrics(
            args, meta, scope, start_time, start_wall,
            final_status="TOOL_EVIDENCE_MISSING",
            rule_violation=rule,
            evidence_files=evidence_files,
            evidence_validation=evidence_validation,
            notes=f"transcript={transcript.name}; command_log={command_log.name}",
        )
        write_json(metrics_path, metrics)
        if args.results_csv:
            append_trial_csv(args.results_csv, metrics)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        return 1

    if evidence_required and args.group == "with_kdebug":
        evidence_validation = validate_case_evidence(repair, verify_inputs=True)
        if not evidence_validation.get("valid"):
            rule = "invalid KDebug evidence manifest: " + "; ".join(evidence_validation.get("errors") or [])
            metrics = make_metrics(
                args, meta, scope, start_time, start_wall,
                final_status="TOOL_EVIDENCE_INVALID",
                rule_violation=rule,
                evidence_files=evidence_files,
                evidence_validation=evidence_validation,
                notes=f"transcript={transcript.name}; command_log={command_log.name}",
            )
            write_json(metrics_path, metrics)
            if args.results_csv:
                append_trial_csv(args.results_csv, metrics)
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            return 1

    try:
        api_key, api_key_env = resolve_api_key(args.api_key_env or default_api_key_env(args.model), args.model)
    except KeyError as exc:
        print(f"ERROR: {exc.args[0]} is required", file=sys.stderr)
        return 2
    api_model_name = API_MODEL_NAMES[args.model]
    base_url = normalize_base_url(args.model, args.base_url or default_base_url(args.model))

    bench_root = Path(__file__).resolve().parents[1]
    rules_name = "agent_rules_with_kdebug.md" if args.group == "with_kdebug" else "agent_rules_without_kdebug.md"
    rules = read_text(bench_root / rules_name, 12000)

    messages = [{"role": "system", "content": system_prompt_for(scope)}]
    token_in = token_out = token_total = 0
    token_is_estimate = True
    build_sec = run_sec = judge_sec = edit_sec = locate_sec = 0.0
    final_build_rc = final_run_rc = final_judge_rc = 1
    iterations = 0
    final_status = "TIMEOUT"
    rule_violation = ""
    pass_marker = ""
    include_files = []
    located = False
    model_response_count = 0
    consecutive_api_errors = 0

    build_cmd = meta.get("build_command") or "scripts/build.sh"
    run_cmd_text = meta.get("fail_command") or meta.get("run_command") or "scripts/run.sh"
    judge_cmd = meta.get("judge_command") or "scripts/judge.sh"

    while True:
        remaining = args.timeout - int(time.time() - start_wall)
        if remaining <= 0:
            final_status = "TIMEOUT"
            break
        if args.max_iterations > 0 and iterations >= args.max_iterations:
            final_status = "TIMEOUT"
            rule_violation = (
                f"iteration_limit_reached_before_timeout: max_iterations={args.max_iterations}; "
                "normal benchmark runs should use max_iterations=0 so only the 1-hour timeout "
                "terminates an unfinished repair"
            )
            break

        context = collect_context(repair, args.group, include_files, scope, meta)
        prompt = f"""Benchmark rules:
{rules}

Repair scope:
- allowed roots/files: {scope_string(scope)}
- requires_rtl_change: {scope['requires_rtl_change']}
- requires_env_change: {scope['requires_env_change']}
- protected files/roots: {', '.join(scope['forbidden_roots'] + scope['forbidden_files'])}

Case context:
{context}

Task for iteration {iterations + 1}:
1. State the likely root cause briefly.
2. If you need another allowed file, name it exactly.
3. If ready to repair, return exactly one unified diff in a fenced ```diff block.

The harness will apply only allowed-scope diffs, then run:
- {build_cmd}
- {run_cmd_text}
- {judge_cmd}
If an attempt does not pass, the harness will feed the build/run/judge logs back
to you and continue the repair loop until the case passes or the wall-clock
timeout expires. A no-patch answer is treated as feedback, not as a final
benchmark failure, but it still consumes the same timeout budget.
Do not include shell commands unless they are explanatory.
"""
        messages.append({"role": "user", "content": prompt})
        try:
            api_messages = compress_messages_for_api(messages, api_model_name)
            response = api_chat(
                base_url,
                api_key,
                api_model_name,
                api_messages,
                timeout=max(30, remaining),
            )
        except Exception as exc:
            if is_rate_limit_api_error(exc):
                rule_violation = f"api_rate_limited_retry_later: {exc}"
                final_status = "RETRY_LATER"
                break
            if is_retryable_api_error(exc):
                rule_violation = f"api_retryable_retry_later: {exc}"
                final_status = "RETRY_LATER"
                break
            else:
                rule_violation = f"api_error: {exc}"
                consecutive_api_errors += 1
                if consecutive_api_errors >= 3 or remaining <= 30:
                    final_status = "INFRA_ERROR"
                    break
                messages.append({
                    "role": "user",
                    "content": (
                        "The previous API call failed before producing a usable repair. "
                        f"Error: {exc}. Continue the same debug task and return either one "
                        "allowed-scope unified diff or one exact allowed file request."
                    ),
                })
                iterations += 1
                time.sleep(min(30, max(1, remaining // 10)))
                continue
        consecutive_api_errors = 0

        usage = token_usage(response)
        token_in += usage["token_input"]
        token_out += usage["token_output"]
        token_total += usage["token_total"]
        token_is_estimate = token_is_estimate and usage["token_is_estimate"]

        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        model_response_count += 1
        messages.append({"role": "assistant", "content": answer})
        with transcript.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "iteration": iterations + 1,
                "model_id": args.model,
                "api_model_name": api_model_name,
                "response": response,
            }, ensure_ascii=False) + "\n")

        if not located and answer.strip():
            locate_sec = time.time() - start_wall
            located = True

        diff_text = extract_diff_blocks(answer)
        if not diff_text:
            requested = parse_requested_files(answer, scope)
            if requested:
                include_files = requested
                iterations += 1
                continue
            rule_violation = "model_returned_no_patch"
            messages.append({
                "role": "user",
                "content": (
                    "Your previous response did not contain a usable unified diff and did not "
                    "name an exact allowed file to inspect. This trial is not over; continue "
                    "debugging. Return exactly one allowed-scope unified diff in a fenced "
                    "```diff block, or name one exact allowed file needed for the next context. "
                    "The only normal failure condition is exhausting the wall-clock timeout."
                ),
            })
            iterations += 1
            continue

        edit_start = time.time()
        try:
            apply_rc, patch_file = apply_patch_with_git(diff_text, repair, scope, command_log)
        except ValueError as exc:
            patch_file = record_invalid_patch(
                diff_text, log_dir, command_log, args.model, iterations + 1, exc
            )
            edit_sec += time.time() - edit_start
            rule_violation = f"invalid_patch_format: {exc}"
            messages.append({
                "role": "user",
                "content": (
                    "The previous patch was not a valid unified diff for the allowed repair scope. "
                    f"Validation error: {exc}. Patch file: {patch_file}. "
                    "Return exactly one corrected unified diff with --- and +++ paths."
                ),
            })
            iterations += 1
            continue
        edit_sec += time.time() - edit_start
        if apply_rc != 0:
            messages.append({
                "role": "user",
                "content": f"The patch failed to apply. Patch file: {patch_file}. Return a corrected unified diff.",
            })
            iterations += 1
            continue
        if rule_violation.startswith("invalid_patch_format"):
            rule_violation = ""

        iterations += 1
        remaining = args.timeout - int(time.time() - start_wall)
        final_build_rc, sec = run_cmd(build_cmd, repair, command_log, remaining, "build")
        build_sec += sec
        if final_build_rc == 0:
            remaining = args.timeout - int(time.time() - start_wall)
            final_run_rc, sec = run_cmd(run_cmd_text, repair, command_log, remaining, "run")
            run_sec += sec
        else:
            final_run_rc = 1
        if final_build_rc == 0 and final_run_rc == 0:
            remaining = min(300, max(1, args.timeout - int(time.time() - start_wall)))
            final_judge_rc, sec = run_cmd(judge_cmd, repair, command_log, remaining, "judge")
            judge_sec += sec
        else:
            final_judge_rc = 1

        if final_judge_rc == 0:
            candidate_modified = changed_files(repair, scope, baseline)
            candidate_status, candidate_rule = finalize_status(
                "PASS", scope, meta, candidate_modified, final_judge_rc, rule_violation
            )
            if candidate_status == "PASS":
                final_status = "PASS"
                rule_violation = ""
                pass_marker = read_text(repair / "agent_logs" / "latest_judge.log", 2000).replace("\n", " | ")
                break
            rule_violation = candidate_rule
            messages.append({
                "role": "user",
                "content": (
                    "The workload and judge passed, but the repair did not satisfy the benchmark "
                    f"scope rules: {candidate_rule}. Continue repairing within the allowed scope "
                    "until both the scope rules and judge pass, or until the wall-clock timeout expires."
                ),
            })
            continue

        if time.time() - start_wall >= args.timeout:
            final_status = "TIMEOUT"
            break

        messages.append({
            "role": "user",
            "content": (
                "The build/run/judge did not pass. Review latest_build.log, latest_run.log, "
                "latest_judge.log in the next context and return another allowed-scope unified diff. "
                "This is an intermediate repair failure, not a final benchmark failure; keep "
                "repairing until judge passes or the wall-clock timeout expires."
            ),
        })

    elapsed = time.time() - start_wall
    if elapsed >= args.timeout and final_status not in {"PASS", "RETRY_LATER"}:
        final_status = "INFRA_ERROR" if rule_violation.startswith("api_error:") and model_response_count == 0 else "TIMEOUT"
    modified = changed_files(repair, scope, baseline)
    final_status, rule_violation = finalize_status(
        final_status, scope, meta, modified, final_judge_rc, rule_violation
    )

    metrics = make_metrics(
        args, meta, scope, start_time, start_wall,
        token_in=token_in,
        token_out=token_out,
        token_total=token_total,
        token_is_estimate=token_is_estimate,
        locate_sec=locate_sec,
        edit_sec=edit_sec,
        build_sec=build_sec,
        run_sec=run_sec,
        judge_sec=judge_sec,
        iterations=iterations,
        final_build_rc=final_build_rc,
        final_run_rc=final_run_rc,
        final_judge_rc=final_judge_rc,
        final_status=final_status,
        rule_violation=rule_violation,
        pass_marker=pass_marker,
        evidence_files=evidence_files,
        evidence_validation=evidence_validation,
        modified=modified,
        notes=f"api_model_name={api_model_name}; api_key_env={api_key_env}; transcript={transcript.name}; command_log={command_log.name}",
    )
    write_json(metrics_path, metrics)
    if args.results_csv:
        append_trial_csv(args.results_csv, metrics)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if final_status == "PASS":
        return 0
    if final_status == "RETRY_LATER":
        return RETRY_LATER_EXIT_CODE
    return 1


if __name__ == "__main__":
    sys.exit(main())
