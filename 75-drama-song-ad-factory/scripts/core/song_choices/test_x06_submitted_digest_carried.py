#!/usr/bin/env python3
"""S75-018 (X06): the admitted-snapshot digest must survive the worker boundary.

``run_takes`` computes ``submitted_digest`` over the exact outbound snapshot it
re-admits inside the governor callback on every retry. ``one_variant`` is the
ONE worker path every caller uses (the umbrella three-up run and the per-unit
``--variant``/``--unit-id`` run), so a digest dropped there is dropped for
every caller. Before this fix it survived only into song_dispatch's own
assertion, and nothing downstream could prove that the snapshot that was
admitted is the snapshot that was submitted.

Offline: the provider transport is a stub returning a known digest.
Run: python3 test_x06_submitted_digest_carried.py
"""
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, os.path.join(CORE, "intake_preflight")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from song_choices import song_choices as SC          # noqa: E402

#: 64 hex characters -- the real shape of ``_take_request_digest``'s answer.
DIGEST = "4f" * 32
VARIANT = {"id": "polished-modern", "label": "Polished Modern"}


def _stub_run_takes(digest):
    """The transport's contract minus the provider: one PASS take, one digest."""
    def run_takes(request, plan, generate, measure, save, script_words,
                  hook_text, spoken_range_pct=None, **kw):
        return {"verdict": "PASS", "delivered": {"audio_path": "/run/music/ok.mp3"},
                "receipt": {"id": "r"}, "receipts": [], "submitted_digest": digest}
    return run_takes


class _HoldingGenerate:
    """A generate() whose preserved dispatch envelope is a resumable save hold.

    X05: the provider task succeeded and charged but the save produced no
    verified file, so the attempt is a HOLD -- and the hold is reached AFTER
    the transport returned, which is the one case that has a digest to carry.
    """
    attempt_envelopes = {"polished-modern": {
        "variant_id": "polished-modern", "attempt_id": "a1", "outcome": "error",
        "reason_code": "KIE_SAVE_FAILED", "detail": "the save transport died",
        "next_action": "re-save the same task id; never resubmit",
        "counts": SC.make_counts(planned=1, submitted=1),
        "evidence": {"resume": {"command": "save", "task_id": "task-1"}},
        "causal_chain": []}}


def _run(generate):
    return SC.one_variant(
        1, dict(VARIANT), {}, {}, generate,
        lambda take: {"ok": 1}, lambda variant, take, receipt: True,
        "", "hook line")


class SubmittedDigestCarried(unittest.TestCase):
    def setUp(self):
        real = SC._SD.run_takes
        SC._SD.run_takes = _stub_run_takes(DIGEST)
        self.addCleanup(setattr, SC._SD, "run_takes", real)

    def test_one_variant_returns_the_admitted_digest(self):
        out = _run(lambda variant, request: [{"audio_path": "/run/music/ok.mp3"}])
        self.assertIn("submitted_digest", out)
        self.assertEqual(out["submitted_digest"], DIGEST)
        self.assertEqual(out["status"], "PASS")

    def test_hold_after_the_transport_keeps_the_digest(self):
        out = _run(_HoldingGenerate())
        self.assertEqual(out["status"], "HELD")
        self.assertEqual(out["submitted_digest"], DIGEST)


if __name__ == "__main__":
    unittest.main(verbosity=2)
