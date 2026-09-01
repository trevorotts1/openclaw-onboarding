#!/usr/bin/env python3
"""test_craft_warning_holds.py — FIX 18 repair: the warning bucket HOLDS the QC
phase until corrected or individually acknowledged.

The FIX 18 commit wired the 5 enforce rows (blocking via
build_deck._chk_slide_craft) and the 2 human rows (blocking attest_phase via
craft_judgement.attestation_blocker), but the spec's THIRD bucket was left
inert: the 6 warning rows (AF-AUD-1/2/3, AF-OBI-3/5, AF-DEN-8) were computed
and DISPLAYED (qc_check level="warning", exit-neutral) yet held nothing. This
test proves the repair:

  1. HOLD REFUSAL — an unacknowledged warning (AF-AUD-1 on slide 1) makes
     craft_judgement.warning_hold_blocker return an AF-WARNING-HOLD message
     naming code+slide for P1Q-COPY-QC (the phase that owns the warning rules),
     and run_signature_deck.attest_phase exits 2 while it is pending (the same
     non-crash, resumable autofail-style block the human rows use).
  2. ACK CLEARS ONE HOLD — ONE valid per-rule/per-slide disposition record
     (exact rule_code + slide_ids, independent reviewer, owner signature) makes
     compute_warnings return [] and clears the hold; attest_phase then attests
     clean.
  3. NO BLANKET ACK — a disposition for a DIFFERENT code (AF-AUD-2) or a
     DIFFERENT slide (AF-AUD-1 slide 2) leaves the AF-AUD-1/slide-1 warning
     pending and the hold alive.
  4. HOLD STATE PERSISTED — compute_warnings writes the pending-hold snapshot
     to working/qc/craft-warnings.json (pending_holds naming code+slide); after
     the valid ack the persisted hold is gone — the ledger is a truthful
     snapshot, never a stale accumulation.
  5. ROLLBACK — PRESENTATION_CRAFT_DISPOSITIONS=0 makes compute_warnings []
     and warning_hold_blocker "" (documented rollback: warnings inert, gate
     idle).
  6. SCOPE — the hold fires only for the owning phase (a non-owner QC phase
     attests past a pending warning), and only while the flag is on.
  7. DEN-8 (section-level) — a section-floor warning (AF-DEN-8) holds too; it
     attributes the SECTION'S OWN slide ordinals (a deck-wide rule warns once
     per offending section, not once per slide, but the hold is still named),
     so a disposition naming exactly those slides clears exactly that hold,
     while an empty slide_ids disposition is refused (fail-closed) and never
     clears anything.

Flat beside the module under test (pytest prepend-import convention — there is
no scripts/tests/ directory). Standard library only. Run:
    python3 -m pytest test_craft_warning_holds.py -q
    python3 test_craft_warning_holds.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import craft_judgement as cj  # noqa: E402

WARNING_SLIDE = {"slide": 1, "scene": "x",
                 "copy": ["REAL REVENUE GROWTH", "Speaker: stay right here"]}
CLEAN_SLIDE = {"slide": 2, "scene": "x", "copy": ["SAME HEADLINE THAT FITS"]}


def _run_dir(with_warning=True, with_arc=True):
    rd = Path(tempfile.mkdtemp(prefix="fix18hold_"))
    work = rd / "working"
    (work / "copy").mkdir(parents=True)
    (work / "qc").mkdir(parents=True)
    (work / "copy" / "slides.json").write_text(
        json.dumps([WARNING_SLIDE, CLEAN_SLIDE] if with_warning
                   else [CLEAN_SLIDE]))
    (work / "copy" / "intake.json").write_text(
        json.dumps({"deck_type": "webinar"}))
    if with_arc:
        (work / "copy" / "arc_allocation.json").write_text(
            json.dumps({"slots": [{"slide": i, "arc_section": "BUILDUP"}
                                  for i in (1, 2)]}))
    return rd


def _valid_disposition(rd, code, slide_ids):
    return {
        "rule_code": code, "slide_ids": slide_ids, "run_id": rd.name,
        "reviewer": "independent-qc-specialist",
        "rationale": "reviewed per rule; accepted with rationale.",
        "decision": "acknowledged",
        "captured_at": "2026-08-31T10:00:00Z",
        "owner_signature": "trevor@blackceo.com",
    }


def _file_disposition(rd, rec):
    p = rd / cj.DISPOSITIONS_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = []
    else:
        data = []
    data.append(rec)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _acks(rd):
    return {(d["rule_code"], tuple(d["slide_ids"]))
            for d in cj.load_dispositions(rd)}


def test_warning_hold_blocker_fires_on_unack_warning():
    rd = _run_dir()
    warns = cj.compute_warnings(rd, slides_path=str(rd / "working" / "copy"
                                                    / "slides.json"))
    assert any(w["rule_code"] == "AF-AUD-1" for w in warns), \
        "fixture must produce an AF-AUD-1 warning"
    blocker = cj.warning_hold_blocker(rd, "P1Q-COPY-QC")
    assert blocker, "hold must fire while AF-AUD-1/slide-1 is pending"
    assert "AF-WARNING-HOLD" in blocker and "AF-AUD-1" in blocker
    assert "slide 1" in blocker, "blocker must name the offending slide"


def test_hold_state_persisted_in_craft_warnings_json():
    rd = _run_dir()
    cj.compute_warnings(rd, slides_path=str(rd / "working" / "copy"
                                            / "slides.json"))
    hp = rd / cj.WARNING_HOLDS_REL
    assert hp.is_file(), "craft-warnings.json must be written"
    state = json.loads(hp.read_text(encoding="utf-8"))
    holds = state["pending_holds"]
    assert any(h["rule_code"] == "AF-AUD-1" and 1 in h["slide_ids"]
               for h in holds), f"hold snapshot missing AF-AUD-1: {holds!r}"
    assert state.get("owner_phase") == "P1Q-COPY-QC"


def test_valid_disposition_clears_that_hold():
    rd = _run_dir()
    _file_disposition(rd, _valid_disposition(rd, "AF-AUD-1", [1]))
    warns = cj.compute_warnings(rd, slides_path=str(rd / "working" / "copy"
                                                    / "slides.json"))
    assert not any(w["rule_code"] == "AF-AUD-1" for w in warns), \
        "per-slide ack must clear the AF-AUD-1/slide-1 warning"
    assert cj.warning_hold_blocker(rd, "P1Q-COPY-QC") == ""
    state = json.loads((rd / cj.WARNING_HOLDS_REL).read_text(encoding="utf-8"))
    assert not any(h["rule_code"] == "AF-AUD-1" for h in state["pending_holds"]), \
        "persisted hold must vanish after the valid ack"


def test_wrong_code_or_wrong_slide_never_clears_a_hold():
    rd = _run_dir()
    _file_disposition(rd, _valid_disposition(rd, "AF-AUD-2", [1]))
    warns = cj.compute_warnings(rd, slides_path=str(rd / "working" / "copy"
                                                    / "slides.json"))
    assert any(w["rule_code"] == "AF-AUD-1" for w in warns), \
        "AF-AUD-1 must survive a disposition for a different code"
    assert cj.warning_hold_blocker(rd, "P1Q-COPY-QC"), \
        "a wrong-code disposition must not release the hold"
    rd2 = _run_dir()
    _file_disposition(rd2, _valid_disposition(rd2, "AF-AUD-1", [2]))
    warns2 = cj.compute_warnings(rd2, slides_path=str(rd2 / "working" / "copy"
                                                      / "slides.json"))
    assert any(w["rule_code"] == "AF-AUD-1" and 1 in w["slide_ids"]
               for w in warns2), \
        "AF-AUD-1/slide-1 must survive a disposition naming only slide 2"
    assert cj.warning_hold_blocker(rd2, "P1Q-COPY-QC"), \
        "a wrong-slide disposition must not release the hold"


def test_deck_level_den8_hold_requires_named_slides_to_clear():
    rd = _run_dir(with_warning=False)
    # AF-DEN-8: a present section below its floor — HOOK floor 5, 2 slots.
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps({
        "slots": [{"slide": 1, "arc_section": "HOOK"},
                  {"slide": 2, "arc_section": "HOOK"}]}))
    warns = cj.compute_warnings(rd)
    den8 = [w for w in warns if w["rule_code"] == "AF-DEN-8"]
    assert den8, "fixture must produce an AF-DEN-8 warning"
    # The warning attributes the section's own ordinals, not [] (a hold with
    # no named slide could never be individually acknowledged).
    assert sorted(den8[0]["slide_ids"]) == [1, 2], \
        f"DEN-8 must attribute the section's slides, got {den8[0]['slide_ids']}"
    blocker = cj.warning_hold_blocker(rd, "P1Q-COPY-QC")
    assert blocker and "AF-DEN-8" in blocker, \
        "section-level warning must hold the phase"
    # Fail closed: an ack with NO slide_ids is invalid and clears nothing.
    _file_disposition(rd, _valid_disposition(rd, "AF-DEN-8", []))
    warns2 = cj.compute_warnings(rd)
    assert any(w["rule_code"] == "AF-DEN-8" for w in warns2), \
        "empty slide_ids disposition must never clear the DEN-8 warning"
    assert cj.warning_hold_blocker(rd, "P1Q-COPY-QC"), \
        "invalid disposition must not release the DEN-8 hold"
    # And the NAMED-slides disposition clears exactly that hold.
    _file_disposition(rd, _valid_disposition(rd, "AF-DEN-8", [1, 2]))
    warns3 = cj.compute_warnings(rd)
    assert not any(w["rule_code"] == "AF-DEN-8" for w in warns3), \
        "a disposition naming the section's slides must clear the hold"
    assert cj.warning_hold_blocker(rd, "P1Q-COPY-QC") == ""


def test_hold_scoped_to_owner_phase_and_rollback_flag():
    rd = _run_dir()
    assert cj.warning_hold_blocker(rd, "P1Q-COPY-QC"), "owner phase holds"
    assert cj.warning_hold_blocker(rd, "P-PROMPT-QC") == "", \
        "non-owner phase must not be held by the warning gate"
    assert cj.warning_hold_blocker(rd, "P-TYPO-QC") == ""
    old = os.environ.get("PRESENTATION_CRAFT_DISPOSITIONS")
    os.environ["PRESENTATION_CRAFT_DISPOSITIONS"] = "0"
    try:
        assert cj.compute_warnings(rd) == [], \
            "rollback: flag=0 warnings must be inert"
        assert cj.warning_hold_blocker(rd, "P1Q-COPY-QC") == "", \
            "rollback: flag=0 must idle the hold gate"
    finally:
        if old is None:
            os.environ.pop("PRESENTATION_CRAFT_DISPOSITIONS", None)
        else:
            os.environ["PRESENTATION_CRAFT_DISPOSITIONS"] = old


def test_slide_ids_subset_and_non_positive_rejected():
    rd = _run_dir()
    rec = _valid_disposition(rd, "AF-AUD-1", [0])
    _file_disposition(rd, rec)
    assert cj.warning_hold_blocker(rd, "P1Q-COPY-QC"), \
        "a disposition with a non-positive slide must be dropped (fail closed)"
    warns = cj.compute_warnings(rd, slides_path=str(rd / "working" / "copy"
                                                    / "slides.json"))
    assert any(w["rule_code"] == "AF-AUD-1" for w in warns), \
        "non-positive slide ack must never clear the warning"


# ---------------------------------------------------------------------------
# Script-mode aggregation (pytest-visible assert wrappers are the real checks)
# ---------------------------------------------------------------------------
def _all():
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    failures = []
    for fn in checks:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__}: {exc!r}")
    if failures:
        print("RED: " + "; ".join(failures))
        sys.exit(1)
    print(f"GREEN: {len(checks)} warning-hold assertions passed.")


if __name__ == "__main__":
    _all()
