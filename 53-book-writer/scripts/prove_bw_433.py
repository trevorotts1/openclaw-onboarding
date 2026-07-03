#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: 4x3x3 OFFER-BOOK GATE (fail-closed, mode=4x3x3)
# -----------------------------------------------------------------------------
#   AF-BK-433-COUNTS — not exactly 4 Transformational Outcomes AND 30 program titles.
#   AF-BK-433-MAP    — the 12 chapters do not map into 4 phases x 3 chapters, or
#                      433_Deck_Data.json is schema-invalid (the Skill 51 handoff).
#
# Deck-data schema (run/433/433_Deck_Data.json): an object with string ProductName,
# BrandName, ShortMDM; outcomes: list[4]; phases: list[4], each {title, chapters:
# list[3]} totalling 12 distinct chapters.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_433.py --titles <30-titles.md> --outcomes <outcomes.md>
#            --deck-data <433_Deck_Data.json> [--json] | --self-test
# =============================================================================
"""Fail-closed 4x3x3 offer-book gate (Skill 53)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_COUNTS = "AF-BK-433-COUNTS"
AF_MAP = "AF-BK-433-MAP"

_DECK_STRINGS = ("ProductName", "BrandName", "ShortMDM")


def evaluate(titles_text: str, outcomes_text: str, deck) -> c.Result:
    r = c.Result("prove_bw_433")

    # --- counts ---------------------------------------------------------------
    n_titles = c.count_list_items(titles_text)
    if n_titles != c.TITLES_433:
        r.fail(AF_COUNTS, "found %d program titles; 4x3x3 requires exactly %d"
               % (n_titles, c.TITLES_433))
    n_outcomes = c.count_list_items(outcomes_text)
    if n_outcomes != c.FOUR_OUTCOMES:
        r.fail(AF_COUNTS, "found %d Transformational Outcomes; 4x3x3 requires exactly %d"
               % (n_outcomes, c.FOUR_OUTCOMES))

    # --- deck-data schema + phase map ----------------------------------------
    if not isinstance(deck, dict):
        r.fail(AF_MAP, "433_Deck_Data.json is not a JSON object")
        return r
    for k in _DECK_STRINGS:
        if not (isinstance(deck.get(k), str) and deck.get(k).strip()):
            r.fail(AF_MAP, "433_Deck_Data.json missing/empty string field %r" % k)
    outcomes = deck.get("outcomes")
    if not (isinstance(outcomes, list) and len(outcomes) == c.FOUR_OUTCOMES):
        r.fail(AF_MAP, "433_Deck_Data.json 'outcomes' must be a list of exactly %d" % c.FOUR_OUTCOMES)
    phases = deck.get("phases")
    if not (isinstance(phases, list) and len(phases) == c.PHASES_433):
        r.fail(AF_MAP, "433_Deck_Data.json 'phases' must be a list of exactly %d" % c.PHASES_433)
    else:
        all_chapters = []
        for i, ph in enumerate(phases, 1):
            if not isinstance(ph, dict):
                r.fail(AF_MAP, "phase %d is not an object" % i); continue
            if not (isinstance(ph.get("title"), str) and ph.get("title").strip()):
                r.fail(AF_MAP, "phase %d missing 'title'" % i)
            chs = ph.get("chapters")
            if not (isinstance(chs, list) and len(chs) == c.CHAPTERS_PER_PHASE):
                r.fail(AF_MAP, "phase %d must list exactly %d chapters (got %r)"
                       % (i, c.CHAPTERS_PER_PHASE, chs))
            else:
                all_chapters += [str(x).strip() for x in chs]
        if len(all_chapters) == c.CHAPTER_COUNT and len(set(all_chapters)) != c.CHAPTER_COUNT:
            r.fail(AF_MAP, "the 4 phases x 3 chapters do not resolve to 12 DISTINCT chapters "
                   "(duplicate chapter across phases)")
        if all_chapters and len(all_chapters) != c.CHAPTER_COUNT:
            r.fail(AF_MAP, "the phase map covers %d chapters; must be exactly %d (4x3)"
                   % (len(all_chapters), c.CHAPTER_COUNT))
    if r.passed:
        r.note("30 titles, 4 outcomes, 4 phases x 3 chapters = 12; deck-data schema-valid")
    return r


def prove(titles_path, outcomes_path, deck_path, as_json=False) -> int:
    return evaluate(c.read_text(titles_path), c.read_text(outcomes_path),
                    c.read_json(deck_path)).emit(as_json)


def _good_deck():
    return {
        "ProductName": "The Quiet Authority System", "BrandName": "Marcus Halloway",
        "ShortMDM": "A 30-day method for first-time managers.",
        "outcomes": ["o1", "o2", "o3", "o4"],
        "phases": [
            {"title": "Unlearn the Star", "chapters": ["c1", "c2", "c3"]},
            {"title": "Lead Through Others", "chapters": ["c4", "c5", "c6"]},
            {"title": "Build the System", "chapters": ["c7", "c8", "c9"]},
            {"title": "Multiply Yourself", "chapters": ["c10", "c11", "c12"]},
        ],
    }


def self_test() -> int:
    titles = "\n".join("%d. Title %d" % (i, i) for i in range(1, 31))
    outcomes = "\n".join("%d. Outcome %d" % (i, i) for i in range(1, 5))
    checks = []
    checks.append(("30 titles + 4 outcomes + valid deck PASSES",
                   evaluate(titles, outcomes, _good_deck()).passed))
    # 29 titles
    t29 = "\n".join("%d. Title %d" % (i, i) for i in range(1, 30))
    checks.append(("29 titles AUTOFAILs AF-BK-433-COUNTS",
                   any(cd == AF_COUNTS for cd, _ in evaluate(t29, outcomes, _good_deck()).violations)))
    # 3 outcomes
    o3 = "\n".join("%d. Outcome %d" % (i, i) for i in range(1, 4))
    checks.append(("3 outcomes AUTOFAILs AF-BK-433-COUNTS",
                   any(cd == AF_COUNTS for cd, _ in evaluate(titles, o3, _good_deck()).violations)))
    # phase with 2 chapters
    bad = _good_deck(); bad["phases"][0]["chapters"] = ["c1", "c2"]
    checks.append(("phase with 2 chapters AUTOFAILs AF-BK-433-MAP",
                   any(cd == AF_MAP for cd, _ in evaluate(titles, outcomes, bad).violations)))
    # duplicate chapter across phases
    dup = _good_deck(); dup["phases"][3]["chapters"] = ["c1", "c11", "c12"]
    checks.append(("duplicate chapter across phases AUTOFAILs AF-BK-433-MAP",
                   any(cd == AF_MAP for cd, _ in evaluate(titles, outcomes, dup).violations)))
    return c.selftest_report("prove_bw_433", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer 4x3x3 offer-book gate (Skill 53).")
    ap.add_argument("--titles", help="30-titles .md")
    ap.add_argument("--outcomes", help="4 transformational outcomes .md")
    ap.add_argument("--deck-data", help="433_Deck_Data.json")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.titles and args.outcomes and args.deck_data):
        ap.error("--titles, --outcomes and --deck-data are required (or use --self-test)")
    return prove(args.titles, args.outcomes, args.deck_data, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
