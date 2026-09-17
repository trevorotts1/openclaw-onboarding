#!/usr/bin/env python3
"""Stub RR escalation intake for tests/test_intake_auth_check.sh.

Answers in ONE of the shapes the live intake actually produces, selected by
RR_STUB_MODE, and journals every request (headers + body) to RR_STUB_JOURNAL so
the test can prove WHERE the credential travelled. It never echoes a credential
to stdout.

Modes:
  suppressed  200 {"accepted":true,"ticketId":null,"status":"test_suppressed"}
  forbidden   403 {"status":"unauthorized"}
  unauth401   401 {"status":"unauthorized"}
  oldrelay    200 {"status":"missing_message"}
  servererr   500 {"status":"error"}
  garbage     200 {"hello":"world"}

Prints the bound port on stdout as `PORT <n>` and then serves forever.
"""
import http.server
import json
import os
import socketserver
import sys
import threading

MODE = os.environ.get("RR_STUB_MODE", "suppressed")
JOURNAL = os.environ.get("RR_STUB_JOURNAL", "")

BODIES = {
    "suppressed": (200, {"accepted": True, "ticketId": None,
                         "status": "test_suppressed"}),
    "forbidden":  (403, {"status": "unauthorized"}),
    "unauth401":  (401, {"status": "unauthorized"}),
    "oldrelay":   (200, {"status": "missing_message"}),
    "servererr":  (500, {"status": "error"}),
    "garbage":    (200, {"hello": "world"}),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the test output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        if JOURNAL:
            with open(JOURNAL, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": raw,
                }) + "\n")
        code, payload = BODIES.get(MODE, BODIES["suppressed"])
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


class Server(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    srv = Server(("127.0.0.1", 0), Handler)
    sys.stdout.write("PORT %d\n" % srv.server_address[1])
    sys.stdout.flush()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        t.join()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
