#!/usr/bin/env python3
"""R2-4 / DSR-104 — the claimed order starts, and the client is told.

The two halves of one broken handoff, each with its own control on the same
instrument:

  A  `poll` leaves the run folder in a state the very next command can use.
     A real order, through the REAL bridge and the REAL factory: `poll` claims
     it, then `factory.py next --run-dir <the folder poll printed>` names a
     stage (exit 0) instead of answering `state-file-missing`.
       control: the same `next` on a folder poll never claimed still fails
       cleanly with `state-file-missing` -- the fix does not paper over a
       missing run.
       control: the run state is written by `state_store.Store` (one writer),
       so the store reads its own schema version back, and a poll that already
       finds the store leaves the existing rows alone.
  B  `wake_agent.sh` delivers the agent's reply back to the client's channel.
     A stub `openclaw` on PATH records its argv: `--deliver` really is passed,
     the channel is the one the rest of the skill sends on, the agent is the
     one the gateway binds that channel to, and the message says in plain words
     that the video has started and where the approvals appear.
       control: a failed agent turn is ONE invocation -- no retry loop -- and
       keeps the turn's own exit code (the wake stays queued in the ledger).
       control: no OpenClaw on PATH -> named wake failure (exit 70), nothing
       invoked, the timer reports it separately from the poll.
       control: an ambiguous agent binding starts NOTHING (never an unnamed
       default agent): exit 70 with DS_AGENT_ID named on stderr.
       control: no --deliver on this runtime -> the turn runs but the gap is
       named (exit 71), never silent success.
       control: a poll line that is not JSON -> exit 65, nothing invoked.
  C  the safe-degradation paths: a poll with no order is silent exit 0; a poll
     on a box that was never enrolled refuses exit 2 before any request.

NO live end-to-end: no link is minted, no order is placed against the real
studio. The only server is a stdlib `http.server` on 127.0.0.1.

Run: python3 checks/test_studio_handoff.py
Exit: 0 all pass · 1 at least one failed
"""
import http.server
import json
import os
import pathlib
import shlex
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
SKILL_ROOT = BRIDGE_DIR.parent                      # 75-drama-song-ad-factory

PY = sys.executable
BRIDGE = str(BRIDGE_DIR / "studio_bridge.py")
WAKE = str(BRIDGE_DIR / "wake_agent.sh")
FACTORY = str(SKILL_ROOT / "scripts" / "core" / "intake_preflight" / "factory.py")

CLIENT = "c-" + "a" * 32
MACHINE_KEY = "machine-" + "c" * 40
STUDIO = {"line": None, "order": {}, "seen": []}

BINDINGS = [
    {"agentId": "drama", "match": {"channel": "telegram", "accountId": "*"}},
    {"agentId": "ops", "match": {"channel": "telegram", "accountId": "ops-acct"}},
    {"agentId": "ops", "match": {"channel": "slack", "accountId": "*"}},
]


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


class _RecordingOpenClaw:
    """A stand-in `openclaw` that records its argv and answers the two probes
    wake_agent.sh makes before it starts a turn."""

    #: {deliver_help} is the one thing a stub can take away: an OpenClaw whose
    #: `agent --help` never mentions `--deliver` (an older gateway).
    SCRIPT = """#{python}
import json, os, sys
argv = sys.argv[1:]
if argv[:2] == ['agent', '--help']:
    sys.stdout.write('  --agent <id>  Agent id (overrides routing bindings)\\n')
    sys.stdout.write({deliver_help})
    sys.exit(0)
if argv[:2] == ['agents', 'bindings']:
    sys.stdout.write(os.environ['STUB_BINDINGS'])
    sys.exit(0)
with open(os.environ['STUB_LOG'], 'a', encoding='utf-8') as fh:
    fh.write(json.dumps(argv) + '\\n')
sys.exit(int(os.environ.get('STUB_AGENT_EXIT', '0')))
"""

    def __init__(self, path, log, agent_exit=0, bindings=BINDINGS, deliver=True):
        self.path = path
        self.log = log
        self.agent_exit = agent_exit
        self.bindings = bindings
        self.deliver = deliver
        path.write_text(self.SCRIPT.format(
            python="!" + PY,
            deliver_help=("'  --deliver  Send the reply back (default: false)\\n'"
                          if self.deliver
                          else "'  (this build cannot hand a reply back)\\n'")),
            encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def env(self, **over):
        env = {"PATH": "/usr/bin:/bin", "STUB_LOG": str(self.log),
               "STUB_BINDINGS": json.dumps(self.bindings),
               "STUB_AGENT_EXIT": str(self.agent_exit)}
        env.update({k: str(v) for k, v in over.items()})
        return env


class HandoffTests(unittest.TestCase):
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
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dsr104-", dir=str(HERE)))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.runs = self.tmp / "drama-runs"
        self.claims = self.tmp / "studio.db"
        self.wakes = 0
        # the box's own state folder: an address that is ALWAYS this fake studio,
        # so nothing on any path can fall back to the real one
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "machine.url").write_text(self.base + "\n", encoding="utf-8")
        STUDIO["line"] = None
        STUDIO["order"] = {}
        STUDIO["seen"] = []

    # -- helpers -------------------------------------------------------------

    def poll(self, **over):
        env = {"PATH": os.environ.get("PATH", ""),
               "HOME": str(self.tmp / "home"),
               "DRAMA_STUDIO_STATE": str(self.tmp / "state"),
               "PYTHONDONTWRITEBYTECODE": "1"}
        env.update({k: str(v) for k, v in over.items()})
        return subprocess.run(
            [PY, BRIDGE, "poll", "--skill-root", str(SKILL_ROOT),
             "--runs", str(self.runs), "--db", str(self.claims),
             "--base-url", self.base],
            capture_output=True, text=True, env=env)

    def next_on(self, run_dir):
        return subprocess.run(
            [PY, FACTORY, "next", "--run-dir", str(run_dir)],
            capture_output=True, text=True,
            env={"PATH": os.environ.get("PATH", ""),
                 "HOME": str(self.tmp / "home"), "PYTHONDONTWRITEBYTECODE": "1"})

    def claim_order(self, order_id="r_handoff01", replies=("yes",)):
        STUDIO["line"] = 'DRAMA_ORDER %s "Spring Sale"' % order_id
        STUDIO["order"] = {"order_id": order_id, "client_id": CLIENT,
                           "title": "Spring Sale", "replies": list(replies)}
        p = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, p.stdout)
        return p, json.loads(lines[0])

    def wake(self, line, agent_exit=0, bindings=BINDINGS, deliver=True, **over):
        # one stub and one log per call: a later wake must never be read back
        # as the argv of an earlier one
        self.wakes += 1
        stub = self.tmp / ("openclaw-stub-%d" % self.wakes)
        log = self.tmp / ("openclaw-argv-%d.jsonl" % self.wakes)
        rec = _RecordingOpenClaw(stub, log, agent_exit=agent_exit,
                                 bindings=bindings, deliver=deliver)
        over.setdefault("OPENCLAW_BIN", str(stub))
        over.setdefault("DRAMA_STUDIO_STATE", str(self.state))
        # a HOME of its own: the bridge's last key rung is ~/.drama-studio, and
        # this test must never reach the operator box's real pairing
        over.setdefault("HOME", str(self.tmp / "home"))
        p = subprocess.run([WAKE, line], capture_output=True, text=True,
                           env=rec.env(**over))
        argvs = []
        if log.is_file():
            argvs = [json.loads(l) for l in
                     log.read_text(encoding="utf-8").splitlines()]
        return p, argvs

    # -- A: the claimed order starts -----------------------------------------

    def test_next_works_on_a_freshly_claimed_run(self):
        """THE CORE PROOF: poll, then the exact command the poll line prints."""
        p, out = self.claim_order()
        self.assertTrue((pathlib.Path(out["run_dir"]) /
                         "control" / "studio-order.json").is_file())

        nxt = self.next_on(pathlib.Path(out["run_dir"]))
        self.assertEqual(nxt.returncode, 0, nxt.stdout + nxt.stderr)
        env = json.loads(nxt.stdout)
        self.assertEqual(env["outcome"], "ok", env)
        self.assertEqual(env["reason_code"], "next-stage", env)
        self.assertEqual(env["data"]["stage"], "research", env)
        # the state authority poll created is the skill's own store
        db = pathlib.Path(out["run_dir"]) / "control" / "state.sqlite3"
        self.assertTrue(db.is_file(), db)
        sys.path.insert(0, str(SKILL_ROOT / "scripts" / "core"))
        import state_store
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        try:
            self.assertEqual(
                con.execute("SELECT v FROM meta WHERE k='db_version'").fetchone()[0],
                str(state_store.DB_SCHEMA_VERSION))
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM stages"
                            " WHERE run_id=?", (out["order_id"],)).fetchone()[0], 12)
        finally:
            con.close()

    def test_the_printed_next_command_works_from_anywhere(self):
        """The poll line's `next` is run as printed, so the paths in it must be
        absolute even when the timer handed poll a relative --runs."""
        STUDIO["line"] = 'DRAMA_ORDER r_relpath01 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_relpath01", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"]}
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir(parents=True, exist_ok=True)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.tmp / "home"),
               "DRAMA_STUDIO_STATE": str(self.state), "PYTHONDONTWRITEBYTECODE": "1",
               "DS_KEY": MACHINE_KEY}
        p = subprocess.run(
            [PY, BRIDGE, "poll", "--skill-root", str(SKILL_ROOT),
             "--runs", "drama-runs", "--db", str(self.claims),
             "--base-url", self.base],
            capture_output=True, text=True, env=env, cwd=str(elsewhere))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = json.loads([l for l in p.stdout.splitlines() if l.strip()][0])
        self.assertTrue(pathlib.Path(out["run_dir"]).is_absolute(), out)
        # and the printed command really runs from an unrelated working directory
        argv = shlex.split(out["next"])
        nxt = subprocess.run(argv, capture_output=True, text=True, env=env,
                             cwd=str(elsewhere))
        self.assertEqual(nxt.returncode, 0, nxt.stdout + nxt.stderr)
        self.assertEqual(json.loads(nxt.stdout)["reason_code"], "next-stage")
        # the same folder addressed RELATIVELY only works from poll's own
        # working directory -- which is why the printed path must be absolute
        ghost = subprocess.run(
            [PY, FACTORY, "next", "--run-dir", "drama-runs/r_relpath01"],
            capture_output=True, text=True, env=env, cwd=str(self.tmp))
        self.assertEqual(ghost.returncode, 1, ghost.stdout + ghost.stderr)
        self.assertEqual(json.loads(ghost.stdout)["reason_code"],
                         "state-file-missing")

    def test_next_still_refuses_a_run_that_was_never_claimed(self):
        """Negative control on the SAME instrument: no poll -> no run -> the
        clean `state-file-missing` refusal, so the fix is not papering over it."""
        ghost = self.tmp / "drama-runs" / "r_neverclaimed"
        ghost.mkdir(parents=True, exist_ok=True)
        nxt = self.next_on(ghost)
        self.assertEqual(nxt.returncode, 1, nxt.stdout + nxt.stderr)
        env = json.loads(nxt.stdout)
        self.assertEqual(env["reason_code"], "state-file-missing", env)

    def test_run_state_is_one_writer_and_idempotent(self):
        """A second poll of the same order never re-initialises the run."""
        _, out = self.claim_order()
        db = pathlib.Path(out["run_dir"]) / "control" / "state.sqlite3"
        before = db.stat().st_mtime_ns, db.stat().st_size
        sys.path.insert(0, str(SKILL_ROOT / "scripts" / "core"))
        import state_store
        with state_store.Store(str(db)) as st:
            st.transition(out["order_id"], "research", "READY",
                          actor="test", reason="control")
            version = st.get(out["order_id"], "research")["version"]
        again = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        # D35 reconcile: the pending wake re-emits the SAME line (the claim is
        # ours and unacknowledged) — never quiet success, never a re-init.
        line2 = [l for l in again.stdout.splitlines() if l.strip()]
        self.assertEqual(len(line2), 1, again.stdout)
        out2 = json.loads(line2[0])
        self.assertEqual(out2["run_dir"], out["run_dir"])
        with state_store.Store(str(db)) as st:
            row = st.get(out["order_id"], "research")
        self.assertEqual(row["state"], "READY", row)   # init_run did not clobber
        self.assertEqual(row["version"], version, row)

    # -- B: the client is told ------------------------------------------------

    def test_wake_delivers_and_says_the_video_started(self):
        # the box holds a key and its stored personal link
        (self.state / "machine.key").write_text(MACHINE_KEY + "\n", encoding="utf-8")
        (self.state / "machine.key").chmod(0o600)
        link = "https://studio.example/#k=" + "d" * 32
        (self.state / "client.url").write_text(link + "\n", encoding="utf-8")
        (self.state / "client.url").chmod(0o600)
        _, out = self.claim_order()
        p, argvs = self.wake(json.dumps(out), DS_KEY=MACHINE_KEY)
        self.assertEqual(len(argvs), 1, argvs)
        argv = argvs[0]
        self.assertEqual(argv[0], "agent")
        self.assertIn("--deliver", argv)                # the reply reaches the client
        self.assertEqual(argv[argv.index("--channel") + 1], "telegram")
        # the agent the gateway binds that channel to (the catch-all binding)
        self.assertEqual(argv[argv.index("--agent") + 1], "drama")
        msg = argv[argv.index("--message") + 1]
        self.assertTrue(msg.startswith("Your video has started"), msg)
        self.assertIn(link, msg)                        # the page's actual URL
        self.assertIn("Drama Studio page", msg)
        self.assertIn("INSTRUCTIONS.md step 6", msg)    # the named action
        self.assertIn(out["next"], msg)                 # and the instruction after
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        # no key on the box: the message still goes out, it just carries no URL
        (self.state / "machine.key").unlink()
        nokey, argvs2 = self.wake(json.dumps(out), DS_KEY="")
        self.assertEqual(nokey.returncode, 0, nokey.stderr)
        msg2 = argvs2[0][argvs2[0].index("--message") + 1]
        self.assertTrue(msg2.startswith("Your video has started"), msg2)
        self.assertNotIn(link, msg2)
        self.assertIn("INSTRUCTIONS.md step 6", msg2)

    def test_wake_names_the_agent_only_when_the_binding_is_unambiguous(self):
        """Control: two agents bind telegram with no catch-all -> NO turn is
        started as an unnamed default agent (SPEC 9.4): the wake fails
        actionably, names DS_AGENT_ID, and stays queued for retry. Then
        DS_AGENT_ID resolves it, over the binding and over any ambiguity."""
        _, out = self.claim_order()
        p, argvs = self.wake(json.dumps(out), bindings=[
            {"agentId": "a", "match": {"channel": "telegram", "accountId": "x"}},
            {"agentId": "b", "match": {"channel": "telegram", "accountId": "y"}}])
        self.assertEqual(argvs, [])                     # nothing unnamed started
        self.assertEqual(p.returncode, 70, p.stdout + p.stderr)
        self.assertIn("DS_AGENT_ID", p.stderr)
        # the failure is NAMED in the claim ledger and the request stays
        # queued (step unchanged) — actionable, never claimed-and-forgotten
        con = sqlite3.connect("file:%s?mode=ro" % out["db"], uri=True)
        try:
            fails = [json.loads(r[0]) for r in con.execute(
                "SELECT payload FROM records WHERE run_id=? AND kind='wake_failed'",
                (out["order_id"],))]
            steps = con.execute("SELECT step FROM orders WHERE order_id=?",
                                (out["order_id"],)).fetchall()
        finally:
            con.close()
        self.assertTrue(fails and fails[0]["reason"] == "AMBIGUOUS_BINDING", fails)
        self.assertEqual(steps, [("wake_queued",)], steps)  # still retryable
        # DS_AGENT_ID always wins, over the binding and over any ambiguity
        _, forced = self.wake(json.dumps(out), DS_AGENT_ID="ops")
        self.assertEqual(forced[0][forced[0].index("--agent") + 1], "ops")

    def test_wake_is_one_turn_never_a_retry_loop(self):
        _, out = self.claim_order()
        p, argvs = self.wake(json.dumps(out), agent_exit=3)
        self.assertEqual(p.returncode, 3)               # the agent's own code
        self.assertEqual(len(argvs), 1, argvs)          # exactly one attempt

    def test_wake_without_delivery_available_names_the_gap_and_fails_separately(self):
        """SPEC 9.4: an unsupported delivery capability is never silent
        success. The turn still runs (work continues) but the exit is the
        wake's own failure code, separate from the poll's success — the timer
        propagates it. No OpenClaw at all starts nothing and fails the same way
        (the wake stays queued either way)."""
        _, out = self.claim_order()
        p, argvs = self.wake(json.dumps(out), deliver=False)
        self.assertEqual(p.returncode, 71, p.stdout + p.stderr)
        self.assertIn("no --deliver", p.stderr)
        self.assertNotIn("--deliver", argvs[0])
        self.assertEqual(len(argvs), 1, argvs)          # the turn DID run
        # control: no OpenClaw on PATH at all -> nothing invoked, named failure
        p2 = subprocess.run([WAKE, json.dumps(out)],
                            capture_output=True, text=True,
                            env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(p2.returncode, 70, p2.stdout + p2.stderr)
        self.assertIn("not on PATH", p2.stderr)

    def test_wake_rejects_a_bad_poll_line_before_touching_openclaw(self):
        bare = subprocess.run([WAKE], capture_output=True, text=True,
                              env={"PATH": os.environ.get("PATH", "")})
        self.assertEqual(bare.returncode, 64, bare.stderr)
        for bad in ("not json", '{"order_id": "r_1"}'):
            p = subprocess.run([WAKE, bad], capture_output=True, text=True,
                               env={"PATH": os.environ.get("PATH", "")})
            self.assertEqual(p.returncode, 65, bad)
        _, argvs = self.wake("not json")
        self.assertEqual(argvs, [])                   # nothing was started

    # -- C: the safe-degradation paths ---------------------------------------

    def test_no_order_is_silent_and_exit_zero(self):
        p = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, "")
        self.assertEqual(p.stderr, "")
        self.assertEqual(STUDIO["seen"],
                         [{"method": "POST", "path": "/api/studio/checkin",
                           "body": {"agnes_remembered": "unknown"},
                           "key": MACHINE_KEY}])
        # and nothing was created in the runs dir
        self.assertFalse(self.runs.exists())

    def test_not_enrolled_refuses_before_any_request(self):
        p = self.poll()                       # no DS_KEY, no machine.key file
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("NO_KEY", p.stdout)
        self.assertEqual(STUDIO["seen"], [])
        self.assertFalse(self.runs.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
