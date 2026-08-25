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


def extract_day_numbers(text: str):
    """Ordered list of the day numbers of every 'Day <n> —|-|:' heading."""
    nums = []
    for line in text.splitlines():
        m = c._DAY_HEAD_RE.match(line)
        if m:
            nums.append(int(m.group(1)))
    return nums


def evaluate(text: str) -> c.Result:
    r = c.Result("prove_bw_challenge")
    nums = extract_day_numbers(text)
    n = len(nums)
    if n != c.CHALLENGE_DAYS:
        r.fail(AF_CHALLENGE, "found %d day-section(s); the challenge must have exactly %d "
               "('Day <n> —' headings)" % (n, c.CHALLENGE_DAYS))
    elif sorted(nums) != list(range(1, c.CHALLENGE_DAYS + 1)):
        missing = [d for d in range(1, c.CHALLENGE_DAYS + 1) if d not in nums]
        dupes = sorted({d for d in nums if nums.count(d) > 1})
        r.fail(AF_CHALLENGE, "day numbers %s are not the exact sequence 1..%d "
               "(missing %s; duplicated %s) — e.g. 30x 'Day 1' is NOT a 30-day challenge"
               % (sorted(nums), c.CHALLENGE_DAYS, missing, dupes))
    else:
        r.note("exactly %d day-sections numbered 1..%d" % (n, c.CHALLENGE_DAYS))
    return r


def prove(path, as_json=False) -> int:
    return evaluate(c.read_text(path)).emit(as_json)


def _build(n_days: int, start=1) -> str:
    lines = ["# 30-Day Challenge — The Quiet Authority", ""]
    for d in range(start, start + n_days):
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
    # 30 sections all claiming Day 1 — right COUNT, wrong NUMBERS
    thirty_x_1 = "".join("## Day 1 — repeat %d\nbody\n\n" % i for i in range(30))
    checks.append(("30x 'Day 1' AUTOFAILs AF-BK-CHALLENGE (count right, numbers wrong)",
                   any(cd == AF_CHALLENGE for cd, _ in evaluate(thirty_x_1).violations)))
    # shifted numbering (2..31) also fails the exact-sequence assertion
    checks.append(("days 2..31 AUTOFAILs AF-BK-CHALLENGE",
                   any(cd == AF_CHALLENGE for cd, _ in evaluate(_build(30, start=2)).violations)))
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
