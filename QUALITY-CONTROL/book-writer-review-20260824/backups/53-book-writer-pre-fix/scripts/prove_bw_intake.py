#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: INTAKE + BOOK/BRAND VERSION GATE (fail-closed)
# -----------------------------------------------------------------------------
# Gate 0. Proves the book intake is complete + the Book/Brand version selector is
# explicit and consistent BEFORE any LLM dispatch.
#
#   AF-BK-INTAKE-MISSING — a required field is missing/empty/boilerplate.
#   AF-BK-VERSION        — version unset / not in {book,brand}; the answered
#                          question set contradicts the version; version=brand is
#                          not handed off to Skill 52; or mode not in {full,4x3x3}.
#
# version=book is THIS skill's target and runs here. version=brand MUST hand off to
# Skill 52 (avatar-alchemist) — NEVER run the book pipeline for a brand request.
# The reciprocal flag --brand-skill-present is the mirror of Skill 52's
# --book-skill-present: present -> route/handoff PASS; absent -> park fail-closed.
# --handoff validates only the shared-answer core Skill 52 forwards (its
# intake-book.json shape), not the full-run fields the book intake later collects.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_intake.py <intake.json|-> [--handoff] [--brand-skill-present] [--json] | --self-test
# =============================================================================
"""Fail-closed Book Writer intake + Book/Brand version gate (Skill 53)."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_INTAKE = "AF-BK-INTAKE-MISSING"
AF_VERSION = "AF-BK-VERSION"

# The shared-answer core Skill 52 forwards on a version=book hand-off (mirrors
# 52/test-fixtures/intake-book.json) — always required, both versions.
CORE_REQUIRED = ["version", "first_name", "last_name", "ideal_avatar", "niche",
                 "primary_goal", "tone_style_1", "tone_style_2"]
# The full-run fields the book intake collects on top of the forwarded core.
RUN_REQUIRED = ["mode", "book_about", "cover_description", "book_stories"]
# Brand-only questions that must NOT carry real content on a book run.
BRAND_ONLY_CONTENT = ["tone", "target_market", "offer_name", "offer_type",
                      "offer_benefit", "product_info", "brand_info",
                      "brand_start_date", "brand_why", "brand_colors"]


def evaluate(intake, handoff: bool = False, brand_skill_present: bool = False) -> c.Result:
    r = c.Result("prove_bw_intake")
    if not isinstance(intake, dict):
        r.fail(AF_INTAKE, "intake is not a JSON object")
        return r

    # --- version enum (no default, no inference) --------------------------
    version = ("" if intake.get("version") is None else str(intake.get("version"))).strip().lower()
    if version not in c.VERSION_ENUM:
        r.fail(AF_VERSION, "version must be explicitly 'book' or 'brand' (got %r); "
               "no default, no inference from other answers" % intake.get("version"))

    # --- shared-answer core required (both versions) ----------------------
    for k in CORE_REQUIRED:
        if k == "version":
            continue
        if not c.is_present(intake.get(k)):
            r.fail(AF_INTAKE, "required shared field %r missing/empty/boilerplate" % k)

    if version == "brand":
        # NEVER run the book pipeline for a brand request — route or park.
        if brand_skill_present:
            r.note("ROUTE: version=brand -> hand off to Skill 52 (avatar-alchemist); "
                   "this skill performs ZERO generation for a brand run")
        else:
            r.fail(AF_VERSION, "version=brand with no resolvable Brand-skill (52) route — parks "
                   "fail-closed 'brand-skill-not-available' (NEVER served by the book pipeline)")

    elif version == "book":
        # book delta must be present (N/A allowed) even on a bare hand-off.
        if not c.is_present(intake.get("book_stories")):
            r.fail(AF_VERSION, "version=book requires the BOOK delta 'book_stories' "
                   "(present; 'N/A' allowed) — missing")
        # brand-only content on a book run signals version confusion.
        for k in BRAND_ONLY_CONTENT:
            v = intake.get(k)
            if c.is_present(v) and not c.is_na(v):
                r.fail(AF_VERSION, "version=book but brand-only field %r carries real content "
                       "(a brand question on a book run)" % k)
        # full-run fields (skipped for a bare Skill 52 hand-off validation).
        if not handoff:
            for k in RUN_REQUIRED:
                if k == "book_stories":
                    continue
                if not c.is_present(intake.get(k)):
                    r.fail(AF_INTAKE, "version=book run requires %r — missing/empty" % k)
            mode = ("" if intake.get("mode") is None else str(intake.get("mode"))).strip().lower()
            if c.is_present(intake.get("mode")) and mode not in c.MODE_ENUM:
                r.fail(AF_VERSION, "mode must be one of %s (got %r)" % (c.MODE_ENUM, intake.get("mode")))
    return r


# ---- IO / CLI ---------------------------------------------------------------
def _load(path):
    if path == "-":
        return json.loads(sys.stdin.read())
    return c.read_json(path)


def prove(path, handoff, brand_present, as_json=False) -> int:
    return evaluate(_load(path), handoff, brand_present).emit(as_json)


# ---- self-test (in-memory fixtures; no golden prose required) ---------------
def _valid_book_run():
    return {
        "version": "book", "mode": "full", "first_name": "Marcus", "last_name": "Halloway",
        "ideal_avatar": "newly-promoted first-time engineering managers",
        "niche": "leadership development for first-time technical managers",
        "primary_goal": "lead a high-trust team that ships without them being the bottleneck",
        "tone_style_1": "Simon Sinek in Leaders Eat Last", "tone_style_2": "N/A",
        "book_about": "how a first-time manager becomes the leader who multiplies others",
        "book_stories": "The night I rewrote a junior engineer's pull request at 2 a.m.",
        "cover_description": "a single unlit lamp with a warm glow beginning at its base",
    }


def _valid_handoff_core():
    # exactly the Skill 52 intake-book.json shape (no mode/book_about/cover_description)
    return {
        "version": "book", "first_name": "Jordan", "last_name": "Rivers",
        "ideal_avatar": "aspiring women founders in the wellness space",
        "niche": "holistic business coaching",
        "primary_goal": "launch a profitable, purpose-led practice",
        "tone_style_1": "Maya Angelou in Letter to My Daughter", "tone_style_2": "N/A",
        "book_stories": "The night I closed my first clinic and decided to start over.",
    }


def _valid_brand():
    d = _valid_book_run()
    d["version"] = "brand"
    d.pop("book_about", None)
    d["book_stories"] = "N/A"
    d["tone"] = "inspirational, thought-provoking"
    return d


def self_test() -> int:
    checks = []
    checks.append(("valid BOOK run PASSES", evaluate(_valid_book_run()).passed))
    checks.append(("Skill 52 hand-off core PASSES under --handoff",
                   evaluate(_valid_handoff_core(), handoff=True).passed))
    checks.append(("Skill 52 hand-off core FAILS as a full run (mode/book_about/cover missing)",
                   not evaluate(_valid_handoff_core(), handoff=False).passed))
    checks.append(("valid BRAND routes with --brand-skill-present",
                   evaluate(_valid_brand(), brand_skill_present=True).passed))

    def has(res, code):
        return any(cd == code for cd, _ in res.violations)

    d = _valid_book_run(); d["version"] = ""
    checks.append(("version unset AUTOFAILs AF-BK-VERSION", has(evaluate(d), AF_VERSION)))
    d = _valid_book_run(); d["version"] = "magazine"
    checks.append(("bad version enum AUTOFAILs AF-BK-VERSION", has(evaluate(d), AF_VERSION)))
    d = _valid_book_run(); d.pop("ideal_avatar", None)
    checks.append(("missing shared field AUTOFAILs AF-BK-INTAKE-MISSING", has(evaluate(d), AF_INTAKE)))
    d = _valid_book_run(); d.pop("book_stories", None)
    checks.append(("book missing stories AUTOFAILs AF-BK-VERSION", has(evaluate(d), AF_VERSION)))
    d = _valid_book_run(); d.pop("book_about", None)
    checks.append(("book run missing book_about AUTOFAILs AF-BK-INTAKE-MISSING", has(evaluate(d), AF_INTAKE)))
    d = _valid_book_run(); d["offer_name"] = "The Rooted Practice Accelerator"
    checks.append(("book carrying a brand field AUTOFAILs AF-BK-VERSION", has(evaluate(d), AF_VERSION)))
    checks.append(("BRAND without route parks AF-BK-VERSION",
                   has(evaluate(_valid_brand(), brand_skill_present=False), AF_VERSION)))
    d = _valid_book_run(); d["mode"] = "anthology"
    checks.append(("mode=anthology (not a mode here) AUTOFAILs AF-BK-VERSION", has(evaluate(d), AF_VERSION)))
    return c.selftest_report("prove_bw_intake", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer intake + version gate (Skill 53).")
    ap.add_argument("path", nargs="?", help="intake.json to prove ('-' reads stdin)")
    ap.add_argument("--handoff", action="store_true",
                    help="validate only the shared-answer core Skill 52 forwards (not full-run fields)")
    ap.add_argument("--brand-skill-present", dest="brand_present", action="store_true",
                    help="declare Skill 52 (avatar-alchemist) is installed to route version=brand to")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, args.handoff, args.brand_present, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
