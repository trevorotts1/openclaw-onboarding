#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: CHAPTER COUNT + LENGTH GATE (fail-closed)
# -----------------------------------------------------------------------------
#   AF-BK-CHAP-COUNT — the book does not have exactly 12 chapters, numbered 1..12.
#   AF-BK-CHAP-LEN   — a chapter's MEASURED stripped word count is outside
#                      [2000,3500]. Whitespace padding is inert (stripped first),
#                      so padding a short chapter to length cannot fool the floor.
#
# Two input modes:
#   * a single assembled manuscript .md (chapters split on "Chapter <n>" headings)
#   * --chapters-dir DIR of ch01.md..ch12.md (each a whole chapter)
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_chapters.py <manuscript.md> [--json]
#        prove_bw_chapters.py --chapters-dir DIR [--json] | --self-test
# =============================================================================
"""Fail-closed chapter count + per-chapter length gate (Skill 53)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_COUNT = "AF-BK-CHAP-COUNT"
AF_LEN = "AF-BK-CHAP-LEN"


def evaluate(chapter_texts: dict) -> c.Result:
    """chapter_texts: {chapter_number:int -> body_text}."""
    r = c.Result("prove_bw_chapters")
    nums = sorted(chapter_texts.keys())
    if len(nums) != c.CHAPTER_COUNT:
        r.fail(AF_COUNT, "found %d chapter(s); the book must have exactly %d"
               % (len(nums), c.CHAPTER_COUNT))
    expected = list(range(1, c.CHAPTER_COUNT + 1))
    if nums and nums != expected:
        r.fail(AF_COUNT, "chapter numbering %s is not the exact sequence 1..%d"
               % (nums, c.CHAPTER_COUNT))
    for num in nums:
        wc = c.word_count(chapter_texts[num])
        if wc < c.CHAP_WORD_MIN or wc > c.CHAP_WORD_MAX:
            r.fail(AF_LEN, "chapter %d measured %d stripped words, outside [%d,%d] "
                   "(self-reported counts ignored; whitespace padding is inert)"
                   % (num, wc, c.CHAP_WORD_MIN, c.CHAP_WORD_MAX))
    if r.passed:
        r.note("exactly %d chapters, each within [%d,%d] stripped words"
               % (c.CHAPTER_COUNT, c.CHAP_WORD_MIN, c.CHAP_WORD_MAX))
    return r


def _from_manuscript(text: str) -> dict:
    return c.chapter_bodies(text)


def _from_dir(dir_path: str) -> dict:
    out = {}
    d = Path(dir_path)
    for p in sorted(d.glob("ch*.md")):
        stem = p.stem  # ch01
        digits = "".join(ch for ch in stem if ch.isdigit())
        if not digits:
            continue
        out[int(digits)] = p.read_text(encoding="utf-8")
    return out


def prove_manuscript(path, as_json=False) -> int:
    return evaluate(_from_manuscript(c.read_text(path))).emit(as_json)


def prove_dir(dir_path, as_json=False) -> int:
    return evaluate(_from_dir(dir_path)).emit(as_json)


def self_test() -> int:
    # deterministic in-memory book: 12 chapters, each padded to ~2100 real words.
    filler = ("word " * 2100).strip()
    good = {}
    for n in range(1, 13):
        good[n] = "This is chapter body number %d. %s" % (n, filler)
    checks = []
    checks.append(("12 chapters each ~2100 words PASS", evaluate(good).passed))
    # 11 chapters
    eleven = dict(list(good.items())[:11])
    checks.append(("11 chapters AUTOFAILs AF-BK-CHAP-COUNT",
                   any(cd == AF_COUNT for cd, _ in evaluate(eleven).violations)))
    # a short chapter
    short = dict(good); short[7] = "way too short chapter"
    checks.append(("a 3-word chapter AUTOFAILs AF-BK-CHAP-LEN",
                   any(cd == AF_LEN for cd, _ in evaluate(short).violations)))
    # whitespace-padded short chapter still fails (stripped)
    padded = dict(good); padded[7] = "short chapter\n\n\n" + ("\n" * 5000) + "   " * 5000
    checks.append(("whitespace-padded short chapter STILL AUTOFAILs AF-BK-CHAP-LEN",
                   any(cd == AF_LEN for cd, _ in evaluate(padded).violations)))
    # an over-long chapter
    longc = dict(good); longc[3] = ("word " * 4000).strip()
    checks.append(("a 4000-word chapter AUTOFAILs AF-BK-CHAP-LEN",
                   any(cd == AF_LEN for cd, _ in evaluate(longc).violations)))
    # manuscript parsing splits on Chapter headings
    manu = "\n".join("# Chapter %d — T\n%s" % (n, good[n]) for n in range(1, 13))
    checks.append(("manuscript parse yields 12 chapters", len(_from_manuscript(manu)) == 12))
    return c.selftest_report("prove_bw_chapters", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer chapter count+length gate (Skill 53).")
    ap.add_argument("manuscript", nargs="?", help="assembled manuscript .md")
    ap.add_argument("--chapters-dir", help="directory of ch01.md..ch12.md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.chapters_dir:
        return prove_dir(args.chapters_dir, as_json=args.json)
    if args.manuscript:
        return prove_manuscript(args.manuscript, as_json=args.json)
    ap.error("a manuscript path or --chapters-dir is required (or use --self-test)")


if __name__ == "__main__":
    sys.exit(main())
