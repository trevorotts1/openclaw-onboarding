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
#   AF-PB-OVERRIDE-UNLOGGED — a per-section count override was APPLIED but is not
#                   logged in the locked brief (--intake section_count_overrides).
#
# CLIENT-EXACT OVERRIDES WIN (quantity bands only): the per-section COUNT_BANDS are
# DEFAULT floors; a client's exact per-section target is honored VERBATIM when it is
# LOGGED in the locked brief as `section_count_overrides` ({section_id: band}). The
# SACRED STRUCTURE is NEVER overridable — the 10 sections, their order, the 24 named
# signature closes, and the 7 StoryBrand beats have NO override channel.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_pb_sections.py <product-bio.md> [--intake I.json]
#        [--section-override SID=LO-HI ...] [--json] | --self-test
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
AF_OVERRIDE_UNLOGGED = c.AF_OVERRIDE_UNLOGGED
_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def _resolve_count_band(sid, logged_map, applied_map):
    """Resolve the (lo, hi, overridden, unlogged) enumerated-item band for one
    section, honoring a LOGGED client-exact override tied to the locked brief. A
    None default max (an open-ended floor) is preserved unless an override sets it."""
    d_lo, d_hi = c.COUNT_BANDS[sid]
    logged = logged_map.get(sid) if isinstance(logged_map, dict) else None
    applied = applied_map.get(sid) if isinstance(applied_map, dict) else None
    hi_default = d_hi if d_hi is not None else 10 ** 9
    lo, hi, overridden, unlogged = c.resolve_band(d_lo, hi_default, logged, applied)
    eff_hi = None if (d_hi is None and not overridden) else hi
    return lo, eff_hi, overridden, unlogged


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


def _check_counts(text, r, sec_logged=None, sec_applied=None):
    for sid in c.COUNT_BANDS:
        mn, mx, overridden, unlogged = _resolve_count_band(sid, sec_logged, sec_applied)
        if unlogged:
            r.fail(AF_OVERRIDE_UNLOGGED, "%s count override applied but not logged in "
                   "the locked brief (%s); using the SACRED default floor"
                   % (sid, c.SECTION_OVERRIDE_KEY))
        n = c.count_numbered_items(c.section_body_lines(text, sid))
        if n < mn or (mx is not None and n > mx):
            band = "%d+" % mn if mx is None else "%d-%d" % (mn, mx)
            tag = " (client-exact override, logged)" if overridden else ""
            r.fail(AF_COUNTS, "%s has %d enumerated items, require %s%s" % (sid, n, band, tag))
    beats = c.storybrand_beats_found(text)
    missing_beats = [b for b in c.STORYBRAND_BEATS if b not in beats]
    if missing_beats:
        r.fail(AF_COUNTS, "StoryBrand beats missing: %s" % ", ".join(missing_beats))
    if not any(code in (AF_COUNTS, AF_OVERRIDE_UNLOGGED) for code, _ in r.violations):
        r.note("per-section count floors met + all 7 StoryBrand beats present")


def evaluate(text: str, sec_logged=None, sec_applied=None) -> c.Result:
    r = c.Result("prove_pb_sections")
    _check_sections(text, r)
    _check_closes(text, r)
    _check_counts(text, r, sec_logged=sec_logged, sec_applied=sec_applied)
    return r


def prove(path, intake_path=None, sec_applied=None, as_json=False) -> int:
    intake = c.load_intake(intake_path)
    sec_logged = intake.get(c.SECTION_OVERRIDE_KEY) if isinstance(intake, dict) else None
    return evaluate(c.read_text(path), sec_logged=sec_logged,
                    sec_applied=sec_applied).emit(as_json)


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

    # --- per-section count override channel (quantity bands only) ------------
    under = c.read_text(_FIX / "attack" / "counts_short.md")
    # The under-count fixture is short on an enumerated section; a LOGGED override
    # that lowers THAT section's floor to the delivered count clears AF-PB-COUNTS...
    n_adj = c.count_numbered_items(c.section_body_lines(under, "power_adjectives"))
    logged = evaluate(under, sec_logged={"power_adjectives": [n_adj, n_adj]})
    checks.append(("logged per-section override lowers ONLY that band (adjectives)",
                   not any(m.startswith("power_adjectives")
                           for code, m in logged.violations if code == AF_COUNTS)))
    # ...but an APPLIED-but-UNLOGGED per-section override is fail-closed.
    unlogged = evaluate(under, sec_applied={"power_adjectives": [n_adj, n_adj]})
    checks.append(("applied-but-UNLOGGED section override AUTOFAILs AF-PB-OVERRIDE-UNLOGGED",
                   any(code == AF_OVERRIDE_UNLOGGED for code, _ in unlogged.violations)))
    # The SACRED 24 closes are NEVER overridable — a closes override changes nothing.
    clo2 = evaluate(c.read_text(_FIX / "attack" / "closes_23.md"),
                    sec_logged={"signature_closes": [23, 23]})
    checks.append(("SACRED 24-closes floor ignores any override (still AF-PB-CLOSES)",
                   any(code == AF_CLOSES for code, _ in clo2.violations)))
    return c.selftest_report("prove_pb_sections", checks)


def _parse_section_overrides(pairs):
    """Parse ['sid=LO-HI', ...] applied overrides into {sid: [lo, hi]}."""
    out = {}
    for pair in pairs or []:
        sid, _, spec = str(pair).partition("=")
        sid = sid.strip()
        lo, _, hi = spec.partition("-")
        try:
            out[sid] = [int(lo.strip()), int(hi.strip())]
        except ValueError:
            continue
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product Bio structure/closes/counts gate (Skill 55).")
    ap.add_argument("path", nargs="?", help="product-bio.md to prove")
    ap.add_argument("--intake", help="locked brief (working/intake.json) — the LOGGED "
                    "override channel; a logged section_count_overrides map wins over defaults")
    ap.add_argument("--section-override", dest="section_override", action="append",
                    help="applied per-section count override SID=LO-HI (repeatable); honored "
                    "only when it matches the locked brief, else AF-PB-OVERRIDE-UNLOGGED")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, intake_path=args.intake,
                 sec_applied=_parse_section_overrides(args.section_override), as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
