from __future__ import annotations

from pathlib import Path

from .errors import TOPIC_NOT_FOUND, KberifError
from .io import read_toml
from .paths import config_dir


def load_kind_config(root: Path) -> dict:
    return read_toml(config_dir(root) / "kind.toml")


def load_topics(root: Path) -> dict:
    return read_toml(config_dir(root) / "topics.toml")


def env_kind(root: Path) -> str:
    return load_kind_config(root)["env_kind"]


def topic_def(root: Path, topic: str) -> dict:
    topics = load_topics(root).get("topics", {})
    if topic not in topics:
        kind = env_kind(root)
        raise KberifError(TOPIC_NOT_FOUND, f"topic {topic} is not available for env_kind {kind}")
    return topics[topic]


def topic_by_card_id(root: Path, card_id: str) -> tuple[str, dict]:
    for topic, cfg in load_topics(root).get("topics", {}).items():
        if cfg.get("card_id") == card_id:
            return topic, cfg
    raise KberifError(TOPIC_NOT_FOUND, f"card {card_id} is not defined in topics.toml")
