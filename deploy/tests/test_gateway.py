#!/usr/bin/env python3
"""Test real proxy configs with a disposable backend; never load production."""
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import time
import unittest


def call(host="gateway:8080", path="/mcp", body=b"{}", ip="192.0.2.1"):
    client = HTTPConnection(host, timeout=10)
    try:
        client.request("POST" if body is not None else "GET", path, body,
                       {"Content-Type": "application/json", "X-Real-IP": ip,
                        "X-Forwarded-For": ip})
        response = client.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        client.close()


class Backend(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok\n")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        time.sleep(json.loads(body).get("hold", 0))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{}')


class GatewayTests(unittest.TestCase):
    def test_1_routes_and_body_limit(self):
        self.assertEqual(call("caddy:80", "/", None)[0], 200)
        self.assertEqual(call("caddy:80", "/healthz", None)[2], b"ok\n")
        for path in ("/statusz", "/sync/status", "/logstream/stream", "/not-public"):
            for host in ("caddy:80", "gateway:8080"):
                self.assertEqual(call(host, path, None)[0], 404)
        self.assertEqual(call(body=b"x" * 16385)[0], 413)
        self.assertEqual(call("caddy:80")[0], 200)

    def test_2_per_ip_concurrency(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            active = [pool.submit(call, body=b'{"hold":1}', ip="192.0.2.2") for _ in range(2)]
            time.sleep(0.25)
            status, headers, _ = call(ip="192.0.2.2")
            self.assertEqual(status, 429)
            self.assertEqual(headers["Retry-After"], "5")
            self.assertTrue(all(f.result()[0] == 200 for f in active))
        self.assertEqual(call(ip="192.0.2.2")[0], 200)

    def test_3_global_concurrency(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            active = [pool.submit(call, body=b'{"hold":1}', ip=f"192.0.2.{10+i}") for i in range(4)]
            time.sleep(0.25)
            self.assertEqual(call(ip="192.0.2.20")[0], 429)
            self.assertTrue(all(f.result()[0] == 200 for f in active))

    def test_4_per_ip_rate_and_spoofing(self):
        # Caddy must collapse all forged forwarding headers to the socket IP.
        results = [call("caddy:80", ip=f"198.51.100.{i}")[0] for i in range(45)]
        self.assertIn(200, results)
        self.assertIn(429, results)
        # A fresh IP still has capacity: the rejection was the per-IP limiter.
        self.assertEqual(call(ip="203.0.113.1")[0], 200)

    def test_5_global_rate(self):
        results = [call(ip=f"203.0.113.{i+10}")[0] for i in range(60)]
        self.assertIn(429, results)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backend":
        ThreadingHTTPServer(("0.0.0.0", 8765), Backend).serve_forever()
    else:
        for attempt in range(30):
            try:
                if call("caddy:80", "/healthz", None)[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.5)
        unittest.main()
