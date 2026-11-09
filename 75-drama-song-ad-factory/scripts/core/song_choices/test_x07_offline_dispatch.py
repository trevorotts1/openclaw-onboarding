#!/usr/bin/env python3
"""X07 offline regression: settlement, ledger write, and the second-resume guard.

WHAT THIS PROVES (all through the REAL product call path):

  cmd_generate -> real _real_generate -> real kie_dispatch.dispatch
      -> real spend_ledger plan/reserve/mark_submitted/mark_terminal/reconcile

against a real temporary SQLite ledger. The ONLY fake is the provider
transport: an injected ``runner`` callable (``kie_dispatch.dispatch(runner=...)``
offline seam). It writes no product file and makes no network call, no
subprocess, and no paid provider call.

  1. SETTLEMENT IS RECORDED. The dispatch envelope carries an ``ok`` outcome,
     the provider task id, the provider-reported credit charge, the accepted
     and terminal stamps, and the seven-count lifecycle.
  2. THE LEDGER IS WRITTEN. ``spend_ledger.summary`` reports the actual cost,
     one generation call and zero reserved/unknown cost; the ``jobs`` row is
     ``reconciled/succeeded`` with the remote task id, and a receipt row holds
     the settled amount.
  3. A SECOND RESUME REFUSES WITHOUT A NEW SUBMIT. Re-running the same logical
     song job after it settled is refused by the spend ledger BEFORE reserve,
     before any adapter call; the provider submit count stays at 1 and the
     ledger cost is unchanged.

GUARD-REMOVAL CONTROL (test_control_guard_removal_replays_the_second_submit):
the second-resume refusal is produced by ``spend_ledger._derive_category``
reading persisted prior state and classifying a settled job as
``creative_retake``, which ``_allocate`` then refuses with ``MISSING_AUTH_REF``
(no authorization reference = no new paid round). That control neutralizes
exactly that classification and asserts the refusal DISAPPEARS and a second
provider submit IS issued. So the zero-submit assertion in test 3 is sensitive
to the guard: remove the guard and test 3 fails.

Run directly (``python3 test_x07_offline_dispatch.py``) or under pytest.
Set ``S75_SONG_FACTORY_ROOT`` to point at the skill root when the test is run
from outside the repo; otherwise it is found by walking up from this file.
"""
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_skill_root():
    """Repo root (the folder holding scripts/core/kie_dispatch). No guesses."""
    env = os.environ.get("S75_SONG_FACTORY_ROOT") or os.environ.get("S75_ROOT")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    probe = HERE
    while True:
        if os.path.isfile(os.path.join(probe, "scripts", "core",
                                       "kie_dispatch", "kie_dispatch.py")):
            return probe
        if os.path.isfile(os.path.join(probe, "kie_dispatch",
                                       "kie_dispatch.py")) and \
                os.path.basename(probe) == "core":
            return os.path.dirname(os.path.dirname(probe))
        parent = os.path.dirname(probe)
        if parent == probe:
            raise RuntimeError(
                "cannot locate the song factory: set S75_SONG_FACTORY_ROOT")
        probe = parent


SKILL = _find_skill_root()
CORE = os.path.join(SKILL, "scripts", "core")
for _sub in ("", "song_choices", "song_dispatch", "suno_recipe"):
    _p = os.path.join(CORE, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kie_dispatch.kie_dispatch as KD       # noqa: E402
import spend_ledger as L                    # noqa: E402
import suno_recipe as R                     # noqa: E402
from song_choices import song_choices as SC  # noqa: E402

CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK_LINES = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}
PACE_ORDER = {"drop": "half-time drop, thin drums",
              "return": "turn and rise back to the groove",
              "boundary_s": 14.0, "return_boundary_s": 38.0}
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung",
          "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK_LINES},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK_LINES},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK_LINES},
         {"tag": "Outro", "delivery": "spoken",
          "lines": ["She Found Power in the Climb. Get the book. Link below."]}]

VARIANT_ID = SC.variants_for("soul-ballad")[0]["id"]
RUN_ID = "run-x07-offline"
TASK_ID = "task-x07-offline-1"
CREDITS = 12                      # provider-reported credits (catalog ~$0.06)
CEILING_CENTS = 10000
CARD = {"answers": {"video_style": "cinematic", "audio_style": "soul-ballad",
                    "length": 60, "video_model": "MiniMax H3 768P"},
        "who": "offline-regression", "at": "2026-11-01T00:00:00Z"}
#: Reasons the ledger/guards may use to refuse a second paid round.
SECOND_RESUME_REFUSALS = ("MISSING_AUTH_REF", "DUPLICATE_LOGICAL_JOB",
                          "DUPLICATE_ATTEMPT", "RECONCILE_FIRST",
                          "PROVIDER_LOOKUP_REQUIRED")


def _suno_words(lyrics):
    out = []
    for block in lyrics.split("\n\n"):
        head, *lines = block.split("\n")
        tokens = " ".join(lines).split() or [""]
        out += [{"word": (head + "\n" + t + " ") if i == 0 else t + " "}
                for i, t in enumerate(tokens)]
    return out


def _request_doc():
    """A real recipe-generated request file (same shape cmd_generate loads)."""
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58,
                          hook_plan=HOOK_PLAN, pace_plan=PACE_ORDER)
    return {"style_id": "soul-ballad", "sheet_text": req["input"]["lyrics"],
            "client_text": CLIENT, "title": "T", "length_s": 58,
            "vocal_gender": "f", "hook_plan": HOOK_PLAN,
            "pace_plan": PACE_ORDER}


def _measured():
    """Measured fields a real measure transport returns for one take."""
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58,
                          hook_plan=HOOK_PLAN, pace_plan=PACE_ORDER)
    words = [dict(w, startS=i, endS=i + 0.5)
             for i, w in enumerate(_suno_words(req["input"]["lyrics"]))]
    return {
        "segments": [{"delivery": "spoken", "start": 0, "end": 2,
                      "source": "measured"},
                     {"delivery": "sung", "start": 2.5, "end": 45,
                      "source": "measured"},
                     {"delivery": "spoken", "start": 45, "end": 54,
                      "source": "measured"}],
        "aligned_words": [dict(w, startS=3 + i * 1.0, endS=3.5 + i * 1.0)
                          for i, w in enumerate(words)],
        "detector": "singing_detector 2.0.0", "duration_s": 57.5,
        "music_under_speech_ratio": 0.6, "tail_rms_dbfs": -30.0,
        "first_sung_s": 2.5,
        "pace_before": {"onset_rate_per_s": 3.0, "rms_dbfs": -14.0},
        "pace_problem": {"onset_rate_per_s": 1.4, "rms_dbfs": -18.5},
        "pace_after": {"onset_rate_per_s": 3.0, "rms_dbfs": -14.0},
    }


class FakeTransport(object):
    """In-process stand-in for the Skill 74 adapter subprocess.

    Speaks only the adapter protocol the dispatcher calls. Records every
    command so the test can prove how many ``submit`` calls reached the
    "provider". No network, no subprocess, no spend.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        cmd = argv[1] if len(argv) > 1 else ""
        self.calls.append(cmd)
        if cmd == "health":
            return 0, json.dumps({"state": "ok", "adapter_mode": "active"})
        if cmd == "preflight":
            return 0, json.dumps({"state": "ok", "data": {"ok": True}})
        if cmd == "prompt-budget":
            return 0, json.dumps({"state": "ok", "data": {"status": "OK"}})
        if cmd == "submit":
            return 0, json.dumps({"state": "success", "task_id": TASK_ID,
                                  "credits_consumed": CREDITS})
        if cmd == "save":
            save_dir = argv[argv.index("--save-dir") + 1]
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, "take-1.mp3")
            with open(path, "wb") as f:
                f.write(b"offline-audio-1")
            return 0, json.dumps({"state": "ok", "saved_paths": [path]})
        return 2, json.dumps({"state": "fail",
                              "error": {"code": "unknown-command",
                                        "message": cmd}})

    def submits(self):
        return self.calls.count("submit")


class X07OfflineDispatch(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="x07-offline-")
        self.addCleanup(_rmtree, self.root)
        self.run_dir = os.path.join(self.root, "run")
        os.makedirs(os.path.join(self.run_dir, "control"))
        with open(os.path.join(self.run_dir, "control",
                               "card-receipt-block.json"), "w",
                  encoding="utf-8") as f:
            json.dump(CARD, f)
        self.req_path = os.path.join(self.root, "request.json")
        with open(self.req_path, "w", encoding="utf-8") as f:
            json.dump(_request_doc(), f)
        self.db = os.path.join(self.root, "spend.sqlite3")
        self.assertEqual(L.init_run(self.db, RUN_ID, CEILING_CENTS)["outcome"],
                         "ok")
        # resolve_adapter() only needs a real file path; the injected runner
        # never executes it.
        self.adapter = os.path.join(self.root, "fake_adapter.py")
        with open(self.adapter, "w", encoding="utf-8") as f:
            f.write("# never executed: the transport is injected\n")
        self._old_adapter = os.environ.get("KIE_LIVE_ADAPTER_PATH")
        os.environ["KIE_LIVE_ADAPTER_PATH"] = self.adapter
        self._real_dispatch = KD.dispatch
        self._install_transport()

    def tearDown(self):
        KD.dispatch = self._real_dispatch
        if self._old_adapter is None:
            os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
        else:
            os.environ["KIE_LIVE_ADAPTER_PATH"] = self._old_adapter

    def _install_transport(self):
        """Fake the EXTERNAL provider only: the real dispatcher runs unchanged."""
        self.transport = FakeTransport()
        real = self._real_dispatch

        def dispatch_with_injected_transport(**kw):
            kw["runner"] = self.transport
            return real(**kw)

        KD.dispatch = dispatch_with_injected_transport

    def _args(self):
        return types.SimpleNamespace(run_dir=self.run_dir,
                                     request=self.req_path, ledger=self.db,
                                     run_id=RUN_ID, variant=VARIANT_ID,
                                     unit_id="")

    def _generate(self):
        return SC.cmd_generate(
            self._args(), measure=lambda take: _measured(),
            save=lambda variant, take=None, rcpt=None:
            os.path.join(self.run_dir, "music", "takes", variant["id"]))

    def _summary(self):
        out = L.summary(self.db, RUN_ID)
        self.assertEqual(out["outcome"], "ok", out)
        return out["evidence"]

    def _job_rows(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT attempt_id,state,final_outcome,remote_task_id,"
                "actual_cost,estimated_cost FROM jobs")]
        finally:
            conn.close()

    def _receipts(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT amount,currency,provider_ref FROM receipts")]
        finally:
            conn.close()

    # ---- 1. settlement is recorded ------------------------------------
    def test_settlement_recorded_on_the_dispatch_envelope(self):
        out = self._generate()
        result = out["results"][0]
        env = result["envelope"]
        self.assertEqual(env["outcome"], "ok", env)
        self.assertEqual(env["reason_code"], "KIE_DISPATCH_OK", env)
        ev = env["evidence"]
        # Offline seam, never a production claim.
        self.assertEqual(ev["execution_mode"], "offline", ev)
        self.assertFalse(ev["production_admitted"], ev)
        self.assertEqual(ev["task_id"], TASK_ID, ev)
        self.assertEqual(ev["credits_consumed"], CREDITS, ev)
        self.assertEqual(ev["actual_cost"], CREDITS, ev)
        self.assertTrue(ev["accepted_submit_at"], ev)
        self.assertTrue(ev["terminal_at"], ev)
        self.assertEqual(len(ev["saved_paths"]), 1, ev)
        self.assertEqual(env["counts"]["submitted"], 1, env["counts"])
        self.assertEqual(env["counts"]["acknowledged"], 1, env["counts"])
        self.assertEqual(env["counts"]["billed"], 1, env["counts"])
        self.assertEqual(env["counts"]["materialized"], 1, env["counts"])
        # Exactly one provider submit was issued.
        self.assertEqual(self.transport.submits(), 1, self.transport.calls)

    # ---- 2. the ledger is written -------------------------------------
    def test_ledger_written_with_the_settled_charge(self):
        self._generate()
        ev = self._summary()
        self.assertEqual(ev["actual_cost"], CREDITS, ev)
        self.assertEqual(ev["number_of_generation_calls"], 1, ev)
        self.assertEqual(ev["unknown_or_reserved_cost"], 0, ev)
        self.assertEqual(ev["committed_cost"], 0, ev)
        self.assertEqual(ev["run_status"], "active", ev)
        rows = self._job_rows()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual(row["state"], "reconciled", row)
        self.assertEqual(row["final_outcome"], "succeeded", row)
        self.assertEqual(row["remote_task_id"], TASK_ID, row)
        self.assertEqual(row["actual_cost"], CREDITS, row)
        receipts = self._receipts()
        self.assertEqual(len(receipts), 1, receipts)
        self.assertEqual(receipts[0]["amount"], CREDITS, receipts)
        self.assertEqual(receipts[0]["provider_ref"], "kie", receipts)

    # ---- 3. a second resume refuses without a new submit --------------
    def test_second_resume_refuses_without_a_new_submit(self):
        first = self._generate()
        self.assertEqual(first["results"][0]["envelope"]["outcome"], "ok")
        self.assertEqual(self.transport.submits(), 1, self.transport.calls)
        before = self._summary()

        second = self._generate()
        env2 = second["results"][0]["envelope"]
        self.assertNotEqual(env2["outcome"], "ok", env2)
        self.assertIn(env2["reason_code"], SECOND_RESUME_REFUSALS, env2)
        # The refusal happened BEFORE the adapter: no health, no submit.
        self.assertEqual(self.transport.submits(), 1, self.transport.calls)
        self.assertEqual(second["dispatched"], 0, second)

        after = self._summary()
        self.assertEqual(after["actual_cost"], before["actual_cost"], after)
        self.assertEqual(after["actual_cost"], CREDITS, after)
        self.assertEqual(after["number_of_generation_calls"], 1, after)
        self.assertEqual(after["unknown_or_reserved_cost"], 0, after)
        self.assertEqual(len(self._receipts()), 1, self._receipts())
        self.assertEqual(len(self._job_rows()), 1, self._job_rows())

    # ---- guard-removal control ----------------------------------------
    def test_control_guard_removal_replays_the_second_submit(self):
        """CONTROL: neutralize the ledger's prior-state classification.

        ``_derive_category`` is what turns a settled prior job into a
        ``creative_retake`` that ``_allocate`` refuses without an
        authorization reference. With it neutralized the second resume
        reaches the provider again. This control passing is what makes the
        zero-submit assertion in test 3 meaningful: remove that guard and
        test 3 fails.
        """
        real_category = L._derive_category

        def no_prior_state(prior, request_digest):
            return "initial", None

        L._derive_category = no_prior_state
        self.addCleanup(setattr, L, "_derive_category", real_category)

        first = self._generate()
        self.assertEqual(first["results"][0]["envelope"]["outcome"], "ok")
        self.assertEqual(self.transport.submits(), 1, self.transport.calls)

        second = self._generate()
        env2 = second["results"][0]["envelope"]
        # Guard removed: the second round is issued, not refused.
        self.assertEqual(env2["outcome"], "ok", env2)
        self.assertEqual(self.transport.submits(), 2, self.transport.calls)
        rows = self._job_rows()
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual(len([r for r in rows if r["remote_task_id"]]), 2, rows)
        self.assertEqual(self._summary()["actual_cost"], CREDITS * 2)


def _rmtree(path):
    import shutil
    shutil.rmtree(path, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
