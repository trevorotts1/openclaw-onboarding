#!/usr/bin/env python3
# =============================================================================
# SKILL 55 — PRODUCT BIO :: WORD-COUNT + VERIFY-BLOCK GATE (fail-closed)
# -----------------------------------------------------------------------------
# The source prompt fights truncation with prose and a SELF-REPORTED word count
# (P1 line 955). This gate replaces that prose with measurement: we count the
# STRIPPED words of the bio and IGNORE the model's reported number entirely.
# Because whitespace collapses before counting, a whitespace-padding attack
# (pad a short bio to book length) cannot fool the floor.
#
#   AF-PB-WORDCOUNT    — measured stripped word count outside 6,000-7,000
#                        (P1 lines 952-953). Self-reported counts are ignored.
#   AF-PB-VERIFY-BLOCK — the mandatory COMPLETION VERIFICATION block is absent
#                        (P1 line 992 contract).
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_pb_wordcount.py <product-bio.md> [--json] | --self-test
# =============================================================================
"""Fail-closed word-count + completion-verification gate (Skill 55)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pb_common as c  # noqa: E402

AF_WORDCOUNT = "AF-PB-WORDCOUNT"
AF_VERIFY_BLOCK = "AF-PB-VERIFY-BLOCK"
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def evaluate(text: str) -> c.Result:
    r = c.Result("prove_pb_wordcount")
    words = c.word_count(text)
    if words < c.WORDCOUNT_MIN or words > c.WORDCOUNT_MAX:
        r.fail(AF_WORDCOUNT, "measured stripped word count %d outside %d-%d "
               "(self-reported counts are ignored)" % (words, c.WORDCOUNT_MIN, c.WORDCOUNT_MAX))
    else:
        r.note("measured stripped word count %d within %d-%d"
               % (words, c.WORDCOUNT_MIN, c.WORDCOUNT_MAX))
    if c.VERIFY_BLOCK_MARKER not in text:
        r.fail(AF_VERIFY_BLOCK, "mandatory %r block absent" % c.VERIFY_BLOCK_MARKER)
    else:
        r.note("%r block present" % c.VERIFY_BLOCK_MARKER)
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_text(path)).emit(as_json)


def self_test() -> int:
    checks = []
    golden = c.read_text(_FIX / "golden" / "product-bio.md")
    checks.append(("golden bio PASS (in-band + verify block)", evaluate(golden).passed))

    short = evaluate(c.read_text(_FIX / "attack" / "wordcount_short.md"))
    checks.append(("short bio AUTOFAILs AF-PB-WORDCOUNT",
                   any(code == AF_WORDCOUNT for code, _ in short.violations)))

    pad = evaluate(c.read_text(_FIX / "attack" / "wordcount_whitespace_pad.md"))
    checks.append(("whitespace-padded short bio STILL AUTOFAILs AF-PB-WORDCOUNT",
                   any(code == AF_WORDCOUNT for code, _ in pad.violations)))

    nover = evaluate(c.read_text(_FIX / "attack" / "verify_block_missing.md"))
    checks.append(("bio without completion block AUTOFAILs AF-PB-VERIFY-BLOCK",
                   any(code == AF_VERIFY_BLOCK for code, _ in nover.violations)))
    return c.selftest_report("prove_pb_wordcount", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio word-count gate (Skill 55).")
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
