#!/usr/bin/env python3
"""Fixture-driven fake of the one GoHighLevel endpoint ghl-client-emails.py reads.

  fake-ghl-api.py --fixture F.json --log LOG --port-file PF

Binds 127.0.0.1 on an ephemeral port and writes it to --port-file. Every request
appends 'METHOD path?query' to --log (never the token). stdlib only.

Fixture: {"token": "...", "location": "<id>", "contacts": [{id, firstName, lastName,
          email, phone, companyName, additionalEmails}], "fail": {"429_once": true}}
GET /contacts/?locationId&query&limit&page : contacts whose name, email, additional
emails, phone or company contain the query (case-insensitive), paged by limit/page,
{"contacts": [...], "meta": {"total": N}}. A wrong bearer token or Version header is
401; a Python-urllib User-Agent is 403 'error code: 1010' (as Cloudflare does).
"""
import argparse, json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

ap = argparse.ArgumentParser()
ap.add_argument("--fixture", required=True)
ap.add_argument("--log", required=True)
ap.add_argument("--port-file", required=True)
A = ap.parse_args()
S = json.load(open(A.fixture))
S.setdefault("contacts", []); S.setdefault("fail", {})
_n = {"req": 0}


def hay(c):
    parts = [c.get("firstName"), c.get("lastName"), "%s %s" % (c.get("firstName") or "", c.get("lastName") or ""),
             c.get("email"), c.get("phone"), c.get("companyName")] + list(c.get("additionalEmails") or [])
    return " | ".join(str(p) for p in parts if p).lower()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj):
        raw = (obj if isinstance(obj, str) else json.dumps(obj)).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        with open(A.log, "a") as f:
            f.write("GET %s\n" % self.path)
        _n["req"] += 1
        if (self.headers.get("User-Agent") or "").startswith("Python-urllib"):
            return self.send(403, "error code: 1010")
        if self.headers.get("Authorization") != "Bearer " + S.get("token", "") or self.headers.get("Version") != "2021-07-28":
            return self.send(401, {"message": "Invalid JWT"})
        if S["fail"].get("429_once") and _n["req"] == 1:
            return self.send(429, {"message": "Too many requests"})
        if S["fail"].get("always_500"):
            return self.send(500, {"message": "boom"})
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path not in ("/contacts/", "/contacts"):
            return self.send(404, {"message": "not found"})
        if q.get("locationId", [""])[0] != S.get("location"):
            return self.send(403, {"message": "The token does not have access to this location."})
        text = q.get("query", [""])[0].lower()
        items = [c for c in S["contacts"] if text in hay(c)]
        lim = int(q.get("limit", ["20"])[0]); pg = int(q.get("page", ["1"])[0])
        return self.send(200, {"contacts": items[(pg - 1) * lim: pg * lim], "meta": {"total": len(items)}})

    def do_POST(self):
        with open(A.log, "a") as f:
            f.write("POST %s\n" % self.path)
        self.send(405, {"message": "read only fake"})

    do_PUT = do_DELETE = do_PATCH = do_POST


srv = HTTPServer(("127.0.0.1", 0), H)
open(A.port_file, "w").write(str(srv.server_address[1]))
try:
    srv.serve_forever()
except KeyboardInterrupt:
    sys.exit(0)
