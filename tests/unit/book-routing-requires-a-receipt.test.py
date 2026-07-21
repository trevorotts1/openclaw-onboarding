#!/usr/bin/env python3
"""tests/unit/book-routing-requires-a-receipt.test.py

REGRESSION GUARD — T0-28: a book handoff was recorded as ROUTED because a
DIRECTORY existed.

52-avatar-alchemist/scripts/aa_director.py::_version_gate decided:

    route = "book-routed" if "AF-AV-BOOK-SKILL-MISSING" not in codes else "book-parked"

and that code came from aa_intake_gate.verify(intake, book_present), where
book_present was `_detect_book_skill_present()` — a glob for a sibling
`53-*book*` folder. No target was ever invoked. Skill 53 never saw the intake.
The durable `<run-dir>/route.json` that downstream automation reads recorded a
completed handoff for a book run that had never begun, and the forwarded intake
would not have satisfied the target's own entry gate anyway.

THE FIX: `book-routed` is written only when the target's own intake-accept
command (53-*book*/scripts/bw_intake_accept.py) returns an acceptance receipt,
read from that process's STDOUT — not from a file that could be pre-planted —
and only when the digest the target signed matches the sha256 of the bytes the
caller forwarded.

WHAT THIS FILE PROVES (hermetic: staged skill trees in a tempdir; no network,
no box state, nothing outside the checkout is written):

  T1  a complete book intake + a real Skill 53  -> book-routed, accepted=true,
      and the receipt is bound to the forwarded bytes
  T2  an INCOMPLETE book intake                 -> book-rejected, accepted=false,
      carrying the target's own AF-BK-* reasons
  T3  Skill 53 present but exposing NO intake-accept command -> book-pending,
      accepted=false — an unconsultable target is reported, never rounded up
  T4  a target that prints a receipt for DIFFERENT bytes -> book-pending; a
      receipt minted for another payload proves nothing about this one
  T5  no Skill 53 at all                        -> book-parked, accepted=false
  T6  the exit code stays 4 for every version=book outcome (the hard stop is
      unchanged; what changed is that route.json now tells the truth)

Run: python3 tests/unit/book-routing-requires-a-receipt.test.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AA_SKILL = REPO_ROOT / "52-avatar-alchemist"
BOOK_SKILL_NAME = "53-book-writer"
BOOK_SKILL = REPO_ROOT / BOOK_SKILL_NAME

PASSN = 0
FAILN = 0


def pass_(m):
    global PASSN
    PASSN += 1
    print("  PASS: %s" % m)


def fail_(m, extra=""):
    global FAILN
    FAILN += 1
    print("  FAIL: %s" % m)
    if extra:
        print("        %s" % extra)


COMPLETE_BOOK_INTAKE = {
    "version": "book",
    "first_name": "Amara",
    "last_name": "Vale",
    "ideal_avatar": "women founders in service businesses who feel invisible",
    "niche": "visibility and authority coaching for women founders",
    "primary_goal": "convert proven competence into a fully-booked, visible practice",
    "tone_style_1": "the cadence of classic abolitionist oratory",
    "tone_style_2": "N/A",
    "book_stories": "The season I stopped hiding my expertise and let the work be seen.",
}


def _load_director():
    """Import aa_director from the real checkout (its own scripts dir is put on
    sys.path by the module itself)."""
    spec = importlib.util.spec_from_file_location(
        "aa_director_under_test", AA_SKILL / "scripts" / "aa_director.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stage(tmp: Path, *, book_mode: str) -> Path:
    """Stage a box layout: <tmp>/box/52-avatar-alchemist plus a Skill 53 in one of
    four shapes. Returns the staged 52 skill root."""
    box = tmp / "box"
    box.mkdir(parents=True, exist_ok=True)
    aa = box / AA_SKILL.name
    if not aa.exists():
        aa.mkdir()
        (aa / "scripts").mkdir()

    if book_mode == "real":
        shutil.copytree(BOOK_SKILL, box / BOOK_SKILL_NAME, dirs_exist_ok=True)
    elif book_mode == "no-accept-command":
        d = box / BOOK_SKILL_NAME / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        (box / BOOK_SKILL_NAME / "skill-version.txt").write_text("1.1.5\n", encoding="utf-8")
    elif book_mode == "wrong-digest":
        d = box / BOOK_SKILL_NAME / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        # A hostile/broken target that always claims acceptance, but for a digest
        # it made up. The caller must refuse to honour it.
        (d / "bw_intake_accept.py").write_text(
            "import json,sys\n"
            "print(json.dumps({'kind':'book-intake-accept/v1','accepted':True,"
            "'target_skill':'53-book-writer','intake_sha256':'"
            + "0" * 64 + "','receipt_id':'deadbeef'}))\n"
            "sys.exit(0)\n", encoding="utf-8")
    elif book_mode == "absent":
        pass
    else:
        raise AssertionError("unknown book_mode %r" % book_mode)
    return aa


def _run_gate(director, staged_aa: Path, intake: dict):
    """Drive the REAL _version_gate against a staged box layout."""
    run_dir = staged_aa.parent / ("run-" + hashlib.sha256(
        json.dumps(intake, sort_keys=True).encode()).hexdigest()[:8])
    run_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(intake, indent=2).encode("utf-8")
    (run_dir / "intake.json").write_bytes(raw)

    saved = director._skill_root
    director._skill_root = lambda: staged_aa
    try:
        rc, record = director._version_gate(run_dir)
    finally:
        director._skill_root = saved
    return rc, record, run_dir, hashlib.sha256(raw).hexdigest()


def main() -> int:
    director = _load_director()
    tmp = Path(tempfile.mkdtemp(prefix="bookroute_"))
    try:
        # ---- T1: real target, complete intake -> ACCEPTED --------------------
        aa = _stage(tmp / "t1", book_mode="real")
        rc, rec, run_dir, sha = _run_gate(director, aa, COMPLETE_BOOK_INTAKE)
        if rec.get("route") == "book-routed" and rec.get("accepted") is True:
            pass_("T1 complete intake + real Skill 53 -> book-routed, accepted=true")
        else:
            fail_("T1 expected book-routed/accepted", json.dumps(rec)[:400])
        receipt = rec.get("receipt") or {}
        if receipt.get("intake_sha256") == sha and receipt.get("target_skill") == BOOK_SKILL_NAME:
            pass_("T1 the receipt is bound to the forwarded bytes and names the target")
        else:
            fail_("T1 receipt not bound to the forwarded bytes", json.dumps(receipt)[:400])
        if (run_dir / "book-intake-receipt.json").is_file():
            pass_("T1 the target also persisted its receipt beside the run")
        else:
            fail_("T1 no persisted receipt beside the run")
        if rc == 4:
            pass_("T1 exit code is still 4 (version=book remains a hard stop)")
        else:
            fail_("T1 exit code changed", str(rc))

        # ---- T2: real target, incomplete intake -> REJECTED ------------------
        incomplete = dict(COMPLETE_BOOK_INTAKE)
        incomplete.pop("niche")
        aa = _stage(tmp / "t2", book_mode="real")
        rc, rec, _, _ = _run_gate(director, aa, incomplete)
        if rec.get("route") == "book-rejected" and rec.get("accepted") is False:
            pass_("T2 incomplete intake -> book-rejected, accepted=false")
        else:
            fail_("T2 expected book-rejected", json.dumps(rec)[:400])
        reasons = json.dumps(rec.get("target_reasons") or [])
        if "AF-BK-INTAKE-MISSING" in reasons:
            pass_("T2 the target's own AF-BK-INTAKE-MISSING reason is carried through")
        else:
            fail_("T2 the target's reasons were not carried through", reasons[:400])
        if rc == 4:
            pass_("T2 exit code is still 4")
        else:
            fail_("T2 exit code changed", str(rc))

        # ---- T3: target installed but exposes no accept command -> PENDING ---
        aa = _stage(tmp / "t3", book_mode="no-accept-command")
        rc, rec, _, _ = _run_gate(director, aa, COMPLETE_BOOK_INTAKE)
        if rec.get("route") == "book-pending" and rec.get("accepted") is False:
            pass_("T3 an unconsultable target -> book-pending, accepted=false")
        else:
            fail_("T3 expected book-pending", json.dumps(rec)[:400])
        if "intake-accept" in str(rec.get("reason", "")):
            pass_("T3 the reason names the missing intake-accept command")
        else:
            fail_("T3 reason does not name the gap", str(rec.get("reason"))[:300])

        # ---- T4: target claims acceptance for other bytes -> PENDING ---------
        aa = _stage(tmp / "t4", book_mode="wrong-digest")
        rc, rec, _, _ = _run_gate(director, aa, COMPLETE_BOOK_INTAKE)
        if rec.get("route") == "book-pending" and rec.get("accepted") is False:
            pass_("T4 a receipt minted for different bytes is NOT honoured -> book-pending")
        else:
            fail_("T4 a mismatched receipt was accepted", json.dumps(rec)[:400])

        # ---- T5: no Skill 53 at all -> PARKED -------------------------------
        aa = _stage(tmp / "t5", book_mode="absent")
        rc, rec, _, _ = _run_gate(director, aa, COMPLETE_BOOK_INTAKE)
        if rec.get("route") == "book-parked" and rec.get("accepted") is False:
            pass_("T5 no Skill 53 on the box -> book-parked, accepted=false")
        else:
            fail_("T5 expected book-parked", json.dumps(rec)[:400])
        if rc == 4:
            pass_("T6 exit code is 4 across every version=book outcome")
        else:
            fail_("T6 exit code changed", str(rc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== %d passed, %d failed ===" % (PASSN, FAILN))
    return 1 if FAILN else 0


if __name__ == "__main__":
    sys.exit(main())
