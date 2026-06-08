import json
import unittest

from xdebug.mcp.server import XdebugMcpServer


class FakeRunner:
    def __init__(self):
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        action = request.get("action")
        if action == "session.open":
            name = request.get("args", {}).get("name", "case")
            return {
                "ok": True,
                "action": action,
                "summary": {"session_id": name, "mode": "waveform"},
                "session": {"id": name},
            }
        if action == "session.close":
            return {"ok": True, "action": action, "summary": {"removed": True}}
        if action == "actions":
            return {"ok": True, "action": action, "data": {"implemented": ["value.at"]}}
        if action == "schema":
            return {"ok": True, "action": action, "data": {"schema": {"type": "object"}}}
        return {"ok": True, "action": action, "target": request.get("target", {}), "args": request.get("args", {})}


class TestXdebugMcpServer(unittest.TestCase):
    def test_tools_list_contains_core_tools(self):
        server = XdebugMcpServer(FakeRunner())
        names = {tool["name"] for tool in server.tools()}
        self.assertIn("xdebug_request", names)
        self.assertIn("xdebug_session_open", names)
        self.assertIn("xdebug_query", names)

    def test_open_session_tracks_default_and_query_uses_it(self):
        runner = FakeRunner()
        server = XdebugMcpServer(runner)
        result = server.tool_session_open({"name": "wave_a", "fsdb": "waves.fsdb"})
        self.assertTrue(result["ok"])
        self.assertEqual(server.default_session, "wave_a")
        self.assertIn("wave_a", server.sessions)

        query = server.tool_query({"action": "value.at", "args": {"signal": "top.clk", "time": "1ns"}})
        self.assertTrue(query["ok"])
        self.assertEqual(runner.requests[-1]["target"], {"session_id": "wave_a"})
        self.assertEqual(runner.requests[-1]["output"]["format"], "json")

    def test_query_explicit_target_overrides_default_session(self):
        runner = FakeRunner()
        server = XdebugMcpServer(runner)
        server.tool_session_open({"name": "wave_a", "fsdb": "waves.fsdb"})
        server.tool_query({"action": "value.at", "target": {"fsdb": "other.fsdb"}, "args": {}})
        self.assertEqual(runner.requests[-1]["target"], {"fsdb": "other.fsdb"})

    def test_multiple_sessions_can_switch_default(self):
        runner = FakeRunner()
        server = XdebugMcpServer(runner)
        server.tool_session_open({"name": "wave_a", "fsdb": "a.fsdb"})
        server.tool_session_open({"name": "wave_b", "fsdb": "b.fsdb"})
        self.assertEqual(server.default_session, "wave_b")
        used = server.tool_session_use({"name": "wave_a"})
        self.assertTrue(used["ok"])
        self.assertEqual(server.default_session, "wave_a")
        server.tool_query({"action": "scope.list"})
        self.assertEqual(runner.requests[-1]["target"], {"session_id": "wave_a"})

    def test_call_tool_wraps_payload_as_mcp_content(self):
        server = XdebugMcpServer(FakeRunner())
        response = server.call_tool("xdebug_actions", {})
        self.assertFalse(response["isError"])
        self.assertEqual(response["content"][0]["type"], "text")
        self.assertTrue(json.loads(response["content"][0]["text"])["ok"])

    def test_jsonrpc_tools_list(self):
        server = XdebugMcpServer(FakeRunner())
        response = server.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response["id"], 1)
        self.assertIn("tools", response["result"])

    def test_session_required_without_target_or_default(self):
        server = XdebugMcpServer(FakeRunner())
        result = server.tool_query({"action": "value.at"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "SESSION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
