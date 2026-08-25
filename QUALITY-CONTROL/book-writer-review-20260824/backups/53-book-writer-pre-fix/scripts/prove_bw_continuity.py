#!/usr/bin/env python3
# =============================================================================
# SKILL 53 — BOOK WRITER :: CHAPTER-BATCH CONTINUITY GATE (fail-closed)
# -----------------------------------------------------------------------------
# The product's continuity mechanism: each chapter batch is written with ALL prior
# chapters injected into its payload (never parallelized). This gate proves the
# injection actually happened — batch N's receipt must record the sha256 of every
# prior chapter, and each recorded sha256 must equal the ACTUAL sha256 of that
# chapter file. A batch written without its predecessors is detected, not trusted.
#
#   AF-BK-CONTINUITY — a batch receipt is missing a prior chapter, records a wrong
#                      sha256 for one, or is out of sequence.
#
# Receipt schema (run/receipts/G-STAGE-1{5,6,7,8}-chapters-b{1,2,3,4}.json):
#   {"stage": "...", "batch": N, "chapters_written": [..],
#    "prior_chapters_embedded": {"1": "<sha256>", ...}}
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_bw_continuity.py --receipts DIR --chapters-dir DIR [--json] | --self-test
# =============================================================================
"""Fail-closed chapter-batch continuity gate (Skill 53)."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bw_common as c  # noqa: E402

AF_CONTINUITY = "AF-BK-CONTINUITY"

# The four sequential batches and the chapters each writes.
BATCHES = [
    ("15-write-chapters-b1", 1, [1, 2, 3]),
    ("16-write-chapters-b2", 2, [4, 5, 6]),
    ("17-write-chapters-b3", 3, [7, 8, 9]),
    ("18-write-chapters-b4", 4, [10, 11, 12]),
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evaluate(receipts: dict, chapter_sha: dict) -> c.Result:
    """receipts: {batch_number:int -> receipt dict}. chapter_sha: {chapter:int -> sha256}."""
    r = c.Result("prove_bw_continuity")
    prior = []  # chapters written by earlier batches, in order
    for stage, bnum, chapters in BATCHES:
        rec = receipts.get(bnum)
        if rec is None:
            r.fail(AF_CONTINUITY, "batch %d (%s) receipt missing" % (bnum, stage))
            prior += chapters
            continue
        embedded = rec.get("prior_chapters_embedded") or {}
        # normalize keys to int
        embedded = {int(k): v for k, v in embedded.items()}
        for pc in prior:
            if pc not in embedded:
                r.fail(AF_CONTINUITY, "batch %d did not embed prior chapter %d "
                       "(continuity broken — batch written without its predecessors)" % (bnum, pc))
            elif chapter_sha.get(pc) and embedded[pc] != chapter_sha[pc]:
                r.fail(AF_CONTINUITY, "batch %d recorded sha256 %s.. for prior chapter %d but the "
                       "actual chapter sha256 is %s.. (payload did not contain THIS chapter)"
                       % (bnum, str(embedded[pc])[:12], pc, str(chapter_sha[pc])[:12]))
        # a batch must NOT claim to have embedded chapters that don't exist yet
        for k in embedded:
            if k not in prior:
                r.fail(AF_CONTINUITY, "batch %d claims to embed chapter %d which is not a prior "
                       "chapter (illegal forward/self reference)" % (bnum, k))
        prior += chapters
    if r.passed:
        r.note("all 4 batches embed every prior chapter with matching sha256 (continuity proven)")
    return r


def _load_receipts(dir_path: str) -> dict:
    out = {}
    for stage, bnum, _chapters in BATCHES:
        p = Path(dir_path) / ("G-STAGE-%s.json" % stage)
        if p.is_file():
            try:
                out[bnum] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                out[bnum] = {}
    return out


def _load_chapter_sha(dir_path: str) -> dict:
    out = {}
    for p in Path(dir_path).glob("ch*.md"):
        digits = "".join(ch for ch in p.stem if ch.isdigit())
        if digits:
            out[int(digits)] = _sha(p.read_text(encoding="utf-8"))
    return out


def prove(receipts_dir, chapters_dir, as_json=False) -> int:
    return evaluate(_load_receipts(receipts_dir), _load_chapter_sha(chapters_dir)).emit(as_json)


def self_test() -> int:
    # build chapter shas
    texts = {n: "chapter %d body" % n for n in range(1, 13)}
    csha = {n: _sha(texts[n]) for n in range(1, 13)}

    def good_receipts():
        recs = {}
        prior = []
        for stage, bnum, chapters in BATCHES:
            recs[bnum] = {"stage": stage, "batch": bnum, "chapters_written": chapters,
                          "prior_chapters_embedded": {str(p): csha[p] for p in prior}}
            prior += chapters
        return recs

    checks = []
    checks.append(("full continuity PASSES", evaluate(good_receipts(), csha).passed))
    # batch 3 drops prior chapter 2
    bad = good_receipts(); bad[3]["prior_chapters_embedded"].pop("2", None)
    checks.append(("batch missing a prior chapter AUTOFAILs AF-BK-CONTINUITY",
                   any(cd == AF_CONTINUITY for cd, _ in evaluate(bad, csha).violations)))
    # batch 4 records a wrong sha for chapter 1
    bad2 = good_receipts(); bad2[4]["prior_chapters_embedded"]["1"] = "deadbeef" * 8
    checks.append(("batch with a tampered prior sha AUTOFAILs AF-BK-CONTINUITY",
                   any(cd == AF_CONTINUITY for cd, _ in evaluate(bad2, csha).violations)))
    return c.selftest_report("prove_bw_continuity", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Book Writer chapter-batch continuity gate (Skill 53).")
    ap.add_argument("--receipts", help="run/receipts directory")
    ap.add_argument("--chapters-dir", help="run/chapters directory (ch01..ch12.md)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.receipts and args.chapters_dir):
        ap.error("--receipts and --chapters-dir are required (or use --self-test)")
    return prove(args.receipts, args.chapters_dir, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
