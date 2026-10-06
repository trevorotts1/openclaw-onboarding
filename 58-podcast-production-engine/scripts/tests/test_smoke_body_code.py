#!/usr/bin/env python3
"""A KIE credit probe must check the BODY code: HTTP 200 with {"code": 401} is a FAIL."""
import http.server
import importlib.util
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("spt", ROOT / "scripts" / "podcast-smoke-test.py")
spt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spt)

BODY = {"b": b""}


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(BODY["b"])

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["KIE_TEST_KEY_NOT_REAL"] = "dummy"
probe = {"probe": "balance", "url": "http://127.0.0.1:%d/" % srv.server_port, "method": "GET",
         "ok_status": [200], "body_code_ok": [200], "auth": "bearer",
         "key_env": ["KIE_TEST_KEY_NOT_REAL"], "timeout_s": 5}


def run(body):
    BODY["b"] = json.dumps(body).encode()
    return spt.probe_provider("kie_ai", dict(probe))["status"]


assert run({"code": 401, "msg": "no access", "data": 5000}) == "FAIL"
assert run({"data": 5000}) == "FAIL"           # no body code: fail closed
assert run({"code": 200, "msg": "success", "data": 5000}) == "PASS"
srv.shutdown()
print("test_smoke_body_code: PASS")
