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
#   AF-PB-OVERRIDE-UNLOGGED — a --band-override was APPLIED but is not logged in
#                        the locked brief (--intake word_count_override); the SACRED
#                        default band is not relaxed by an unlogged value.
#
# CLIENT-EXACT OVERRIDES WIN: the 6,000-7,000 band is the DEFAULT floor. A client's
# exact word target (e.g. an exact 5,500- or 8,000-word bio) is honored VERBATIM
# when it is LOGGED in the locked brief as `word_count_override` (a band / exact /
# {min,max}); it is never floored, capped, or substituted. --intake reads that
# logged channel; --band-override is the applied value the orchestrator threads in
# and MUST equal the logged one (else AF-PB-OVERRIDE-UNLOGGED, fail-closed).
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_pb_wordcount.py <product-bio.md> [--intake I.json]
#        [--band-override LO-HI|N] [--json] | --self-test
# =============================================================================
"""Fail-closed word-count + completion-verification gate (Skill 55)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pb_common as c  # noqa: E402

AF_WORDCOUNT = "AF-PB-WORDCOUNT"
AF_VERIFY_BLOCK = "AF-PB-VERIFY-BLOCK"
AF_OVERRIDE_UNLOGGED = c.AF_OVERRIDE_UNLOGGED
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def _parse_override_arg(raw):
    """Parse a --band-override CLI string into a spec: 'LO-HI' -> [lo, hi], 'N' ->
    {'exact': n}. Returns None on an unparseable value (treated as no override)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "-" in s:
        lo, _, hi = s.partition("-")
        try:
            return [int(lo.strip()), int(hi.strip())]
        except ValueError:
            return None
    try:
        return {"exact": int(s)}
    except ValueError:
        return None


def evaluate(text: str, logged_override=None, applied_override=None) -> c.Result:
    r = c.Result("prove_pb_wordcount")
    lo, hi, overridden, unlogged = c.resolve_band(
        c.WORDCOUNT_MIN, c.WORDCOUNT_MAX, logged_override, applied_override)
    if unlogged:
        r.fail(AF_OVERRIDE_UNLOGGED,
               "a word-band override was applied but is not logged in the locked "
               "brief (%s); measuring against the SACRED default band %d-%d"
               % (c.WORD_OVERRIDE_KEY, c.WORDCOUNT_MIN, c.WORDCOUNT_MAX))
    band = ("client-exact override %d-%d (logged; never floored/capped)" % (lo, hi)
            if overridden else "default band %d-%d" % (lo, hi))
    words = c.word_count(text)
    if words < lo or words > hi:
        r.fail(AF_WORDCOUNT, "measured stripped word count %d outside %s "
               "(self-reported counts are ignored)" % (words, band))
    else:
        r.note("measured stripped word count %d within %s" % (words, band))
    if c.VERIFY_BLOCK_MARKER not in text:
        r.fail(AF_VERIFY_BLOCK, "mandatory %r block absent" % c.VERIFY_BLOCK_MARKER)
    else:
        r.note("%r block present" % c.VERIFY_BLOCK_MARKER)
    return r


def prove(path, intake_path=None, applied_override=None, as_json=False) -> int:
    intake = c.load_intake(intake_path)
    logged = intake.get(c.WORD_OVERRIDE_KEY) if isinstance(intake, dict) else None
    return evaluate(c.read_text(path), logged_override=logged,
                    applied_override=applied_override).emit(as_json)


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

    # --- client-exact override channel (mirror Skill 57) ---------------------
    # A 5,500-word bio is BELOW the default 6,000-7,000 band...
    short_bio = ("word " * 5500) + "\n\n## COMPLETION VERIFICATION\nall sections present\n"
    default_res = evaluate(short_bio)
    checks.append(("5,500-word bio AUTOFAILs the DEFAULT band (AF-PB-WORDCOUNT)",
                   any(code == AF_WORDCOUNT for code, _ in default_res.violations)))
    # ...but PASSES when the client's exact target is LOGGED in the locked brief.
    logged_res = evaluate(short_bio, logged_override=[5000, 6000])
    checks.append(("...PASSES with a LOGGED client-exact override [5000,6000] "
                   "(never floored)", logged_res.passed))
    # An override APPLIED but NOT logged is fail-closed.
    unlogged_res = evaluate(short_bio, applied_override=[5000, 6000])
    checks.append(("applied-but-UNLOGGED override AUTOFAILs AF-PB-OVERRIDE-UNLOGGED",
                   any(code == AF_OVERRIDE_UNLOGGED for code, _ in unlogged_res.violations)))
    # An applied override that MATCHES the logged one is honored (no unlogged fail).
    match_res = evaluate(short_bio, logged_override=[5000, 6000], applied_override=[5000, 6000])
    checks.append(("applied override that MATCHES the logged brief PASSES",
                   match_res.passed))
    # An exact-N logged target ({"exact": 8000}) honors 8,000 verbatim (the marker
    # line contributes 5 stripped words, so the body is 7,995 -> 8,000 measured).
    long_bio = ("word " * 7995) + "\n\n## COMPLETION VERIFICATION\nall sections present\n"
    exact_res = evaluate(long_bio, logged_override={"exact": 8000})
    checks.append(("8,000-word bio PASSES with a LOGGED exact target {exact:8000}",
                   exact_res.passed))
    return c.selftest_report("prove_pb_wordcount", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio word-count gate (Skill 55).")
    ap.add_argument("path", nargs="?", help="product-bio.md to prove")
    ap.add_argument("--intake", help="locked brief (working/intake.json) — the LOGGED "
                    "override channel; a logged word_count_override wins over the default band")
    ap.add_argument("--band-override", dest="band_override",
                    help="applied word-band override (LO-HI or N); honored only when it "
                    "equals the locked brief's word_count_override, else AF-PB-OVERRIDE-UNLOGGED")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, intake_path=args.intake,
                 applied_override=_parse_override_arg(args.band_override), as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
