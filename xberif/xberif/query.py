from __future__ import annotations

from pathlib import Path

from .cards import validate_detail
from .errors import CARDS_CATALOG_INVALID, DETAIL_REQUIRED_MISSING, KIND_MISMATCH, TOPIC_NOT_FOUND, XberifError
from .io import read_json, read_text, read_toml
from .paths import config_dir, state_dir
from .topics import env_kind, topic_def


def status(root: Path) -> dict:
    cfg_path = config_dir(root) / "kind.toml"
    topics_path = config_dir(root) / "topics.toml"
    sdir = state_dir(root)
    catalog_path = sdir / "cards.json"
    raw_cards = sorted((sdir / "cards").glob("*.json")) if (sdir / "cards").is_dir() else []
    raw_details = sorted((sdir / "details").glob("*.md")) if (sdir / "details").is_dir() else []
    if not cfg_path.exists() or not topics_path.exists():
        state = "not_configured"
    elif not sdir.exists():
        state = "configured_only"
    else:
        catalog_count = 0
        if catalog_path.exists():
            try:
                catalog_count = len(read_json(catalog_path).get("cards", []))
            except Exception:
                catalog_count = 0
        if catalog_count > 0:
            state = "ready"
        elif raw_cards or raw_details:
            state = "generated_raw"
        else:
            state = "configured_only"
    return {
        "schema_version": "xberif.status.v1",
        "state": state,
        "configured": cfg_path.exists() and topics_path.exists(),
        "state_dir_exists": sdir.exists(),
        "catalog_exists": catalog_path.exists(),
        "catalog_card_count": len(read_json(catalog_path).get("cards", [])) if catalog_path.exists() else 0,
        "raw_card_count": len(raw_cards),
        "raw_detail_count": len(raw_details),
        "next_action": _next_action_for_state(state),
    }


def _next_action_for_state(state: str) -> str:
    if state == "not_configured":
        return "run xberif config init --kind <bt|it|st|soc>"
    if state == "configured_only":
        return "run xberif init --model <model>"
    if state == "generated_raw":
        return "run xberif repair-catalog"
    if state == "invalid":
        return "run xberif validate and fix reported cards/details"
    return "use xberif brief/get/detail"


def _catalog_or_error(root: Path) -> dict:
    catalog_path = state_dir(root) / "cards.json"
    if not catalog_path.exists():
        raise XberifError(CARDS_CATALOG_INVALID, ".xberif/cards.json is missing; run xberif status")
    catalog = read_json(catalog_path)
    if not catalog.get("cards"):
        st = status(root)
        if st["state"] == "generated_raw":
            raise XberifError(
                CARDS_CATALOG_INVALID,
                ".xberif/cards.json is empty but raw cards/details exist; run xberif repair-catalog",
            )
        raise XberifError(CARDS_CATALOG_INVALID, ".xberif/cards.json has no cards; run xberif status")
    return catalog


def list_topics(root: Path) -> dict:
    catalog = _catalog_or_error(root)
    topics_cfg = read_toml(config_dir(root) / "topics.toml").get("topics", {})
    generated = {card["topic"]: card for card in catalog.get("cards", [])}
    return {
        "env_kind": env_kind(root),
        "topics": [
            {
                "topic": topic,
                "card_id": cfg["card_id"],
                "title": cfg["title"],
                "key_item_count": generated.get(topic, {}).get("key_item_count", 0),
                "detail_available": generated.get(topic, {}).get("detail_available", False),
                "detail_token_estimate": generated.get(topic, {}).get("detail_token_estimate", 0),
            }
            for topic, cfg in topics_cfg.items()
        ],
    }


def get_topic(root: Path, topic: str) -> dict:
    kind = env_kind(root)
    catalog = _catalog_or_error(root)
    entry = next((c for c in catalog.get("cards", []) if c.get("topic") == topic), None)
    if not entry:
        raise XberifError(TOPIC_NOT_FOUND, f"topic {topic} is not available for env_kind {kind}")
    card = read_json(root / entry["path"])
    detail = card.get("detail", {})
    return {
        "schema_version": "xberif.topic_result.v1",
        "env_kind": kind,
        "topic": topic,
        "source_card": card["id"],
        "title": card["title"],
        "summary": card.get("summary", ""),
        "confidence": card.get("confidence", "low"),
        "key_items": card.get("key_items", []),
        "detail_available": detail.get("available", False),
        "detail_path": detail.get("path", ""),
        "detail_token_estimate": detail.get("token_estimate", 0),
        "detail_method": "xberif.get_topic_detail",
        "notes": card.get("notes", []),
        "unknowns": card.get("unknowns", []),
    }


def get_topic_detail(root: Path, topic: str) -> dict:
    cfg = topic_def(root, topic)
    path = state_dir(root) / "details" / f"{cfg['card_id']}.md"
    if not path.exists():
        raise XberifError(DETAIL_REQUIRED_MISSING, f"topic {topic} has no detail")
    content = read_text(path)
    stats = validate_detail(root, topic, content, path=path)
    return {
        "schema_version": "xberif.topic_detail_result.v1",
        "env_kind": env_kind(root),
        "topic": topic,
        "card_id": cfg["card_id"],
        "format": "markdown",
        "content": content,
        "evidence": stats["evidence"],
    }


def check_namespace(root: Path, namespace: str) -> None:
    kind = env_kind(root)
    if namespace != kind:
        raise XberifError(
            KIND_MISMATCH,
            f'current env_kind is "{kind}"; command namespace "{namespace}" is unavailable.',
        )


def brief_result(root: Path, mode: str) -> dict:
    view = read_toml(config_dir(root) / "views" / f"{mode}.toml")
    kind = env_kind(root)
    if view.get("env_kind") != kind:
        raise XberifError(KIND_MISMATCH, f"view {mode} env_kind does not match {kind}")
    topics = []
    for topic in view.get("topics", []):
        result = get_topic(root, topic)
        topics.append(
            {
                "topic": topic,
                "title": result["title"],
                "summary": result["summary"],
                "key_items": result["key_items"],
                "detail_available": result["detail_available"],
                "detail_token_estimate": result["detail_token_estimate"],
                "detail_hint": f"Use xberif.get_topic_detail(topic='{topic}') for deeper analysis.",
            }
        )
    return {"schema_version": "xberif.brief.v1", "env_kind": kind, "mode": mode, "topics": topics}


def brief(root: Path, mode: str) -> str:
    parts = [f"# xberif brief: {mode}", ""]
    for result in brief_result(root, mode)["topics"]:
        parts.extend([f"## {result['title']}", "", result["summary"]])
        for item in result["key_items"]:
            parts.append(f"- **{item.get('name', 'item')}**: {item.get('one_line', '')}")
        if result["detail_available"]:
            parts.extend(["", f"Detail: `xberif detail {result['topic']}`"])
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"
