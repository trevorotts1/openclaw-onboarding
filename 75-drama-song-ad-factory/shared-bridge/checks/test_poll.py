#!/usr/bin/env python3
"""W1-box-bridge-U1 — enroll, link, poll and the machine.key fallback.

Proves, against a local fake studio (stdlib `http.server`, no network):

  1  key fallback order: env DS_KEY → $DRAMA_STUDIO_STATE/machine.key →
     ~/.drama-studio/machine.key — with a positive control per rung, so an
     empty answer can never mean "the reader is broken"
  2  base address fallback: --base-url → machine.url → studio.url
  3  enroll writes machine.key 0600 in a 0700 folder, never prints the key,
     and refuses a second time (with a negative control: no secret → refused)
  4  poll with no order → no output at all, exit 0
  5  poll with an order → claim posted, run dir created, `factory.py card`
     invoked with every reply IN ORDER, one JSON line printed — and a second
     poll of the same order RECONCILES (D35): the same line re-emitted for the
     pending wake, no second claim post, no second card replay, and silence
     only after `wake --ack` records execution-accepted
  6  publish-approval / approval-answer are registered and refuse without a
     key BEFORE any module import or request
  7  link --new stores client.url 0600 and prints it; a plain link re-reads
     the stored value without touching the server again

Run: python3 checks/test_poll.py
Exit: 0 all pass · 1 at least one failed
"""
import http.server
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent
sys.path.insert(0, str(BRIDGE_DIR))
import studio_bridge as bridge  # noqa: E402

PY = sys.executable
BRIDGE = str(BRIDGE_DIR / "studio_bridge.py")

CLIENT = "c-" + "a" * 32
ENROLL_KEY = "enroll-" + "b" * 40
MACHINE_KEY = "machine-" + "c" * 40
LINK_URL = "https://studio.example/#k=" + "d" * 32
ENROLL_SECRET = "fleet-enrollment-secret-fixture"
STUDIO = {"line": None, "order": {}, "seen": []}


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class _FakeStudio(http.server.BaseHTTPRequestHandler):
    """The service contract the bridge speaks, on 127.0.0.1 only."""

    def _send(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._route(b"")

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        self._route(self.rfile.read(n) if n else b"")

    def _route(self, raw):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            body = {}
        rec = {"method": self.command, "path": path, "body": body,
               "key": self.headers.get("x-ds-key") or ""}
        STUDIO["seen"].append(rec)
        if path != "/api/studio/enroll" and not rec["key"]:
            return self._send(401, {"ok": False, "code": "AF-DS-AUTH",
                                    "message": "no key"})
        if path == "/api/studio/enroll":
            if body.get("enrollment_secret") != ENROLL_SECRET:
                return self._send(403, {"ok": False, "code": "AF_ENROLL_REFUSED",
                                        "message": "Registration was refused."})
            return self._send(201, {"ok": True, "client_id": CLIENT,
                                    "key": ENROLL_KEY})
        if path == "/api/studio/link":
            return self._send(200, {"ok": True, "link": LINK_URL})
        if path == "/api/studio/checkin":
            return self._send(200, {"ok": True, "checked_in_at": 1,
                                    "line": STUDIO["line"]})
        if path.endswith("/state") and "/orders/" in path:
            return self._send(200, {"ok": True, "order": {"state": "claimed"}})
        if "/orders/" in path:
            return self._send(200, {"ok": True, "order": STUDIO["order"]})
        return self._send(404, {"ok": False, "code": "AF-DS-NOT-FOUND",
                                "message": "No route."})

    def log_message(self, *args):
        pass


class PollBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeStudio)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="u1-poll-", dir=str(HERE)))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.state = self.tmp / "state"
        self.home.mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)
        self.runs = self.tmp / "runs"
        self.factory_log = self.tmp / "factory-argv.jsonl"
        self.skill_root = self._stub_skill_root()
        STUDIO["line"] = None
        STUDIO["order"] = {}
        STUDIO["seen"] = []

    def _stub_skill_root(self):
        """A skill root whose factory.py records its argv and nothing else."""
        core = self.tmp / "stub-skill" / "scripts" / "core" / "intake_preflight"
        core.mkdir(parents=True, exist_ok=True)
        (core / "factory.py").write_text(
            "import json, os, sys\n"
            "with open(os.environ['STUB_FACTORY_LOG'], 'a', encoding='utf-8') as fh:\n"
            "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.write('next question\\n')\n",
            encoding="utf-8")
        return self.tmp / "stub-skill"

    def env(self, **over):
        env = {"PATH": os.environ.get("PATH", ""),
               "HOME": str(self.home),
               "DRAMA_STUDIO_STATE": str(self.state),
               "PYTHONDONTWRITEBYTECODE": "1",
               "STUB_FACTORY_LOG": str(self.factory_log)}
        env.update({k: str(v) for k, v in over.items()})
        return env

    def run_bridge(self, args, **over):
        return subprocess.run([PY, BRIDGE] + list(args),
                              capture_output=True, text=True,
                              env=self.env(**over))

    def poll(self, **over):
        return self.run_bridge(["poll", "--skill-root", str(self.skill_root),
                                "--runs", str(self.runs),
                                "--base-url", self.base], **over)

    # -- 1 the key fallback ---------------------------------------------------

    def test_key_fallback_order(self):
        (self.state / "machine.key").write_text("state-key\n", encoding="utf-8")
        (self.home / ".drama-studio").mkdir(parents=True, exist_ok=True)
        (self.home / ".drama-studio" / "machine.key").write_text(
            "home-key\n", encoding="utf-8")
        env = self.env(DS_KEY="env-key")
        self.assertEqual(bridge.load_key(env), "env-key")     # env wins
        env = self.env()
        self.assertEqual(bridge.load_key(env), "state-key")   # state wins over home
        env = {"HOME": str(self.home)}
        self.assertEqual(bridge.load_key(env), "home-key")    # home is the last rung
        # controls on the SAME instrument: each rung answers when it is the only one
        (self.state / "machine.key").write_text("state-key-2\n", encoding="utf-8")
        self.assertEqual(bridge.load_key(self.env()), "state-key-2")
        self.assertEqual(bridge.load_key({"HOME": str(self.tmp / "empty")}), "")
        self.assertNotIn("env-key", bridge.load_key(self.env()))

    # -- 2 the base address ---------------------------------------------------

    def test_base_url_fallback(self):
        env = self.env()
        self.assertEqual(bridge.resolve_base_url("https://given.example/", env),
                         "https://given.example")
        (self.state / "machine.url").write_text("https://state.example\n",
                                                encoding="utf-8")
        self.assertEqual(bridge.resolve_base_url(None, env), "https://state.example")
        home_state = self.home / ".drama-studio"
        home_state.mkdir(parents=True, exist_ok=True)
        (home_state / "studio.url").write_text("https://home.example\n",
                                               encoding="utf-8")
        self.assertEqual(bridge.resolve_base_url(None, {"HOME": str(self.home)}),
                         "https://home.example")
        # control: with nothing stored and no --base-url there is no address
        self.assertEqual(bridge.resolve_base_url(None, {"HOME": str(self.tmp / "x")}),
                         "")

    # -- 3 enroll -------------------------------------------------------------

    def test_enroll_writes_private_files_and_refuses_twice(self):
        env = {"DS_ENROLLMENT_SECRET": ENROLL_SECRET}
        p = self.run_bridge(["enroll", "--base-url", self.base,
                             "--label", "fixture-box"], **env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.state / "machine.key").read_text(encoding="utf-8").strip(),
                         ENROLL_KEY)
        self.assertEqual((self.state / "machine.url").read_text(encoding="utf-8").strip(),
                         self.base)
        self.assertEqual(_mode(self.state / "machine.key"), 0o600)
        self.assertEqual(_mode(self.state / "machine.url"), 0o600)
        self.assertEqual(_mode(self.state), 0o700)
        self.assertNotIn(ENROLL_KEY, p.stdout + p.stderr)

        # control 1: no enrollment secret → refused, before any request
        bare = self.run_bridge(["enroll", "--base-url", self.base],
                               DRAMA_STUDIO_STATE=str(self.tmp / "state2"))
        self.assertEqual(bare.returncode, 2)
        self.assertIn("NO_ENROLLMENT_SECRET", bare.stdout)

        # control 2: a second enroll is refused and changes nothing
        enrolls = len([r for r in STUDIO["seen"] if r["path"] == "/api/studio/enroll"])
        again = self.run_bridge(["enroll", "--base-url", self.base], **env)
        self.assertEqual(again.returncode, 2)
        self.assertIn("ALREADY_ENROLLED", again.stdout)
        self.assertEqual(len([r for r in STUDIO["seen"]
                              if r["path"] == "/api/studio/enroll"]), enrolls)
        self.assertEqual((self.state / "machine.key").read_text(encoding="utf-8").strip(),
                         ENROLL_KEY)
        self.assertNotIn(ENROLL_KEY, again.stdout + again.stderr)

    # -- 4 poll with no order -------------------------------------------------

    def test_poll_no_order_is_silent(self):
        p = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, "")
        self.assertEqual(p.stderr, "")
        # control: the same server, the same key, an order appears → output
        STUDIO["line"] = 'DRAMA_ORDER r_ff00ff00 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_ff00ff00", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"]}
        ok = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertNotEqual(ok.stdout, "")

    # -- 5 poll with an order -------------------------------------------------

    def test_poll_claims_replays_and_prints_one_json_line(self):
        STUDIO["line"] = 'DRAMA_ORDER r_ab12cd34 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_ab12cd34", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["1", "2", "yes"],
                           "upload_ids": ["u_1"]}
        p = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, p.stdout)
        out = json.loads(lines[0])
        run_dir = self.runs / "r_ab12cd34"
        self.assertEqual(out["order_id"], "r_ab12cd34")
        self.assertEqual(out["run_dir"], str(run_dir))
        self.assertIn("factory.py next --run-dir", out["next"])

        control = run_dir / "control" / "studio-order.json"
        self.assertTrue(control.is_file())
        stored = json.loads(control.read_text(encoding="utf-8"))
        self.assertEqual(stored, {"base_url": self.base, "client_id": CLIENT,
                                  "order_id": "r_ab12cd34",
                                  "title": "Spring Sale"})

        # every reply reached the card, in order, in ONE argv list (no shell)
        calls = [json.loads(l) for l in
                 self.factory_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(calls), 1, calls)
        argv = calls[0]
        self.assertEqual(argv[:6],
                         ["card", "--step", "--format", "text",
                          "--run-dir", str(run_dir)])
        self.assertEqual(argv[argv.index("--reply", 4):],
                         ["--reply", "1", "--reply", "2", "--reply", "yes"])

        # the chain the service saw: check-in → state claim → order fetch
        paths = [(r["method"], r["path"], r["key"]) for r in STUDIO["seen"]]
        self.assertIn(("POST", "/api/studio/checkin", MACHINE_KEY), paths)
        self.assertIn(("POST", "/api/studio/orders/r_ab12cd34/state", MACHINE_KEY), paths)
        self.assertIn(("GET", "/api/studio/orders/r_ab12cd34", MACHINE_KEY), paths)
        self.assertNotIn(MACHINE_KEY, p.stdout)
        self.assertNotIn(MACHINE_KEY, control.read_text(encoding="utf-8"))

        # D35 reconcile: a repeated poll of OUR OWN claim is not quiet success.
        # The line is re-emitted (the wake request persists until the runtime
        # ack), the claim event is never re-posted, and the card is replayed
        # exactly once. After `wake --ack` (execution-accepted) the poll goes
        # silent for good — no duplicate campaign can start.
        claims = len([r for r in STUDIO["seen"] if r["path"].endswith("/state")])
        again = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        lines = [l for l in again.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, again.stdout)
        out2 = json.loads(lines[0])
        self.assertEqual(out2["order_id"], out["order_id"])
        self.assertEqual(out2["run_dir"], out["run_dir"])
        self.assertEqual(out2["next"], out["next"])
        self.assertEqual(out2["db"], out["db"])          # same ledger, same order
        self.assertEqual(len([r for r in STUDIO["seen"] if r["path"].endswith("/state")]),
                         claims)
        self.assertEqual(len([json.loads(l) for l in
                              self.factory_log.read_text(encoding="utf-8").splitlines()]),
                         1)
        # the supported runtime acknowledges the wake -> the claim is final
        ack = subprocess.run([PY, BRIDGE, "wake", "--ack",
                              "--order", out["order_id"], "--db", out["db"]],
                             capture_output=True, text=True, env=self.env(DS_KEY=MACHINE_KEY))
        self.assertEqual(ack.returncode, 0, ack.stdout + ack.stderr)
        done = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")                # execution-accepted: silent

    def test_poll_without_a_key_refuses(self):
        p = self.poll()
        self.assertEqual(p.returncode, 2)
        self.assertIn("NO_KEY", p.stdout)
        self.assertEqual(STUDIO["seen"], [])

    # -- 6 approvals subcommands (U2 owns approvals_bridge) -------------------

    def test_approval_subcommands_registered_and_key_gated(self):
        help_out = self.run_bridge(["--help"]).stdout
        for name in ("publish-approval", "approval-answer", "enroll", "link", "poll"):
            self.assertIn(name, help_out)
        # no key → refused BEFORE any module import or request
        a = self.run_bridge(["approval-answer", "--order", "r_1", "--stage", "script",
                             "--version", "1", "--base-url", self.base])
        self.assertEqual(a.returncode, 2)
        self.assertIn("NO_KEY", a.stdout)
        self.assertEqual(STUDIO["seen"], [])

    # -- 7 link ---------------------------------------------------------------

    def test_link_new_stores_client_url(self):
        p = self.run_bridge(["link", "--new", "--base-url", self.base],
                            DS_KEY=MACHINE_KEY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout.strip(), LINK_URL)
        saved = self.state / "client.url"
        self.assertEqual(saved.read_text(encoding="utf-8").strip(), LINK_URL)
        self.assertEqual(_mode(saved), 0o600)
        self.assertNotIn(MACHINE_KEY, p.stdout + p.stderr)

        links = len([r for r in STUDIO["seen"] if r["path"] == "/api/studio/link"])
        again = self.run_bridge(["link", "--base-url", self.base], DS_KEY=MACHINE_KEY)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(again.stdout.strip(), LINK_URL)
        self.assertEqual(len([r for r in STUDIO["seen"]
                              if r["path"] == "/api/studio/link"]), links)


if __name__ == "__main__":
    unittest.main(verbosity=2)
