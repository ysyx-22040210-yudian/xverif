from __future__ import annotations

import pytest

from xverif_sdk import CallbackTransport, ToolResponseError, XcovClient, XdebugClient


def _ok(request):
    action = request["action"]
    if action == "session.open":
        session_id = request.get("args", {}).get("name", "session")
        return {"ok": True, "action": action, "summary": {"session_id": session_id}}
    return {"ok": True, "action": action, "data": {"request": request}}


def test_xdebug_session_and_convenience_requests():
    transport = CallbackTransport(_ok)
    client = XdebugClient(transport)
    with client.session("wave0", fsdb="waves.fsdb"):
        response = client.value_batch_at(["top.valid", "top.ready"], "100ns")
        client.trace_graph("top.ready", max_depth=7)
    assert [request["action"] for request in transport.requests] == [
        "session.open", "value.batch_at", "trace.graph", "session.close"]
    assert transport.requests[0]["target"] == {"fsdb": "waves.fsdb"}
    value_request = response["data"]["request"]
    assert value_request["target"] == {"session_id": "wave0"}
    assert value_request["args"]["signals"] == ["top.valid", "top.ready"]
    assert transport.requests[2]["limits"]["max_depth"] == 7
    assert transport.requests[-1]["target"] == {"session_id": "wave0"}


def test_xcov_session_and_query_mapping():
    transport = CallbackTransport(_ok)
    client = XcovClient(transport)
    with client.session("cov0", "simv.vdb", fake=True):
        client.coverage_summary(metrics=["line", "toggle"], scope="top.u")
        client.coverage_holes(metrics=["branch"], max_items=5,
                              include_patterns=["*fifo*"])
    assert transport.requests[0]["target"] == {"vdb": "simv.vdb"}
    assert transport.requests[0]["args"]["fake"] is True
    assert transport.requests[1]["output"]["response_format"] == "json"
    assert transport.requests[1]["args"]["scope"] == "top.u"
    assert transport.requests[2]["limits"] == {"max_items": 5}
    assert transport.requests[2]["args"]["query"]["include_patterns"] == ["*fifo*"]


def test_raw_request_keeps_future_actions_extensible():
    transport = CallbackTransport(_ok)
    client = XdebugClient(transport)
    response = client.raw_request({
        "action": "site.future.analysis",
        "target": {"fsdb": "waves.fsdb"},
        "args": {"site_option": 42},
        "trace_id": "trace-1",
    })
    request = response["data"]["request"]
    assert request["api_version"] == "xdebug.v1"
    assert request["trace_id"] == "trace-1"
    assert request["args"]["site_option"] == 42
    assert request["output"]["format"] == "json"


def test_structured_tool_errors_are_raised_without_losing_response():
    response = {"ok": False, "action": "trace.driver",
                "error": {"code": "SIGNAL_NOT_FOUND", "message": "missing"}}
    client = XdebugClient(CallbackTransport(lambda request: response))
    with pytest.raises(ToolResponseError) as caught:
        client.trace_driver("top.missing")
    assert caught.value.code == "SIGNAL_NOT_FOUND"
    assert caught.value.response is response or caught.value.response == response
