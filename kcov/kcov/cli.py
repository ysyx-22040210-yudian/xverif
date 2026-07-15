from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .actions import Dispatcher
from .errors import KcovError, error_response
from .logging import (log_action_event, log_transport_event,
                      request_summary_for_log, response_summary_for_log)
from .protocol import json_dumps, parse_request, render_kout, response_format

Json = Dict[str, Any]

_PROTOCOL_OUT = None

SHORTCUT_COMMANDS = {
    "actions", "schema", "open", "status", "close", "tests", "metrics",
    "scope-summary", "scope-children", "scope-search",
    "cov-summary", "cov-holes", "object-get", "object-search",
    "functional-summary", "functional-holes",
    "source-map",
    "export-summary", "export-holes", "export-scope-tree", "export-functional",
    "query",
}


def _setup_protocol_stdout() -> None:
    global _PROTOCOL_OUT
    if _PROTOCOL_OUT is not None:
        return
    saved = os.dup(1)
    _PROTOCOL_OUT = os.fdopen(saved, "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)


def _protocol_write(text: str) -> None:
    out = _PROTOCOL_OUT or sys.stdout
    out.write(text)
    out.flush()


def _emit(req: Json, rsp: Json) -> None:
    if response_format(req) == "json":
        _protocol_write(json_dumps(rsp) + "\n")
    else:
        _protocol_write(render_kout(rsp))


def run_once(text: str, dispatcher: Dispatcher) -> int:
    try:
        req = parse_request(text)
    except KcovError as exc:
        req = {"request_id": "req-unknown", "action": ""}
        rsp = error_response("", "req-unknown", exc.code, exc.message, **exc.detail)
        log_action_event("public", "adhoc", "", "parse_failed", False, 0,
                         {"error": rsp.get("error")})
        _emit(req, rsp)
        return 1
    rsp = dispatcher.dispatch(req)
    _emit(req, rsp)
    return 0 if rsp.get("ok") else 1


def _parse_scalar(value: str) -> Any:
    if value in {"true", "false"}:
        return value == "true"
    if value == "null":
        return None
    if value and value[0] in "[{":
        try:
            return json.loads(value)
        except Exception:
            return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _csv(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    return [item for item in (part.strip() for part in value.split(",")) if item]


def _set_dotted(root: Json, dotted: str, value: Any) -> None:
    if "." not in dotted:
        root[dotted] = value
        return
    head, tail = dotted.split(".", 1)
    child = root.setdefault(head, {})
    if not isinstance(child, dict):
        child = {}
        root[head] = child
    _set_dotted(child, tail, value)


def _apply_key_value(root: Json, item: str) -> None:
    if "=" not in item or item.startswith("="):
        raise KcovError("INVALID_CLI", f"expected key=value, got: {item}")
    key, value = item.split("=", 1)
    _set_dotted(root, key, _parse_scalar(value))


def _add_common_query_options(parser: argparse.ArgumentParser, *,
                              include_session: bool = True,
                              include_vdb: bool = True,
                              include_fake: bool = False) -> None:
    parser.add_argument("--json", action="store_true", help="emit JSON response")
    if include_session:
        parser.add_argument("--session", "--session-id", dest="session_id")
    if include_vdb:
        parser.add_argument("--vdb")
    if include_fake:
        parser.add_argument("--fake", action="store_true", help="use built-in fake coverage data")
    parser.add_argument("--scope")
    parser.add_argument("--test")
    parser.add_argument("--metrics", help="comma-separated metrics, e.g. line,toggle,branch")
    parser.add_argument("--include", action="append", default=[], help="glob include pattern")
    parser.add_argument("--exclude", action="append", default=[], help="glob exclude pattern")
    parser.add_argument("--match-field", default=None, help="query field, e.g. full_name, name, file")
    parser.add_argument("--case-insensitive", action="store_true")
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--overflow", choices=["truncate", "error", "to_file", "summary_only"])
    parser.add_argument("--output-mode", choices=["inline", "file", "both", "summary_only"])
    parser.add_argument("--output-path")
    parser.add_argument("--artifact-format", choices=["json", "ndjson", "csv", "md"])
    parser.add_argument("--allow-absolute-path", action="store_true")
    parser.add_argument("--sort-by")
    parser.add_argument("--sort-order", choices=["asc", "desc"])
    parser.add_argument("--arg", action="append", default=[], help="set args key=value")
    parser.add_argument("--target", action="append", default=[], help="set target key=value")


def build_shortcut_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kcov", description="VCS/Verdi coverage query tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("actions", help="list kcov actions")
    _add_common_query_options(p)

    p = sub.add_parser("schema", help="show action schema")
    _add_common_query_options(p)
    p.add_argument("--action", required=True)
    p.add_argument("--kind", choices=["request", "response"], default="request")

    p = sub.add_parser("open", help="open coverage database session")
    _add_common_query_options(p, include_vdb=False)
    p.add_argument("--vdb", required=True)
    p.add_argument("--name")
    p.add_argument("--fake", action="store_true")
    p.add_argument("--reuse", dest="reuse", action="store_true", default=None)
    p.add_argument("--no-reuse", dest="reuse", action="store_false")
    p.add_argument("--reopen", action="store_true")

    for name, action in (("status", "session.status"), ("close", "session.close")):
        p = sub.add_parser(name, help=action)
        _add_common_query_options(p, include_session=False)
        p.add_argument("--session", "--session-id", dest="session_id", required=True)

    simple_session = {
        "tests": "tests.list",
        "metrics": "metrics.list",
        "scope-summary": "scope.summary",
        "scope-search": "scope.search",
        "cov-summary": "cov.summary",
        "cov-holes": "cov.holes",
        "object-search": "cov.object.search",
        "functional-summary": "functional.summary",
        "functional-holes": "functional.holes",
        "export-summary": "export.summary",
        "export-holes": "export.holes",
        "export-scope-tree": "export.scope_tree",
        "export-functional": "export.functional",
    }
    for name in simple_session:
        p = sub.add_parser(name, help=simple_session[name])
        _add_common_query_options(p, include_session=True, include_fake=True)
        if name in {"cov-summary", "functional-summary", "export-summary"}:
            p.add_argument("--group-by")
        if name in {"functional-summary", "functional-holes", "export-functional"}:
            p.add_argument("--levels", help="comma-separated functional levels")
        if name == "export-functional":
            p.add_argument("--mode", choices=["summary", "holes"])
        if name == "export-scope-tree":
            p.add_argument("--recursive", action="store_true", default=None)
            p.add_argument("--no-recursive", dest="recursive", action="store_false")

    p = sub.add_parser("scope-children", help="scope.children")
    _add_common_query_options(p, include_session=True, include_fake=True)
    p.add_argument("--recursive", action="store_true", default=False)

    p = sub.add_parser("object-get", help="cov.object.get")
    _add_common_query_options(p, include_session=True, include_fake=True)
    p.add_argument("--object", "--name", dest="object_name", required=True)
    p.add_argument("--include-children", action="store_true")
    p.add_argument("--max-children", type=int)

    p = sub.add_parser("source-map", help="source.map")
    _add_common_query_options(p, include_session=True, include_fake=True)
    p.add_argument("--file", required=True)
    p.add_argument("--line", type=int, required=True)
    p.add_argument("--window", type=int)

    p = sub.add_parser("query", help="run any kcov action without writing JSON")
    _add_common_query_options(p, include_fake=True)
    p.add_argument("action")

    return parser


def _shortcut_action(command: str, ns: argparse.Namespace) -> str:
    mapping = {
        "actions": "actions",
        "schema": "schema",
        "open": "session.open",
        "status": "session.status",
        "close": "session.close",
        "tests": "tests.list",
        "metrics": "metrics.list",
        "scope-summary": "scope.summary",
        "scope-children": "scope.children",
        "scope-search": "scope.search",
        "cov-summary": "cov.summary",
        "cov-holes": "cov.holes",
        "object-get": "cov.object.get",
        "object-search": "cov.object.search",
        "functional-summary": "functional.summary",
        "functional-holes": "functional.holes",
        "source-map": "source.map",
        "export-summary": "export.summary",
        "export-holes": "export.holes",
        "export-scope-tree": "export.scope_tree",
        "export-functional": "export.functional",
    }
    if command == "query":
        return str(ns.action)
    return mapping[command]


def _apply_common(ns: argparse.Namespace, req: Json, force_json: bool = False) -> None:
    target = req.setdefault("target", {})
    args = req.setdefault("args", {})
    limits = req.setdefault("limits", {})
    output = req.setdefault("output", {})
    if getattr(ns, "session_id", None):
        target["session_id"] = ns.session_id
    if getattr(ns, "vdb", None):
        if req.get("action") == "session.open":
            target["vdb"] = ns.vdb
    if getattr(ns, "scope", None):
        args["scope"] = ns.scope
    if getattr(ns, "test", None):
        args["test"] = ns.test
    metrics = _csv(getattr(ns, "metrics", None))
    if metrics:
        args["metrics"] = metrics
    query: Json = {}
    if getattr(ns, "include", None):
        query["include_patterns"] = ns.include
    if getattr(ns, "exclude", None):
        query["exclude_patterns"] = ns.exclude
    if getattr(ns, "match_field", None):
        query["match_field"] = ns.match_field
    if getattr(ns, "case_insensitive", False):
        query["case_sensitive"] = False
    if query:
        args["query"] = query
    if getattr(ns, "max_items", None) is not None:
        limits["max_items"] = ns.max_items
    if getattr(ns, "overflow", None):
        limits["overflow"] = ns.overflow
    out_set = False
    if force_json or getattr(ns, "json", False):
        output["response_format"] = "json"
        out_set = True
    if getattr(ns, "output_mode", None):
        output["mode"] = ns.output_mode
        out_set = True
    if getattr(ns, "output_path", None):
        output["path"] = ns.output_path
        out_set = True
    if getattr(ns, "artifact_format", None):
        output["artifact_format"] = ns.artifact_format
        out_set = True
    if getattr(ns, "allow_absolute_path", False):
        output["allow_absolute_path"] = True
        out_set = True
    sort: Json = {}
    if getattr(ns, "sort_by", None):
        sort["by"] = ns.sort_by
    if getattr(ns, "sort_order", None):
        sort["order"] = ns.sort_order
    if sort:
        args["sort"] = sort
    for item in getattr(ns, "arg", []) or []:
        _apply_key_value(args, item)
    for item in getattr(ns, "target", []) or []:
        _apply_key_value(target, item)
    if not target:
        req.pop("target", None)
    if not args:
        req.pop("args", None)
    if not limits:
        req.pop("limits", None)
    if not out_set and not output:
        req.pop("output", None)


def request_from_shortcut(ns: argparse.Namespace, force_json: bool = False) -> Json:
    action = _shortcut_action(ns.command, ns)
    req: Json = {"api_version": "kcov.v1", "request_id": f"cli-{ns.command}", "action": action}
    _apply_common(ns, req, force_json=force_json)
    args = req.setdefault("args", {})
    if ns.command == "schema":
        args["action"] = ns.action
        args["kind"] = ns.kind
    elif ns.command == "open":
        args["name"] = ns.name
        if ns.fake:
            args["fake"] = True
        if ns.reuse is not None:
            args["reuse"] = ns.reuse
        if ns.reopen:
            args["reopen"] = True
    elif ns.command == "scope-children":
        args["recursive"] = bool(ns.recursive)
    elif ns.command == "object-get":
        args["name"] = ns.object_name
        if ns.include_children:
            args["include_children"] = True
        if ns.max_children is not None:
            args["max_children"] = ns.max_children
    elif ns.command in {"cov-summary", "functional-summary", "export-summary"} and getattr(ns, "group_by", None):
        args["group_by"] = ns.group_by
    elif ns.command in {"functional-summary", "functional-holes", "export-functional"}:
        levels = _csv(getattr(ns, "levels", None))
        if levels:
            args["levels"] = levels
    if ns.command == "source-map":
        args["file"] = ns.file
        args["line"] = ns.line
        if ns.window is not None:
            args["window"] = ns.window
    if ns.command == "export-scope-tree" and ns.recursive is not None:
        args["recursive"] = ns.recursive
    if ns.command == "export-functional" and ns.mode:
        args["mode"] = ns.mode
    if not args:
        req.pop("args", None)
    return req


def _needs_ephemeral_session(req: Json, ns: argparse.Namespace) -> bool:
    if req.get("action") in {"actions", "schema", "session.open", "session.status", "session.close"}:
        return False
    target = req.get("target") if isinstance(req.get("target"), dict) else {}
    return not target.get("session_id") and bool(getattr(ns, "vdb", None))


def _run_with_ephemeral_session(ns: argparse.Namespace, req: Json, dispatcher: Dispatcher) -> Json:
    session_id = f"cli_cov_{os.getpid()}"
    open_req: Json = {
        "api_version": "kcov.v1",
        "request_id": "cli-open-ephemeral",
        "action": "session.open",
        "target": {"vdb": ns.vdb},
        "args": {"name": session_id, "reuse": False},
    }
    if getattr(ns, "fake", False):
        open_req["args"]["fake"] = True
    open_rsp = dispatcher.dispatch(open_req)
    if not open_rsp.get("ok"):
        return open_rsp
    query_req = json.loads(json.dumps(req))
    query_req.setdefault("target", {})["session_id"] = session_id
    try:
        return dispatcher.dispatch(query_req)
    finally:
        close_req: Json = {
            "api_version": "kcov.v1",
            "request_id": "cli-close-ephemeral",
            "action": "session.close",
            "target": {"session_id": session_id},
        }
        dispatcher.dispatch(close_req)


def run_shortcut(argv: List[str], dispatcher: Dispatcher, force_json: bool = False) -> int:
    ns = build_shortcut_parser().parse_args(argv)
    try:
        req = request_from_shortcut(ns, force_json=force_json)
        if _needs_ephemeral_session(req, ns):
            rsp = _run_with_ephemeral_session(ns, req, dispatcher)
        else:
            rsp = dispatcher.dispatch(req)
    except KcovError as exc:
        req = {"api_version": "kcov.v1", "request_id": "cli-error", "action": getattr(ns, "command", "")}
        if force_json or getattr(ns, "json", False):
            req["output"] = {"response_format": "json"}
        rsp = error_response(req.get("action", ""), req.get("request_id", "cli-error"),
                             exc.code, exc.message, **exc.detail)
    _emit(req, rsp)
    return 0 if rsp.get("ok") else 1


def stdio_loop(dispatcher: Dispatcher) -> int:
    ready = {"type": "ready", "protocol": "kcov-stdio-loop", "version": 1,
             "pid": os.getpid()}
    _protocol_write(json.dumps(ready, separators=(",", ":")) + "\n")
    log_transport_event("adhoc", "ready", True, ready)
    seq = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        seq += 1
        try:
            req = parse_request(line)
            rid = req.get("request_id") or req.get("id") or f"req-{seq}"
            req["request_id"] = rid
            sid = _log_session_id(req)
            log_transport_event(sid, "request", True, {"request": request_summary_for_log(req)})
            if req.get("action") == "stdio.quit":
                _protocol_write(json.dumps({"id": rid, "ok": True, "payload_format": "json",
                                            "json": {"ok": True, "action": "stdio.quit"}}) + "\n")
                log_transport_event(sid, "stdio.quit", True, {"request_id": rid})
                return 0
            rsp = dispatcher.dispatch(req)
        except KcovError as exc:
            rid = f"req-{seq}"
            req = {"request_id": rid, "action": ""}
            rsp = error_response("", rid, exc.code, exc.message, **exc.detail)
            log_transport_event("adhoc", "parse_failed", False, {"error": rsp.get("error")})
        kout = render_kout(rsp)
        envelope = {"id": req.get("request_id", f"req-{seq}"),
                    "ok": bool(rsp.get("ok")),
                    "payload_format": "json" if response_format(req) == "json" else "kout",
                    "json": rsp,
                    "kout": kout}
        _protocol_write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
        log_transport_event(_log_session_id(req), "response", bool(rsp.get("ok")),
                            {"response": response_summary_for_log(rsp)})
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    _setup_protocol_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    force_json = False
    shortcut_argv = list(argv)
    while shortcut_argv and shortcut_argv[0] in {"--json", "--text", "--kout"}:
        token = shortcut_argv.pop(0)
        if token == "--json":
            force_json = True
    dispatcher = Dispatcher()
    if shortcut_argv and shortcut_argv[0] in {"-h", "--help"}:
        build_shortcut_parser().print_help()
        print("\nJSON protocol options:")
        parser = argparse.ArgumentParser(prog="kcov")
        parser.add_argument("--stdio-loop", action="store_true")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--request")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("file", nargs="?")
        parser.print_help()
        return 0
    if not shortcut_argv and sys.stdin.isatty():
        build_shortcut_parser().print_help()
        print("\nJSON protocol options:")
        parser = argparse.ArgumentParser(prog="kcov")
        parser.add_argument("--stdio-loop", action="store_true")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--request")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("file", nargs="?")
        parser.print_help()
        return 0
    if shortcut_argv and shortcut_argv[0] in SHORTCUT_COMMANDS:
        return run_shortcut(shortcut_argv, dispatcher, force_json=force_json)
    parser = argparse.ArgumentParser(prog="kcov")
    parser.add_argument("--stdio-loop", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--request")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("file", nargs="?")
    ns = parser.parse_args(argv)
    if ns.stdio_loop:
        return stdio_loop(dispatcher)
    if ns.request:
        with open(ns.request, "r", encoding="utf-8") as fh:
            text = fh.read()
    elif ns.file and ns.file != "-":
        with open(ns.file, "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    if ns.json:
        try:
            obj = json.loads(text)
            obj.setdefault("output", {})["response_format"] = "json"
            text = json.dumps(obj)
        except Exception:
            pass
    return run_once(text, dispatcher)


def _log_session_id(req: Json) -> str:
    target = req.get("target") if isinstance(req.get("target"), dict) else {}
    args = req.get("args") if isinstance(req.get("args"), dict) else {}
    if target.get("session_id"):
        return str(target["session_id"])
    if req.get("action") == "session.open" and args.get("name"):
        return str(args["name"])
    return "adhoc"


if __name__ == "__main__":
    raise SystemExit(main())
