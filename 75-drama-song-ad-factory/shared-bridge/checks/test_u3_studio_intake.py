#!/usr/bin/env python3
"""S75-W07-U3 — optional Studio intake and durable claim/wake (D24, D35).

Every acceptance line of the unit, each with a control on the SAME instrument,
against a local fake studio (stdlib `http.server`, no network) and the real
bridge / claim ledger / wake script / timer:

  1  Chat-only install: Studio capability is modelled EXPLICITLY as disabled /
     needs-enrollment / ready / degraded in the installation state; an idle
     optional poller (`capability --gate`) skips QUIETLY — one transition line
     ever, no per-tick failure, and never an auto-enrol to silence logs.
  2  Interrupted/key-only enrolment reconciles WITHOUT a duplicate identity or
     a discarded valid key: `enroll --resume` restores machine.url and modes
     locally, makes zero HTTP calls, and leaves the key bytes untouched.
     A stray pre-contract key is adopted only on the real root-split shape
     (Contabo) — an explicitly overridden state root is never raided.
  3  Studio HTTP/wake failure after a local claim resumes durably under the
     SAME order: the claim survives a failed fetch, the next poll completes it
     with no second claim post and one card replay, a wake request stays
     queued until `wake --ack`, and execution-accepted silences the poll for
     good (no duplicate campaign).
  4  Poll success + failed wake propagates the wake failure SEPARATELY:
     run-timer.sh exits with the wake's own named code (70/71/turn rc) and
     says so, while the poll's success is preserved in the message.
  5  Old log tails are never new failures: capability.json keeps
     last-attempt / successful-check timestamps and an error older than the
     last success reads as STALE (and a success clears it).

Run: python3 checks/test_u3_studio_intake.py
Exit: 0 all pass · 1 at least one failed
"""
import http.server
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent
SKILL_ROOT = BRIDGE_DIR.parent

sys.path.insert(0, str(BRIDGE_DIR))
import studio_bridge as SB  # noqa: E402
import studio_claim as SC  # noqa: E402

PY = sys.executable
BRIDGE = str(BRIDGE_DIR / "studio_bridge.py")
WAKE = str(BRIDGE_DIR / "wake_agent.sh")
RUN_TIMER = str(SKILL_ROOT / "timer-artifacts" / "run-timer.sh")

CLIENT = "c-" + "a" * 32
MACHINE_KEY = "machine-" + "c" * 40
STUDIO = {"line": None, "order": {}, "seen": [], "fail_get": 0}


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
        STUDIO["seen"].append({"method": self.command, "path": path,
                               "key": self.headers.get("x-ds-key") or ""})
        if path == "/api/studio/enroll":
            return self._send(201, {"ok": True, "client_id": CLIENT,
                                    "key": "enroll-" + "k" * 40})
        if path == "/api/studio/checkin":
            return self._send(200, {"ok": True, "checked_in_at": 1,
                                    "line": STUDIO["line"]})
        if not (self.headers.get("x-ds-key") or ""):
            return self._send(401, {"ok": False, "code": "AF-DS-AUTH",
                                    "message": "no key"})
        if path.endswith("/state") and "/orders/" in path:
            return self._send(200, {"ok": True, "order": {"state": "claimed"}})
        if "/orders/" in path:
            if STUDIO["fail_get"] > 0:          # D35: fetch fails after claim
                STUDIO["fail_get"] -= 1
                return self._send(500, {"ok": False, "code": "AF_ORDER_FETCH",
                                        "message": "fetch failed"})
            return self._send(200, {"ok": True, "order": STUDIO["order"]})
        return self._send(404, {"ok": False, "code": "AF-DS-NOT-FOUND",
                                "message": "No route."})

    def log_message(self, *args):
        pass


def _enroll_posts():
    return len([r for r in STUDIO["seen"] if r["path"] == "/api/studio/enroll"])


class U3Tests(unittest.TestCase):
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
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="u3-", dir=str(HERE)))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.state = self.tmp / "state"
        self.home.mkdir()
        self.state.mkdir()
        self.runs = self.tmp / "runs"
        STUDIO["line"] = None
        STUDIO["order"] = {}
        STUDIO["seen"] = []
        STUDIO["fail_get"] = 0

    def env(self, **over):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home),
               "DRAMA_STUDIO_STATE": str(self.state),
               "PYTHONDONTWRITEBYTECODE": "1"}
        env.update({k: str(v) for k, v in over.items()})
        return env

    def bridge(self, args, **over):
        return subprocess.run([PY, BRIDGE] + list(args), capture_output=True,
                              text=True, env=self.env(**over))

    def stub_skill_root(self):
        core = self.tmp / "stub-skill" / "scripts" / "core" / "intake_preflight"
        core.mkdir(parents=True, exist_ok=True)
        (core / "factory.py").write_text(
            "import json, os, sys\n"
            "with open(os.environ['STUB_FACTORY_LOG'], 'a', encoding='utf-8') as fh:\n"
            "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.write('next question\\n')\n",
            encoding="utf-8")
        return self.tmp / "stub-skill"

    def poll(self, skill_root, **over):
        return self.bridge(["poll", "--skill-root", str(skill_root),
                            "--runs", str(self.runs), "--base-url", self.base], **over)

    # -- 1: capability states + quiet optional poller (D24) --------------------

    def test_capability_states_and_quiet_gate(self):
        # chat-only box: no key, no intent -> disabled, and the gate SKIPS QUIETLY
        g1 = self.bridge(["capability", "--gate"])
        self.assertEqual(g1.returncode, SB.GATE_SKIP, g1.stdout + g1.stderr)
        self.assertIn("disabled", g1.stderr)          # one transition line
        g2 = self.bridge(["capability", "--gate"])
        self.assertEqual(g2.returncode, SB.GATE_SKIP)
        self.assertEqual(g2.stderr, "")               # NO per-tick noise
        self.assertEqual(g2.stdout, "")
        # the state is modelled explicitly in the installation state
        rec = json.loads((self.state / "capability.json").read_text())
        self.assertEqual(rec["capability"], "disabled")
        self.assertIn("last_attempt_at", rec)
        # operator intent flips it to needs-enrollment (the record IS the
        # transition, so the next gate stays silent — never per-tick noise)
        r = self.bridge(["capability", "--record", "needs-enrollment"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        g3 = self.bridge(["capability", "--gate"])
        self.assertEqual(g3.returncode, SB.GATE_SKIP)
        self.assertEqual(g3.stderr, "")
        self.assertEqual(json.loads((self.state / "capability.json").read_text())["intent"],
                         "needs-enrollment")
        # control: a complete receipt + live handshake -> ready, gate proceeds
        (self.state / "machine.key").write_text(MACHINE_KEY + "\n")
        (self.state / "machine.key").chmod(0o600)
        (self.state / "machine.url").write_text(self.base + "\n")
        (self.state / "machine.url").chmod(0o600)
        g4 = self.bridge(["capability", "--gate"], DS_KEY=MACHINE_KEY)
        self.assertEqual(g4.returncode, SB.GATE_READY, g4.stdout + g4.stderr)
        rec = json.loads((self.state / "capability.json").read_text())
        self.assertEqual(rec["capability"], "ready")
        self.assertGreaterEqual(rec["last_success_at"], rec["last_attempt_at"])
        # control 2: a key with a broken receipt is DEGRADED, not ready
        (self.state / "machine.url").unlink()
        g5 = self.bridge(["capability", "--gate"], DS_KEY=MACHINE_KEY)
        self.assertEqual(g5.returncode, SB.GATE_SKIP)
        self.assertEqual(json.loads((self.state / "capability.json").read_text())["capability"],
                         "degraded")
        # control 3: an install pass never downgrades an observed enrolment
        keep = self.bridge(["capability", "--record", "disabled"])
        self.assertIn('"kept": true', keep.stdout)

    # -- 2: interrupted/key-only receipt (D24) --------------------------------

    def test_key_only_receipt_reconciles_without_duplicate_identity(self):
        key_bytes = MACHINE_KEY + "\n"
        (self.state / "machine.key").write_text(key_bytes)
        (self.state / "machine.key").chmod(0o644)      # interrupted: mode wrong too
        before = _enroll_posts()
        p = self.bridge(["enroll", "--resume", "--base-url", self.base])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn('"recovered": true', p.stdout)
        # the valid key is preserved byte-for-byte: no duplicate identity
        self.assertEqual((self.state / "machine.key").read_text(), key_bytes)
        self.assertEqual(_enroll_posts(), before)      # zero HTTP: no re-enrol
        # the missing URL is restored and modes are private again
        self.assertEqual((self.state / "machine.url").read_text().strip(), self.base)
        self.assertEqual(stat.S_IMODE((self.state / "machine.key").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.state / "machine.url").stat().st_mode), 0o600)
        # the receipt now validates complete
        again = self.bridge(["enroll", "--resume", "--base-url", self.base])
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn('"recovered": false', again.stdout)
        self.assertEqual(_enroll_posts(), before)
        # control: a plain second `enroll` still refuses to replace the key
        refuse = self.bridge(["enroll", "--base-url", self.base])
        self.assertEqual(refuse.returncode, 2)
        self.assertIn("ALREADY_ENROLLED", refuse.stdout)
        self.assertEqual((self.state / "machine.key").read_text(), key_bytes)
        self.assertEqual(_enroll_posts(), before)

    def test_stray_key_adopted_only_on_the_contract_shape(self):
        # the one platform shape with a real root split is Contabo's
        self.assertEqual(str(SB._contract_state({"HOME": "/home/node"})),
                         "/home/node/.openclaw/.drama-studio")
        self.assertEqual(str(SB._contract_state({"HOME": str(self.home)})),
                         str(self.home / ".drama-studio"))
        # adoption on that shape (in-process: the shape is what a Contabo box
        # sees; the module functions are stood in for the un-writable paths)
        legacy = self.home / ".drama-studio"
        legacy.mkdir()
        (legacy / "machine.key").write_text(MACHINE_KEY + "\n")
        contract = self.tmp / "contract"
        real_contract, real_legacy = SB._contract_state, SB._legacy_state
        SB._contract_state = lambda env=None: contract
        SB._legacy_state = lambda env=None: legacy
        try:
            key_path, changes = SB._recover_receipt({}, base_url=str(self.base))
            self.assertIsNotNone(key_path)
            self.assertTrue(any("adopted machine.key" in c for c in changes), changes)
            self.assertEqual((contract / "machine.key").read_text().strip(),
                             MACHINE_KEY)            # valid key preserved
            self.assertFalse((legacy / "machine.key").exists())  # moved, not copied
            rec = SB._receipt({}, base_url=str(self.base))
            self.assertTrue(rec["complete"], rec)
        finally:
            SB._contract_state, SB._legacy_state = real_contract, real_legacy
        # control: an EXPLICITLY overridden state root is never raided — an
        # identity in the home fallback stays where it is (it may be another
        # installation's), and nothing is written into the override
        real_home_key = self.home / ".drama-studio" / "machine.key"
        real_home_key.write_text("other-installation-key\n")
        rec = SB._receipt({"DRAMA_STUDIO_STATE": str(self.state)})
        self.assertFalse(rec["has_key"], rec)         # out of scope: not ours
        key_path, changes = SB._recover_receipt({"DRAMA_STUDIO_STATE": str(self.state)})
        self.assertIsNone(key_path)
        self.assertEqual(changes, [])
        self.assertFalse((self.state / "machine.key").exists())
        self.assertEqual(real_home_key.read_text().strip(), "other-installation-key")

    # -- 3: durable claim / wake steps (D35) ----------------------------------

    def test_claim_steps_resume_and_fence(self):
        db = str(self.tmp / "studio.db")
        with SC.ClaimLedger(db) as led:
            self.assertTrue(led.claim_order("r_steps", "runA", now=100.0))
            st = led.order_state("r_steps")
            self.assertEqual(st["step"], SC.STEP_CLAIMED)
            # steps move forward only
            self.assertTrue(led.advance_step("r_steps", "runA",
                                             SC.STEP_ORDER_FETCHED, now=101.0))
            self.assertFalse(led.advance_step("r_steps", "runA",
                                              SC.STEP_CLAIMED, now=102.0))
            self.assertTrue(led.advance_step("r_steps", "runA",
                                             SC.STEP_MATERIALIZED, now=102.0))
            self.assertTrue(led.advance_step("r_steps", "runA",
                                             SC.STEP_WAKE_QUEUED, now=103.0))
            self.assertTrue(led.advance_step("r_steps", "runA",
                                             SC.STEP_EXECUTION_ACCEPTED, now=104.0))
            self.assertEqual(led.order_state("r_steps")["step"],
                             SC.STEP_EXECUTION_ACCEPTED)
            # same owner re-claims RESUME (a crash must be retryable)
            self.assertTrue(led.claim_order("r_steps", "runA", now=105.0))
            # a live OTHER owner is the only refusal
            self.assertFalse(led.claim_order("r_steps", "runB", now=106.0))
        # fencing: an expired claim is taken over with a NEW fence, and the
        # fenced-out old worker can no longer write
        with SC.ClaimLedger(db) as led:
            self.assertTrue(led.claim_order("r_fence", "runA", now=100.0))
            self.assertTrue(led.advance_step("r_fence", "runA",
                                             SC.STEP_ORDER_FETCHED, now=101.0))
            self.assertFalse(led.claim_order("r_fence", "runB", now=102.0))
            fence_before = led.order_state("r_fence")["fence"]
            self.assertTrue(led.claim_order("r_fence", "runB", now=100000.0))
            self.assertEqual(led.order_state("r_fence")["fence"], fence_before + 1)
            self.assertFalse(led.advance_step("r_fence", "runA",
                                              SC.STEP_MATERIALIZED, now=100001.0))
            self.assertFalse(led.advance_step("r_fence", "runB",
                                              SC.STEP_MATERIALIZED, now=100001.0,
                                              fence=fence_before))  # stale fence
            self.assertTrue(led.advance_step("r_fence", "runB",
                                             SC.STEP_MATERIALIZED, now=100001.0))

    def test_v1_ledger_migrates_without_losing_claims(self):
        db = str(self.tmp / "v1.db")
        # a genuine v1 ledger: the orders table as shipped before the step
        # machine existed, with one live claim in it
        con = sqlite3.connect(db)
        with con:
            con.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            con.execute("CREATE TABLE orders(order_id TEXT PRIMARY KEY,"
                        " owner TEXT NOT NULL, claimed_at REAL NOT NULL,"
                        " state TEXT NOT NULL DEFAULT 'claimed')")
            con.execute("INSERT INTO orders(order_id, owner, claimed_at)"
                        " VALUES('r_v1', 'runA', 1.0)")
        con.close()
        with SC.ClaimLedger(db) as led:
            st = led.order_state("r_v1")
            self.assertIsNotNone(st, "v1 claim row lost in migration")
            self.assertEqual(st["owner"], "runA")
            self.assertEqual(st["step"], SC.STEP_CLAIMED)
            self.assertTrue(led.claim_order("r_v1", "runA", now=5.0))  # resumes

    def test_failed_fetch_resumes_under_the_same_order(self):
        skill = self.stub_skill_root()
        log = self.tmp / "factory-argv.jsonl"
        STUDIO["line"] = 'DRAMA_ORDER r_fetch01 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_fetch01", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"]}
        STUDIO["fail_get"] = 1                      # the fetch fails once
        p1 = self.poll(skill, DS_KEY=MACHINE_KEY, STUB_FACTORY_LOG=str(log))
        self.assertNotEqual(p1.returncode, 0, "a failed fetch must not look ok")
        self.assertIn("AF_ORDER_FETCH", p1.stdout)   # actionable, not silent
        # the LOCAL claim survived the failed fetch
        db = self.state / "studio.db"
        con = sqlite3.connect(str(db))
        try:
            rows = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            posts = con.execute("SELECT COUNT(*) FROM records"
                                " WHERE kind='claim_event'").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(rows, 1)                    # one owned order, no duplicate
        self.assertEqual(posts, 1)                   # claim posted exactly once
        # the NEXT poll resumes and completes under the same order
        p2 = self.poll(skill, DS_KEY=MACHINE_KEY, STUB_FACTORY_LOG=str(log))
        self.assertEqual(p2.returncode, 0, p2.stdout + p2.stderr)
        out = json.loads([l for l in p2.stdout.splitlines() if l.strip()][0])
        self.assertEqual(out["order_id"], "r_fetch01")
        con = sqlite3.connect(str(db))
        try:
            rows = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            posts = con.execute("SELECT COUNT(*) FROM records"
                                " WHERE kind='claim_event'").fetchone()[0]
            state_posts = len([r for r in STUDIO["seen"]
                               if r["path"].endswith("/state")])
        finally:
            con.close()
        self.assertEqual(rows, 1)                    # same order, resumed
        self.assertEqual(posts, 1)                   # no second claim post
        self.assertEqual(state_posts, 1)
        self.assertEqual(len(log.read_text().splitlines()), 1)  # one card replay
        # wake failure keeps the request queued; the poll re-emits for retry
        wf = self.bridge(["wake", "--fail", "--reason", "NO_CLI",
                          "--order", "r_fetch01", "--db", out["db"]])
        self.assertEqual(wf.returncode, 0, wf.stdout + wf.stderr)
        self.assertIn('"retryable": true', wf.stdout)
        again = self.poll(skill, DS_KEY=MACHINE_KEY, STUB_FACTORY_LOG=str(log))
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("r_fetch01", again.stdout)     # wake persists: re-emitted
        # the supported runtime ack ends it: silent for good
        ack = self.bridge(["wake", "--ack", "--order", "r_fetch01", "--db", out["db"]])
        self.assertEqual(ack.returncode, 0, ack.stdout + ack.stderr)
        done = self.poll(skill, DS_KEY=MACHINE_KEY, STUB_FACTORY_LOG=str(log))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")            # no duplicate campaign

    # -- 4: wake failure propagated separately (D35) --------------------------

    def _stub_openclaw(self, name, agent_exit):
        stub = self.tmp / name
        stub.write_text(
            "#!%s\n"
            "import json, os, sys\n"
            "argv = sys.argv[1:]\n"
            "if argv[:2] == ['agent', '--help']:\n"
            "    sys.stdout.write('  --agent <id>\\n  --deliver  reply back\\n')\n"
            "    sys.exit(0)\n"
            "if argv[:2] == ['agents', 'bindings']:\n"
            "    sys.stdout.write(os.environ['STUB_BINDINGS'])\n"
            "    sys.exit(0)\n"
            "with open(os.environ['STUB_LOG'], 'a', encoding='utf-8') as fh:\n"
            "    fh.write(json.dumps(argv) + '\\n')\n"
            "sys.exit(%d)\n" % (PY, agent_exit), encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        return stub

    def test_run_timer_propagates_wake_failure_separately(self):
        # an identity-legal HOME for the mac contract: leaf == stubbed user
        thome = self.tmp / "testuser"
        thome.mkdir()
        bindir = self.tmp / "bin"
        bindir.mkdir()
        (bindir / "id").write_text("#!/bin/sh\necho testuser\n", encoding="utf-8")
        (bindir / "id").chmod(0o755)
        state = thome / ".drama-studio"
        state.mkdir()
        (state / "machine.key").write_text(MACHINE_KEY + "\n")
        (state / "machine.key").chmod(0o600)
        (state / "machine.url").write_text(self.base + "\n")
        (state / "machine.url").chmod(0o600)
        STUDIO["line"] = 'DRAMA_ORDER r_timer01 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_timer01", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"]}
        bindings = json.dumps(
            [{"agentId": "drama", "match": {"channel": "telegram",
                                            "accountId": "*"}}])

        def run_timer(openclaw, agent_exit):
            stub = self._stub_openclaw(openclaw, agent_exit)
            log = self.tmp / (openclaw + ".argv")
            env = {"PATH": "%s:%s" % (bindir, os.environ.get("PATH", "")),
                   "HOME": str(thome), "DS_PLATFORM": "mac",
                   "DS_SKILL_ROOT": str(SKILL_ROOT),
                   "STUB_BINDINGS": bindings, "STUB_LOG": str(log),
                   "OPENCLAW_BIN": str(stub), "PYTHONDONTWRITEBYTECODE": "1"}
            return subprocess.run(["bash", RUN_TIMER], capture_output=True,
                                  text=True, env=env, cwd=str(self.tmp))
        # control: a healthy wake -> the tick is clean
        ok = run_timer("openclaw-ok", 0)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        # the turn fails: the WAKE failure is propagated SEPARATELY from the
        # poll's success — named in the log, carried in the exit code
        STUDIO["line"] = 'DRAMA_ORDER r_timer02 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_timer02", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"]}
        bad = run_timer("openclaw-bad", 3)
        self.assertEqual(bad.returncode, 3, bad.stdout + bad.stderr)
        self.assertIn("poll succeeded but the WAKE failed", bad.stderr)
        self.assertIn("rc=3", bad.stderr)
        # and no-CLI is the same contract: named, exit 70, never silent success
        STUDIO["line"] = 'DRAMA_ORDER r_timer03 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_timer03", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"]}
        env = {"PATH": "%s:%s" % (bindir, os.environ.get("PATH", "")),
               "HOME": str(thome), "DS_PLATFORM": "mac",
               "DS_SKILL_ROOT": str(SKILL_ROOT),
               "OPENCLAW_BIN": str(self.tmp / "openclaw-missing"),
               "PYTHONDONTWRITEBYTECODE": "1"}
        nocl = subprocess.run(["bash", RUN_TIMER], capture_output=True,
                              text=True, env=env, cwd=str(self.tmp))
        self.assertEqual(nocl.returncode, 70, nocl.stdout + nocl.stderr)
        self.assertIn("poll succeeded but the WAKE failed", nocl.stderr)

    # -- 5: old log tails are never new failures (D24) ------------------------

    def test_old_error_is_stale_not_a_new_failure(self):
        env = self.env()
        (self.state / "machine.key").write_text(MACHINE_KEY + "\n")
        (self.state / "machine.key").chmod(0o600)
        (self.state / "machine.url").write_text(self.base + "\n")
        (self.state / "machine.url").chmod(0o600)
        # a failure is recorded WITH its timestamp...
        SB._record_capability("degraded", env, now=100.0,
                              error={"code": "HTTP_500", "message": "boom"})
        rec = SB._read_capability(env)
        self.assertEqual(rec["last_error"]["at"], 100.0)
        view = SB._capability_view(rec, now=150.0)
        self.assertFalse(view["last_error"]["stale"])  # fresh while unrecovered
        # ...and a later success moves last_success_at PAST it: the old error
        # is then STALE — history, never a new failure
        SB._record_capability("ready", env, now=200.0)
        rec = SB._read_capability(env)
        self.assertGreater(rec["last_success_at"], 100.0)
        self.assertNotIn("last_error", rec)           # recovered: cleared
        # the staleness rule itself, on a record that kept its old error
        kept = dict(rec)
        kept["last_error"] = {"at": 100.0, "code": "HTTP_500", "message": "boom"}
        view = SB._capability_view(kept, now=250.0)
        self.assertTrue(view["last_error"]["stale"], view)

    # -- redaction of capability-bearing links (D24) --------------------------

    def test_capability_links_redacted_from_diagnostics(self):
        secret = "SECRETTOKEN123"
        link = "https://studio.example/#k=" + secret
        (self.state / "machine.key").write_text(MACHINE_KEY + "\n")
        (self.state / "machine.key").chmod(0o600)
        (self.state / "machine.url").write_text(self.base + "\n")
        (self.state / "machine.url").chmod(0o600)
        (self.state / "client.url").write_text(link + "\n")
        (self.state / "client.url").chmod(0o600)
        p = self.bridge(["capability"], DS_KEY=MACHINE_KEY)
        self.assertNotIn(secret, p.stdout + p.stderr)  # routine diagnostics
        self.assertIn('"link_present": true', p.stdout)
        # control on the SAME instrument: the authorized handoff route still
        # prints the link (that is its one job)
        q = self.bridge(["link"], DS_KEY=MACHINE_KEY)
        self.assertEqual(q.stdout.strip(), link)
        # and the scrubber itself discriminates
        self.assertEqual(SB.redact_links("x %s y" % link), "x [redacted-link] y")
        self.assertEqual(SB.redact_links("plain"), "plain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
