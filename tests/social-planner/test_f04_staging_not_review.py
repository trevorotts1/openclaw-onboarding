#!/usr/bin/env python3
"""test_f04_staging_not_review.py — F04 acceptance (QC-F04).

"Do not move staged Skill 35 work into review."

run-publishing-cycle.sh STAGES a cycle: it returns an explicit QUEUED result
with a durable dispatch record (working/dispatch.json) and NEVER moves the
Command Center task out of backlog at staging. in_progress requires an ACCEPTED
WORKER EXECUTION (--ack-execution); review requires EVERY phase complete with
verified sha256 artifact hashes (--complete-phase N + --mark-review). With all
workers stopped the cycle stays queued (+ overdue past the threshold) with NO
review/completion receipt.

QC-F04 matrix (unittest, offline — no network, a fake in-process CC board):
  1. Staging with no worker -> state=queued, card stays backlog, NEVER
     in_progress/review/done, no completion receipt; overdue fires past the
     threshold.
  2. Worker ack -> state=in_progress and the CC card moves in_progress AT THE
     ACK (never at staging).
  3. --complete-phase without artifacts / without an ack -> refused (exit 7).
  4. Artifacts + verified sha256 hashes per phase -> review only after ALL 5.
  5. Tampering with a completed phase's artifacts -> review refused (hash
     re-verified at the review boundary).
  6. A foreign worker cannot complete a phase; ack on a review-state cycle is
     refused.
  7. The public contract: --help documents the queue/ack/complete/review
     lifecycle and the script never PATCHes in_progress or review from the
     staging path.

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_ONB_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ONB_ROOT / "35-social-media-planner" / "scripts" / "run-publishing-cycle.sh"
assert _SCRIPT.is_file(), "run-publishing-cycle.sh not found"

_PLATFORMS = "linkedin"


# ---------------------------------------------------------------------------
# Offline helpers: fixture $HOME (Skill 35 prereqs) + a curl stub that refuses
# the LIVE GHL preflight (transient-warn path) but forwards board traffic.
# ---------------------------------------------------------------------------
def _make_fixture_home(root: Path) -> Path:
    oc = root / ".openclaw"
    (oc / "secrets").mkdir(parents=True, exist_ok=True)
    (oc / "config").mkdir(parents=True, exist_ok=True)
    for f in ("SOUL.md", "IDENTITY.md", "USER.md"):
        (oc / f).write_text("fixture %s" % f, encoding="utf-8")
    (oc / "secrets" / ".env").write_text(
        "GOHIGHLEVEL_API_KEY=fixture-key\nGOHIGHLEVEL_LOCATION_ID=fixture-loc\n",
        encoding="utf-8")
    (oc / "openclaw.json").write_text('{"agents": {"list": []}}', encoding="utf-8")
    return root


class _FakeBoard:
    """In-process Command Center stand-in (ingest + PATCH + GET), no network
    beyond loopback. Dedupes on idempotency_key like the real ingest route."""

    def __init__(self):
        self.tasks = {}
        self.moves = []
        self._seq = 0
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        self.base = "http://127.0.0.1:%d" % self._srv.server_address[1]

    def _handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def _send(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path == "/api/tasks/ingest":
                    p = json.loads(body or b"{}")
                    key = p.get("idempotency_key")
                    if key and key in outer.tasks:
                        return self._send(200, {"ok": True, "deduped": True,
                                                "task_id": outer.tasks[key]})
                    outer._seq += 1
                    tid = "task-%d" % outer._seq
                    outer.tasks[key] = tid
                    outer.tasks[tid] = "backlog"
                    return self._send(200, {"ok": True, "deduped": False, "task_id": tid})
                return self._send(404, {"ok": False})

            def do_PATCH(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                tid = self.path.rstrip("/").rsplit("/", 1)[-1]
                st = (json.loads(body or b"{}") or {}).get("status")
                outer.moves.append((tid, outer.tasks.get(tid), st))
                outer.tasks[tid] = st
                return self._send(200, {"ok": True})

            def do_GET(self):
                tid = self.path.rstrip("/").rsplit("/", 1)[-1]
                return self._send(200, {"id": tid, "status": outer.tasks.get(tid, "backlog")})

        return H

    def status(self, task_id):
        with urllib.request.urlopen(self.base + "/api/tasks/" + task_id, timeout=5) as r:
            return json.load(r).get("status")

    def stop(self):
        self._srv.shutdown()
        self._srv.server_close()


_CURL_STUB = """#!/bin/sh
# test stub: refuse the LIVE GHL preflight (transient-warn path), forward the rest
for a in "$@"; do
  case "$a" in
    *leadconnectorhq.com*) exit 7 ;;
  esac
done
exec {REAL_CURL} "$@"
"""


class _Cycle:
    """One staged cycle against an optional fake board."""

    def __init__(self, home: Path, board: _FakeBoard | None):
        self.home = home
        self.run_dir = home / "run"
        self.board = board
        self.stub = home / "bin"
        self.stub.mkdir(parents=True, exist_ok=True)
        p = self.stub / "curl"
        p.write_text(_CURL_STUB.format(REAL_CURL=shutil.which("curl") or "/usr/bin/curl"),
                     encoding="utf-8")
        p.chmod(0o755)

    def run(self, *args):
        env = {
            "HOME": str(self.home),
            "PATH": "%s:/usr/bin:/bin" % self.stub,
        }
        if self.board is not None:
            env["MISSION_CONTROL_URL"] = self.board.base
            env["MC_API_TOKEN"] = "test-token"
        return subprocess.run(["bash", str(_SCRIPT), *args],
                              capture_output=True, text=True, timeout=120, env=env)

    def stage(self):
        return self.run("--topic", "F04 acceptance", "--platforms", _PLATFORMS,
                        "--workdir", str(self.run_dir))

    @property
    def dispatch(self):
        return json.loads((self.run_dir / "working" / "dispatch.json").read_text())

    def cc_task_id(self):
        return self.dispatch.get("cc_task_id") or ""

    def complete_phase(self, phase, worker="w1"):
        pdir = self.run_dir / "working" / ("phase-%s" % phase) / "artifacts"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / ("artifact-%s.txt" % phase)).write_text("phase %s output" % phase,
                                                      encoding="utf-8")
        return self.run("--complete-phase", str(phase), "--worker-id", worker,
                        "--workdir", str(self.run_dir))


class TestStagingIsQueuedNeverReview(unittest.TestCase):
    """QC-F04 setup 1: run the staging entry with NO worker."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = _make_fixture_home(Path(self.tmp.name) / "home")
        self.cycle = _Cycle(self.home, board=None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_staging_returns_queued_with_durable_dispatch_record(self):
        p = self.cycle.stage()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("QUEUED", p.stdout)
        d = self.cycle.dispatch
        self.assertEqual(d["state"], "queued")
        self.assertEqual(d["accepted_execution"], None)
        self.assertEqual(d["completion_receipt"], None)
        self.assertFalse(d["review_eligible"])
        # Durable record connects to the consumer model (CC dispatcher / F33)
        # with per-phase operation keys (W0 dispatch.json contract).
        self.assertIn("dispatcher", str(d.get("consumer", "")))
        keys = d.get("operation_keys") or {}
        self.assertEqual(len(keys), 5, "one operation key per phase")
        for i in range(1, 6):
            self.assertEqual(keys.get("phase-%d" % i),
                             "skill35-cycle:%s:phase-%d" % (d["run_id"], i))

    def test_staging_never_writes_review_or_completion_receipt(self):
        self.cycle.stage()
        # No completion receipt artifacts anywhere in the run dir.
        self.assertIsNone(self.cycle.dispatch.get("completion_receipt"))
        handoff = (self.cycle.run_dir / "READY-FOR-ORCHESTRATOR").read_text()
        self.assertIn("STAGED", handoff)
        self.assertNotIn("Cycle complete", handoff)
        journal = (self.cycle.run_dir / "journal.log").read_text()
        self.assertNotIn("review", journal.lower().replace("review-eligible", ""))

    def test_staged_cycle_is_overdue_with_workers_stopped_never_done(self):
        self.cycle.stage()
        p = self.cycle.run("--status", "--workdir", str(self.cycle.run_dir),
                           "--overdue-after", "0")
        self.assertEqual(p.returncode, 0, p.stderr)
        st = json.loads(p.stdout)
        self.assertEqual(st["state"], "queued")
        self.assertTrue(st["overdue"], "a queued cycle with no worker ack must be OVERDUE")
        self.assertIn("no worker ack", st["overdue_reason"])
        self.assertFalse(st["review_eligible"])
        self.assertIsNone(st["completion_receipt"])

    def test_help_documents_lifecycle_and_staging_is_not_completion(self):
        p = self.cycle.run("--help")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("--ack-execution", p.stdout)
        self.assertIn("--complete-phase", p.stdout)
        self.assertIn("--mark-review", p.stdout)
        self.assertIn("--status", p.stdout)
        self.assertIn("LIFECYCLE", p.stdout)
        self.assertIn("queued", p.stdout)
        self.assertIn("OVERDUE", p.stdout)


class TestAcceptedExecutionBoundary(unittest.TestCase):
    """QC-F04 setup 2: in_progress ONLY after worker acknowledgement."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = _make_fixture_home(Path(self.tmp.name) / "home")
        self.board = _FakeBoard()
        self.cycle = _Cycle(self.home, board=self.board)

    def tearDown(self):
        self.board.stop()
        self.tmp.cleanup()

    def test_card_stays_backlog_at_staging_then_in_progress_at_ack(self):
        p = self.cycle.stage()
        self.assertEqual(p.returncode, 0, p.stderr)
        tid = self.cycle.cc_task_id()
        self.assertTrue(tid, "staging registers a CC card")
        self.assertEqual(self.board.status(tid), "backlog",
                         "staging must NOT move the card (old in_progress lie)")
        # No in_progress/review PATCH may have been issued by staging.
        self.assertEqual(self.board.moves, [], "staging issues no card moves")

        ack = self.cycle.run("--ack-execution", "--worker-id", "w1",
                             "--workdir", str(self.cycle.run_dir))
        self.assertEqual(ack.returncode, 0, ack.stderr)
        rec = json.loads(ack.stdout.strip().splitlines()[-1])
        self.assertTrue(rec.get("ok"))
        self.assertEqual(self.cycle.dispatch["state"], "in_progress")
        self.assertEqual(self.board.status(tid), "in_progress",
                         "the CC in_progress move happens AT THE ACK, not before")
        self.assertEqual(self.board.moves, [(tid, "backlog", "in_progress")])

    def test_ack_without_a_card_records_execution_and_state(self):
        self.cycle.stage()
        # Drop the board (simulate a board-less box): the durable record still
        # moves to in_progress on the accepted execution.
        self.cycle.board = None
        ack = self.cycle.run("--ack-execution", "--worker-id", "w2",
                             "--workdir", str(self.cycle.run_dir))
        self.assertEqual(ack.returncode, 0, ack.stderr)
        d = self.cycle.dispatch
        self.assertEqual(d["state"], "in_progress")
        self.assertEqual((d.get("accepted_execution") or {}).get("worker_id"), "w2")

    def test_ack_is_idempotent_for_the_same_worker(self):
        self.cycle.stage()
        self.cycle.run("--ack-execution", "--worker-id", "w3",
                       "--workdir", str(self.cycle.run_dir))
        again = self.cycle.run("--ack-execution", "--worker-id", "w3",
                               "--workdir", str(self.cycle.run_dir))
        self.assertEqual(again.returncode, 0, again.stderr)


class TestArtifactsBeforeReview(unittest.TestCase):
    """QC-F04: review requires expected artifacts + verified sha256 hashes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = _make_fixture_home(Path(self.tmp.name) / "home")
        self.board = _FakeBoard()
        self.cycle = _Cycle(self.home, board=self.board)

    def tearDown(self):
        self.board.stop()
        self.tmp.cleanup()

    def _staged_and_acked(self, worker="w1"):
        self.cycle.stage()
        self.cycle.run("--ack-execution", "--worker-id", worker,
                       "--workdir", str(self.cycle.run_dir))
        return worker

    def test_complete_phase_without_ack_refused(self):
        self.cycle.stage()
        p = self.cycle.complete_phase(1, worker="nobody-acked")
        self.assertEqual(p.returncode, 7, "completion without an accepted execution is refused")
        self.assertIn("accepted worker execution", p.stderr)

    def test_complete_phase_without_artifacts_refused(self):
        self._staged_and_acked()
        p = self.cycle.run("--complete-phase", "1", "--worker-id", "w1",
                           "--workdir", str(self.cycle.run_dir))
        self.assertEqual(p.returncode, 7)
        self.assertIn("artifacts", p.stderr)

    def test_empty_artifacts_directory_refused(self):
        self._staged_and_acked()
        (self.cycle.run_dir / "working" / "phase-1" / "artifacts").mkdir(parents=True)
        p = self.cycle.run("--complete-phase", "1", "--worker-id", "w1",
                           "--workdir", str(self.cycle.run_dir))
        self.assertEqual(p.returncode, 7)
        self.assertIn("EMPTY", p.stderr)

    def test_foreign_worker_cannot_complete_a_phase(self):
        self._staged_and_acked(worker="w1")
        p = self.cycle.complete_phase(1, worker="w-impersonator")
        self.assertEqual(p.returncode, 7)
        self.assertIn("not the accepted executor", p.stderr)

    def test_review_refused_until_every_phase_complete_with_hashes(self):
        worker = self._staged_and_acked()
        for i in (1, 2, 3, 4):
            self.cycle.complete_phase(i, worker=worker)
        p = self.cycle.run("--mark-review", "--workdir", str(self.cycle.run_dir))
        self.assertEqual(p.returncode, 7, "review before phase 5 is refused")
        self.assertIn("5", p.stderr)
        self.cycle.complete_phase(5, worker=worker)
        p = self.cycle.run("--mark-review", "--workdir", str(self.cycle.run_dir))
        self.assertEqual(p.returncode, 0, p.stderr)
        d = self.cycle.dispatch
        self.assertEqual(d["state"], "review")
        self.assertTrue(d["review_eligible"])
        # Each completed phase recorded verified sha256 hashes.
        for rec in d["phases_complete"]:
            self.assertTrue(rec["sha256"], "phase %s records artifact hashes" % rec["phase"])
            self.assertEqual(len(rec["sha256"]), rec["artifacts"])
        tid = self.cycle.cc_task_id()
        self.assertEqual(self.board.status(tid), "review",
                         "the CC review move happens at --mark-review only")
        self.assertNotIn("done", [m[2] for m in self.board.moves],
                         "no producer path ever sets done")

    def test_review_reverifies_hashes_tampering_refused(self):
        worker = self._staged_and_acked()
        for i in range(1, 6):
            self.cycle.complete_phase(i, worker=worker)
        artifact = (self.cycle.run_dir / "working" / "phase-2" / "artifacts"
                    / "artifact-2.txt")
        artifact.write_text("TAMPERED after completion", encoding="utf-8")
        p = self.cycle.run("--mark-review", "--workdir", str(self.cycle.run_dir))
        self.assertEqual(p.returncode, 7, "a post-completion edit invalidates review")
        self.assertIn("changed after its hash was recorded", p.stderr)
        d = self.cycle.dispatch
        self.assertNotEqual(d["state"], "review")

    def test_ack_on_review_cycle_refused(self):
        worker = self._staged_and_acked()
        for i in range(1, 6):
            self.cycle.complete_phase(i, worker=worker)
        self.cycle.run("--mark-review", "--workdir", str(self.cycle.run_dir))
        p = self.cycle.run("--ack-execution", "--worker-id", "w-late",
                           "--workdir", str(self.cycle.run_dir))
        self.assertEqual(p.returncode, 7)
        self.assertIn("cannot ack a review cycle", p.stderr)

    def test_worker_stopped_after_ack_cycle_stays_in_progress_overdue_not_done(self):
        """A worker acks then dies: the cycle holds in_progress; it never
        acquires review/done or a completion receipt on its own."""
        self._staged_and_acked(worker="w1")
        d = self.cycle.dispatch
        self.assertEqual(d["state"], "in_progress")
        self.assertIsNone(d["completion_receipt"])
        st = self.cycle.run("--status", "--workdir", str(self.cycle.run_dir))
        rec = json.loads(st.stdout)
        self.assertEqual(rec["state"], "in_progress")
        self.assertFalse(rec["overdue"], "an ACKED cycle is not overdue (an execution exists)")


class TestPublicContract(unittest.TestCase):
    """The script's own contract: no staging-path in_progress/review PATCHes."""

    def test_staging_path_never_patches_in_progress_or_review(self):
        src = _SCRIPT.read_text()
        # The staging CC block sits between "register the staged cycle" and the
        # "phase execution" section: the ack/mark-review lifecycle modes PATCH
        # the card BY DESIGN elsewhere; the STAGING block must not.
        staging = src.split("Command Center: register the staged cycle")[1]
        staging = staging.split("# ---------- phase execution ----------")[0]
        self.assertNotIn('\\"status\\":\\"in_progress\\"', staging,
                         "staging must not move the card to in_progress")
        self.assertNotIn('\\"status\\":\\"review\\"', staging,
                         "staging must not move the card to review")

    def test_dispatch_record_follows_w0_contract_fields(self):
        src = _SCRIPT.read_text()
        # The record binds to the W0 dispatch.json CONTRACT via shared-utils'
        # ExecutionPolicy (F33) — operation keys + consumer binding live in the
        # script; lease fields live in the policy it dispatches against.
        for field in ("operation_key", "worker_id"):
            self.assertIn(field, src,
                          "dispatch record references the W0 dispatch.json contract (%s)" % field)
        policy = (_ONB_ROOT / "shared-utils" / "social_execution_policy.py").read_text()
        for field in ("fencing_token", "lease_expires_at", "heartbeat_at", "retry_at"):
            self.assertIn(field, policy,
                          "the execution policy carries the W0 lease contract (%s)" % field)
        self.assertIn("social-publish-dispatcher", src,
                      "durable consumer model binding present")


if __name__ == "__main__":
    unittest.main()