#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: BLENDED-TONE LENGTH GATE (fail-closed)
# -----------------------------------------------------------------------------
# The blended "The {First} {Last} Tone" signature-voice spec must be a real,
# substantial document — >= 3000 STRIPPED words (per shared-utils/tone-writing-core).
# Measured on stripped text, so whitespace padding cannot fake it.
#
#   AF-BK-TONE-LEN — the blended tone document is below the 3000 stripped-word floor.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_tone.py <08-blended-tone.md> [--json] | --self-test
# =============================================================================
"""Fail-closed blended-tone length gate (Skill 53)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_TONE_LEN = "AF-BK-TONE-LEN"


def evaluate(text: str) -> c.Result:
    r = c.Result("prove_bw_tone")
    words = c.word_count(text)
    if words < c.TONE_WORD_FLOOR:
        r.fail(AF_TONE_LEN, "blended tone measured %d stripped words, below the %d floor "
               "(self-reported counts ignored)" % (words, c.TONE_WORD_FLOOR))
    else:
        r.note("blended tone measured %d stripped words (>= %d)" % (words, c.TONE_WORD_FLOOR))
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_text(path)).emit(as_json)


def self_test() -> int:
    checks = []
    long_tone = "# The Marcus Halloway Tone\n" + ("voice " * 3200)
    checks.append(("3200-word tone PASSES", evaluate(long_tone).passed))
    short_tone = "# The Marcus Halloway Tone\n" + ("voice " * 1200)
    checks.append(("1200-word tone AUTOFAILs AF-BK-TONE-LEN",
                   any(cd == AF_TONE_LEN for cd, _ in evaluate(short_tone).violations)))
    padded = "# Tone\n" + ("voice " * 1200) + ("\n" * 40000)
    checks.append(("whitespace-padded short tone STILL AUTOFAILs AF-BK-TONE-LEN",
                   any(cd == AF_TONE_LEN for cd, _ in evaluate(padded).violations)))
    return c.selftest_report("prove_bw_tone", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer blended-tone length gate (Skill 53).")
    ap.add_argument("path", nargs="?", help="08-blended-tone.md")
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
