import json
import os
import sys
import threading
import time
import unittest

from xdebug_lsf.bsub import BsubRunner
from xdebug_lsf.router_client import RouterClient
from xdebug_lsf.session_launcher import SessionLauncher
from xdebug_mcp.backend import XDebugMcpBackend, LsfBackend
from xdebug_mcp.server import XdebugMcpServer


FAKE_BSUB = f"{sys.executable} -m xdebug_lsf.fake_bsub"


class TestLsfRouter(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        os.environ["XDEBUG_MCP_FAKE_LSF"] = "1"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_fake_bsub_router_ready_and_ping(self):
        router = RouterClient.start(BsubRunner(FAKE_BSUB), timeout_sec=5)
        try:
            self.assertEqual(router.ready["protocol"], "xdebug-router-jsonl")
            self.assertTrue(router.ping()["ok"])
        finally:
            router.close()

    def test_fake_bsub_skips_ready_before_stdout_noise(self):
        os.environ["FAKE_BSUB_STDOUT_NOISE_BEFORE_READY"] = "1"
        router = RouterClient.start(BsubRunner(FAKE_BSUB), timeout_sec=5)
        try:
            self.assertTrue(router.ping()["ok"])
        finally:
            router.close()

    def test_session_ready_and_xout_passthrough(self):
        launcher = SessionLauncher(BsubRunner(FAKE_BSUB), fake=True)
        info = launcher.open("case_a", "waves.fsdb")
        try:
            self.assertEqual(info.session_id, "case_a")
            router = RouterClient.start(BsubRunner(FAKE_BSUB), timeout_sec=5)
            try:
                self.assertTrue(router.register({"session_id": info.session_id, "host": info.host, "port": info.port, "token": info.token})["ok"])
                rsp = router.query(info.session_id, {"api_version": "xdebug.v1", "action": "value.at", "args": {"signal": "top.clk", "time": "1ns"}}, "xout")
                self.assertTrue(rsp["ok"])
                self.assertTrue(rsp["xout"].startswith("@xdebug.value.at.v1"))
            finally:
                router.close()
        finally:
            info.process.terminate()

    def _open_fake_session(self, name):
        launcher = SessionLauncher(BsubRunner(FAKE_BSUB), fake=True)
        return launcher.open(name, f"{name}.fsdb")

    def test_router_parallel_sessions_and_out_of_order_responses(self):
        router = RouterClient.start(BsubRunner(FAKE_BSUB), timeout_sec=5)
        sessions = [self._open_fake_session("sess_a"), self._open_fake_session("sess_b"), self._open_fake_session("sess_c")]
        try:
            for info in sessions:
                self.assertTrue(router.register({"session_id": info.session_id, "host": info.host, "port": info.port, "token": info.token})["ok"])
            delays = {"sess_a": 800, "sess_b": 100, "sess_c": 400}
            start = time.time()
            for sid, delay in delays.items():
                router.process.write_json({
                    "id": sid,
                    "method": "xdebug.query",
                    "params": {
                        "session_id": sid,
                        "payload_format": "xout",
                        "request": {"api_version": "xdebug.v1", "action": "value.at", "args": {"sleep_ms": delay}},
                    },
                })
            order = [router.process.read_json_response(sid, 3)["id"] for sid in ("sess_b", "sess_c", "sess_a")]
            elapsed = time.time() - start
            self.assertEqual(order, ["sess_b", "sess_c", "sess_a"])
            self.assertLess(elapsed, 1.4)
        finally:
            router.close()
            for info in sessions:
                info.process.terminate()

    def test_same_session_serial(self):
        router = RouterClient.start(BsubRunner(FAKE_BSUB), timeout_sec=5)
        info = self._open_fake_session("sess_serial")
        try:
            self.assertTrue(router.register({"session_id": info.session_id, "host": info.host, "port": info.port, "token": info.token})["ok"])
            start = time.time()
            for rid in ("r1", "r2"):
                router.process.write_json({
                    "id": rid,
                    "method": "xdebug.query",
                    "params": {
                        "session_id": info.session_id,
                        "payload_format": "xout",
                        "request": {"api_version": "xdebug.v1", "action": "value.at", "args": {"sleep_ms": 350}},
                    },
                })
            router.process.read_json_response("r1", 3)
            router.process.read_json_response("r2", 3)
            elapsed = time.time() - start
            self.assertGreaterEqual(elapsed, 0.65)
        finally:
            router.close()
            info.process.terminate()

    def test_mcp_lsf_backend_xout_json_and_envelope(self):
        server = XdebugMcpServer(backend=XDebugMcpBackend(mode="lsf"))
        opened = server.tool_session_open({"name": "case_a", "fsdb": "waves.fsdb"})
        self.assertTrue(opened["ok"])
        xout = server.tool_query({"session": "case_a", "action": "value.at", "args": {"signal": "top.clk", "time": "1ns"}})
        self.assertIsInstance(xout, str)
        self.assertTrue(xout.startswith("@xdebug.value.at.v1"))
        js = server.tool_query({"session": "case_a", "action": "value.at", "output_format": "json"})
        self.assertTrue(js["ok"])
        env = server.tool_query({"session": "case_a", "action": "value.at", "output_format": "envelope"})
        self.assertTrue(env["ok"])
        self.assertEqual(env["payload_format"], "envelope")
        self.assertTrue(server.tool_session_close({"name": "case_a"})["ok"])

    def test_router_crash_recovery_and_session_crash_isolated(self):
        backend = LsfBackend(fake=True)
        self.assertTrue(backend.session_open("a", "a.fsdb")["ok"])
        self.assertTrue(backend.session_open("b", "b.fsdb")["ok"])
        self.assertIsInstance(backend.query("a", "value.at", {}, "xout"), str)
        old_router = backend.router
        old_router.close()
        self.assertIsInstance(backend.query("b", "value.at", {}, "xout"), str)

        session_a = backend.sessions["a"]
        session_a.process.terminate()
        failed = backend.query("a", "value.at", {}, "xout")
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["error"]["code"], "session_dead")
        self.assertIsInstance(backend.query("b", "value.at", {}, "xout"), str)


if __name__ == "__main__":
    unittest.main()
