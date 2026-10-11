#!/usr/bin/env python3
"""WF1848F-U1 acceptance tests: the four measured holes in the timed rap review
and the rap plan.

Each test pins ONE of the four fixes the WF1848F-U1 brief names against the head
it was written at:

  1. ``rap_check._voice_intervals`` must keep a segment ONLY when its
     ``source`` is ``measured`` and its ``delivery`` is not ``none`` -- a
     planned-only voice map is ZERO voice, and the rap gate on it is
     unavailable, never PASS.
  2. ``judge_rap_delivery`` / ``rap_union`` must REQUIRE the take's real
     ``audio_sha256`` (``RAP_REVIEW_UNBOUND`` when it is missing) and must
     refuse a record that records no ``maker`` (a self-review cannot be ruled
     out without one) with ``RAP_REVIEW_UNBOUND``.
  3. ``length_formula.plan`` must reserve
     ``max(rap_floor_s(D), rap_verse_budget_s(D))`` out of the spoken allowance
     BEFORE it caps the spoken words, so spoken seconds plus rap seconds never
     exceed ``word_budget(D)["spoken_s"]``.
  4. Two verse labels may never cover the same physical seconds.

Run: python3 scripts/core/music_qc/test_ww1848f_rap_accept.py

The 0.5 s verse-overlap threshold is a PROPOSED value named by the WF1848F-U1
diagnosing lane; it is NOT measured. Nothing else here is a new threshold: the
per-verse floor and the lexical floor ride on WW-01 (length_formula).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import length_formula as LF                  # noqa: E402
import music_qc.rap_check as RC              # noqa: E402

#: The delivered length the WW-01 numbers are quoted at.
D = 88.0
HASH = "a" * 64
#: A voice map the DETECTOR never measured: every segment is planned and the
#: only delivery is "none". The docstring of _voice_intervals says the intervals
#: are the MEASURED voice (source == "measured"), so this map is ZERO voice.
PLANNED_ONLY = [{"start": 0.0, "end": 88.0, "delivery": "none", "source": "planned"},
                {"start": 10.0, "end": 20.0, "delivery": "planned", "source": "planned"},
                {"start": 30.0, "end": 40.0, "delivery": "rap", "source": "planned"}]
#: A real measured voice map for the same take.
MEASURED_VOICE = [{"start": 0.0, "end": 88.0, "delivery": "sung", "source": "measured"}]


def _windows(v1=(10.0, 20.0), v2=(30.0, 40.0)):
    """Two 10 s rap verses, each past the 8.0 s per-verse floor."""
    return [{"start_s": v1[0], "end_s": v1[1], "label": "rap", "verse": 1},
            {"start_s": v2[0], "end_s": v2[1], "label": "rap", "verse": 2}]


def _bound_record(**kw):
    """A record that binds to HASH and names a maker who is not the reviewer."""
    v1, v2 = kw.pop("v1", (10.0, 20.0)), kw.pop("v2", (30.0, 40.0))
    base = dict(audio_sha256=HASH, reviewer="r1", maker="m1", session="s1",
                timestamp="2026-10-11T00:00:00Z", windows=_windows(v1, v2))
    base.update(kw)
    return RC.make_review(**base)


def test_planned_only_voice_is_zero_voice_and_the_rap_gate_is_unavailable():
    """FIX 1. The body never checked ``source`` and never excluded
    ``delivery == "none"``, so a PLANNED segment list was counted as measured
    voice and a review could PASS on evidence the detector never produced."""
    assert RC._voice_intervals(PLANNED_ONLY, D) == [], (
        "_voice_intervals kept a planned/delivery-none segment as measured voice: %r"
        % (RC._voice_intervals(PLANNED_ONLY, D),))
    out = RC.judge_rap_delivery(_bound_record(), audio_sha256=HASH, duration_s=D,
                                voice_segments=PLANNED_ONLY, delivered_s=D)
    assert out["verdict"] != "PASS", (
        "a planned-only voice map let the rap gate PASS: %r" % (out,))
    assert out["verdict"] == "UNMEASURED", (
        "a planned-only voice map must report the gate UNAVAILABLE "
        "(rap_check's fail-closed state), got %r" % (out,))


def test_a_review_with_no_take_hash_is_refused_as_unbound():
    """FIX 2. The audio binding was checked only when the caller passed it, so a
    caller that passed nothing got RAP_REVIEW_BOUND for a review bound to ANY
    audio at all. The take's real hash is now REQUIRED."""
    out = RC.judge_rap_delivery(_bound_record(), duration_s=D,
                                voice_segments=MEASURED_VOICE, delivered_s=D)
    assert out["verdict"] == "FAIL" and out["reason_code"] == "RAP_REVIEW_UNBOUND", (
        "judge_rap_delivery did not require the take's audio_sha256: %r" % (out,))
    union = RC.rap_union(_bound_record(), duration_s=D, voice_segments=MEASURED_VOICE)
    assert union["ok"] is False and union["reason_code"] == "RAP_REVIEW_UNBOUND", (
        "rap_union did not require the take's audio_sha256: %r" % (union,))


def test_a_review_with_no_maker_is_refused_as_unbound():
    """FIX 2. ``maker`` was optional, so a record with no maker SKIPPED the
    self-approval refusal entirely and a maker could review their own take."""
    rec = RC.make_review(audio_sha256=HASH, reviewer="r1", session="s1",
                         timestamp="t", windows=_windows())
    assert rec.get("maker") is None
    out = RC.judge_rap_delivery(rec, audio_sha256=HASH, duration_s=D,
                                voice_segments=MEASURED_VOICE, delivered_s=D)
    assert out["verdict"] == "FAIL" and out["reason_code"] == "RAP_REVIEW_UNBOUND", (
        "a record with no maker was not refused as unbound: %r" % (out,))
    assert "no maker" in (out.get("detail") or ""), (
        "the refusal must carry the reason: no maker recorded (%r)" % (out,))


def test_spoken_and_rap_seconds_add_up_within_the_spoken_allowance():
    """FIX 3. ``spoken_cap_words`` reserved only ``rap_floor_s(D)`` while
    ``rap_s`` was then raised to ``rap_verse_budget_s(D)`` (16.0 s at D 88), so
    spoken seconds plus rap seconds exceeded the spoken allowance and the words
    did not add up."""
    over = []
    for d in (88, 90, 105, 120, 150):
        p = LF.plan(d + LF.END_EARLY_S, style_id="rnb-flow")
        wb = LF.word_budget(d)
        tot = p["words"]["spoken"] / LF.SPOKEN_WPS + p["rap_s"]
        if tot > wb["spoken_s"] + 1e-6:
            over.append((d, round(tot, 4), wb["spoken_s"]))
    assert not over, "spoken + rap exceeds the spoken allowance: %r" % (over,)

    # D 60: the style's whole spoken allowance is 13.5 s (22.5 % of 60), which is
    # BELOW the 16.0 s the ordered two-verse reservation demands -- the two rules
    # are contradictory there. The invariant must still hold: the plan either
    # refuses or it emits seconds that add up. It must never emit rap seconds
    # larger than the allowance it is carved from.
    try:
        p60 = LF.plan(60 + LF.END_EARLY_S, style_id="rnb-flow")
    except LF.LengthError:
        p60 = None
    if p60 is not None:
        wb60 = LF.word_budget(60)
        tot60 = p60["words"]["spoken"] / LF.SPOKEN_WPS + p60["rap_s"]
        assert tot60 <= wb60["spoken_s"] + 1e-6, (
            "at D 60 the plan claims %.4f s of spoken + rap inside a %.1f s "
            "allowance" % (tot60, wb60["spoken_s"]))


def test_two_verse_labels_may_not_cover_the_same_physical_seconds():
    """FIX 4. Two verse labels over the same seconds were counted twice: each
    verse cleared the per-verse floor off the SAME window. The PROPOSED
    threshold is 0.5 s -- an overlap of more than that fails."""
    rec = _bound_record(v1=(10.0, 26.0), v2=(10.0, 26.0))
    out = RC.judge_rap_delivery(rec, audio_sha256=HASH, duration_s=D,
                                voice_segments=MEASURED_VOICE, delivered_s=D)
    assert out["verdict"] == "FAIL" and out["reason_code"] == "RAP_REVIEW_VERSE_OVERLAP", (
        "two verse labels over the same 16 seconds were not refused: %r" % (out,))
    # 0.4 s of overlap is BELOW the proposed 0.5 s threshold and is tolerated.
    ok = _bound_record(v1=(10.0, 20.0), v2=(19.6, 29.6))
    okout = RC.judge_rap_delivery(ok, audio_sha256=HASH, duration_s=D,
                                  voice_segments=MEASURED_VOICE, delivered_s=D)
    assert okout["verdict"] == "PASS", (
        "0.4 s of overlap is inside the proposed 0.5 s tolerance: %r" % (okout,))


def test_the_named_overlapping_verse_record_is_refused():
    """FIX 4's regression record, exactly as the brief names it: NO take hash
    from the caller, NO maker recorded, a timestamp of just "t", a voice map
    that is planned only with delivery "none", and the SAME 16-second window
    labelled as both verse 1 and verse 2. It used to PASS."""
    rec = RC.make_review(audio_sha256=HASH, reviewer="r1", session="s1",
                         timestamp="t",
                         windows=[{"start_s": 10.0, "end_s": 26.0,
                                   "label": "rap", "verse": 1},
                                  {"start_s": 10.0, "end_s": 26.0,
                                   "label": "rap", "verse": 2}])
    out = RC.judge_rap_delivery(rec, duration_s=D, voice_segments=PLANNED_ONLY,
                                delivered_s=D)
    assert out["verdict"] != "PASS", (
        "the named overlapping-verse record still passes: %r" % (out,))
    assert out["reason_code"] == "RAP_REVIEW_VERSE_OVERLAP", (
        "the named record must fail on the overlap reason, got %r" % (out,))


def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed.append(name)
            print("FAIL %s\n     %s" % (name, e))
        else:
            print("ok   %s" % name)
    if failed:
        print("\n%d FAILED: %s" % (len(failed), "; ".join(failed)))
        return 1
    print("\nALL PASS (%d checks)" % len(tests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
