#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: TITLE-LOCK GATE (fail-closed)
# -----------------------------------------------------------------------------
# The source method mandates "DO NOT CHANGE ABOVE TITLES in ANY CIRCUMSTANCE".
# This gate replaces that prose with a check: the GATE-1 locked title AND subtitle
# must appear BYTE-EXACT (as raw substrings) in every required downstream artifact
# — the blurb, the approved outline, every chapter payload/title page, the
# manuscript title page, and the cover prompt. Any drift = AF-BK-TITLE-LOCK.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE:
#   prove_bw_titlelock.py --approved-title <APPROVED-TITLE.txt> <target.md> [<target.md> ...] [--json]
#   prove_bw_titlelock.py --title "T" --subtitle "S" <target.md> ... [--json]
#   prove_bw_titlelock.py --self-test
# =============================================================================
"""Fail-closed byte-exact title/subtitle lock gate (Skill 53)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_TITLE_LOCK = "AF-BK-TITLE-LOCK"


def parse_approved_title(text: str):
    """Read APPROVED-TITLE.txt -> (title, subtitle). Lines 'TITLE:' / 'SUBTITLE:'."""
    title = subtitle = ""
    for line in text.splitlines():
        s = line.strip()
        if s.upper().startswith("TITLE:") and not s.upper().startswith("SUBTITLE:"):
            title = line.split(":", 1)[1].strip()
        elif s.upper().startswith("SUBTITLE:"):
            subtitle = line.split(":", 1)[1].strip()
    return title, subtitle


def evaluate(title: str, subtitle: str, targets: dict) -> c.Result:
    """targets: {label: text}. Both title and subtitle must be byte-exact substrings
    of each target text."""
    r = c.Result("prove_bw_titlelock")
    if not title.strip():
        r.fail(AF_TITLE_LOCK, "no locked TITLE provided (APPROVED-TITLE.txt missing 'TITLE:')")
    if not subtitle.strip():
        r.fail(AF_TITLE_LOCK, "no locked SUBTITLE provided (APPROVED-TITLE.txt missing 'SUBTITLE:')")
    if not title.strip() or not subtitle.strip():
        return r
    for label, text in targets.items():
        if title not in text:
            r.fail(AF_TITLE_LOCK, "locked TITLE %r not byte-exact in %s" % (title, label))
        if subtitle not in text:
            r.fail(AF_TITLE_LOCK, "locked SUBTITLE %r not byte-exact in %s" % (subtitle, label))
    if r.passed:
        r.note("locked title+subtitle byte-exact across %d target(s)" % len(targets))
    return r


def prove(title, subtitle, target_paths, as_json=False) -> int:
    targets = {p: c.read_text(p) for p in target_paths}
    return evaluate(title, subtitle, targets).emit(as_json)


def self_test() -> int:
    title = "The Quiet Authority"
    subtitle = "How the Best New Leaders Trade Control for Trust"
    good = ("# %s\n## %s\n\nBody echoing the locked strings verbatim." % (title, subtitle))
    checks = []
    checks.append(("good target with both strings byte-exact PASSES",
                   evaluate(title, subtitle, {"good.md": good}).passed))
    # subtitle changed by one word
    bad_sub = good.replace("Trade Control for Trust", "Trade Control for Power")
    checks.append(("changed subtitle AUTOFAILs AF-BK-TITLE-LOCK",
                   any(cd == AF_TITLE_LOCK for cd, _ in
                       evaluate(title, subtitle, {"bad.md": bad_sub}).violations)))
    # title re-cased (byte-exact must fail)
    bad_case = good.replace("The Quiet Authority", "The quiet authority")
    checks.append(("re-cased title AUTOFAILs AF-BK-TITLE-LOCK",
                   any(cd == AF_TITLE_LOCK for cd, _ in
                       evaluate(title, subtitle, {"bad.md": bad_case}).violations)))
    # parse APPROVED-TITLE.txt
    t, s = parse_approved_title("TITLE: %s\nSUBTITLE: %s\nLOCKED_BY: GATE-1-title\n" % (title, subtitle))
    checks.append(("APPROVED-TITLE.txt parses title+subtitle", t == title and s == subtitle))
    return c.selftest_report("prove_bw_titlelock", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer title-lock gate (Skill 53).")
    ap.add_argument("targets", nargs="*", help="artifact(s) that must echo the locked strings")
    ap.add_argument("--approved-title", help="path to APPROVED-TITLE.txt")
    ap.add_argument("--title", help="locked title (alternative to --approved-title)")
    ap.add_argument("--subtitle", help="locked subtitle (alternative to --approved-title)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.approved_title:
        title, subtitle = parse_approved_title(c.read_text(args.approved_title))
    else:
        title, subtitle = (args.title or ""), (args.subtitle or "")
    if not args.targets:
        ap.error("at least one target artifact is required (or use --self-test)")
    return prove(title, subtitle, args.targets, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
