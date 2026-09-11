#!/usr/bin/env python3
"""PRES-008 acceptance gate: the bridge declares processed ONLY when the
handoff is durably complete, and every refusal/deferral stays retryable.

Run: python3 test/test_pres008_durable_states.py

The five QC-PRES-008 scenarios, end to end through cmd_ingest/cmd_poll with
stubbed transports (worker HTTP stubbed at module boundary, cc_board and
presentation_job stubbed at their loader boundary — the durable-state
machine launch_ledger.py itself is the REAL production module):

  1. Mock engine refusal + successful CC card => remains launch_pending,
     retries next tick, NO duplicate card.
  2. Successful launch then crash before ledger write => resume discovers
     the existing worker, NO second executor.
  3. Worker endpoint returns 202 deferred => NO processed mark.
  4. Poison session does not block a healthy one.
  5. Both pollers concurrently target the same run => ONE active execution,
     ownership recoverable.
"""
from __future__ import annotations

import io
import json
import contextlib
import pathlib
import subprocess
import sys
import tempfile
import time
import types
import unittest
import urllib.error
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "bridge"))

_SCRIPTS = HERE.parent.parent.parent / "scripts"
if (_SCRIPTS / "presentation_job" / "lease.py").is_file():
    sys.path.insert(0, str(_SCRIPTS))

import intake_bridge as ib  # noqa: E402
import launch_ledger as _ll  # noqa: E402

FAST_POLICY = {
    "backoff_base_s": 0.0,          # tests: retries are due immediately
    "backoff_cap_s": 0.0,
    "max_attempts": 10,
    "notify_thresholds": (3, 7),
    "claim_ttl_s": 120.0,
}


def _intake(session_id: str) -> dict:
    return {
        "intake_session_id": session_id,
        "deck_type": "signature_presentation",
        "presentation_type": "signature",
        "requester_chat_id": "12345",
        "answers": {"presentation_type": "signature", "offer_name": "X"},
        "deck_brief": {"OFFER_NAME": "X", "NAMED_METHODOLOGY": "Method", "TRANSFORMATION_PROMISE": "Improve", "TIME_TO_RESULT": "8 weeks", "AUDIENCE": "Founders", "CTA_ACTION": "Book", "TONE": "Clear", "FINAL_PRICE": "$10"},
        "pre_presentation_capture": {"PRESENTATION_TYPE": "signature", "WANT_SALES_CHECKOUT": "no", "WANT_VSL_PAGE": "no"},
    }


class _StubWorld:
    """All external actors stubbed at their loader boundary; the state
    machine underneath is the real launch_ledger.py."""

    def __init__(self, tc: unittest.TestCase, tmp: pathlib.Path):
        self.tc = tc
        self.runs = tmp / "pres-runs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self.dispatch_calls: list[dict] = []
        self.card_calls: list[dict] = []
        self.next_dispatch_rc = 4242          # a PID-shaped success
        self.next_card_task_id = "CC-STUB-1"
        self.next_dispatch_error: str | None = None
        self._patches = []

    # -- presentation_job stub -------------------------------------------------
    def _fake_pj(self) -> types.SimpleNamespace:
        world = self

        class _L:
            DISPATCH_UNKNOWN_DECK_TYPE = -5
            DISPATCH_CAPACITY_REFUSED = -4
            DISPATCH_NOTIFY_REFUSED = -7
            DISPATCH_OCR_REFUSED = -8
            DISPATCH_CREDIT_REFUSED = -6
            DISPATCH_MODE_INVALID = -9

            def dispatch_new(self, run_dir, client=None, deck_type=None,
                             background=True, requested_parallel=None, mode=None):
                world.dispatch_calls.append({"run_dir": str(run_dir),
                                             "deck_type": deck_type})
                if world.next_dispatch_error:
                    raise RuntimeError(world.next_dispatch_error)
                return world.next_dispatch_rc

        import presentation_job.lease as real_lease
        return types.SimpleNamespace(launcher=_L(), lease=real_lease)

    # -- cc_board stub ----------------------------------------------------------
    def _fake_cc(self) -> types.SimpleNamespace:
        world = self

        class _CC:
            def ingest_deck_task(self, run_dir, deck_slug=None, title=None,
                                 description=None, priority=None,
                                 requester_chat_id=None):
                world.card_calls.append({"deck_slug": deck_slug})
                return world.next_card_task_id

        return types.SimpleNamespace(ingest_deck_task=_CC().ingest_deck_task)

    def install(self):
        self._patches = [
            mock.patch.object(ib, "_load_presentation_job", self._fake_pj),
            mock.patch.object(ib, "_load_cc_board", lambda: self._fake_cc()),
            mock.patch.object(ib, "_retry_policy", lambda: dict(FAST_POLICY)),
        ]
        for p in self._patches:
            p.start()
            self.tc.addCleanup(p.stop)

    # -- worker stub --------------------------------------------------------------
    def intake_payload(self, session_id: str) -> dict:
        return {"intake": _intake(session_id)}


def _ingest_ns(worker_url: str, session_id: str, run_root: pathlib.Path,
               verbose: bool = False) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        worker_url=worker_url, session_id=session_id,
        run_dir=str(run_root), verbose=verbose,
        per_session_dirs=True, no_per_session_dirs=False, func=ib.cmd_ingest,
    )


def _fetch_ok(args) -> dict:
    return {"intake": _intake(args.session_id)}


class TestPres008DurableStates(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.world = _StubWorld(self, self.tmp)
        self.world.install()
        self._orig_fetch = ib._fetch_intake
        ib._fetch_intake = _fetch_ok
        self.addCleanup(setattr, ib, "_fetch_intake", self._orig_fetch)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # Scenario 1: mock engine refusal + successful CC card => remains
    # launch_pending, retries next tick, no duplicate card.
    # ------------------------------------------------------------------
    def test_01_refusal_with_card_stays_launch_pending_retries_no_dup_card(self):
        w = self.world
        w.next_dispatch_rc = -7  # AF-NOTIFY-UNCONFIGURED: retryable refusal
        root = w.runs

        with contextlib.redirect_stderr(io.StringIO()):
            rc1 = ib.cmd_ingest(_ingest_ns("http://w", "sess-r1", root))
        self.assertEqual(rc1, 7, "a retryable refusal is DEFERRED, not success")
        rd = root / "sess-r1"
        doc = _ll.load(rd, "sess-r1")
        self.assertIsNotNone(doc)
        self.assertIn(doc["state"], (_ll.LAUNCH_PENDING, _ll.FAILED_RETRYABLE))
        self.assertEqual(doc.get("board_task_id"), "CC-STUB-1",
                         "the card binding is persisted before the launch")
        self.assertEqual(len(w.card_calls), 1, "exactly one card so far")
        self.assertFalse(_ll.is_complete(doc), "refusal is NOT processed")

        # next tick: engine healthy now — the SAME submission re-drives.
        w.next_dispatch_rc = 4242
        # simulate the engine having started and died leaving no live pid:
        # dispatch succeeds, no live worker -> launching, retried next tick.
        with contextlib.redirect_stderr(io.StringIO()):
            rc2 = ib.cmd_ingest(_ingest_ns("http://w", "sess-r1", root))
        self.assertEqual(rc2, 7)
        self.assertEqual(len(w.card_calls), 1,
                         "NO duplicate card on the retry")
        self.assertEqual(len(w.dispatch_calls), 2, "the launch WAS retried")
        doc2 = _ll.load(rd, "sess-r1")
        self.assertEqual(doc2.get("board_task_id"), "CC-STUB-1",
                         "board binding survives the retry")

    # ------------------------------------------------------------------
    # Scenario 2: successful launch then crash before ledger write =>
    # resume discovers the existing worker, no second executor.
    # ------------------------------------------------------------------
    def test_02_crash_before_ledger_resume_discovers_worker_no_second_executor(self):
        w = self.world
        root = w.runs
        rd = root / "sess-c1"

        # The engine "starts" (state.json names a live pid) but the bridge
        # process dies BEFORE writing the state document. Simulate: create
        # the run-dir record + a live engine, NO submission state file.
        sentinel = subprocess.Popen(
            ["/usr/bin/env", "python3", "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.2)
            rd.mkdir(parents=True, exist_ok=True)
            (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
            (rd / "working" / "copy" / "intake.json").write_text(
                json.dumps(_intake("sess-c1")), encoding="utf-8")
            (rd / "state.json").write_text(json.dumps({
                "job_id": "pj_crashed_bridge", "engine_pid": sentinel.pid}),
                encoding="utf-8")
            self.assertFalse((_ll.state_path(rd, "sess-c1")).exists(),
                             "fixture: the ledger write never happened")

            with contextlib.redirect_stderr(io.StringIO()):
                rc = ib.cmd_ingest(_ingest_ns("http://w", "sess-c1", root))
            self.assertEqual(rc, 0)
            self.assertEqual(len(w.dispatch_calls), 0,
                             "resume must NOT spawn a second executor")
            doc = _ll.load(rd, "sess-c1")
            self.assertTrue(_ll.is_complete(doc))
            self.assertEqual(doc["worker_ack"]["execution_id"],
                             "pj_crashed_bridge",
                             "the CURRENT execution id is what completed it")
        finally:
            sentinel.kill()
            sentinel.wait()

    # ------------------------------------------------------------------
    # Scenario 3: worker endpoint returns 202 deferred => no processed mark.
    # ------------------------------------------------------------------
    def test_03_worker_202_deferred_is_not_processed(self):
        w = self.world
        root = w.runs

        def fake_dept_start(session_id, intake):
            return 202, ("worker returned 202 deferred (COMMAND_CENTER_URL unset) — "
                         "NOT success; submission stays unprocessed and retries")
        with mock.patch.object(ib, "_load_cc_board", lambda: None), \
                mock.patch.object(ib, "_dept_start_via_worker", fake_dept_start):
            with contextlib.redirect_stderr(io.StringIO()):
                rc = ib.cmd_ingest(_ingest_ns("http://w", "sess-202", root))
        self.assertEqual(rc, 7, "202 deferred is a deferral, not rc 0")
        doc = _ll.load(root / "sess-202", "sess-202")
        self.assertIsNotNone(doc)
        self.assertFalse(_ll.is_complete(doc))
        self.assertNotEqual(doc["state"], _ll.WORKER_ACKNOWLEDGED)
        # no intake record was marked processed anywhere
        self.assertEqual(_ll.list_submissions(root / "sess-202"),
                         ["intake_submission_state.json"])
        self.assertIn(doc["state"], (_ll.BOARD_REGISTERED, _ll.LAUNCH_PENDING))

    # ------------------------------------------------------------------
    # Scenario 4: poison session does not block a healthy one.
    # ------------------------------------------------------------------
    def test_04_poison_session_does_not_block_healthy(self):
        w = self.world
        root = w.runs
        healthy = "sess-ok"
        poisoned = "sess-bad"

        real_fetch = ib._fetch_intake

        def fetch_mixed(args):
            if args.session_id == poisoned:
                raise RuntimeError("malformed payload from worker")
            return real_fetch(args)

        ib._fetch_intake = fetch_mixed
        try:
            listed = [{"session_id": poisoned}, {"session_id": healthy}]

            def fake_list(args):
                return listed
            with mock.patch.object(ib, "_list_intakes", fake_list):
                # poll writes json to stdout; capture but ignore
                buf = io.StringIO()
                err = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                    rc = ib.cmd_poll(types.SimpleNamespace(
                        worker_url="http://w", run_dir=str(root),
                        verbose=False, per_session_dirs=True,
                        no_per_session_dirs=False, func=ib.cmd_poll))
        finally:
            ib._fetch_intake = real_fetch
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["crashed"], 1, "the poison session is contained")
        self.assertEqual(summary["completed"], 0)
        doc = _ll.load(root / healthy, healthy)
        self.assertIsNotNone(doc, "the healthy session was still driven")
        # healthy run: dispatch rc 4242 (no live engine in stub) -> deferred
        self.assertFalse(_ll.is_complete(doc))
        self.assertEqual(len(w.card_calls), 1, "healthy session got its card")

    # ------------------------------------------------------------------
    # Scenario 5: both pollers concurrently target the same run =>
    # one active execution, recoverable ownership.
    # ------------------------------------------------------------------
    def test_05_dual_pollers_one_execution_recoverable_ownership(self):
        w = self.world
        root = w.runs
        rd = root / "sess-dual"

        # Poller A holds the claim (a genuinely live process: THIS test proc
        # writes its claim via _submission_hold, then a SECOND poller process
        # runs the same submission and must skip the dispatch).
        doc_a = ib._submission_hold(rd, "sess-dual", FAST_POLICY,
                                    holder={"claimed_by": "poller-A"},
                                    run_dir_str=str(rd))
        self.assertTrue(doc_a, "A claims first")

        # Poller B = a real second process running cmd_ingest for the same
        # session with ITS OWN claim identity.
        child_code = "\n".join([
            "import sys",
            f"sys.path.insert(0, {str(HERE)!r})",
            f"sys.path.insert(0, {str(HERE.parent / 'bridge')!r})",
            "import intake_bridge as ib",
            "ib._load_presentation_job = lambda: None",
            "ib._fetch_intake = lambda a: {'intake': "
            "{'intake_session_id': a.session_id}}",
            "import contextlib, io, types",
            "err = io.StringIO()",
            "with contextlib.redirect_stderr(err):",
            "    rc = ib.cmd_ingest(types.SimpleNamespace("
            "worker_url='http://w',",
            f"        session_id='sess-dual', run_dir={str(root)!r},"
            " verbose=False,",
            "        per_session_dirs=True, no_per_session_dirs=False,",
            "        func=ib.cmd_ingest))",
            "print('RC', rc)",
            "import sys as s; s.stderr.write(err.getvalue())",
        ])
        child = subprocess.Popen(
            [sys.executable, "-c", child_code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = child.communicate(timeout=120)
        self.assertIn("RC", out, f"child poller crashed: {err[:400]}")
        rc_b = int(out.strip().splitlines()[0].split()[1])
        self.assertEqual(rc_b, 7, "B sees a live foreign claim: deferred, never a "
                                  "second execution")
        self.assertIn("claim_held_elsewhere", err)
        self.assertEqual(len(w.dispatch_calls), 0)

        # A crashes (simulated: its claim goes stale beyond the TTL), and a
        # third driver takes over after the TTL — ownership is RECOVERABLE.
        # (The child poller B released its skip-tick claim per the release
        # contract; A's stale claim is what the takeover must find.)
        stale = _ll.load(rd, "sess-dual")
        stale["claim"] = {
            "claimed_by": "poller-A",
            "claimed_at": "2000-01-01T00:00:00+00:00",
        }
        _ll.save(rd, "sess-dual", stale)
        w.next_dispatch_rc = -7   # still refusing; the takeover must not spawn
        with contextlib.redirect_stderr(io.StringIO()):
            rc3 = ib.cmd_ingest(_ingest_ns("http://w", "sess-dual", root))
        self.assertEqual(rc3, 7)
        doc3 = _ll.load(rd, "sess-dual")
        self.assertTrue(doc3.get("claim", {}).get("took_over")
                        or doc3.get("retry_attempt") == 1,
                        "the expired claim was taken over, not lost forever — "
                        "the third driver DROVE the submission (attempt 1)")
        self.assertFalse(_ll.is_complete(doc3))
        self.assertEqual(len(w.dispatch_calls), 1,
                         "exactly one dispatch attempt across three drivers")

    # ------------------------------------------------------------------
    # PRES-008 implementation-step proof (beyond the five scenarios):
    # completion REQUIRES a persisted current execution id + worker ack.
    # ------------------------------------------------------------------
    def test_06_completion_requires_execution_id_fail_closed(self):
        rd = self.world.runs / "sess-strict"
        doc = ib._submission_hold(rd, "sess-strict", FAST_POLICY,
                                  holder={"claimed_by": "t"},
                                  run_dir_str=str(rd))
        with self.assertRaises(ValueError):
            _ll.mark_worker_acknowledged(rd, "sess-strict", doc, execution_id="")
        after = _ll.load(rd, "sess-strict")
        self.assertFalse(_ll.is_complete(after),
                         "a bare rc must NEVER complete a submission")

    def test_07_completion_is_final_idempotent_reak(self):
        rd = self.world.runs / "sess-final"
        doc = ib._submission_hold(rd, "sess-final", FAST_POLICY,
                                  holder={"claimed_by": "t"},
                                  run_dir_str=str(rd))
        _ll.mark_worker_acknowledged(rd, "sess-final", doc,
                                     execution_id="pj_x",
                                     note="first ack")
        again = _ll.mark_worker_acknowledged(rd, "sess-final",
                                             _ll.load(rd, "sess-final"),
                                             execution_id="pj_y",
                                             note="re-ack by resume")
        self.assertTrue(_ll.is_complete(again))
        self.assertEqual(again["worker_ack"]["execution_id"], "pj_x",
                         "idempotent: the FIRST ack's execution id stands")
        with self.assertRaises(RuntimeError):
            _ll.transition(rd, "sess-final", _ll.load(rd, "sess-final"),
                           _ll.FAILED_RETRYABLE, why="must be refused")
        final = _ll.load(rd, "sess-final")
        self.assertTrue(_ll.is_complete(final), "completion is FINAL")

    def test_08_backoff_not_due_and_budget_exhaustion_blocks(self):
        rd = self.world.runs / "sess-backoff"
        doc = ib._submission_hold(rd, "sess-backoff", FAST_POLICY,
                                  holder={"claimed_by": "t"},
                                  run_dir_str=str(rd))
        notified = []
        doc = _ll.mark_retry_pending(
            rd, "sess-backoff", doc, "capacity unmeasured",
            failure_class="dispatch_refused",
            backoff_base_s=60.0, backoff_cap_s=1800.0, max_attempts=3,
            notify_thresholds=(2,), notifier=lambda k, s, m: notified.append(m))
        self.assertEqual(doc["state"], _ll.LAUNCH_PENDING)
        self.assertFalse(_ll.due_for_retry(doc),
                         "bounded backoff: not due until next_retry_at")
        from datetime import datetime as _dt
        scheduled = _dt.fromisoformat(doc["next_retry_at"])
        self.assertAlmostEqual(
            (scheduled - _dt.now(scheduled.tzinfo)).total_seconds(), 60.0,
            delta=5.0, msg="the base backoff (60s) is the scheduled delay")
        # drive past the budget -> blocked_actionable with remediation
        doc = _ll.load(rd, "sess-backoff")
        doc = _ll.mark_retry_pending(rd, "sess-backoff", doc, "again",
                                     failure_class="dispatch_refused",
                                     max_attempts=3)
        doc = _ll.mark_retry_pending(rd, "sess-backoff", doc, "again",
                                     failure_class="dispatch_refused",
                                     max_attempts=3)
        doc = _ll.mark_retry_pending(rd, "sess-backoff", doc, "final straw",
                                     failure_class="dispatch_refused",
                                     max_attempts=3, notifier=lambda k, s, m: None)
        self.assertEqual(doc["state"], _ll.BLOCKED_ACTIONABLE)
        self.assertTrue(doc["blocked"]["remediation"])
        self.assertFalse(_ll.due_for_retry(doc),
                         "blocked consumes no further retries")

    def test_09_never_overwrite_completed_intake_on_retry(self):
        w = self.world
        root = w.runs
        rd = root / "sess-keep"
        seeded = {"intake_session_id": "sess-keep", "answers": {"x": "FIRST"}}
        rd_mkdir = rd / "working" / "copy"
        rd_mkdir.mkdir(parents=True, exist_ok=True)
        (rd / "working" / "copy" / "intake.json").write_text(
            json.dumps(seeded), encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            ib.cmd_ingest(_ingest_ns("http://w", "sess-keep", root))
        on_disk = json.loads(
            (rd / "working" / "copy" / "intake.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["answers"], {"x": "FIRST"},
                         "the retry re-reads the FIRST record — never overwrites")

    def test_10_per_session_dirs_default_on_and_shared_refused(self):
        w = self.world
        root = w.runs
        listed = [{"session_id": "sess-a"}, {"session_id": "sess-b"}]

        real_fetch = ib._fetch_intake
        ib._fetch_intake = _fetch_ok
        try:
            buf = io.StringIO()
            with mock.patch.object(ib, "_list_intakes", lambda a: listed), \
                    contextlib.redirect_stdout(buf), \
                    contextlib.redirect_stderr(io.StringIO()):
                ib.cmd_poll(types.SimpleNamespace(
                    worker_url="http://w", run_dir=str(root), verbose=False,
                    per_session_dirs=False,          # legacy opt-out attempted
                    no_per_session_dirs=True, func=ib.cmd_poll))
        finally:
            ib._fetch_intake = real_fetch
        self.assertTrue((root / "sess-a" / "working").is_dir(),
                        "per-session dirs ON by default")
        self.assertTrue((root / "sess-b" / "working").is_dir(),
                        "two submissions never share one run dir even with "
                        "the legacy opt-out")


if __name__ == "__main__":
    unittest.main(verbosity=2)
