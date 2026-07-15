from __future__ import annotations

import json
import sys
from typing import Any

from .. import ops
from ..check import run_check
from ..errors import EvalError
from ..eval import eval_expr, parse_vars
from ..format import failure, success
from ..literal import parse_value


def _params(request: dict) -> dict:
    params = request.get("params", {})
    if not isinstance(params, dict):
        raise EvalError("params must be an object")
    return params


def dispatch(request: dict) -> dict:
    method = request.get("method")
    params = _params(request)
    state = params.get("state", "2state")
    if state == "2":
        state = "2state"
    if state == "4":
        state = "4state"
    if method == "kbit.conv":
        return success("conv", input_value=params.get("value"), result=parse_value(params["value"], state=state))
    if method == "kbit.eval":
        variables = parse_vars(params.get("var", []), state=state)
        for name, value in params.get("vars", {}).items():
            variables[name] = parse_value(value, state=state)
        return success("eval", input_value=params.get("expr"), result=eval_expr(params["expr"], variables, state=state))
    if method == "kbit.slice":
        value = parse_value(params["value"], state=state)
        return success("slice", input_value=params.get("value"), result=ops.slice_bits(value, int(params["msb"]), int(params["lsb"])))
    if method == "kbit.concat":
        return success("concat", input_value=params.get("values"), result=ops.concat([parse_value(v, state=state) for v in params["values"]]))
    if method == "kbit.repeat":
        return success("repeat", input_value=params, result=ops.repeat(int(params["count"]), parse_value(params["value"], state=state)))
    if method == "kbit.mask":
        return success("mask", input_value=params, result=ops.mask(int(params["width"]), int(params.get("lsb", 0))))
    if method == "kbit.popcount":
        return success("popcount", input_value=params.get("value"), result=ops.popcount(parse_value(params["value"], state=state)))
    if method == "kbit.check":
        result = run_check(
            params["expr"],
            var_items=params.get("var", []),
            values_payload=params.get("values"),
            state=state,
        )
        return success("check", input_value=params.get("expr"), result=result["result"], matched=result["matched"], evaluated=result["evaluated"])
    raise EvalError("unknown method", method=method)


def wrap_response(request: dict[str, Any], payload: dict) -> dict:
    response = dict(payload)
    if "id" in request:
        response["id"] = request["id"]
    if "jsonrpc" in request:
        response["jsonrpc"] = request["jsonrpc"]
    return response


def serve() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise EvalError("request must be an object")
            payload = dispatch(request)
        except Exception as exc:
            request = request if isinstance(locals().get("request"), dict) else {}
            payload = failure(exc)
        print(json.dumps(wrap_response(request, payload), ensure_ascii=False), flush=True)
    return 0
