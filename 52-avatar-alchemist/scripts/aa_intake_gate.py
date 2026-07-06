#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_intake_gate.py — fail-closed intake + Book/Brand version-selector prover
for the Avatar-Alchemist brand-intelligence pipeline (Skill 52).

Enforces Gate 0 (G0-INTAKE) and the version gate (G0-VERSION, PRD 5.4):
  * required intake fields present, non-empty, not template boilerplate  -> AF-AV-INTAKE-INCOMPLETE
  * version explicitly 'book' or 'brand' (no default, no inference)       -> AF-AV-VERSION-UNSET
  * the answered question set matches the selected version                -> AF-AV-VERSION-MISMATCH
  * version=book routes to the separate Book skill (53) or parks
    fail-closed 'book-skill-not-available' (NEVER the brand pipeline)      -> AF-AV-BOOK-SKILL-MISSING

No silent cross-version fallback, ever. stdlib only.
Exit 0 = pass, 2 = contract violation, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# --- shared answers on BOTH forms (PRD 5.2) -------------------------------
SHARED_REQUIRED = ["ideal_avatar", "niche", "primary_goal", "tone_style_1", "tone_style_2"]
# lead-capture identity used to label deliverables
IDENTITY_REQUIRED = ["first_name", "last_name"]
# brand-only required payload (PRD 5.2). 'tone' is the BRAND delta.
BRAND_REQUIRED = ["tone", "target_market", "tone_style_3", "tone_style_4",
                  "offer_name", "offer_type", "offer_benefit", "product_info",
                  "brand_info", "brand_start_date", "brand_why", "brand_colors"]
# fields that must NOT carry real content on a BOOK run (would signal version confusion)
BRAND_ONLY_CONTENT = ["tone", "target_market", "tone_style_3", "tone_style_4",
                      "offer_name", "offer_type", "offer_benefit", "product_info",
                      "brand_info", "brand_start_date", "brand_why", "brand_colors"]

_BOILERPLATE = {
    "", "todo", "tbd", "...", "<fill>", "<fill me>", "fill me", "xxx",
    "your answer here", "answer here", "example", "placeholder",
    "my ideal avatar / dream customer is…", "my niche or category is…",
    "my writing tone is…", "my writing tone is... i.e. inspirational, thought-provoking, etc.",
}


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _present(v: Any) -> bool:
    """Non-empty, not boilerplate. 'N/A' counts as a real (permitted) answer."""
    s = _s(v)
    return bool(s) and s.lower() not in _BOILERPLATE


def _real_content(v: Any) -> bool:
    """Present AND not an N/A non-answer — i.e. a genuine value."""
    s = _s(v)
    return _present(v) and s.lower() not in {"n/a", "na", "none"}


def resolve_apply_repairs(intake: Dict[str, Any]) -> bool:
    """R3 (RATIFIED 2026-07-05): the CLIENT-run repairs default is ON. A run is
    faithful-to-live (repairs OFF) ONLY when the intake explicitly sets
    apply_repairs=false. Absent => True (client default). aa_director.py layers
    an explicit --apply-repairs/--no-repairs override on top of this."""
    ar = intake.get("apply_repairs")
    return True if ar is None else bool(ar)


def verify(intake: Dict[str, Any], book_skill_present: bool) -> Tuple[List[Tuple[str, str]], List[str]]:
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        violations.append((code, msg))

    if not isinstance(intake, dict):
        fail("AF-AV-INTAKE-INCOMPLETE", "intake is not a JSON object")
        return violations, notes

    # --- G0-VERSION: version explicitly book|brand ------------------------
    version = _s(intake.get("version")).lower()
    if version not in ("book", "brand"):
        fail("AF-AV-VERSION-UNSET",
             f"version must be explicitly 'book' or 'brand' (got {intake.get('version')!r}); "
             f"no default, no inference from other answers")
        # cannot meaningfully continue version-specific checks
        # still surface generic incompleteness below

    # --- shared + identity required fields --------------------------------
    for k in IDENTITY_REQUIRED + SHARED_REQUIRED:
        if not _present(intake.get(k)):
            fail("AF-AV-INTAKE-INCOMPLETE", f"required field '{k}' missing/empty/boilerplate")

    # --- version-specific question-set match + branch routing -------------
    if version == "brand":
        # brand delta 'tone' must be answered
        if not _present(intake.get("tone")):
            fail("AF-AV-VERSION-MISMATCH",
                 "version=brand requires the BRAND delta 'tone' (My Writing Tone) — missing")
        # book delta must NOT carry real content on a brand run
        if _real_content(intake.get("book_stories")):
            fail("AF-AV-VERSION-MISMATCH",
                 "version=brand but 'book_stories' carries real content (book-only question on a brand run)")
        # full brand payload required
        for k in BRAND_REQUIRED:
            if not _present(intake.get(k)):
                fail("AF-AV-INTAKE-INCOMPLETE", f"version=brand requires brand field '{k}' — missing/empty")
        # --- R3 (RATIFIED 2026-07-05): client-run repairs default = ON ----
        # A CLIENT brand run defaults to apply_repairs=true so the delivered
        # package does NOT ship the live workflow's known content bugs. A
        # fidelity/regression run opts out with apply_repairs=false (or
        # aa_director.py --no-repairs). Absent => the client default (ON).
        ar = intake.get("apply_repairs")
        if ar is None:
            notes.append("REPAIRS: apply_repairs absent -> client-run DEFAULT ON "
                         "(delivered package excludes the known live-workflow content bugs; set "
                         "apply_repairs=false / aa_director.py --no-repairs for a fidelity/regression run)")
        elif not isinstance(ar, bool):
            fail("AF-AV-INTAKE-INCOMPLETE",
                 f"apply_repairs must be a JSON boolean when present (got {ar!r})")
        else:
            notes.append(f"REPAIRS: apply_repairs={str(ar).lower()} (explicit)")

    elif version == "book":
        # book delta must be present (N/A allowed)
        if not _present(intake.get("book_stories")):
            fail("AF-AV-VERSION-MISMATCH",
                 "version=book requires the BOOK delta 'book_stories' (present; 'N/A' allowed) — missing")
        # brand-only content must NOT be present on a book run
        for k in BRAND_ONLY_CONTENT:
            if _real_content(intake.get(k)):
                fail("AF-AV-VERSION-MISMATCH",
                     f"version=book but brand-only field '{k}' carries real content (brand question on a book run)")
        # ROUTE (never run the brand pipeline for a book request)
        if book_skill_present:
            notes.append("ROUTE: version=book -> hand off to the separate Avatar Alchemist Book skill (53); "
                         "this skill performs ZERO generation for a book run")
        else:
            fail("AF-AV-BOOK-SKILL-MISSING",
                 "version=book with no resolvable Book-skill route — parks fail-closed "
                 "'book-skill-not-available' (NEVER silently served by the brand pipeline)")

    return violations, notes


# --------------------------------------------------------------------------
# IO / CLI
# --------------------------------------------------------------------------
def _load(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(violations, notes) -> None:
    for n in notes:
        print(f"NOTE: {n}")
    if not violations:
        print("PASS: intake clears G0-INTAKE + G0-VERSION.")
        return
    print(f"FAIL: {len(violations)} intake/version violation(s) — run refused, no LLM dispatch.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# --- self-test fixtures ---------------------------------------------------
def _valid_brand() -> Dict[str, Any]:
    return {
        "version": "brand", "first_name": "Jordan", "last_name": "Rivers",
        "ideal_avatar": "aspiring women founders in wellness",
        "niche": "holistic business coaching", "primary_goal": "launch a profitable practice",
        "tone_style_1": "Maya Angelou in Letter to My Daughter", "tone_style_2": "N/A",
        "tone": "inspirational, thought-provoking", "target_market": "US women 30-50",
        "tone_style_3": "N/A", "tone_style_4": "N/A",
        "offer_name": "The Rooted Practice Accelerator", "offer_type": "group coaching program",
        "offer_benefit": "a fully-booked practice in 90 days",
        "product_info": "12-week live cohort with templates and coaching",
        "brand_info": "Rooted Practice is a movement for purpose-led founders",
        "brand_start_date": "2021", "brand_why": "to end burnout culture in coaching",
        "brand_colors": "deep green, warm gold",
    }


def _valid_book() -> Dict[str, Any]:
    return {
        "version": "book", "first_name": "Jordan", "last_name": "Rivers",
        "ideal_avatar": "aspiring women founders in wellness",
        "niche": "holistic business coaching", "primary_goal": "launch a profitable practice",
        "tone_style_1": "Maya Angelou in Letter to My Daughter", "tone_style_2": "N/A",
        "book_stories": "The night I closed my first clinic and started over.",
    }


def _violation_cases():
    def unset(d): d["version"] = ""
    def bad_enum(d): d["version"] = "magazine"
    def brand_missing_tone(d): d.pop("tone", None)
    def brand_has_bookstories(d): d["book_stories"] = "a real childhood story for the book"
    def brand_missing_offer(d): d.pop("offer_name", None)
    def shared_boiler(d): d["ideal_avatar"] = "TODO"
    def book_missing_stories(d): d.pop("book_stories", None)
    def book_has_brand(d): d["offer_name"] = "The Rooted Practice Accelerator"
    return [
        ("version_unset", "AF-AV-VERSION-UNSET", lambda: (_valid_brand(), True, unset)),
        ("version_bad_enum", "AF-AV-VERSION-UNSET", lambda: (_valid_brand(), True, bad_enum)),
        ("brand_missing_tone_delta", "AF-AV-VERSION-MISMATCH", lambda: (_valid_brand(), True, brand_missing_tone)),
        ("brand_carries_book_stories", "AF-AV-VERSION-MISMATCH", lambda: (_valid_brand(), True, brand_has_bookstories)),
        ("brand_missing_offer_name", "AF-AV-INTAKE-INCOMPLETE", lambda: (_valid_brand(), True, brand_missing_offer)),
        ("shared_field_boilerplate", "AF-AV-INTAKE-INCOMPLETE", lambda: (_valid_brand(), True, shared_boiler)),
        ("book_missing_stories_delta", "AF-AV-VERSION-MISMATCH", lambda: (_valid_book(), True, book_missing_stories)),
        ("book_carries_brand_field", "AF-AV-VERSION-MISMATCH", lambda: (_valid_book(), True, book_has_brand)),
        ("book_no_route_parks", "AF-AV-BOOK-SKILL-MISSING", lambda: (_valid_book(), False, lambda d: None)),
    ]


def run_self_test() -> int:
    ok = True
    # valid brand passes
    v, _ = verify(_valid_brand(), True)
    if v:
        ok = False; print(f"SELF-TEST FAIL: valid BRAND intake -> {v}")
    else:
        print("SELF-TEST ok: valid BRAND intake PASSES.")
    # valid book with skill present routes (passes, note only)
    v, notes = verify(_valid_book(), True)
    if v:
        ok = False; print(f"SELF-TEST FAIL: valid BOOK (skill present) -> {v}")
    else:
        print(f"SELF-TEST ok: valid BOOK routes to skill 53 ({len(notes)} note).")
    # each violation fixture fails with its expected code
    for name, expected, build in _violation_cases():
        base, book_present, mut = build()
        mut(base)
        vio, _ = verify(base, book_present)
        codes = {c for c, _ in vio}
        if not vio:
            ok = False; print(f"SELF-TEST FAIL: '{name}' produced NO violation (expected {expected}).")
        elif expected not in codes:
            ok = False; print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Avatar-Alchemist intake + Book/Brand version gate.")
    ap.add_argument("--intake", help="path to intake.json ('-' reads stdin)")
    ap.add_argument("--book-skill-present", action="store_true",
                    help="declare that the Avatar Alchemist Book skill (53) is installed on this box")
    ap.add_argument("--self-test", action="store_true", help="run VALID + VIOLATION fixtures")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not args.intake:
        print("USAGE ERROR: pass --intake <intake.json> (or --self-test).")
        return 3
    try:
        intake = _load(args.intake)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load intake: {exc}")
        return 3
    violations, notes = verify(intake, args.book_skill_present)
    _report(violations, notes)
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
