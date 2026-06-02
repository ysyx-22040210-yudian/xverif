from __future__ import annotations

from typing import Any

from .config import load_config_file
from .decode import decode_entry, explain_config, validate_entry
from .errors import RequestError
from .fragments import load_fragments_file


API_VERSION = "xentry.v1"


def dispatch_request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise RequestError("request must be a JSON object")
    if request.get("api_version") != API_VERSION:
        raise RequestError("api_version must be xentry.v1", api_version=request.get("api_version"))
    action = request.get("action")
    if action not in {"decode", "explain", "validate"}:
        raise RequestError("action must be decode, explain, or validate", action=action)
    config = resolve_config(request)
    fragments = resolve_fragments(request, required=action == "decode")
    if action == "decode":
        assert fragments is not None
        payload = decode_entry(config, fragments)
    elif action == "explain":
        payload = explain_config(config)
    else:
        payload = validate_entry(config, fragments)
    if "request_id" in request:
        payload["request_id"] = request["request_id"]
    return payload


def resolve_config(request: dict) -> dict:
    has_config = "config" in request
    has_path = "config_path" in request
    if has_config == has_path:
        raise RequestError("request must provide exactly one of config or config_path")
    config = request["config"] if has_config else load_config_file(str(request["config_path"]))
    if not isinstance(config, dict):
        raise RequestError("config must be an object")
    return config


def resolve_fragments(request: dict, *, required: bool) -> list[dict] | None:
    has_fragments = "fragments" in request
    has_path = "input_path" in request
    if has_fragments and has_path:
        raise RequestError("request must not provide both fragments and input_path")
    if not has_fragments and not has_path:
        if required:
            raise RequestError("decode requires fragments or input_path")
        return None
    fragments = request["fragments"] if has_fragments else load_fragments_file(str(request["input_path"]))
    if not isinstance(fragments, list):
        raise RequestError("fragments must be an array")
    return fragments
