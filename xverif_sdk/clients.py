"""Typed convenience clients over the stable xdebug/xcov JSON contracts."""

from __future__ import annotations

import copy
import itertools
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional

from .errors import ProtocolError, ToolResponseError

Json = Dict[str, Any]


class _BaseClient:
    api_version = ""
    output_key = "format"

    def __init__(self, transport: Any, *, default_target: Optional[Mapping[str, Any]] = None) -> None:
        if not hasattr(transport, "request"):
            raise TypeError("transport must provide request(request, timeout_sec=None)")
        self.transport = transport
        self.default_target = dict(default_target or {})
        self._ids = itertools.count(1)

    def raw_request(self, request: Mapping[str, Any], *, check: bool = True,
                    timeout_sec: Optional[float] = None) -> Json:
        outgoing = copy.deepcopy(dict(request))
        outgoing.setdefault("api_version", self.api_version)
        outgoing.setdefault("request_id", "sdk-%d" % next(self._ids))
        output = outgoing.setdefault("output", {})
        if not isinstance(output, dict):
            raise TypeError("request.output must be an object")
        output.setdefault(self.output_key, "json")
        response = self.transport.request(outgoing, timeout_sec=timeout_sec)
        if not isinstance(response, dict):
            raise ProtocolError("transport returned a non-object response")
        if check and not response.get("ok"):
            raise ToolResponseError(response)
        return response

    def request(self, action: str, *, target: Optional[Mapping[str, Any]] = None,
                args: Optional[Mapping[str, Any]] = None,
                limits: Optional[Mapping[str, Any]] = None,
                output: Optional[Mapping[str, Any]] = None,
                extra: Optional[Mapping[str, Any]] = None,
                check: bool = True,
                timeout_sec: Optional[float] = None) -> Json:
        merged_target = dict(self.default_target)
        if target:
            merged_target.update(target)
        request = dict(extra or {})
        request.update({
            "api_version": self.api_version,
            "action": action,
            "target": merged_target,
            "args": dict(args or {}),
        })
        if limits:
            request["limits"] = dict(limits)
        if output:
            request["output"] = dict(output)
        return self.raw_request(request, check=check, timeout_sec=timeout_sec)

    @staticmethod
    def _session_id(response: Json, fallback: str) -> str:
        summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
        if summary.get("session_id"):
            return str(summary["session_id"])
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        session = data.get("session") if isinstance(data.get("session"), dict) else {}
        return str(session.get("session_id") or fallback)


class XdebugClient(_BaseClient):
    api_version = "xdebug.v1"
    output_key = "format"

    def open_session(self, name: str, *, fsdb: Optional[str] = None,
                     daidir: Optional[str] = None,
                     args: Optional[Mapping[str, Any]] = None) -> Json:
        target = {}
        if fsdb:
            target["fsdb"] = fsdb
        if daidir:
            target["daidir"] = daidir
        open_args = dict(args or {})
        open_args["name"] = name
        return self.request("session.open", target=target, args=open_args)

    def close_session(self, session_id: str, *, check: bool = True) -> Json:
        return self.request("session.close", target={"session_id": session_id}, check=check)

    @contextmanager
    def session(self, name: str, *, fsdb: Optional[str] = None,
                daidir: Optional[str] = None,
                args: Optional[Mapping[str, Any]] = None) -> Iterator["XdebugClient"]:
        opened = self.open_session(name, fsdb=fsdb, daidir=daidir, args=args)
        session_id = self._session_id(opened, name)
        previous = dict(self.default_target)
        self.default_target = {"session_id": session_id}
        body_failed = False
        try:
            yield self
        except BaseException:
            body_failed = True
            raise
        finally:
            try:
                try:
                    self.close_session(session_id)
                except Exception:
                    if not body_failed:
                        raise
            finally:
                self.default_target = previous

    def value_batch_at(self, signals: Iterable[str], time_value: str, *,
                       value_format: str = "hex",
                       target: Optional[Mapping[str, Any]] = None,
                       limits: Optional[Mapping[str, Any]] = None) -> Json:
        return self.request(
            "value.batch_at", target=target,
            args={"signals": list(signals), "time": time_value, "format": value_format},
            limits=limits,
        )

    def signal_changes(self, signal_name: str, start: str, end: str, *,
                       include_rows: bool = True, aggregate_only: bool = False,
                       limit: int = 100, mode: str = "head",
                       target: Optional[Mapping[str, Any]] = None) -> Json:
        return self.request(
            "signal.changes", target=target,
            args={
                "signal": signal_name,
                "time_range": {"start": start, "end": end},
                "include_rows": include_rows,
                "aggregate_only": aggregate_only,
                "limit": limit,
                "mode": mode,
            },
        )

    def trace_driver(self, signal_name: str, *, include_source: bool = True,
                     include_trace: bool = False,
                     target: Optional[Mapping[str, Any]] = None,
                     limits: Optional[Mapping[str, Any]] = None) -> Json:
        return self.request(
            "trace.driver", target=target,
            args={"signal": signal_name, "include_source": include_source,
                  "include_trace": include_trace},
            limits=limits,
        )

    def trace_graph(self, signal_name: str, *, max_depth: int = 4,
                    include_source: bool = True, include_trace: bool = False,
                    target: Optional[Mapping[str, Any]] = None) -> Json:
        return self.request(
            "trace.graph", target=target,
            args={"signal": signal_name, "include_source": include_source,
                  "include_trace": include_trace},
            limits={"max_depth": max_depth},
        )


class XcovClient(_BaseClient):
    api_version = "xcov.v1"
    output_key = "response_format"

    def open_session(self, name: str, vdb: str, *, fake: bool = False,
                     args: Optional[Mapping[str, Any]] = None) -> Json:
        open_args = dict(args or {})
        open_args.update({"name": name, "fake": fake})
        return self.request("session.open", target={"vdb": vdb}, args=open_args)

    def close_session(self, session_id: str, *, check: bool = True) -> Json:
        return self.request("session.close", target={"session_id": session_id}, check=check)

    @contextmanager
    def session(self, name: str, vdb: str, *, fake: bool = False,
                args: Optional[Mapping[str, Any]] = None) -> Iterator["XcovClient"]:
        opened = self.open_session(name, vdb, fake=fake, args=args)
        session_id = self._session_id(opened, name)
        previous = dict(self.default_target)
        self.default_target = {"session_id": session_id}
        body_failed = False
        try:
            yield self
        except BaseException:
            body_failed = True
            raise
        finally:
            try:
                try:
                    self.close_session(session_id)
                except Exception:
                    if not body_failed:
                        raise
            finally:
                self.default_target = previous

    def coverage_summary(self, *, metrics: Optional[Iterable[str]] = None,
                         scope: Optional[str] = None, test: str = "merged",
                         group_by: str = "metric") -> Json:
        args = {"test": test, "group_by": group_by}  # type: Json
        if metrics is not None:
            args["metrics"] = list(metrics)
        if scope:
            args["scope"] = scope
        return self.request("cov.summary", args=args)

    def coverage_holes(self, *, metrics: Optional[Iterable[str]] = None,
                       scope: Optional[str] = None, test: str = "merged",
                       max_items: int = 100,
                       include_patterns: Optional[Iterable[str]] = None) -> Json:
        args = {"test": test}  # type: Json
        if metrics is not None:
            args["metrics"] = list(metrics)
        if scope:
            args["scope"] = scope
        if include_patterns:
            args["query"] = {"include_patterns": list(include_patterns)}
        return self.request("cov.holes", args=args, limits={"max_items": max_items})
