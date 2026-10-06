"""End to end through the real urllib transport against a localhost stub server.
Runs every subcommand in a subprocess with a temp HOME seeded with sentinel config files."""
import hashlib
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from fakes import HERE, KEY, fx

SCRIPT = os.path.join(HERE, "..", "scripts", "kie_live_adapter.py")
MODEL = "gpt-image-2-5-sunburst-text-to-image"
SEEN = []


class Stub(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, st=200, raw=None):
        b = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(st)
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        names = [k.lower() for k in self.headers.keys()]
        ok = self.headers.get("Authorization") == "Bearer " + KEY and "apikey" not in names
        SEEN.append((self.command, self.path, ok))
        return ok

    def do_GET(self):
        p = self.path
        if p.startswith("/files/"):
            return self._send(None, raw=b"\x89PNG\r\n\x1a\nfake")
        if not self._auth():
            return self._send({"code": 401, "msg": "unauthorized"})
        if p.endswith("/schema"):
            return self._send(fx("schema_image.json"))
        if p.startswith("/api/v1/models"):
            return self._send(fx("catalog.json"))
        if p.startswith("/api/v1/chat/credit"):
            return self._send({"code": 200, "data": 100})
        if p.startswith("/api/v1/jobs/recordInfo"):
            url = "http://127.0.0.1:%d/files/a.png" % self.server.server_port
            return self._send({"code": 200, "data": {"taskId": "T1", "state": "success", "creditsConsumed": 1,
                                                     "response": {"resultUrls": [url]}}})
        self._send({"code": 404, "msg": "no"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        if not self._auth():
            return self._send({"code": 401, "msg": "unauthorized"})
        if self.path.endswith("createTask"):
            return self._send({"code": 200, "data": {"taskId": "T1"}})
        if "/api/file-" in self.path:
            return self._send({"code": 200, "data": {"downloadUrl": "https://tempfile.example/u.png"}})
        self._send({"code": 404, "msg": "no"})


def digest_tree(root):
    h = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                h[p] = hashlib.sha256(fh.read()).hexdigest()
    return h


class NoMutation(unittest.TestCase):
    def test_every_subcommand(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_port
        with tempfile.TemporaryDirectory() as home:
            sentinels = {".claude/settings.json": '{"env":{"ANTHROPIC_BASE_URL":"x"}}',
                         ".claude-nine/settings.json": "{}", ".9router/db.json": "{}",
                         ".openclaw/openclaw.json": '{"agents":{}}'}
            for rel, body in sentinels.items():
                p = os.path.join(home, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as fh:
                    fh.write(body)
            before = {k: digest_tree(os.path.join(home, k.split("/")[0])) for k in sentinels}
            req = os.path.join(home, "req.json")
            with open(req, "w") as fh:
                json.dump({"model": MODEL, "input": {"prompt": "leaf", "resolution": "1K"}}, fh)
            pay = os.path.join(home, "pay.json")
            with open(pay, "w") as fh:
                json.dump({"prompt": "leaf"}, fh)
            img = os.path.join(home, "i.png")
            with open(img, "wb") as fh:
                fh.write(b"\x89PNG0000")
            save = os.path.join(home, "save")
            env = dict(os.environ, HOME=home, KIE_API_KEY=KEY, KIE_LIVE_ADAPTER_MODE="active",
                       KIE_LIVE_API_BASE=base, KIE_LIVE_UPLOAD_BASE=base, KIE_LIVE_MIN_SPACING="0",
                       KIE_LIVE_POLL_INITIAL="0", ANTHROPIC_API_KEY="sentinel-anthropic", PYTHONDONTWRITEBYTECODE="1")
            env.pop("OC_CONFIG", None)
            cmds = [["health"], ["credits"], ["discover", "--modality", "image"], ["schema", "--model", MODEL],
                    ["validate", "--model", MODEL, "--payload", pay], ["upload", "--file", img],
                    ["submit", "--request", req, "--dry-run"], ["submit", "--request", req],
                    ["wait", "--task-id", "T1"], ["run", "--request", req, "--save-dir", save],
                    ["save", "--task-id", "T1", "--save-dir", save]]
            outs = []
            for c in cmds:
                p = subprocess.run([sys.executable, SCRIPT] + c + ["--json"], env=env, capture_output=True, text=True, timeout=60)
                outs.append(p.stdout + p.stderr)
                self.assertEqual(p.returncode, 0, (c, p.stdout, p.stderr))
                j = json.loads(p.stdout)
                self.assertEqual(j["adapter"], "74-kie-live-adapter")
            self.assertTrue(any(os.path.getsize(os.path.join(save, f)) > 0 for f in os.listdir(save)))
            for k in sentinels:
                self.assertEqual(digest_tree(os.path.join(home, k.split("/")[0])) if k.split("/")[0] != ".openclaw"
                                 else {x: y for x, y in digest_tree(os.path.join(home, ".openclaw")).items() if "/cache/" not in x},
                                 before[k] if k.split("/")[0] != ".openclaw"
                                 else {x: y for x, y in before[k].items() if "/cache/" not in x}, k)
            self.assertEqual(env["ANTHROPIC_API_KEY"], "sentinel-anthropic")
            self.assertTrue(all(ok for _, _, ok in SEEN), "every request: Bearer only, no apikey header")
            blob = "".join(outs)
            for f in digest_tree(home):  # stdout, stderr, cache and receipts: the key never appears
                with open(f, "rb") as fh:
                    blob += fh.read().decode("latin-1")
            self.assertNotIn(KEY, blob)
            self.assertTrue(os.path.isdir(os.path.join(home, ".openclaw", "cache", "kie-live-adapter", "receipts")))


if __name__ == "__main__":
    unittest.main()
