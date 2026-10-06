#!/usr/bin/env python3
"""Hermetic n8n data-table stub for the RR-031 registry tests.

Speaks the exact API subset reconcile-rr-agent-map.sh uses, on a loopback
ephemeral port:
  GET    /api/v1/data-tables/<id>/rows?cursor=<c>  -> {data:[...], nextCursor}
  POST   /api/v1/data-tables/<id>/rows             -> {success, insertedRows}
  PATCH  /api/v1/data-tables/<id>/rows/update      -> true
Cursor pagination is REAL: rows are sliced by PAGE_SIZE and nextCursor is the
index of the next page, so a single-page reader provably loses rows.

Failure injection (touch the files, no restart needed):
  control/fail_status   -> "<code> <body-file>" served for every GET rows
  control/corrupt_page  -> every GET serves a non-JSON body
  control/fail_post     -> POST -> 500
  control/fail_patch    -> PATCH -> 500
Every mutation is appended to STATE_DIR/writes.jsonl, so a test can prove a
run wrote NOTHING (the RR-031 "abort on incomplete source" clause) instead of
inferring it from an exit code.
Usage: mock-rr-datatable.py <state-dir> <table-id> <page-size>
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

STATE = sys.argv[1]
TABLE = sys.argv[2]
PAGE = int(sys.argv[3]) if len(sys.argv) > 3 else 250
CONTROL = os.path.join(STATE, "control")
ROWS = json.load(open(os.path.join(STATE, "seed.json")))
WRITES = os.path.join(STATE, "writes.jsonl")


def save():
    with open(os.path.join(STATE, "state.json"), "w") as f:
        json.dump(ROWS, f, indent=1)


def log_write(kind, payload, matched):
    with open(WRITES, "a") as f:
        f.write(json.dumps({"op": kind, "payload": payload, "matched": matched}) + "\n")


def match(row, flt):
    for c in (flt or {}).get("filters", []):
        col, val = c["columnName"], str(c["value"])
        if c["condition"] == "eq" and str(row.get(col, "")) != val:
            return False
        if c["condition"] == "neq" and str(row.get(col, "")) == val:
            return False
    return True


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        p = urlparse(self.path)
        if not p.path.startswith("/api/v1/data-tables/%s/rows" % TABLE):
            return self._send(404, {"error": "not found"})
        fs = os.path.join(CONTROL, "fail_status")
        if os.path.exists(fs):
            spec = open(fs).read().split(None, 1)
            code = int(spec[0])
            body = b"<html><body><h1>Unauthorized</h1></body></html>" if len(spec) < 2 else open(spec[1]).read().encode()
            return self._send(code, body, "text/html")
        if os.path.exists(os.path.join(CONTROL, "corrupt_page")):
            return self._send(200, b"<html>not json</html>", "text/html")
        q = parse_qs(p.query)
        start = 0
        if "cursor" in q:
            try:
                start = int(q["cursor"][0])
            except Exception:
                return self._send(400, {"error": "bad cursor"})
        chunk = ROWS[start:start + PAGE]
        nxt = (start + PAGE) if (start + PAGE) < len(ROWS) else None
        self._send(200, {"data": chunk, "nextCursor": nxt})

    def do_POST(self):
        p = urlparse(self.path)
        if not p.path.startswith("/api/v1/data-tables/%s/rows" % TABLE):
            return self._send(404, {"error": "not found"})
        if os.path.exists(os.path.join(CONTROL, "fail_post")):
            return self._send(500, {"error": "injected create failure"})
        body = self._body()
        added = 0
        for row in body.get("data", []):
            rec = dict(row)
            ROWS.append(rec)
            added += 1
        save()
        log_write("POST", body, added)
        self._send(200, {"success": True, "insertedRows": added})

    def do_PATCH(self):
        p = urlparse(self.path)
        if not p.path.endswith("/rows/update"):
            return self._send(404, {"error": "not found"})
        if os.path.exists(os.path.join(CONTROL, "fail_patch")):
            return self._send(500, {"error": "injected patch failure"})
        body = self._body()
        flt = body.get("filter", {"filters": []})
        hit = 0
        for row in ROWS:
            if match(row, flt):
                row.update(body.get("data", {}))
                hit += 1
        save()
        log_write("PATCH", body, hit)
        self._send(200, True)


httpd = HTTPServer(("127.0.0.1", 0), H)
with open(os.path.join(STATE, "port"), "w") as f:
    f.write(str(httpd.server_port))
httpd.serve_forever()
