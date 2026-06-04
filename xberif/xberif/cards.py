from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .errors import (
    CARD_ID_MISMATCH,
    CARD_REQUIRED_MISSING,
    CARD_SCHEMA_INVALID,
    CARDS_CATALOG_INVALID,
    DENY_PATH_REFERENCED,
    DETAIL_CARD_MISMATCH,
    DETAIL_METADATA_MISMATCH,
    DETAIL_REQUIRED_MISSING,
    DETAIL_SCHEMA_INVALID,
    DETAIL_SECTION_MISSING,
    EVIDENCE_LINE_RANGE_INVALID,
    EVIDENCE_PATH_NOT_IN_MANIFEST,
    ITEM_COUNT_MISMATCH,
    KIND_MISMATCH,
    MANIFEST_MISSING,
    RUNTIME_AI_DISABLED,
    VALIDATION_FAILED,
    XberifError,
)
from .io import read_json, read_toml, read_text, write_json, write_text
from .manifest import _matches
from .paths import config_dir, state_dir
from .topics import load_kind_config, load_topics, topic_by_card_id, topic_def

DETAIL_SECTIONS = (
    "结论摘要",
    "关键路径",
    "关键项详解",
    "验证与 Debug 提示",
    "相关 Topic",
    "未确认信息",
    "Evidence",
)
EVIDENCE_RE = re.compile(r"^-\s+([^:\n]+):(\d+)-(\d+)(?:\s+-\s+.*)?$", re.MULTILINE)
EVIDENCE_STRING_RE = re.compile(r"^(.+):(\d+)-(\d+)(?:\s+-\s+.*)?$")


def empty_catalog(kind: str) -> dict:
    return {"schema_version": "xberif.cards_catalog.v1", "env_kind": kind, "cards": []}


def card_path(root: Path, card_id: str) -> Path:
    return state_dir(root) / "cards" / f"{card_id}.json"


def detail_path(root: Path, card_id: str) -> Path:
    return state_dir(root) / "details" / f"{card_id}.md"


def init_state(root: Path, kind: str) -> None:
    sdir = state_dir(root)
    for generated_dir in (sdir / "cards", sdir / "details"):
        if generated_dir.exists():
            shutil.rmtree(generated_dir)
        generated_dir.mkdir(parents=True, exist_ok=True)
    write_json(sdir / "cards.json", empty_catalog(kind))


def _manifest(root: Path) -> dict:
    path = state_dir(root) / "manifest.json"
    if not path.exists():
        raise XberifError(MANIFEST_MISSING, ".xberif/manifest.json is missing")
    return read_json(path)


def _manifest_files(root: Path) -> dict[str, dict]:
    return {f["path"]: f for f in _manifest(root).get("files", [])}


def _normalize_evidence(evidence: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for ev in evidence:
        if isinstance(ev, dict):
            normalized.append(ev)
            continue
        if isinstance(ev, str):
            match = EVIDENCE_STRING_RE.match(ev.strip())
            if match:
                normalized.append(
                    {
                        "path": match.group(1),
                        "line_start": int(match.group(2)),
                        "line_end": int(match.group(3)),
                    }
                )
                continue
        raise XberifError(CARD_SCHEMA_INVALID, "evidence must be objects or path:start-end strings")
    return normalized


def normalize_card_evidence(card: dict[str, Any]) -> bool:
    changed = False
    for item in card.get("key_items", []):
        if not isinstance(item, dict):
            continue
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            raise XberifError(CARD_SCHEMA_INVALID, "key_item evidence must be a list")
        normalized = _normalize_evidence(evidence)
        if normalized != evidence:
            item["evidence"] = normalized
            changed = True
    return changed


def _validate_evidence(root: Path, evidence: list[Any]) -> None:
    evidence = _normalize_evidence(evidence)
    files = _manifest_files(root)
    deny_paths = load_kind_config(root).get("safety", {}).get("deny_paths", [])
    for ev in evidence:
        path = ev.get("path")
        if not path or path not in files:
            raise XberifError(EVIDENCE_PATH_NOT_IN_MANIFEST, f"evidence path {path} is not in manifest")
        if _matches(path, deny_paths):
            raise XberifError(DENY_PATH_REFERENCED, f"evidence path {path} matches deny_paths")
        start = ev.get("line_start")
        end = ev.get("line_end")
        max_lines = int(files[path].get("lines", 0))
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or end > max_lines:
            raise XberifError(EVIDENCE_LINE_RANGE_INVALID, f"invalid evidence line range for {path}")


def _expected_detail_ref(card_id: str) -> str:
    return f".xberif/details/{card_id}.md"


def validate_card(root: Path, card: dict[str, Any]) -> None:
    kind = load_kind_config(root)["env_kind"]
    if card.get("schema_version") != "xberif.topic_card.v1":
        raise XberifError(CARD_SCHEMA_INVALID, "card schema_version must be xberif.topic_card.v1")
    if card.get("env_kind") != kind:
        raise XberifError(KIND_MISMATCH, f"card env_kind {card.get('env_kind')} does not match {kind}")
    topic = card.get("topic")
    cfg = topic_def(root, topic)
    if card.get("id") != cfg.get("card_id"):
        raise XberifError(CARD_ID_MISMATCH, f"card id must be {cfg.get('card_id')}")
    if card.get("title") != cfg.get("title"):
        raise XberifError(CARD_SCHEMA_INVALID, f"card title must be {cfg.get('title')}")
    if not isinstance(card.get("summary"), str) or not card["summary"].strip():
        raise XberifError(CARD_SCHEMA_INVALID, "card summary must contain a short, clear topic conclusion")
    key_items = card.get("key_items")
    if not isinstance(key_items, list):
        raise XberifError(CARD_SCHEMA_INVALID, "card key_items must be a list")
    if cfg.get("required") and not key_items:
        raise XberifError(CARD_SCHEMA_INVALID, "required card must contain key_items")
    if len(key_items) > 8:
        raise XberifError(CARD_SCHEMA_INVALID, "card key_items must contain no more than 8 entries")
    normalize_card_evidence(card)
    for item in key_items:
        if not isinstance(item, dict) or not item.get("name") or not item.get("one_line"):
            raise XberifError(CARD_SCHEMA_INVALID, "each key_item requires name and one_line")
        _validate_evidence(root, item.get("evidence", []))
    detail = card.get("detail")
    if not isinstance(detail, dict) or detail.get("available") is not True:
        raise XberifError(CARD_SCHEMA_INVALID, "card detail.available must be true")
    if detail.get("path") != _expected_detail_ref(card["id"]) or detail.get("format") != "markdown":
        raise XberifError(CARD_SCHEMA_INVALID, "card detail reference is invalid")


def validate_card_file(root: Path, path: Path) -> None:
    expected_dir = (state_dir(root) / "cards").resolve()
    resolved = path.resolve()
    if resolved.parent != expected_dir:
        raise XberifError(CARD_SCHEMA_INVALID, f"card file must be under {expected_dir}")
    card = read_json(resolved)
    validate_card(root, card)
    if resolved.name != f"{card['id']}.json":
        raise XberifError(CARD_ID_MISMATCH, f"card filename must be {card['id']}.json")


def _frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise XberifError(DETAIL_SCHEMA_INVALID, "detail must start with YAML-style frontmatter")
    raw, body = content[4:].split("\n---\n", 1)
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            raise XberifError(DETAIL_SCHEMA_INVALID, "detail frontmatter must use key: value lines")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")
    return meta, body


def _detail_statistics(content: str) -> tuple[int, int]:
    return max(1, (len(content) + 3) // 4), len(re.findall(r"^##\s+", content, re.MULTILINE))


def validate_detail(root: Path, topic: str, content: str, path: Path | None = None) -> dict[str, Any]:
    cfg = topic_def(root, topic)
    kind = load_kind_config(root)["env_kind"]
    card_id = cfg["card_id"]
    if path is not None and path.resolve() != detail_path(root, card_id).resolve():
        raise XberifError(DETAIL_CARD_MISMATCH, f"detail filename must be {card_id}.md")
    meta, body = _frontmatter(content)
    expected = {
        "schema_version": "xberif.topic_detail.v1",
        "env_kind": kind,
        "topic": topic,
        "card_id": card_id,
        "title": cfg["title"],
    }
    for key, value in expected.items():
        if meta.get(key) != value:
            raise XberifError(DETAIL_CARD_MISMATCH, f"detail {key} must be {value}")
    if not meta.get("confidence"):
        raise XberifError(DETAIL_SCHEMA_INVALID, "detail confidence is required")
    for section in DETAIL_SECTIONS:
        if not re.search(rf"^##\s+{re.escape(section)}\s*$", body, re.MULTILINE):
            raise XberifError(DETAIL_SECTION_MISSING, f"detail section is missing: {section}")
    evidence = [
        {"path": match.group(1), "line_start": int(match.group(2)), "line_end": int(match.group(3))}
        for match in EVIDENCE_RE.finditer(body)
    ]
    if not evidence:
        raise XberifError(DETAIL_SCHEMA_INVALID, "detail Evidence section must contain parseable evidence")
    _validate_evidence(root, evidence)
    token_estimate, section_count = _detail_statistics(content)
    return {"token_estimate": token_estimate, "section_count": section_count, "evidence": evidence}


def validate_detail_file(root: Path, path: Path) -> dict[str, Any]:
    expected_dir = (state_dir(root) / "details").resolve()
    resolved = path.resolve()
    if resolved.parent != expected_dir or resolved.suffix != ".md":
        raise XberifError(DETAIL_SCHEMA_INVALID, f"detail file must be under {expected_dir}")
    topic, _cfg = topic_by_card_id(root, resolved.stem)
    return validate_detail(root, topic, read_text(resolved), path=resolved)


def reconcile_detail_metadata(root: Path) -> None:
    for topic, cfg in load_topics(root).get("topics", {}).items():
        cpath = card_path(root, cfg["card_id"])
        dpath = detail_path(root, cfg["card_id"])
        if not cpath.exists() or not dpath.exists():
            continue
        card = read_json(cpath)
        if normalize_card_evidence(card):
            write_json(cpath, card)
        stats = validate_detail(root, topic, read_text(dpath), path=dpath)
        card["detail"] = {
            "available": True,
            "path": _expected_detail_ref(cfg["card_id"]),
            "format": "markdown",
            "token_estimate": stats["token_estimate"],
            "section_count": stats["section_count"],
        }
        write_json(cpath, card)


def update_catalog(root: Path) -> dict:
    kind = load_kind_config(root)["env_kind"]
    cards = []
    for topic, cfg in load_topics(root).get("topics", {}).items():
        cid = cfg["card_id"]
        cpath = card_path(root, cid)
        if not cpath.exists():
            continue
        card = read_json(cpath)
        detail = card.get("detail", {})
        cards.append(
            {
                "id": cid,
                "topic": topic,
                "title": cfg["title"],
                "path": f".xberif/cards/{cid}.json",
                "summary": card.get("summary", ""),
                "key_item_count": len(card.get("key_items", [])),
                "detail_available": detail.get("available", False),
                "detail_path": detail.get("path", ""),
                "detail_token_estimate": detail.get("token_estimate", 0),
                "required": bool(cfg.get("required", False)),
            }
        )
    catalog = {"schema_version": "xberif.cards_catalog.v1", "env_kind": kind, "cards": cards}
    write_json(state_dir(root) / "cards.json", catalog)
    return catalog


def repair_catalog(root: Path) -> dict:
    reconcile_detail_metadata(root)
    catalog = update_catalog(root)
    errors = validate_all(root)
    if errors:
        raise XberifError(VALIDATION_FAILED, "; ".join(errors))
    return catalog


def upsert_card(root: Path, card: dict[str, Any]) -> None:
    validate_card(root, card)
    write_json(card_path(root, card["id"]), card)
    update_catalog(root)


def append_key_items(root: Path, card_id: str, key_items: list[dict[str, Any]]) -> None:
    topic_by_card_id(root, card_id)
    path = card_path(root, card_id)
    if not path.exists():
        raise XberifError(CARD_SCHEMA_INVALID, f"card {card_id} must be upserted before appending key_items")
    card = read_json(path)
    existing = {json.dumps(i, sort_keys=True, ensure_ascii=False) for i in card.get("key_items", [])}
    for item in key_items:
        _validate_evidence(root, item.get("evidence", []))
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in existing:
            card["key_items"].append(item)
            existing.add(key)
    validate_card(root, card)
    write_json(path, card)
    update_catalog(root)


def upsert_detail(root: Path, topic: str, content: str) -> None:
    cfg = topic_def(root, topic)
    path = detail_path(root, cfg["card_id"])
    validate_detail(root, topic, content, path=path)
    write_text(path, content)
    reconcile_detail_metadata(root)
    update_catalog(root)


def validate_all(root: Path) -> list[str]:
    errors: list[str] = []
    xkind = load_kind_config(root)
    kind = xkind["env_kind"]
    if xkind.get("query", {}).get("runtime_ai") is not False:
        errors.append(f"{RUNTIME_AI_DISABLED}: query.runtime_ai must be false")
    skind_path = state_dir(root) / "kind.json"
    if not skind_path.exists():
        errors.append(f"{KIND_MISMATCH}: .xberif/kind.json is missing")
    elif read_json(skind_path).get("env_kind") != kind:
        errors.append(f"{KIND_MISMATCH}: .xberif/kind.json does not match xberif/kind.toml")
    try:
        _manifest(root)
    except XberifError as exc:
        errors.append(f"{exc.code}: {exc.message}")
    catalog_path = state_dir(root) / "cards.json"
    if not catalog_path.exists():
        errors.append(f"{CARDS_CATALOG_INVALID}: .xberif/cards.json is missing")
        catalog = {"cards": []}
    else:
        catalog = read_json(catalog_path)
        if catalog.get("env_kind") != kind:
            errors.append(f"{KIND_MISMATCH}: cards catalog env_kind mismatch")
    catalog_by_topic = {c.get("topic"): c for c in catalog.get("cards", [])}
    for topic, cfg in read_toml(config_dir(root) / "topics.toml").get("topics", {}).items():
        cpath = card_path(root, cfg["card_id"])
        dpath = detail_path(root, cfg["card_id"])
        if cfg.get("required") and not cpath.exists():
            errors.append(f"{CARD_REQUIRED_MISSING}: required topic {topic} has no card")
        if cfg.get("required") and not dpath.exists():
            errors.append(f"{DETAIL_REQUIRED_MISSING}: required topic {topic} has no detail")
        if not cpath.exists():
            continue
        if topic not in catalog_by_topic:
            errors.append(f"{CARDS_CATALOG_INVALID}: topic {topic} is missing from catalog")
        try:
            card = read_json(cpath)
            validate_card(root, card)
            if not dpath.exists():
                errors.append(f"{DETAIL_REQUIRED_MISSING}: topic {topic} card has no detail")
                continue
            stats = validate_detail(root, topic, read_text(dpath), path=dpath)
            detail = card.get("detail", {})
            if detail.get("token_estimate") != stats["token_estimate"] or detail.get("section_count") != stats["section_count"]:
                errors.append(f"{DETAIL_METADATA_MISMATCH}: {cfg['card_id']} detail statistics mismatch")
            entry = catalog_by_topic.get(topic, {})
            if int(entry.get("key_item_count", -1)) != len(card.get("key_items", [])):
                errors.append(f"{ITEM_COUNT_MISMATCH}: {cfg['card_id']} key_item_count mismatch")
            if entry.get("detail_path") != detail.get("path") or entry.get("detail_token_estimate") != detail.get("token_estimate"):
                errors.append(f"{DETAIL_METADATA_MISMATCH}: {cfg['card_id']} catalog detail metadata mismatch")
        except (OSError, ValueError, XberifError) as exc:
            if isinstance(exc, XberifError):
                errors.append(f"{exc.code}: {exc.message}")
            else:
                errors.append(f"{DETAIL_SCHEMA_INVALID}: {exc}")
    return errors
