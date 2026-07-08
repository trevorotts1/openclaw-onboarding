#!/usr/bin/env python3
# =============================================================================
# SKILL 55 — PRODUCT BIO :: SOCIAL-PROOF AUTHENTICITY GATE (fail-closed) — SK2-17
# -----------------------------------------------------------------------------
# The source IP's Social Proof section generates "illustrative example statements"
# (formerly framed as "unattributed testimonial-style statements"). Presenting
# FABRICATED statements as REAL testimonials is a compliance hazard. This gate is
# DETERMINISTIC, NO-AI, FAIL-CLOSED over the GENERATED product bio:
#
#   AF-PB-TESTIMONIAL-UNSOURCED — the bio has a Social Proof section but the
#       statements are NEITHER (a) marked with a visible ILLUSTRATIVE disclaimer
#       (clearly illustrative example copy, not real testimonials) NOR (b) backed
#       by a sourced-testimonials manifest (real, attributed, consented quotes).
#
# A bio with no Social Proof section, or one whose section is empty, passes (there
# is nothing to authenticate). The gate NEVER inspects prose meaning — it looks for
# an explicit disclaimer marker or a structured sourced manifest, so it cannot be
# spoofed by a keyword and cannot pass fabricated testimonials silently.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE:
#   prove_pb_authenticity.py <product-bio.md> [--sourced FILE] [--json]
#   prove_pb_authenticity.py --self-test
# The optional sourced manifest is a JSON list of objects each carrying a
# non-empty `quote`, an `attribution` (real person/company), and a `source` or
# `consent` field (evidence the quote is real and cleared to publish).
# =============================================================================
"""Fail-closed social-proof authenticity gate for the Product Bio engine (Skill 55)."""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pb_common as c  # noqa: E402

AF_TESTIMONIAL_UNSOURCED = "AF-PB-TESTIMONIAL-UNSOURCED"

# An explicit, visible illustrative disclaimer — the statements are example copy,
# NOT real testimonials. Matched against the section body AND the whole document.
_DISCLAIMER_RE = re.compile(
    r"illustrative"
    r"|for\s+illustration"
    r"|not\s+(?:a\s+|real\s+)*(?:real\s+)?testimonial"
    r"|example\s+(?:statements?|copy|testimonials?)"
    r"|sample\s+testimonials?"
    r"|hypothetical"
    r"|representative\s+example",
    re.I,
)


def _valid_sourced(sourced) -> bool:
    """True when the sourced-testimonials manifest is a non-empty list where every
    entry carries a real quote, an attribution, and a source OR consent field."""
    if not isinstance(sourced, list) or not sourced:
        return False
    for item in sourced:
        if not isinstance(item, dict):
            return False
        if not str(item.get("quote", "")).strip():
            return False
        if not str(item.get("attribution", "")).strip():
            return False
        if not (str(item.get("source", "")).strip() or str(item.get("consent", "")).strip()):
            return False
    return True


def evaluate(text: str, sourced=None) -> c.Result:
    r = c.Result("prove_pb_authenticity")
    found = c.find_sections(text)
    if "social_proof" not in found:
        r.note("no social-proof section present; nothing to authenticate")
        return r
    body = "\n".join(c.section_body_lines(text, "social_proof"))
    if not body.strip():
        r.note("social-proof section is empty; nothing to authenticate")
        return r
    if _valid_sourced(sourced):
        r.note("social proof backed by a sourced-testimonials manifest "
               "(real/attributed/consented) — authentic")
        return r
    # The disclaimer must be IN the social-proof section (its heading or body), not
    # anywhere in the doc, so a stray 'illustrative' elsewhere cannot spoof the gate.
    scope = found["social_proof"][1] + "\n" + body
    if _DISCLAIMER_RE.search(scope):
        r.note("social-proof statements carry a visible ILLUSTRATIVE disclaimer "
               "(illustrative example copy, not real testimonials)")
        return r
    r.fail(AF_TESTIMONIAL_UNSOURCED,
           "the Social Proof section presents testimonial-style statements with NEITHER a "
           "visible ILLUSTRATIVE disclaimer NOR a sourced-testimonials manifest — fabricated "
           "statements may not be presented as real testimonials (SK2-17); fail-closed")
    return r


def prove(path, sourced_path=None, as_json=False) -> int:
    sourced = None
    if sourced_path:
        try:
            sourced = json.loads(Path(sourced_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sourced = None  # unreadable/absent manifest => fail-closed (no sourcing)
    return evaluate(c.read_text(path), sourced=sourced).emit(as_json)


def self_test() -> int:
    checks = []

    def has(res, code):
        return any(cd == code for cd, _ in res.violations)

    # A PLAIN heading (no disclaimer word) for the negative cases, and the real
    # prompt's ILLUSTRATIVE-labeled heading for the heading-disclaimer case.
    hdr_plain = "### **8. Social Proof Section (What Industry Leaders Are Saying)**\n"
    hdr_illus = "### **8. Social Proof Section (Illustrative Market-Voice Examples)**\n"
    stmts = ("* Teams say it cut their busywork in half.\n"
             "* Leaders report faster, calmer launches.\n")
    # 1) social proof WITHOUT a disclaimer and WITHOUT sourcing -> FAIL
    checks.append(("social proof, no disclaimer, no sourcing -> AUTOFAIL",
                   has(evaluate("# Bio\n" + hdr_plain + stmts), AF_TESTIMONIAL_UNSOURCED)))
    # 2) social proof WITH an illustrative disclaimer in the body -> PASS
    good_disc = "# Bio\n" + hdr_plain + "> ILLUSTRATIVE — not real testimonials.\n" + stmts
    checks.append(("social proof + illustrative disclaimer (body) -> PASS", evaluate(good_disc).passed))
    # 2b) illustrative disclaimer in the section HEADING (the real prompt's shape) -> PASS
    checks.append(("social proof + illustrative disclaimer (heading) -> PASS",
                   evaluate("# Bio\n" + hdr_illus + stmts).passed))
    # 3) social proof WITH a valid sourced manifest -> PASS (real testimonials)
    sourced = [{"quote": "Cut our launch time in half.", "attribution": "Jane Doe, Acme",
                "source": "https://example.test/case-study", "consent": "on file"}]
    checks.append(("social proof + sourced manifest -> PASS",
                   evaluate("# Bio\n" + hdr_plain + stmts, sourced=sourced).passed))
    # 4) sourced manifest MISSING required fields -> still FAIL (no disclaimer)
    bad_src = [{"quote": "Great!", "attribution": ""}]
    checks.append(("incomplete sourced manifest (no attribution/consent) -> AUTOFAIL",
                   has(evaluate("# Bio\n" + hdr_plain + stmts, sourced=bad_src),
                       AF_TESTIMONIAL_UNSOURCED)))
    # 5) NO social-proof section -> PASS (nothing to authenticate)
    checks.append(("no social-proof section -> PASS",
                   evaluate("# Bio\n## Description\nGreat product.\n").passed))
    # 6) a stray 'illustrative' OUTSIDE the section must NOT spoof the gate -> FAIL
    checks.append(("stray 'illustrative' outside the section does not spoof -> AUTOFAIL",
                   has(evaluate("# Bio\n## Description\nSee the illustrative diagram.\n"
                                + hdr_plain + stmts), AF_TESTIMONIAL_UNSOURCED)))
    return c.selftest_report("prove_pb_authenticity", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio social-proof authenticity gate (Skill 55).")
    ap.add_argument("path", nargs="?", help="product-bio.md to authenticate")
    ap.add_argument("--sourced", help="path to a sourced-testimonials manifest (JSON list)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a product-bio path is required (or use --self-test)")
    return prove(args.path, sourced_path=args.sourced, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
