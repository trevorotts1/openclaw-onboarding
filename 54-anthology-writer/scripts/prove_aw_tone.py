#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: TONE-DOC GATE  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# Enforces the shared tone-writing-core contract (08-blended-tone) as it applies
# to an anthology contributor's blended tone document ("The {First} {Last}
# Tone"): it is synthesized from EXACTLY FOUR tone-style influence analyses, and
# it clears the shared stripped-word floor (tone-core R7 / writing-rails R7).
#
#   AF-AW-TONE-4     — the blended tone doc does not reference exactly 4 distinct
#                      influence analyses (indices 1..4). Fewer means a thinned
#                      tone; a self-report of "4 influences" is never trusted.
#   AF-AW-TONE-FLOOR — measured stripped word count below the 3,000 floor
#                      (whitespace padding is inert; the count is measured).
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_aw_tone.py <tone-doc.md> [--json] | prove_aw_tone.py --self-test
# =============================================================================
"""Fail-closed blended-tone gate for the Anthology Writer (Skill 54)."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_TONE_4 = "AF-AW-TONE-4"
AF_TONE_FLOOR = "AF-AW-TONE-FLOOR"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"

# An influence-analysis header carries an explicit index 1..4, e.g.
# "## Influence 1 — ...", "**Tone Style 2:**", "Influence #3". We collect the
# distinct indices from HEADER lines only (prose mentioning "influence" is not
# counted), and require the full set {1,2,3,4}.
_INFLUENCE_RE = re.compile(r"(?:influence|tone[\s-]?style)\s*#?\s*([1-4])\b", re.I)


def _influence_indices(text: str) -> set:
    idx = set()
    for _i, htext in c.header_lines(text):
        m = _INFLUENCE_RE.search(htext)
        if m:
            idx.add(int(m.group(1)))
    return idx


def evaluate(text: str) -> c.Result:
    r = c.Result("prove_aw_tone")
    idx = _influence_indices(text)
    if idx != {1, 2, 3, 4}:
        r.fail(AF_TONE_4, "blended tone references influence analyses %s, require exactly "
               "{1,2,3,4} (4 distinct tone-style influences)"
               % (sorted(idx) if idx else "none"))
    else:
        r.note("all 4 tone-style influence analyses present (indices 1-4)")

    words = c.word_count(text)
    if words < c.TONE_WORD_FLOOR:
        r.fail(AF_TONE_FLOOR, "measured stripped word count %d below the %d floor "
               "(self-reported counts are ignored; padding is inert)"
               % (words, c.TONE_WORD_FLOOR))
    else:
        r.note("measured stripped word count %d meets the %d floor" % (words, c.TONE_WORD_FLOOR))
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_text(path)).emit(as_json)


def self_test() -> int:
    checks = []
    golden = c.read_text(_FIX / "golden" / "tone-doc.md")
    checks.append(("golden tone doc PASS (4 influences + floor)", evaluate(golden).passed))

    thin = evaluate(c.read_text(_FIX / "attack" / "tone_three_influences.md"))
    checks.append(("3-influence tone doc AUTOFAILs AF-AW-TONE-4",
                   any(code == AF_TONE_4 for code, _ in thin.violations)))

    short = evaluate(c.read_text(_FIX / "attack" / "tone_short.md"))
    checks.append(("short tone doc AUTOFAILs AF-AW-TONE-FLOOR",
                   any(code == AF_TONE_FLOOR for code, _ in short.violations)))
    return c.selftest_report("prove_aw_tone", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Anthology Writer blended-tone gate (Skill 54).")
    ap.add_argument("path", nargs="?", help="tone-doc.md to prove")
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
