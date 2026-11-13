#!/usr/bin/env python3
"""S75-018 (audit row X06 via U-R02 R2): the reason a take was WITHHELD for a
pending bounded review must reach the client-facing message.

The review block ``run_takes`` builds is the only record of why a take was not
delivered. Until this unit it died at the ``one_variant`` wrapper -- zero
production reads. This test stubs ``run_takes`` to withhold a take on a review
requirement with a KNOWN reason and proves the client message names it. It
FAILS pre-fix, when the key never leaves the wrapper.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/song_choices/test_s75_018_review_reason.py
No provider, no ffmpeg, no spend: run_takes is stubbed and nothing is written.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for sub in ("", "intake_preflight"):
    sys.path.insert(0, os.path.join(CORE, sub))
from song_choices import song_choices as SC     # noqa: E402
from song_dispatch import song_dispatch as _SD  # noqa: E402

REASON = ("sung/spoken classifier confidence 0.400 is below 0.550: classifier "
          "uncertainty triggers remeasurement or ONE bounded independent "
          "review -- never a definite creative failure (spec 6.5)")
REVIEW = {"required": True, "satisfied": False, "kind": "independent_media_review",
          "check_id": "sung_spoken_classification", "confidence": 0.4,
          "source": "detector", "reason": REASON}


def _rcpt():
    return {"verdict": "FAIL",
            "gates": {"hook_placement": _SD._gate("FAIL", "hook lands late")},
            "required_gates": ["hook_placement"]}


def _withheld(reason=REASON, review_required=None):
    rv = dict(REVIEW)
    if reason is None:
        rv.pop("reason", None)
    else:
        rv["reason"] = reason
    return {"delivered": None, "verdict": "FAIL", "receipts": [_rcpt()],
            "spent_cents": 0, "duration": 0, "submitted_digest": "digest",
            "review_required": review_required if review_required is not None else rv}


def _drive(monkeypatch, stub):
    monkeypatch.setattr(_SD, "run_takes", lambda *a, **k: stub)
    variant = {"id": "v1", "label": "WW-001 - A", "description": "faithful"}
    return SC.one_variant(1, variant, {"_style_id": None}, {},
                          lambda v, rq: {"take": {"audio_path": "x", "duration_s": 1.0}},
                          lambda t: {}, lambda v, t, rc: None, {}, "")


def test_withheld_take_reason_reaches_client_message(monkeypatch):
    result = _drive(monkeypatch, _withheld())
    # the reason leaves the wrapper ...
    assert result["review_required"]["reason"] == REASON
    # ... and reaches the client-facing text
    msg = SC.failure_fork_message([result])
    assert REASON in msg
    assert "bounded review pending" in msg


def test_missing_reason_uses_module_fallback(monkeypatch):
    result = _drive(monkeypatch, _withheld(reason=None))
    msg = SC.failure_fork_message([result])
    assert "bounded review pending: low-confidence classification" in msg


def test_satisfied_review_names_no_reason(monkeypatch):
    result = _drive(monkeypatch, _withheld(review_required=dict(REVIEW, satisfied=True)))
    msg = SC.failure_fork_message([result])
    assert REASON not in msg
