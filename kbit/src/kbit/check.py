from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bitvector import BitVector
from .errors import ParseError
from .eval import eval_expr, parse_vars
from .literal import parse_value


def _coerce_wave_value(value: Any, *, state: str) -> BitVector:
    if isinstance(value, dict):
        for key in ("value", "sv", "literal"):
            if key in value:
                return parse_value(value[key], state=state)
        if "hex" in value:
            width = value.get("width")
            text = str(value["hex"])
            if text.startswith("0x"):
                text = text[2:]
            return parse_value(f"{width}'h{text}" if width else f"'h{text}", state=state)
        if "bin" in value:
            width = value.get("width")
            text = str(value["bin"]).replace("_", "")
            return parse_value(f"{width}'b{text}" if width else f"'b{text}", state=state)
    return parse_value(value, state=state)


def extract_values(payload: Any, *, state: str = "2state") -> dict[str, BitVector]:
    if isinstance(payload, (str, Path)):
        with open(payload, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ParseError("--values JSON must be an object")
    if isinstance(payload.get("values"), dict):
        values = payload["values"]
    elif isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("values"), dict):
        values = payload["data"]["values"]
    else:
        values = payload
    out: dict[str, BitVector] = {}
    for key, value in values.items():
        if not isinstance(key, str):
            continue
        out[key] = _coerce_wave_value(value, state=state)
    return out


def run_check(
    expr: str,
    *,
    var_items: list[str] | None = None,
    values_file: str | None = None,
    values_payload: Any | None = None,
    state: str = "2state",
) -> dict:
    variables = {}
    if values_file:
        variables.update(extract_values(values_file, state=state))
    if values_payload is not None:
        variables.update(extract_values(values_payload, state=state))
    variables.update(parse_vars(var_items, state=state))
    result = eval_expr(expr, variables, state=state)
    matched = result.truthy()
    return {
        "matched": matched,
        "value": result.to_sv("b"),
        "result": result.to_result(),
        "evaluated": {name: value.to_sv("h") for name, value in sorted(variables.items())},
    }
