#!/usr/bin/env python3
"""Fixture-driven fake of the Cloudflare endpoints provision-council-access.sh uses.

  fake-cloudflare-api.py --fixture F.json --log LOG --port-file PF [--state-out S.json]

Binds 127.0.0.1 on an ephemeral port and writes it to --port-file. Every request
(except /__*) appends 'METHOD path?query' to --log. After each write the full
state is dumped to --state-out. stdlib only; never a real network call.

Fixture keys (all optional except zone):
  account  expected account id (default qc-acct)    token  expected bearer token
  zone     {id, name}                                dns    [{id,type,name,content,proxied}]
  tunnels  {tunnel_id: {name, source, config, conns, status, token, deleted_at, config_missing}}
           conns [] = connector down; a conn may carry origin_ip (the connector's public address);
           status defaults to "healthy" (GET cfd_tunnel/<id>); token defaults to qc-tunnel-TOKEN-<id>;
           deleted_at set or config_missing true -> GET .../configurations answers 404
           "Configuration for tunnel not found"; a tunnel id not in the fixture answers 404 everywhere
  apps     [{id,name,domain,session_duration,...}]
  policies {app_id: [policy,...]}                    edge   {host|"default": {status, location}}
  idps     [{id,type,name}]  Access identity providers (ensure-cc-access.sh)
  fail     {dns_create: true}  -> POST dns_records answers 500; {connections: true} -> connections answers 500
           {app_create: true}  -> POST access/apps answers 500
           {tunnel_create: true} -> POST cfd_tunnel answers 500
           {policy_update: true} -> PUT access/apps/<id>/policies/<pid> answers 400
           {tunnel_read: true} -> GET cfd_tunnel/<id> and GET .../configurations answer 503
           {config_read_after_put: true} -> GET .../configurations answers 503 once that tunnel's
             configuration has been PUT (a read failing during a rollback)
  PUT access/apps/<id>/policies/<pid> replaces an app-scoped policy (reusable or a
  read-only field in the body -> 400); every PUT body is kept in state put_bodies.
  POST cfd_tunnel creates a remote-managed tunnel with no connector (status "inactive").
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
S.setdefault("policies", {}); S.setdefault("edge", {}); S.setdefault("fail", {}); S.setdefault("idps", [])
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
        if rest == "cfd_tunnel" and method == "GET":
            want = q.get("name", [None])[0]
            items = [dict(id=k, name=t.get("name", k), status=t.get("status", "healthy"), deleted_at=t.get("deleted_at"))
                     for k, t in S["tunnels"].items() if want is None or t.get("name") == want]
            if q.get("is_deleted", [""])[0] == "false":
                items = [i for i in items if not i["deleted_at"]]
            return self.send(200, env(items))
        if rest == "cfd_tunnel" and method == "POST":
            if S["fail"].get("tunnel_create"):
                return self.send(500, env(None, False, [{"code": 9999, "message": "internal error (injected)"}]))
            b = self.body(); tid = nid("tun")
            S["tunnels"][tid] = {"name": b.get("name"), "source": b.get("config_src", "local"), "config": None,
                                 "conns": [], "status": "inactive"}
            dump()
            return self.send(200, env({"id": tid, "name": b.get("name"), "status": "inactive"}))
        m = re.match(r"^cfd_tunnel/([^/]+)(/token)?$", rest)
        if m and method == "GET":
            t = S["tunnels"].get(m.group(1))
            if t is None:
                return self.send(404, env(None, False, [{"code": 1003, "message": "tunnel not found"}]))
            if m.group(2):
                return self.send(200, env(t.get("token", "qc-tunnel-TOKEN-" + m.group(1))))
            if S["fail"].get("tunnel_read"):
                return self.send(503, env(None, False, [{"message": "service unavailable (injected)"}]))
            return self.send(200, env({"id": m.group(1), "name": t.get("name", m.group(1)), "status": t.get("status", "healthy"),
                                       "deleted_at": t.get("deleted_at")}))
        m = re.match(r"^cfd_tunnel/([^/]+)/connections$", rest)
        if m and method == "GET":
            t = S["tunnels"].get(m.group(1))
            if t is None:
                return self.send(404, env(None, False, [{"message": "tunnel not found"}]))
            if S["fail"].get("connections"):
                return self.send(500, env(None, False, [{"message": "internal error (injected)"}]))
            # default: one live connection; fixture "conns": [] means the connector is down
            conns = t.get("conns", [{"id": "conn-1", "colo_name": "ORD", "is_pending_reconnect": False}])
            return self.send(200, env([{"id": "client-1", "conns": conns}] if conns else []))
        m = re.match(r"^cfd_tunnel/([^/]+)/configurations$", rest)
        if m:
            t = S["tunnels"].get(m.group(1))
            if t is None:
                return self.send(404, env(None, False, [{"message": "tunnel not found"}]))
            if method == "GET" and (S["fail"].get("tunnel_read") or (S["fail"].get("config_read_after_put") and t.get("_put"))):
                return self.send(503, env(None, False, [{"message": "service unavailable (injected)"}]))
            if method == "GET" and (t.get("deleted_at") or t.get("config_missing")):
                return self.send(404, env(None, False, [{"code": 1003, "message": "Configuration for tunnel not found"}]))
            if method == "GET":
                return self.send(200, env({"tunnel_id": m.group(1), "version": 1,
                                           "config": t.get("config"), "source": t.get("source", "cloudflare")}))
            if method == "PUT":
                b = self.body(); t["config"] = b.get("config"); S["put_bodies"].append(b)
                if S["fail"].get("config_read_after_put"):
                    t["_put"] = True
                dump()
                return self.send(200, env({"tunnel_id": m.group(1), "config": t["config"]}))
        if rest == "access/identity_providers" and method == "GET":
            return self.send(200, env(S["idps"]))
        if rest == "access/apps":
            if method == "GET":
                items, info = page(S["apps"], q)
                return self.send(200, env(items, info=info))
            if method == "POST":
                if S["fail"].get("app_create"):
                    return self.send(500, env(None, False, [{"code": 9999, "message": "internal error (injected)"}]))
                b = self.body(); app = {k: v for k, v in b.items() if k != "policies"}
                app["id"] = nid("app"); pols = []
                for pol in b.get("policies", []):
                    if set(pol) <= {"id", "precedence"}:  # reusable: attach by reference
                        pols += [x for ps in S["policies"].values() for x in ps if x["id"] == pol["id"]][:1]
                    else:
                        pols.append(dict(pol, id=nid("pol")))
                S["apps"].append(app); S["policies"][app["id"]] = pols; dump()
                return self.send(200, env(app))
        m = re.match(r"^access/apps/([^/]+)/policies/([^/]+)$", rest)
        if m and method == "PUT":
            # app-scoped policy update; a reusable policy or a read-only field in the body is refused, as Cloudflare does
            pols = S["policies"].get(m.group(1))
            old = next((x for x in (pols or []) if x["id"] == m.group(2)), None)
            if old is None:
                return self.send(404, env(None, False, [{"message": "policy not found"}]))
            b = self.body(); S["put_bodies"].append(b)
            if old.get("reusable") or S["fail"].get("policy_update"):
                return self.send(400, env(None, False, [{"code": 12130, "message": "reusable policy cannot be edited here"}]))
            bad = sorted(set(b) & {"id", "created_at", "updated_at", "reusable", "app_count", "uid"})
            if bad:
                return self.send(400, env(None, False, [{"message": "read-only field(s): " + ",".join(bad)}]))
            new = dict(b, id=old["id"])
            for k in ("created_at", "reusable"):
                if k in old:
                    new[k] = old[k]
            new["updated_at"] = "2026-10-21T00:00:00Z"
            pols[pols.index(old)] = new; dump()
            return self.send(200, env(new))
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
