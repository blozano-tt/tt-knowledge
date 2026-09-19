"""Exercise the policy independently of the vector database."""
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location(
    "public_mcp", Path(__file__).parents[1] / "scripts" / "public-mcp.py")
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


def request(name="mempalace_search", **arguments):
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def server(dispatch=lambda req: {"result": "ok"}, read_only=True):
    tools = {name: {"input_schema": {"type": "object", "properties": {
        "query": {"type": "string", "maxLength": 250},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "offset": {"type": "integer", "minimum": 0}}, "required": ["query"]}}
        for name in public.PUBLIC_TOOLS | {"mempalace_add_drawer", "future_admin_tool"}}
    return SimpleNamespace(_READ_ONLY=read_only, TOOLS=tools, _http_dispatch=dispatch)


class PublicPolicyTests(unittest.TestCase):
    def setUp(self):
        self.server = server()
        public.install(self.server)

    def test_fail_closed_and_advertised_allowlist(self):
        self.assertEqual(set(self.server.TOOLS), public.PUBLIC_TOOLS)
        with self.assertRaises(RuntimeError):
            public.install(server(read_only=False))
        missing = server()
        del missing.TOOLS["mempalace_search"]
        with self.assertRaises(RuntimeError):
            public.install(missing)

    def test_write_admin_and_batch_cannot_reach_dispatch(self):
        for name in ("mempalace_add_drawer", "mempalace_reconnect", "mempalace_event_wait",
                     "future_admin_tool", ["mempalace_search"]):
            self.assertEqual(self.server._http_dispatch(request(name))["error"]["code"], -32003)
        self.assertEqual(self.server._http_dispatch([request()])["error"]["code"], -32600)

    def test_invalid_arguments_cannot_reach_dispatch(self):
        for args in ({}, {"query": "x", "limit": 21}, {"query": "x", "limit": -1},
                     {"query": "x", "limit": "20"}, {"query": "x" * 251},
                     {"query": "x", "offset": 100001}, {"query": "x", "unexpected": True}):
            self.assertEqual(self.server._http_dispatch(request(**args))["error"]["code"], -32602)
        self.assertEqual(self.server._http_dispatch(request(query="Tensix", limit=3)), {"result": "ok"})

    def test_active_work_is_bounded_and_slots_released(self):
        entered = [Event() for _ in range(public.MAX_ACTIVE_REQUESTS)]
        release = Event()
        def blocking(req):
            entered[req["id"]].set()
            release.wait(5)
            raise RuntimeError("backend failure")
        guarded = server(blocking)
        public.install(guarded)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(guarded._http_dispatch, dict(request(query="x"), id=i))
                       for i in range(4)]
            try:
                self.assertTrue(all(event.wait(2) for event in entered))
                self.assertEqual(guarded._http_dispatch(request(query="x"))["error"]["code"], -32000)
            finally:
                release.set()
            for future in futures:
                with self.assertRaises(RuntimeError):
                    future.result()
        # Backend exceptions release capacity; this gets through to the handler.
        with self.assertRaises(RuntimeError):
            guarded._http_dispatch(dict(request(query="x"), id=0))


if __name__ == "__main__":
    unittest.main()
