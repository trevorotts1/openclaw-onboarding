#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: 30-DAY-CHALLENGE GATE (fail-closed)
# -----------------------------------------------------------------------------
# The 30-Day Challenge companion must have EXACTLY 30 day-sections — no more, no
# fewer. Day-sections are counted by heading pattern 'Day <n> —|-|:' so ordinary
# prose that mentions "day" is never miscounted.
#
#   AF-BK-CHALLENGE — the challenge does not have exactly 30 day-sections.
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_challenge.py <30_Day_Challenge.md> [--json] | --self-test
# =============================================================================
"""Fail-closed 30-Day-Challenge section-count gate (Skill 53)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_CHALLENGE = "AF-BK-CHALLENGE"


def evaluate(text: str) -> c.Result:
    r = c.Result("prove_bw_challenge")
    n = c.count_day_sections(text)
    if n != c.CHALLENGE_DAYS:
        r.fail(AF_CHALLENGE, "found %d day-section(s); the challenge must have exactly %d "
               "('Day <n> —' headings)" % (n, c.CHALLENGE_DAYS))
    else:
        r.note("exactly %d day-sections" % c.CHALLENGE_DAYS)
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_text(path)).emit(as_json)


def _build(n_days: int) -> str:
    lines = ["# 30-Day Challenge — The Quiet Authority", ""]
    for d in range(1, n_days + 1):
        lines.append("## Day %d — theme %d" % (d, d))
        lines.append("Do the thing for day %d." % d)
        lines.append("")
    return "\n".join(lines)


def self_test() -> int:
    checks = []
    checks.append(("exactly 30 days PASSES", evaluate(_build(30)).passed))
    checks.append(("29 days AUTOFAILs AF-BK-CHALLENGE",
                   any(cd == AF_CHALLENGE for cd, _ in evaluate(_build(29)).violations)))
    checks.append(("31 days AUTOFAILs AF-BK-CHALLENGE",
                   any(cd == AF_CHALLENGE for cd, _ in evaluate(_build(31)).violations)))
    prose = "# Challenge\n\nOn a hard day you might feel like every day is day one. Keep going.\n"
    checks.append(("prose mentioning 'day' counts 0 -> AUTOFAILs AF-BK-CHALLENGE",
                   any(cd == AF_CHALLENGE for cd, _ in evaluate(prose).violations)))
    return c.selftest_report("prove_bw_challenge", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer 30-Day-Challenge gate (Skill 53).")
    ap.add_argument("path", nargs="?", help="30_Day_Challenge.md")
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
