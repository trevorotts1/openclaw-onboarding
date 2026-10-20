#!/usr/bin/env python3
"""Fixture-driven fake of the Cloudflare endpoints provision-council-access.sh uses.

  fake-cloudflare-api.py --fixture F.json --log LOG --port-file PF [--state-out S.json]

Binds 127.0.0.1 on an ephemeral port and writes it to --port-file. Every request
(except /__*) appends 'METHOD path?query' to --log. After each write the full
state is dumped to --state-out. stdlib only; never a real network call.

Fixture keys (all optional except zone):
  account  expected account id (default qc-acct)    token  expected bearer token
  zone     {id, name}                                dns    [{id,type,name,content,proxied}]
  tunnels  {tunnel_id: {source, config}}             apps   [{id,name,domain,session_duration,...}]
  policies {app_id: [policy,...]}                    edge   {host|"default": {status, location}}
  fail     {dns_create: true}  -> POST dns_records answers 500
"""
import argparse, json, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

ap = argparse.ArgumentParser()
ap.add_argument("--fixture", required=True)
ap.add_argument("--log", required=True)
ap.add_argument("--port-file", required=True)
ap.add_argument("--state-out")
A = ap.parse_args()

S = json.load(open(A.fixture))
S.setdefault("account", "qc-acct")
S.setdefault("dns", []); S.setdefault("tunnels", {}); S.setdefault("apps", [])
S.setdefault("policies", {}); S.setdefault("edge", {}); S.setdefault("fail", {})
S["put_bodies"] = []
_ids = {"n": 0}


def nid(prefix):
    _ids["n"] += 1
    return "%s-%04d" % (prefix, _ids["n"])


def dump():
    if A.state_out:
        json.dump(S, open(A.state_out, "w"), indent=1)


def env(result, ok=True, errors=None, info=None):
    d = {"success": ok, "errors": errors or [], "messages": [], "result": result}
    if info:
        d["result_info"] = info
    return d


def page(items, q):
    per = int(q.get("per_page", ["100"])[0]); pg = int(q.get("page", ["1"])[0])
    total = max(1, -(-len(items) // per))
    return items[(pg - 1) * per: pg * per], {"page": pg, "per_page": per, "total_pages": total, "count": len(items)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj, headers=None):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def handle_any(self, method):
        u = urlparse(self.path); q = parse_qs(u.query); p = u.path
        if p.startswith("/__"):
            return self.send(200, S)
        with open(A.log, "a") as f:
            f.write("%s %s\n" % (method, self.path))
        m = re.match(r"^/edge/([^/]+)/", p)
        if m:
            e = S["edge"].get(m.group(1)) or S["edge"].get("default") or {"status": 200}
            hdr = {"Location": e["location"]} if e.get("location") else {}
            return self.send(e.get("status", 200), {"edge": m.group(1)}, hdr)
        if not p.startswith("/client/v4/"):
            return self.send(404, env(None, False, [{"message": "not found"}]))
        p = p[len("/client/v4"):]
        if S.get("token") and self.headers.get("Authorization") != "Bearer " + S["token"]:
            return self.send(403, env(None, False, [{"code": 10000, "message": "Authentication error"}]))
        if p == "/zones" and method == "GET":
            z = S["zone"]
            res = [z] if q.get("name", [z["name"]])[0] == z["name"] else []
            return self.send(200, env(res))
        m = re.match(r"^/zones/([^/]+)/dns_records(?:/([^/]+))?$", p)
        if m:
            if m.group(1) != S["zone"]["id"]:
                return self.send(404, env(None, False, [{"message": "zone not found: wrong zone id"}]))
            return self.dns(method, m.group(2), q)
        m = re.match(r"^/accounts/([^/]+)/(.*)$", p)
        if m:
            if m.group(1) != S["account"]:
                return self.send(403, env(None, False, [{"message": "wrong account"}]))
            return self.account(method, m.group(2), q)
        return self.send(404, env(None, False, [{"message": "no such endpoint"}]))

    def dns(self, method, rid, q):
        if method == "GET":
            items = [r for r in S["dns"]
                     if ("name" not in q or r["name"] == q["name"][0]) and ("type" not in q or r["type"] == q["type"][0])]
            items, info = page(items, q)
            return self.send(200, env(items, info=info))
        if method == "POST":
            if S["fail"].get("dns_create"):
                return self.send(500, env(None, False, [{"code": 9999, "message": "internal error (injected)"}]))
            b = self.body(); b["id"] = nid("dns"); S["dns"].append(b); dump()
            return self.send(200, env(b))
        if method == "DELETE" and rid:
            S["dns"] = [r for r in S["dns"] if r["id"] != rid]; dump()
            return self.send(200, env({"id": rid}))
        return self.send(405, env(None, False, [{"message": "method"}]))

    def account(self, method, rest, q):
        m = re.match(r"^cfd_tunnel/([^/]+)/configurations$", rest)
        if m:
            t = S["tunnels"].get(m.group(1))
            if t is None:
                return self.send(404, env(None, False, [{"message": "tunnel not found"}]))
            if method == "GET":
                return self.send(200, env({"tunnel_id": m.group(1), "version": 1,
                                           "config": t.get("config"), "source": t.get("source", "cloudflare")}))
            if method == "PUT":
                b = self.body(); t["config"] = b.get("config"); S["put_bodies"].append(b); dump()
                return self.send(200, env({"tunnel_id": m.group(1), "config": t["config"]}))
        if rest == "access/apps":
            if method == "GET":
                items, info = page(S["apps"], q)
                return self.send(200, env(items, info=info))
            if method == "POST":
                b = self.body(); app = {k: v for k, v in b.items() if k != "policies"}
                app["id"] = nid("app"); pols = []
                for pol in b.get("policies", []):
                    if set(pol) <= {"id", "precedence"}:  # reusable: attach by reference
                        pols += [x for ps in S["policies"].values() for x in ps if x["id"] == pol["id"]][:1]
                    else:
                        pols.append(dict(pol, id=nid("pol")))
                S["apps"].append(app); S["policies"][app["id"]] = pols; dump()
                return self.send(200, env(app))
        m = re.match(r"^access/apps/([^/]+)(/policies)?$", rest)
        if m and method == "GET":
            app = next((a for a in S["apps"] if a["id"] == m.group(1)), None)
            if app is None:
                return self.send(404, env(None, False, [{"message": "app not found"}]))
            return self.send(200, env(S["policies"].get(app["id"], []) if m.group(2) else app))
        return self.send(404, env(None, False, [{"message": "no such endpoint"}]))

    def do_GET(self): self.handle_any("GET")
    def do_POST(self): self.handle_any("POST")
    def do_PUT(self): self.handle_any("PUT")
    def do_DELETE(self): self.handle_any("DELETE")


srv = HTTPServer(("127.0.0.1", 0), H)
open(A.port_file, "w").write(str(srv.server_address[1]))
dump()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    sys.exit(0)
