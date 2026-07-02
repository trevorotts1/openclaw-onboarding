#!/usr/bin/env python3
# =============================================================================
# SKILL 55 — PRODUCT BIO :: STRUCTURE / CLOSES / COUNTS GATE (fail-closed)
# -----------------------------------------------------------------------------
# Enforces the SACRED shape of the bio against the STRIPPED text + header lines
# (never prose), so a keyword in a paragraph can't spoof a section.
#
#   AF-PB-SECTION — any of the 10 mandatory sections absent OR out of order
#                   (P1 §2.2: product name / power adjectives / who it's best
#                   for / description / positioning / objections / FAQs / social
#                   proof / StoryBrand 2.0 / signature closes).
#   AF-PB-CLOSES  — signature-close styles != 24 distinct names (the tracker's
#                   named 24, P1 lines 900-928/947; PRD O3 enforces 24 even
#                   though the prompt teaches 20).
#   AF-PB-COUNTS  — a per-section floor is missed: 10 intros, 15-20 adjectives,
#                   8-10 objections, 10-12 FAQs, 8-10 social-proof statements,
#                   or a StoryBrand beat is missing (all 7 required).
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_pb_sections.py <product-bio.md> [--json] | --self-test
# =============================================================================
"""Fail-closed structure / closes / counts gate for the Product Bio engine."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pb_common as c  # noqa: E402

AF_SECTION = "AF-PB-SECTION"
AF_CLOSES = "AF-PB-CLOSES"
AF_COUNTS = "AF-PB-COUNTS"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def _check_sections(text, r):
    found = c.find_sections(text)
    order = [sid for sid, _t, _p in c.SECTIONS]
    missing = [sid for sid in order if sid not in found]
    if missing:
        r.fail(AF_SECTION, "missing section(s): %s" % ", ".join(missing))
        return
    positions = [found[sid][0] for sid in order]
    if positions != sorted(positions):
        seq = [sid for sid, _ in sorted(((sid, found[sid][0]) for sid in order),
                                        key=lambda x: x[1])]
        r.fail(AF_SECTION, "sections out of order; by-position order was: %s" % ", ".join(seq))
    else:
        r.note("all 10 sections present and in order")


def _check_closes(text, r):
    present = c.closes_found(text)
    if len(present) != c.CLOSES_REQUIRED:
        missing = [n for n in c.CLOSE_STYLES if n not in present]
        r.fail(AF_CLOSES, "found %d distinct signature-close styles, require %d%s"
               % (len(present), c.CLOSES_REQUIRED,
                  (" (missing: %s)" % ", ".join(missing)) if missing else ""))
    else:
        r.note("all 24 signature-close styles present")


def _check_counts(text, r):
    for sid, (mn, mx) in c.COUNT_BANDS.items():
        n = c.count_numbered_items(c.section_body_lines(text, sid))
        if n < mn or (mx is not None and n > mx):
            band = "%d+" % mn if mx is None else "%d-%d" % (mn, mx)
            r.fail(AF_COUNTS, "%s has %d enumerated items, require %s" % (sid, n, band))
    beats = c.storybrand_beats_found(text)
    missing_beats = [b for b in c.STORYBRAND_BEATS if b not in beats]
    if missing_beats:
        r.fail(AF_COUNTS, "StoryBrand beats missing: %s" % ", ".join(missing_beats))
    if not any(code == AF_COUNTS for code, _ in r.violations):
        r.note("per-section count floors met + all 7 StoryBrand beats present")


def evaluate(text: str) -> c.Result:
    r = c.Result("prove_pb_sections")
    _check_sections(text, r)
    _check_closes(text, r)
    _check_counts(text, r)
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_text(path)).emit(as_json)


def self_test() -> int:
    checks = []
    golden = c.read_text(_FIX / "golden" / "product-bio.md")
    checks.append(("golden bio PASS (10 sections / 24 closes / counts)", evaluate(golden).passed))

    sec = evaluate(c.read_text(_FIX / "attack" / "section_missing.md"))
    checks.append(("dropped-section bio AUTOFAILs AF-PB-SECTION",
                   any(code == AF_SECTION for code, _ in sec.violations)))

    clo = evaluate(c.read_text(_FIX / "attack" / "closes_23.md"))
    checks.append(("23-closes bio AUTOFAILs AF-PB-CLOSES",
                   any(code == AF_CLOSES for code, _ in clo.violations)))

    cnt = evaluate(c.read_text(_FIX / "attack" / "counts_short.md"))
    checks.append(("under-count bio AUTOFAILs AF-PB-COUNTS",
                   any(code == AF_COUNTS for code, _ in cnt.violations)))
    return c.selftest_report("prove_pb_sections", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio structure/closes/counts gate (Skill 55).")
    ap.add_argument("path", nargs="?", help="product-bio.md to prove")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
