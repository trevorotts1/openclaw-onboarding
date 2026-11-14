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
  8  a reply count that cannot complete the card's question list asks the
     client for a second look (`needs_you`), never cancels the order, and puts
     both counts on the operator's stderr line; a 409 (the claim post itself was
     refused, so the order is still `waiting`) is accepted and logged
  9  a replay the card refuses (a testimonial whose permission answer is "No")
     writes the durable halt record, posts `needs_you` with the client's own
     sentence, prints no wake line, and RELEASES the claim - the second poll
     still checks in, and a halted order never blocks the next one
 10  each answer travels with its screen id: ids that do not match the card's,
     in order, ask the client first (the second sentence), never a shifted run
 11  each answer also travels with its option text ("<n>. <option text>"): the
     card receives the number, the text must be the card's own option for that
     screen, and a reordered option list asks the client with the second
     sentence instead of silently answering a different choice; a bare number
     from an old page still passes straight through
 12  a claimed order's uploaded files are fetched into
     `<run>/intake/uploads/<id>.<ext>` before the replay, hashed into
     `control/studio-order.json`; a file the studio does not have is a warning
     line on the wake output and the order still runs

Run: python3 checks/test_poll.py
Exit: 0 all pass · 1 at least one failed
"""
import http.server
import contextlib
import hashlib
import io
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
import studio_bridge as bridge  # noqa: E402

PY = sys.executable
BRIDGE = str(BRIDGE_DIR / "studio_bridge.py")

CLIENT = "c-" + "a" * 32
ENROLL_KEY = "enroll-" + "b" * 40
MACHINE_KEY = "machine-" + "c" * 40
LINK_URL = "https://studio.example/#k=" + "d" * 32
ENROLL_SECRET = "fleet-enrollment-secret-fixture"
STUDIO = {"line": None, "order": {}, "seen": [], "needs_you_409": False,
          "files": {}}


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

    def _send_file(self, status, raw, content_type):
        self.send_response(status)
        self.send_header("content-type", content_type)
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
               "key": self.headers.get("x-ds-key") or "",
               "query": urllib.parse.urlparse(self.path).query}
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
        if path.startswith("/api/studio/uploads/") and path.endswith("/file"):
            upload_id = path[len("/api/studio/uploads/"):-len("/file")]
            found = STUDIO["files"].get(upload_id)
            if found is None:
                return self._send(404, {"ok": False,
                                        "code": "AF-DS-UP-NOT-ARRIVED",
                                        "message": "That file has not arrived."})
            raw, content_type = found
            return self._send_file(200, raw, content_type)
        if path.endswith("/state") and "/orders/" in path:
            if body.get("event") == "needs_you" and STUDIO["needs_you_409"]:
                # The order never left `waiting` (its claim post was refused),
                # and lifecycle.js has no waiting -> needs_you move.
                return self._send(409, {"ok": False,
                                        "code": "AF-DS-STATE-ILLEGAL",
                                        "message": "waiting cannot move to needs_you."})
            return self._send(200, {"ok": True, "order": {"state": "claimed"}})
        if "/orders/" in path:
            return self._send(200, {"ok": True, "order": STUDIO["order"]})
        return self._send(404, {"ok": False, "code": "AF-DS-NOT-FOUND",
                                "message": "No route."})

    def log_message(self, *args):
        pass


class PollBridgeTests(unittest.TestCase):
    #: purpose -> the card's own reply list, built once per run (the card is
    #: deterministic, so every test that needs a complete order shares it).
    _CARD_REPLIES = {}

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
        STUDIO["needs_you_409"] = False
        STUDIO["files"] = {}

    def _stub_skill_root(self):
        """A skill root whose factory.py records its argv and answers the card.

        The bridge drives the card with `--format session-json` (S75-106), so
        the stand-in answers a completed session - the same shape the real
        durable session prints; a stand-in that printed plain text would be a
        different instrument and could not prove the turn contract.
        """
        core = self.tmp / "stub-skill" / "scripts" / "core" / "intake_preflight"
        core.mkdir(parents=True, exist_ok=True)
        (core / "factory.py").write_text(
            "import json, os, sys\n"
            "with open(os.environ['STUB_FACTORY_LOG'], 'a', encoding='utf-8') as fh:\n"
            "    fh.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.write(json.dumps({'done': True, 'outcome': 'ok',\n"
            "                             'reason_code': 'INTAKE_CONFIRMED',\n"
            "                             'question_id': None}) + '\\n')\n",
            encoding="utf-8")
        return self.tmp / "stub-skill"

    def _orders(self):
        """The ledger's owned orders; [] when the table was never created."""
        path = self.state / "studio.db"
        if not path.is_file():
            return []
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        try:
            try:
                return [row[0] for row in con.execute("SELECT order_id FROM orders")]
            except sqlite3.OperationalError:
                return []
        finally:
            con.close()

    def _card_answer(self, question_id, purpose):
        """One reply the card accepts for this screen, in ask order."""
        if question_id in ("offer", "link", "audience", "character", "photos"):
            return "Spring cookie class for local families"
        if question_id == "spend":
            return "$25"
        if question_id == "purpose":
            return purpose
        if question_id == "permission":
            return "2"           # No - the client has not given permission
        return "1"

    def _card_replies(self, purpose="2"):
        """The card's own reply list for a purpose-flow order.

        Asks the installed card, one turn at a time, which screen it is on and
        answers it, then appends the one recap confirmation the studio page
        sends (`mini-app/ui/studio.js`). purpose "2" is a testimonial whose
        client has not given permission, so the card itself waits (S75-106).
        """
        if purpose in self._CARD_REPLIES:
            return list(self._CARD_REPLIES[purpose])
        factory = str(SKILL_ROOT / "scripts" / "core"
                      / "intake_preflight" / "factory.py")
        probe = self.tmp / ("card-probe-" + purpose)
        probe.mkdir(parents=True, exist_ok=True)   # a run folder: purpose flow on
        replies = []
        for _ in range(40):
            argv = [PY, factory, "card", "--step", "--format", "session-json",
                    "--run-dir", str(probe)]
            for reply in replies:
                argv.extend(["--reply", reply])
            done = subprocess.run(argv, capture_output=True, text=True,
                                  env=self.env(), cwd=str(SKILL_ROOT))
            state = json.loads(done.stdout) if done.stdout.strip() else {}
            question_id = state.get("question_id")
            if question_id == "recap" or not question_id:
                break
            replies.append(self._card_answer(question_id, purpose))
        replies.append("yes")
        self._CARD_REPLIES[purpose] = list(replies)
        return replies

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

        # every reply reached the card, ONE TURN PER ANSWER, in argv lists (no
        # shell): the no-reply prime turn presents the first question and every
        # later turn carries the growing prefix, which is what the durable
        # session's own replay absorption reduces to its one new answer.
        calls = [json.loads(l) for l in
                 self.factory_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(calls), 4, calls)
        self.assertEqual(calls[0][:6],
                         ["card", "--step", "--format", "session-json",
                          "--run-dir", str(run_dir)])
        self.assertNotIn("--reply", calls[0])            # the prime turn
        self.assertEqual(calls[1][calls[1].index("--reply"):], ["--reply", "1"])
        self.assertEqual(calls[2][calls[2].index("--reply"):],
                         ["--reply", "1", "--reply", "2"])
        self.assertEqual(calls[3][calls[3].index("--reply"):],
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
                         4)                      # one replay: prime + one per reply
        # the supported runtime acknowledges the wake -> the claim is final
        ack = subprocess.run([PY, BRIDGE, "wake", "--ack",
                              "--order", out["order_id"], "--db", out["db"]],
                             capture_output=True, text=True, env=self.env(DS_KEY=MACHINE_KEY))
        self.assertEqual(ack.returncode, 0, ack.stdout + ack.stderr)
        done = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")                # execution-accepted: silent

    # -- 12 the order's uploaded files land in the run ------------------------

    def test_an_uploaded_file_lands_in_the_run_folder(self):
        upload_id = "u_" + "e" * 24
        raw = b"\xff\xd8\xff\xe0" + b"photo-bytes-sentinel"
        STUDIO["files"] = {upload_id: (raw, "image/jpeg")}
        STUDIO["line"] = 'DRAMA_ORDER r_up01 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_up01", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"],
                           "upload_ids": [upload_id]}
        p = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        run_dir = self.runs / "r_up01"
        landed = run_dir / "intake" / "uploads" / (upload_id + ".jpg")
        self.assertEqual(landed.read_bytes(), raw)
        record = json.loads((run_dir / "control" / "studio-order.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(record["uploads"], [{
            "upload_id": upload_id, "path": str(landed), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}])
        # the key rode in the header, never the query string
        fetches = [r for r in STUDIO["seen"]
                   if r["path"].endswith("/uploads/%s/file" % upload_id)]
        self.assertEqual(len(fetches), 1, fetches)
        self.assertEqual((fetches[0]["method"], fetches[0]["key"],
                          fetches[0]["query"]), ("GET", MACHINE_KEY, ""))
        self.assertNotIn(MACHINE_KEY, p.stdout)
        self.assertNotIn("upload_warnings",
                         json.loads(p.stdout.strip()))

    def test_a_missing_upload_is_a_warning_never_a_refusal(self):
        upload_id = "u_" + "f" * 24
        STUDIO["line"] = 'DRAMA_ORDER r_up02 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_up02", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": ["yes"],
                           "upload_ids": [upload_id]}
        p = self.poll(DS_KEY=MACHINE_KEY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        run_dir = self.runs / "r_up02"
        # the order still ran: a wake line, the replay, the run folder
        self.assertTrue((run_dir / "control" / "studio-order.json").is_file())
        self.assertFalse((run_dir / "intake" / "uploads"
                          / (upload_id + ".jpg")).exists())
        out = json.loads(p.stdout.strip())
        self.assertEqual(len(out["upload_warnings"]), 1, out)
        self.assertIn("has not reached the studio", out["upload_warnings"][0])
        stored = json.loads((run_dir / "control" / "studio-order.json")
                            .read_text(encoding="utf-8"))
        self.assertNotIn("uploads", stored)

    # -- 8 a count short of the card asks the client, never cancels -----------

    def test_mismatch_asks_the_client_instead_of_cancelling(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = bridge._refuse_mismatch(self.base, MACHINE_KEY,
                                           "r_mismatch01", (3, 5))
        self.assertEqual(code, bridge.EXIT["refused"])
        posts = [r for r in STUDIO["seen"] if r["path"].endswith("/state")]
        self.assertEqual(len(posts), 1, posts)
        self.assertEqual(posts[0]["body"]["event"], "needs_you")
        self.assertEqual(posts[0]["body"]["reason"],
                         "A few of your answers need a second look. "
                         "Open your studio page and tap Continue.")
        self.assertNotIn("cancel", [r["body"].get("event") for r in posts])
        stderr = err.getvalue()
        self.assertIn("REPLAY_QUESTION_MISMATCH", stderr)
        self.assertIn("3 replies", stderr)
        self.assertIn("5 questions", stderr)
        # control on the SAME function: the order never left `waiting` (its
        # claim post was refused), so the service answers 409 - accepted and
        # logged, never a different event and never a failed poll
        STUDIO["seen"] = []
        STUDIO["needs_you_409"] = True
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            again = bridge._refuse_mismatch(self.base, MACHINE_KEY,
                                            "r_mismatch02", (2, 6))
        self.assertEqual(again, bridge.EXIT["refused"])
        events = [r["body"].get("event") for r in STUDIO["seen"]
                  if r["path"].endswith("/state")]
        self.assertEqual(events, ["needs_you"])
        self.assertIn("409", err.getvalue())

    # -- 9 a card-refused replay waits on the client, never blocks the box ----

    def poll_real_card(self):
        """One poll against the REAL card and factory (the halt is the card's)."""
        return self.run_bridge(["poll", "--skill-root", str(SKILL_ROOT),
                                "--runs", str(self.runs),
                                "--base-url", self.base], DS_KEY=MACHINE_KEY)

    def test_a_halted_replay_waits_on_the_client_and_releases_the_claim(self):
        replies = self._card_replies("2")
        STUDIO["line"] = 'DRAMA_ORDER r_halt01 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_halt01", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": replies}
        p = self.poll_real_card()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, "")                 # no wake line for it
        self.assertIn("testimonial-permission-pending", p.stderr)
        posts = [r["body"] for r in STUDIO["seen"]
                 if r["path"].endswith("/state")
                 and r["body"].get("event") == "needs_you"]
        self.assertEqual(len(posts), 1, posts)
        self.assertEqual(posts[0]["reason"],
                         "Your order is paused until you have your client's OK "
                         "to use their story. Open your order and tap Continue "
                         "when you have it.")
        halted = json.loads((self.runs / "r_halt01" / "control"
                             / "replay-halted.json").read_text(encoding="utf-8"))
        self.assertEqual(halted["reason_code"], "testimonial-permission-pending")
        self.assertEqual(halted["question_id"], "recap")
        self.assertEqual(self._orders(), [])          # the claim was released
        # the second poll still CHECKS IN (the box is alive for other orders)
        STUDIO["seen"] = []
        again = self.poll_real_card()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("POST", [r["method"] for r in STUDIO["seen"]
                               if r["path"].endswith("/checkin")])
        self.assertEqual(again.stdout, "")
        self.assertEqual(self._orders(), [])

    def test_a_halted_order_does_not_block_the_next_one(self):
        replies = self._card_replies("2")
        STUDIO["line"] = 'DRAMA_ORDER r_halt02 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_halt02", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": replies}
        first = self.poll_real_card()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(self._orders(), [])
        # control on the SAME box: a new waiting order is claimed on the next
        # poll - the halted one is not on the ledger any more and holds nothing
        STUDIO["seen"] = []
        STUDIO["line"] = 'DRAMA_ORDER r_next02 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_next02", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": replies}
        second = self.poll_real_card()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        claimed = [r["path"] for r in STUDIO["seen"]
                   if r["method"] == "POST" and r["path"].endswith("/state")
                   and r["body"].get("event") == "claim"]
        self.assertEqual(claimed, ["/api/studio/orders/r_next02/state"])
        fetched = [(r["method"], r["path"]) for r in STUDIO["seen"]]
        self.assertIn(("GET", "/api/studio/orders/r_next02"), fetched)

    # -- 10 ids that do not match the card's ask the client first -------------

    def test_reply_ids_that_do_not_match_ask_the_client_first(self):
        replies = ["2", "2", "Spring cookie class for local families"]
        asked = bridge._card_replay(str(SKILL_ROOT), replies)[0]
        self.assertEqual(asked, ["purpose", "permission", "offer"])
        # controls on the SAME function: the card's own ids agree (with or
        # without the page's trailing recap id); a reordered page does not
        self.assertIsNone(bridge._reply_id_mismatch(str(SKILL_ROOT), asked, replies))
        self.assertIsNone(bridge._reply_id_mismatch(str(SKILL_ROOT),
                                                    asked + ["recap"], replies))
        page = ["permission", "purpose", "offer"]
        self.assertIsNotNone(bridge._reply_id_mismatch(str(SKILL_ROOT), page, replies))
        STUDIO["line"] = 'DRAMA_ORDER r_ids01 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_ids01", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": replies,
                           "reply_ids": page}
        p = self.poll_real_card()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, "")                 # no wake line for it
        self.assertIn("INTAKE_REPLAY_MISMATCH", p.stderr)
        posts = [r["body"] for r in STUDIO["seen"]
                 if r["path"].endswith("/state")
                 and r["body"].get("event") == "needs_you"]
        self.assertEqual(len(posts), 1, posts)
        self.assertEqual(posts[0]["reason"],
                         "One of your answers did not match the choices. "
                         "Open your order and tap Continue to fix it.")
        halted = json.loads((self.runs / "r_ids01" / "control"
                             / "replay-halted.json").read_text(encoding="utf-8"))
        self.assertEqual(halted["reason_code"], "INTAKE_REPLAY_MISMATCH")
        self.assertEqual(halted["question_id"], "purpose")
        self.assertEqual(self._orders(), [])

    # -- 11 option text: a reordered list asks, never guesses (S75-059) ------

    def _numbered(self, replies):
        """The card's own replies in the new page format: "<n>. <option text>"."""
        core = str(SKILL_ROOT / "scripts" / "core")
        if core not in sys.path:
            sys.path.insert(0, core)
        from choice_card.intake_card import intake_card as IC
        out, accepted = [], []
        for reply in replies:
            qs = IC._shaped(IC.QUESTIONS, accepted, "")
            if len(accepted) >= len(qs):
                out.append(reply)          # the recap confirmation, not a screen
                continue
            q = qs[len(accepted)]
            n = str(reply).strip()
            opts = q.get("options") or []
            if q.get("free_text") or not (n.isdigit() and 1 <= int(n) <= len(opts)):
                out.append(n)          # a typed answer or amount: never numbered
                answer = IC._parse(n, q)
            else:
                out.append("%s. %s" % (n, opts[int(n) - 1][0]))
                answer = IC._parse(n, q)
            if isinstance(answer, dict) and "error" not in answer:
                accepted.append(answer)
        return out

    def test_option_text_travels_with_the_number(self):
        replies = self._card_replies("2")
        numbered = self._numbered(replies)
        plain, mismatch = bridge._plain_replies(str(SKILL_ROOT), numbered)
        self.assertIsNone(mismatch)
        self.assertEqual(plain, replies)       # the card receives its numbers
        # control on the SAME function: an old page (bare numbers, bare typed
        # answers) passes straight through, unchanged and unjudged
        self.assertEqual(bridge._plain_replies(str(SKILL_ROOT), replies),
                         (replies, None))
        # a reordered option list: number 2 now carries another screen's option
        # text, so the number can never be trusted on its own
        swapped = list(numbered)
        swapped[0] = "%s. %s" % (numbered[0].split(". ", 1)[0],
                                 numbered[1].split(". ", 1)[1])
        _, found = bridge._plain_replies(str(SKILL_ROOT), swapped)
        self.assertIsNotNone(found)
        self.assertEqual(found[0], 0)
        self.assertEqual(found[1], "purpose")

    def test_reordered_option_text_asks_the_client_never_guesses(self):
        numbered = self._numbered(self._card_replies("3"))   # a lesson
        slots = [i for i, r in enumerate(numbered) if ". " in r]
        self.assertGreaterEqual(len(slots), 2, numbered)
        first, second = slots[0], slots[1]
        swapped = list(numbered)
        swapped[first] = "%s. %s" % (numbered[first].split(". ", 1)[0],
                                     numbered[second].split(". ", 1)[1])
        STUDIO["line"] = 'DRAMA_ORDER r_text01 "Spring Sale"'
        STUDIO["order"] = {"order_id": "r_text01", "client_id": CLIENT,
                           "title": "Spring Sale", "replies": swapped}
        p = self.poll_real_card()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, "")                 # no wake line for it
        self.assertIn("INVALID_OPTION", p.stderr)
        posts = [r["body"] for r in STUDIO["seen"]
                 if r["path"].endswith("/state")
                 and r["body"].get("event") == "needs_you"]
        self.assertEqual(len(posts), 1, posts)
        self.assertEqual(posts[0]["reason"],
                         "One of your answers did not match the choices. "
                         "Open your order and tap Continue to fix it.")
        halted = json.loads((self.runs / "r_text01" / "control"
                             / "replay-halted.json").read_text(encoding="utf-8"))
        self.assertEqual(halted["reason_code"], "INVALID_OPTION")
        self.assertEqual(halted["question_id"], "purpose")
        self.assertEqual(self._orders(), [])           # the claim was released

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
