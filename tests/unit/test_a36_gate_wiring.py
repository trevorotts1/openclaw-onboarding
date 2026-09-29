#!/usr/bin/env python3
"""JEV A36 (ONB-212): production call-site wiring + real-DB single-writer CAS.

GAP 1 — the four late gates (late selector / backfill / producer report /
audience rescore) must be INVOKED by their own file's command flow, and the
gate's False return must change control flow (refuse / skip), never be
discarded. Each test below drives the REAL entry point of the file named in
the acceptance row and asserts the refusal path, with the head moved by a
side effect injected at a real interleaving point inside that same flow.

GAP 3 — the spec's transaction rule (1.1 spec 10.3, line 963):

    "A late selector, backfill, producer report, or audience rescore must fail
     cleanly against an obsolete input/decision revision. Do not hold a SQLite
     transaction open during a network call."

  So the CAS tests here run through a REAL file-backed SQLite handle in WAL
  mode across two real connections — never a dict + RLock. That harness found
  a genuine defect the in-memory test could not reach: a losing racer hit a
  raw sqlite3.IntegrityError (UNIQUE constraint on decision_revisions
  .decision_id) instead of the typed ObsoleteRevisionError the module's own
  contract documents. Fixed at the persistence seam in
  shared-utils/decision_engine/commit/dispatch.py::append_revision.

GAP 2 — detect_audience_update -> re-dispatch is chained on a production
call path (comms_audience_trigger.build_comms_trigger), not caller-supplied.

Run: python3 -m pytest tests/unit/test_a36_gate_wiring.py -q
"""
import atexit
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

# Every temp file/dir this test makes lands in one sandbox, removed at exit (pass or fail).
tempfile.tempdir = tempfile.mkdtemp(prefix="onb-test-")
atexit.register(shutil.rmtree, tempfile.tempdir, True)

_REPO = Path(__file__).resolve().parent.parent.parent
_COMMIT = _REPO / "shared-utils" / "decision_engine" / "commit"
sys.path.insert(0, str(_COMMIT))

import dispatch  # noqa: E402


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wal_conn(db):
    """A REAL WAL connection: the file-backed handle production uses."""
    con = sqlite3.connect(str(db), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    return con


def _scope(**over):
    s = {k: "d0" for k in dispatch.SCOPE_FIELDS}
    s.update(over)
    return s


def _compute(base, scope):
    return ({"decisionId": "sel", "action": "select", "scope": dict(scope)},
            {"board": "sel"})


def _bump_head(db, task_key, reason):
    """Simulate a concurrent writer committing while a call flow is in flight."""
    con = _wal_conn(db)
    try:
        dispatch.redispatch(con, task_key, _scope(title=reason), _compute,
                            reason, {"by": "concurrent"})
    finally:
        con.close()


class RealDbSingleWriterCasTests(unittest.TestCase):
    """GAP 3: CAS through a real file-backed WAL handle, two real connections."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-cas-"))
        self.db = self.tmp / "decision_revisions.db"
        self.con = _wal_conn(self.db)

    def tearDown(self):
        self.con.close()

    def test_wal_mode_is_really_on_for_the_file_handle(self):
        row = self.con.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(str(row[0]).lower(), "wal")

    def test_head_revision_reads_the_real_chain(self):
        self.assertEqual(dispatch.head_revision(self.tmp, "t-head"), 0)
        dispatch.redispatch(self.con, "t-head", _scope(), _compute, "one", {})
        self.con.commit()
        self.assertEqual(dispatch.head_revision(self.tmp, "t-head"), 1)

    def test_no_transaction_is_open_during_the_compute_call(self):
        """Spec line 963: no SQLite transaction may span a network call.

        recompute_fn stands in for the network call: at that moment the
        connection must hold no open transaction, and the same must be true
        after redispatch returns.
        """
        seen = {}

        def compute(base, scope):
            seen["in_transaction_during"] = self.con.in_transaction
            seen["appears_in_file"] = self.db.exists()
            return _compute(base, scope)

        dispatch.redispatch(self.con, "t-net", _scope(), compute, "r", {})
        self.assertFalse(seen["in_transaction_during"],
                         "a SQLite transaction was open across the compute call")
        self.assertFalse(self.con.in_transaction,
                         "redispatch returned with a transaction still open")

    def test_two_real_connections_race_and_the_loser_loses_typed(self):
        """The defect the dict+RLock test could not reach (GAP 3).

        Pre-fix, the losing racer surfaced a raw
        ``sqlite3.IntegrityError: UNIQUE constraint failed:
        decision_revisions.decision_id``. Post-fix it is the typed
        ObsoleteRevisionError the module contract documents, and the loser
        writes NOTHING (no torn chain, no clobbered head).

        The rendezvous sits INSIDE the compute call (after redispatch has read
        head=1, before either INSERT), so both racers always CAS from the same
        basis. A start-line barrier is not enough: under load one thread could
        finish its whole redispatch before the other read the head, and that
        second caller then (correctly) recommitted rev 3 from rev 2 -- a
        sequential write, not a race, and a spurious "2 winners" failure.
        """
        dispatch.redispatch(self.con, "t-race", _scope(), _compute, "seed", {})
        self.con.commit()

        out = {}
        barrier = threading.Barrier(2)

        def overlapped_compute(base, scope):
            barrier.wait(timeout=15)  # both have read head=1; neither wrote
            return _compute(base, scope)

        def race(key, tag):
            con = _wal_conn(self.db)
            try:
                out[key] = dispatch.redispatch(
                    con, "t-race", _scope(title=tag), overlapped_compute,
                    tag, {})
                con.commit()
            except Exception as exc:  # noqa: BLE001 -- asserted below
                out[key] = exc
            finally:
                con.close()

        threads = [threading.Thread(target=race, args=("a", "B")),
                   threading.Thread(target=race, args=("b", "C"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        winners = [k for k in out if isinstance(out[k], tuple)]
        losers = [k for k in out if isinstance(out[k], Exception)]
        self.assertEqual(len(winners), 1, "exactly one CAS winner expected")
        self.assertEqual(len(losers), 1, "exactly one CAS loser expected")

        loser = out[losers[0]]
        self.assertIsInstance(loser, _commit_error("ObsoleteRevisionError"))
        self.assertNotIsInstance(loser, sqlite3.IntegrityError)

        hist = dispatch.revision_history(self.con, "t-race")
        self.assertEqual([r["revision"] for r in hist], [1, 2],
                         "the loser must leave the chain untouched")
        winner_tag = {"a": "B", "b": "C"}[winners[0]]
        self.assertEqual(hist[1]["reason"], winner_tag,
                         "rev 2 must be the winner's write, not the loser's")

    def test_all_four_kinds_gate_against_the_file_backed_chain(self):
        dispatch.redispatch(self.con, "t-kinds", _scope(), _compute, "one", {})
        dispatch.redispatch(self.con, "t-kinds", _scope(voice="v2"), _compute,
                            "two", {})
        self.con.commit()
        _commit, store = dispatch.load_cas_store(self.con, "t-kinds")
        for kind in ("selector", "backfill", "producer_report",
                     "audience_rescore"):
            self.assertTrue(dispatch.guard_late_result(store, kind, 2), kind)
            with self.assertRaises(_commit_error("LateResultError"), msg=kind):
                dispatch.guard_late_result(store, kind, 1)


def _commit_error(name):
    return getattr(dispatch._load_commit(), name)


class BackfillGateWiringTests(unittest.TestCase):
    """GAP 1 call site 1: 23-ai-workforce-blueprint/scripts/backfill-build-state.py

    Before: gate_backfill_result appeared only at its own def (line 46);
    main() wrote state at line 293 with no gate anywhere in the flow.
    After: main() reads the basis before the detection scan and refuses the
    write (exit 2) when the head moved.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-backfill-"))
        self.home = self.tmp / "home"
        (self.home / ".openclaw" / "workspace").mkdir(parents=True)
        self.state_path = self.home / ".openclaw" / "workspace" / ".workforce-build-state.json"
        self.mod = _load(_REPO / "23-ai-workforce-blueprint" / "scripts"
                         / "backfill-build-state.py", "a36_backfill")
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        os.environ.pop("COMPANY_SLUG", None)

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home

    def _seed_head(self, revision_note):
        con = _wal_conn(self.state_path.parent / "decision_revisions.db")
        try:
            dispatch.redispatch(con, "backfill-build-state", _scope(),
                                _compute, revision_note, {})
        finally:
            con.close()

    def _run_main(self):
        argv = sys.argv
        sys.argv = ["backfill-build-state.py"]
        try:
            return self.mod.main()
        finally:
            sys.argv = argv

    def test_head_moved_mid_run_refuses_the_write(self):
        self._seed_head("r1")
        real = self.mod.detect_sop_library_status
        calls = []

        def detect_then_head_moves(departments_dir):
            out = real(departments_dir)
            if not calls:
                calls.append(1)
                _bump_head(self.state_path.parent / "decision_revisions.db",
                           "backfill-build-state", "r2-concurrent")
            return out

        self.mod.detect_sop_library_status = detect_then_head_moves
        try:
            rc = self._run_main()
        finally:
            self.mod.detect_sop_library_status = real

        self.assertEqual(rc, 2, "stale backfill must refuse with a non-zero exit")
        self.assertFalse(self.state_path.exists(),
                         "the stale backfill clobbered the newer decision state")

    def test_head_still_matches_proceeds(self):
        self._seed_head("r1")
        rc = self._run_main()
        self.assertEqual(rc, 0)
        self.assertTrue(self.state_path.exists())
        written = json.loads(self.state_path.read_text())
        self.assertIn("sopLibraryStatus", written)


class IntakeRouterGateWiringTests(unittest.TestCase):
    """GAP 1 call site 2: 59-anthology-engine/scripts/intake_router.py

    Before: gate_late_result appeared only at its own def (line 121); route()
    reached the upsert + spawn with no gate.
    After: route() reads the basis before the tenant read and refuses a
    delivery whose basis went obsolete, releasing the dedup claim so a
    re-delivery re-routes on the new basis.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-intake-"))
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True)
        self.mod = _load(_REPO / "59-anthology-engine" / "scripts"
                         / "intake_router.py", "a36_intake_router")
        rc, _, err = self.mod._run_writer(
            ["upsert-anthology", "--anthology-id", "ANTH1",
             "--caf-location-binding", "LOC-AAA", "--name", "T"], self.state)
        if rc != 0:
            self.skipTest("sole writer unavailable: rc=%s %s" % (rc, err))
        self.cfg = self.mod.load_config()
        self.cfg["secret_mode"] = "verify_if_present"
        self.cfg["standing_check_mode"] = "off"

    def _call(self, payload, **over):
        class NS:
            pass
        a = NS()
        a.__dict__.update(secret_mode=None, trusted=False, no_spawn=True,
                          replay=False, payload=None, payload_json=None,
                          state_dir=str(self.state))
        for k, v in over.items():
            setattr(a, k, v)
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        return self.mod.route(raw, self.cfg, self.state, a)

    def _payload(self, contact="C9"):
        return {"contact_id": contact, "anthology_id": "ANTH1",
                "stage": "intake", "location_id": "LOC-AAA",
                "first_name": "Ada", "email": "ada@example.test"}

    def _seed_head(self, task_key):
        con = _wal_conn(self.state / "decision_revisions.db")
        try:
            dispatch.redispatch(con, task_key, _scope(), _compute, "r1", {})
        finally:
            con.close()

    def test_head_moved_mid_route_refuses_before_the_write(self):
        self._seed_head("C9::ANTH1")
        real = self.mod.classify_stage

        def classify_then_head_moves(stage_token, cfg, part):
            out = real(stage_token, cfg, part)
            _bump_head(self.state / "decision_revisions.db", "C9::ANTH1",
                       "r2-concurrent")
            return out

        self.mod.classify_stage = classify_then_head_moves
        try:
            code, body = self._call(self._payload())
        finally:
            self.mod.classify_stage = real

        self.assertEqual(code, self.mod.EX_LEDGER)
        self.assertEqual(body["action"], "stale_refused")
        con = self.mod._mirror_ro(self.state)
        try:
            row = self.mod._ro_query_one(
                con, "SELECT participant_key FROM participants"
                     " WHERE participant_key=?", ("C9::ANTH1",))
        finally:
            con.close()
        self.assertIsNone(row, "the stale delivery still wrote the participant")

    def test_current_basis_still_routes(self):
        code, body = self._call(self._payload())
        self.assertEqual(code, self.mod.EX_OK)
        self.assertEqual(body["action"], "routed")


class NudgeSendGateWiringTests(unittest.TestCase):
    """GAP 1 call site 3: 59-anthology-engine/scripts/nudge_send.py

    Before: gate_rescore_result appeared only at its own def (line 68);
    cmd_send delivered with no gate.
    After: cmd_send reads the basis before the ledger resolve and refuses
    with EX_REFUSE when the head moved before the send.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-nudge-"))
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True)
        self.mod = _load(_REPO / "59-anthology-engine" / "scripts"
                         / "nudge_send.py", "a36_nudge_send")

    def _args(self):
        class NS:
            pass
        a = NS()
        a.__dict__.update(template="gate-open", subject_key="C9::ANTH1",
                          gate="s1_producer", gate_link="https://x.test/g",
                          deliverable_label=None, deliverable_link=None,
                          config=None, state_dir=str(self.state), dry_run=False,
                          json=True)
        return a

    def _patch_ledger(self, mod, ctx):
        class _Con:
            def close(self):
                return None

        ctx = dict(ctx)
        ctx.setdefault("first_name", "Ada")
        ctx.setdefault("anthology_name", "ANTH1")
        ctx.setdefault("producer_display_name", "the producer")
        mod._mirror_ro = lambda state_dir: _Con()
        mod._resolve_context = lambda con, key, target: ctx
        mod._deliver = lambda cfg, to, subj, body: (True, "sent")

    def _seed_head(self):
        con = _wal_conn(self.state / "decision_revisions.db")
        try:
            dispatch.redispatch(con, "C9::ANTH1", _scope(), _compute, "r1", {})
        finally:
            con.close()

    def test_head_moved_before_send_refuses(self):
        self._seed_head()
        self._patch_ledger(self.mod, {"recipient": "a@b.test"})
        real = self.mod._target_and_label

        def target_then_head_moves(*a, **kw):
            out = real(*a, **kw)
            _bump_head(self.state / "decision_revisions.db", "C9::ANTH1",
                       "r2-concurrent")
            return out

        self.mod._target_and_label = target_then_head_moves
        try:
            _body, rc = self.mod.cmd_send(self._args())
        finally:
            self.mod._target_and_label = real
            self.mod._resolve_gate_link = getattr(self.mod, "_resolve_gate_link")
        self.assertEqual(rc, self.mod.EX_REFUSE)

    def test_current_basis_still_sends(self):
        self._patch_ledger(self.mod, {"recipient": "a@b.test"})
        self.mod._resolve_gate_link = lambda *a, **kw: "https://x.test/g"
        _body, rc = self.mod.cmd_send(self._args())
        self.assertEqual(rc, self.mod.EX_OK)


class NudgeSweepGateWiringTests(unittest.TestCase):
    """GAP 1 call site 3 (the automatic path): cmd_renudge_sweep.

    The sweep is the daily-tick send path. Its per-candidate gate must refuse
    a candidate whose rescore basis moved between eligibility and send.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-sweep-"))
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True)
        self.mod = _load(_REPO / "59-anthology-engine" / "scripts"
                         / "nudge_send.py", "a36_nudge_sweep")
        self.key = "C7::ANTH1"
        # A real ledger row parked at a gate cursor, entered long ago.
        con = sqlite3.connect(str(self.state / "anthology_state.db"))
        con.execute("CREATE TABLE participants (participant_key TEXT PRIMARY KEY,"
                    " stage_cursor TEXT, stage_timestamps TEXT, anthology_id TEXT)")
        con.execute("INSERT INTO participants VALUES(?,?,?,?)",
                    (self.key, "s1_gate",
                     json.dumps({"s1_gate": "2020-01-01T00:00:00+00:00"}),
                     "ANTH1"))
        con.commit()
        con.close()

    def _args(self):
        class NS:
            pass
        a = NS()
        a.__dict__.update(days=7, now=None, config=None,
                          state_dir=str(self.state), dry_run=False, json=True)
        return a

    def _seed_head(self):
        con = _wal_conn(self.state / "decision_revisions.db")
        try:
            dispatch.redispatch(con, self.key, _scope(), _compute, "r1", {})
        finally:
            con.close()

    def test_head_moves_during_sweep_refuses_candidate_without_sending(self):
        self._seed_head()
        sent = []
        self.mod._send_one = lambda *a, **kw: sent.append(a) or 0
        # Interleave at a REAL production step that sits between the basis read
        # (eligibility) and the per-candidate gate: the dedup claim.
        real_claim = self.mod.NudgeSentStore.claim
        calls = []

        def claim_then_head_moves(self_, *a, **kw):
            out = real_claim(self_, *a, **kw)
            if not calls:
                calls.append(1)
                _bump_head(self.state / "decision_revisions.db", self.key,
                           "r2-concurrent")
            return out

        self.mod.NudgeSentStore.claim = claim_then_head_moves
        try:
            body, rc = self.mod.cmd_renudge_sweep(self._args())
        finally:
            self.mod.NudgeSentStore.claim = real_claim
        self.assertEqual(rc, self.mod.EX_OK)
        self.assertEqual(body["sent"], 0)
        self.assertEqual(body["stale_refused"], 1)
        self.assertEqual(sent, [], "a stale candidate was still sent")

    def test_matching_basis_sends_the_candidate(self):
        self._seed_head()
        sent = []
        self.mod._send_one = lambda *a, **kw: sent.append(a) or 0
        body, rc = self.mod.cmd_renudge_sweep(self._args())
        self.assertEqual(rc, self.mod.EX_OK)
        self.assertEqual(body["sent"], 1)
        self.assertEqual(body["stale_refused"], 0)
        self.assertEqual(len(sent), 1)


class CommsAudienceGateWiringTests(unittest.TestCase):
    """GAP 1 call site 4 + GAP 2: shared-utils/comms_audience_trigger.py

    Before: gate_audience_rescore appeared only at its own def (line 104);
    build_comms_trigger handed the bundle back with no gate and no chain.
    After: it reads the basis before the compute, refuses a stale rescore,
    and chains detect_audience_update -> dispatch.redispatch on the SAME path.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-comms-"))
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True)
        self.mod = _load(_REPO / "shared-utils" / "comms_audience_trigger.py",
                         "a36_comms")
        self.mod._load_persona_blend = lambda: _FakePb()

    def _seed_head(self):
        con = _wal_conn(self.state / "decision_revisions.db")
        try:
            dispatch.redispatch(con, "comm-1", _scope(), _compute, "r1", {})
        finally:
            con.close()

    def _call(self):
        return self.mod.build_comms_trigger(
            "email", "write an email about Q3 budgeting wins", "marketing",
            use_llm=False, record=False, cas_task_key="comm-1",
            cas_state_dir=self.state)

    def test_head_moved_mid_compute_refuses(self):
        self._seed_head()
        real = self.mod._derive_topic

        def topic_then_head_moves(*a, **kw):
            out = real(*a, **kw)
            _bump_head(self.state / "decision_revisions.db", "comm-1",
                       "r2-concurrent")
            return out

        self.mod._derive_topic = topic_then_head_moves
        try:
            out = self._call()
        finally:
            self.mod._derive_topic = real
        self.assertTrue(out["refused"])
        self.assertEqual(out["refusal_reason"], "stale_rescore_refused")
        self.assertIsNone(out["bundle"])

    def test_current_basis_proceeds_and_chains_the_detector(self):
        self._seed_head()
        out = self._call()
        self.assertFalse(out["refused"], out)
        cas = out["bundle"]["cas"]
        self.assertEqual(cas["cas_action"], "recommitted")
        self.assertEqual(cas["cas_revision"], 2)
        self.assertIn("voice", cas["changed_fields"])
        con = _wal_conn(self.state / "decision_revisions.db")
        try:
            hist = dispatch.revision_history(con, "comm-1")
        finally:
            con.close()
        self.assertEqual([r["revision"] for r in hist], [1, 2])

    def test_unchanged_audience_reuses_no_new_revision(self):
        self._seed_head()
        self._call()
        out = self._call()
        self.assertFalse(out["refused"])
        self.assertEqual(out["bundle"]["cas"]["cas_action"], "reuse")


class _FakePb:
    """Hermetic persona_blend stand-in (the u116 fixture pattern)."""

    def _tokens(self, text):
        return set(str(text).lower().split())

    def _selector(self):
        class Sel:
            @staticmethod
            def get_openclaw_paths():
                return {}

            @staticmethod
            def load_company_config(paths):
                return {}
        return Sel()

    def load_catalog(self, paths):
        return {}

    def resolve_audience(self, catalog, company_cfg, soul_text="",
                         audience_override=""):
        return {"label": "founders", "source": "resolved",
                "confirm_required": False, "candidates": []}

    def build_bundle(self, task, dept, **kw):
        return {"persona_id": "voice-a", "topic": "budgeting, wins",
                "task_category": "content", "content_task": True,
                "voice": {"style": "warm"}, "resolved_audience": {},
                "blend_directive": {}, "confirm_required": False}


if __name__ == "__main__":
    unittest.main()
