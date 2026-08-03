#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: mock n8n Data Tables API (T6 tests)
# -----------------------------------------------------------------------------
# A throwaway local HTTP server that speaks the exact subset of the n8n public
# API v1 data-table contract used by provision-podcast-client.sh (--show) and
# revoke-podcast-client.sh (--client-email):
#   GET    /api/v1/data-tables/<id>/rows?filter=<json>&cursor=<c>  -> {data,nextCursor}
#   POST   /api/v1/data-tables/<id>/rows                           -> {success,insertedRows}
#   PATCH  /api/v1/data-tables/<id>/rows/update                    -> true
#   DELETE /api/v1/data-tables/<id>/rows/delete?filter=<json>      -> true
# Rows live in memory, seeded from STATE_DIR/seed.json, and are persisted to
# STATE_DIR/state.json after every mutation so the test can assert on them.
# Failure injection: touch STATE_DIR/control/fail_read (GET rows -> 500),
# STATE_DIR/control/fail_post (POST rows -> 500) or STATE_DIR/control/fail_patch
# (PATCH rows/update -> 500).
# Zero secrets involved: the X-N8N-API-KEY header is accepted but never used.
# =============================================================================
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

STATE_DIR = sys.argv[1]
TABLE_ID = sys.argv[2]
PORT = int(sys.argv[3])
CONTROL = os.path.join(STATE_DIR, "control")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

with open(os.path.join(STATE_DIR, "seed.json")) as f:
    ROWS = json.load(f)
NEXT_ID = max((r["id"] for r in ROWS), default=0) + 1


def save():
    with open(STATE_FILE, "w") as f:
        json.dump(ROWS, f)


def match(row, flt):
    for cond in flt.get("filters", []):
        col, val = cond["columnName"], str(cond["value"])
        if cond["condition"] == "eq" and str(row.get(col, "")) != val:
            return False
        if cond["condition"] == "neq" and str(row.get(col, "")) == val:
            return False
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        p = urlparse(self.path)
        if not p.path.startswith(f"/api/v1/data-tables/{TABLE_ID}/rows"):
            return self._send(404, {"error": "not found"})
        if os.path.exists(os.path.join(CONTROL, "fail_read")):
            return self._send(500, {"error": "injected read failure"})
        q = parse_qs(p.query)
        flt = json.loads(q["filter"][0]) if "filter" in q else {"filters": []}
        data = [r for r in ROWS if match(r, flt)]
        self._send(200, {"data": data, "nextCursor": None})

    def do_POST(self):
        p = urlparse(self.path)
        global NEXT_ID
        if not p.path.startswith(f"/api/v1/data-tables/{TABLE_ID}/rows"):
            return self._send(404, {"error": "not found"})
        if os.path.exists(os.path.join(CONTROL, "fail_post")):
            return self._send(500, {"error": "injected create failure"})
        body = self._read_body()
        added = 0
        for row in body.get("data", []):
            rec = dict(row)
            rec["id"] = NEXT_ID
            NEXT_ID += 1
            ROWS.append(rec)
            added += 1
        save()
        self._send(200, {"success": True, "insertedRows": added})

    def do_PATCH(self):
        p = urlparse(self.path)
        if not p.path.endswith("/rows/update"):
            return self._send(404, {"error": "not found"})
        if os.path.exists(os.path.join(CONTROL, "fail_patch")):
            return self._send(500, {"error": "injected patch failure"})
        body = self._read_body()
        flt = body.get("filter", {"filters": []})
        for row in ROWS:
            if match(row, flt):
                row.update(body.get("data", {}))
        save()
        self._send(200, True)

    def do_DELETE(self):
        p = urlparse(self.path)
        global ROWS
        if not p.path.endswith("/rows/delete"):
            return self._send(404, {"error": "not found"})
        q = parse_qs(p.query)
        flt = json.loads(q["filter"][0]) if "filter" in q else {"filters": []}
        ROWS = [r for r in ROWS if not match(r, flt)]
        save()
        self._send(200, True)


save()
HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
