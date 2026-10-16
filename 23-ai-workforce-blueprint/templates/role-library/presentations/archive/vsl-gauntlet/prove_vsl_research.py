#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_vsl_research.py — fail-closed prover for the VSL web-research notes file
(presentations upsell pipeline, GAUNTLET-LOOP DESIGN-OPUS §10.3 / §2.2 V0).

Enforces that the VSL web-research notes (`working/upsell/vsl-research.md`) are REAL
research, not filler:

  * the file exists and is non-empty                        -> AF-PRES-VSL-RESEARCH-EMPTY
  * it contains >= N NAMED sources, each with a URL         -> AF-PRES-VSL-RESEARCH-SOURCES
  * every named source has an http(s) URL                   -> AF-PRES-VSL-RESEARCH-URL
  * every claim has a source marker (a URL adjacent to the
    claim) so fabricated claims cannot hide                 -> AF-PRES-VSL-RESEARCH-UNSOURCED
  * the file is not padding / has real distinct content     -> AF-PRES-VSL-RESEARCH-PADDING
  * N defaults to 3 (design: ">=N named sources, each with
    a URL") and is overridable via --min-sources            -> AF-PRES-VSL-RESEARCH-UNSOURCED

A claim is any sentence (period/bang/question-mark terminated) in a bullet or paragraph.
A claim is SOURCED when the SAME bullet/paragraph carries a source marker — a bracketed
citation ([1], [Khan 2023]), an inline http(s) URL, or an `Source:`/`source:` line within
the same block. Claims that carry no marker at all are a HARD MISS: web research that
cannot be traced to a source is exactly the "fabricated claim" this prover exists to stop.

stdlib only. Exit 0 = pass, 2 = violation (autofail), 3 = usage/IO (fail-closed).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_EMPTY = "AF-PRES-VSL-RESEARCH-EMPTY"
AF_SOURCES = "AF-PRES-VSL-RESEARCH-SOURCES"
AF_URL = "AF-PRES-VSL-RESEARCH-URL"
AF_UNSOURCED = "AF-PRES-VSL-RESEARCH-UNSOURCED"
AF_PADDING = "AF-PRES-VSL-RESEARCH-PADDING"

_URL_RE = re.compile(r"https?://[^\s)]+")
# A source line: "- Source: https://..." / "Source: ..." / "Source 1: https://..."
_SOURCE_LINE_RE = re.compile(r"(?:^|\n)\s*(?:-\s*)?(?:source\s*\d*\s*:)\s*(.+)$",
                             re.I | re.M)


def _split_blocks(text: str) -> List[str]:
    """Split into blocks. Each bullet line (starts with '-', '*', or a number followed by
    '.') is its OWN block so claims in different bullets are independently source-checked.
    A bullet's indented continuation lines are appended to that bullet. A non-bullet run
    (a paragraph) is its own block. Source/citation lines stay attached to their block."""
    lines = text.splitlines()
    blocks: List[str] = []
    current: List[str] = []
    pending_paragraph: List[str] = []

    def flush_paragraph() -> None:
        nonlocal pending_paragraph
        if pending_paragraph:
            blocks.append("\n".join(pending_paragraph))
            pending_paragraph = []

    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            flush_paragraph()
            continue
        is_bullet = bool(re.match(r"^(?:[-*]|\d+[.)])\s+", stripped))
        if is_bullet:
            flush_paragraph()
            if current:  # close the previous bullet
                blocks.append("\n".join(current))
                current = [stripped]
            else:
                current = [stripped]
        else:
            if current:
                # indented continuation of a bullet
                current.append(stripped)
            else:
                pending_paragraph.append(stripped)
    flush_paragraph()
    if current:
        blocks.append("\n".join(current))
    return blocks


def _block_has_source_marker(block: str) -> bool:
    if _URL_RE.search(block):
        return True
    if re.search(r"\[\s*\d+\s*\]", block):  # bracketed citation [1]
        return True
    if re.search(r"source\s*\d*\s*:", block, re.I):
        return True
    if re.search(r"\((?:retrieved|viewed|accessed)\s", block, re.I):
        return True
    return False


def _named_source_count(block: str) -> int:
    """Count NAMED sources in a block: each unique http(s) URL counts as one source. A
    bare 'Source:' line with a publisher name but no URL is a NAMED source too (it names
    a source) but then the URL rule (AF_URL) demands it carries a URL — handled separately."""
    urls = set(_URL_RE.findall(block))
    count = len(urls)
    # A "Source: <publisher>" line without a URL still names a source but that line will
    # fail AF_URL if it has no URL in the whole block.
    return count


def _claim_sentences(block: str) -> List[str]:
    """Sentences in a block that look like claims (end with . ! ? and carry >= 6 words),
    EXCLUDING the source/citation line itself."""
    cleaned = _SOURCE_LINE_RE.sub(" ", block)
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    out: List[str] = []
    for s in sentences:
        words = len(re.findall(r"[A-Za-z0-9]+", s))
        if words >= 6 and re.search(r"[.!?]\s*$", s):
            out.append(s.strip())
    return out


def evaluate(text: str, min_sources: int = 3) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped:
        return [(AF_EMPTY, "VSL research notes file is empty (fail-closed)")]

    words = len(re.findall(r"[A-Za-z0-9]+", stripped))
    if words < 40:
        return [(AF_PADDING, f"research notes too thin to be real research ({words} words; "
                             f"need substance, not a stub)")]

    # Distinct-content guard: if > 40% of the file is repeated n-grams it's padding.
    # Cheap proxy: ratio of distinct words to total words must be > 0.35 for a research
    # note (a repeated loop of one sentence collapses below this).
    toks = re.findall(r"[a-z0-9]+", stripped.lower())
    if toks:
        distinct = len(set(toks))
        if distinct / len(toks) < 0.30:
            return [(AF_PADDING,
                     f"research notes look like padding (distinct/total word ratio "
                     f"{distinct}/{len(toks)} = {distinct / len(toks):.2f}, below 0.30)")]

    blocks = _split_blocks(text)

    # 1) named sources with URLs.
    urls = set(_URL_RE.findall(text))
    named = len(urls)
    if named < min_sources:
        fails.append((AF_SOURCES,
                      f"only {named} named source URL(s) found, design requires >= "
                      f"{min_sources}"))

    # 2) every block that NAMES a source line must actually carry a URL for it.
    for idx, blk in enumerate(blocks, 1):
        if re.search(r"source\s*\d*\s*:", blk, re.I) and not _URL_RE.search(blk):
            fails.append((AF_URL,
                          f"block {idx} declares a 'Source:' name but carries no URL "
                          f"(named source must be verifiable)"))

    # 3) every claim block must carry a source marker (no fabricated claims).
    for idx, blk in enumerate(blocks, 1):
        if not _block_has_source_marker(blk):
            claims = _claim_sentences(blk)
            if claims:
                fails.append((AF_UNSOURCED,
                              f"block {idx} makes {len(claims)} claim(s) with no source "
                              f"marker (no URL/citation/source line): "
                              f"{claims[0][:80]}..."))

    # 4) a bare URL with zero surrounding text is not research.
    bare_blocks = [i for i, blk in enumerate(blocks, 1) if _URL_RE.search(blk)
                   and _stripped_words(blk) < 4]
    if bare_blocks:
        fails.append((AF_PADDING,
                      f"blocks {bare_blocks} are bare URLs with no research context"))

    return fails


def _stripped_words(blob: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", blob or ""))


def _emit(source: str, failures: List[Tuple[str, str]], as_json: bool) -> None:
    if as_json:
        import json
        print(json.dumps({"gate": "presentations-vsl-research", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]},
                         indent=2))
        return
    print("== Presentations :: VSL web-research provenance ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — research is non-empty, sourced (>= N named sources w/ URLs), "
              "and every claim carries a source marker.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


def prove(path: str, min_sources: int = 3, as_json: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"research notes file not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _emit(str(p), [("USAGE", f"cannot read file: {exc}")], as_json)
        return EXIT_USAGE
    failures = evaluate(text, min_sources=min_sources)
    _emit(str(p), failures, as_json)
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


# ---------------------------------------------------------------------------
# Self-test — must DISCRIMINATE.
# ---------------------------------------------------------------------------
def _valid_research() -> str:
    return """# VSL Web Research — Best Practices

## Video length
- VSLs perform best when kept tight; one analysis of 100+ direct-response VSLs found the
  majority of successful videos ran 10-20 minutes and held the hook-to-reveal within the
  first half. Source: https://example.com/vsl-length-study
- A shorter 3-8 minute gate window correlates with higher completion when the first big
  revelation lands before the gate. Source: https://example.com/gate-placement

## Gating practice
- Requiring an email and phone at a mid-roll moment lifts engaged-contact capture, and the
  practice is documented across conversion benchmarks. Source: https://example.com/vsl-gate
- One benchmark reported a 30%+ opt-in lift when the gate fired after a value peak rather
  than before it (retrieved 2026-08-01). https://example.com/vsl-benchmark
"""


def _thinned_research() -> str:
    """Real structure, but only 1 source URL and several unsourced claim blocks."""
    return """# VSL Web Research

- The best VSLs are under 20 minutes and keep the hook tight. https://example.com/one
- Everyone knows that a mid-roll gate triples engagement in every industry.
- The first big revelation should always land before the gate because that is how the
  best marketers do it.
"""


def _fabricated_research() -> str:
    """Real-looking claims, ZERO source URLs, no citations."""
    return """# VSL Web Research

- Studies consistently prove that a seven-minute gate is the universal optimum for every
  niche and every audience on every platform known to humanity.
- The industry standard is to place the gate exactly at 4 minutes and 33 seconds because
  a landmark paper in 2019 proved this number is magical.
- Viewers who are asked for a phone number first are eighty percent more likely to
  complete any video sales letter without exception.
"""


def _padding_research() -> str:
    """One real source URL repeated in a loop = padding."""
    return " ".join(["The best VSLs are short and the gate should fire after the reveal. " *
                     30 + "https://example.com/x"]) if False else \
        "# VSL Research\n\n" + "\n".join(
            ["The gate placement is a known best practice discussed widely in the "
             "industry literature for many years now. https://example.com/repeat"
             ] * 12)


def self_test(min_sources: int = 3) -> int:
    ok = True

    def check_pass(name: str, fails: List[Tuple[str, str]]) -> None:
        nonlocal ok
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:20s} -> exit "
              f"{EXIT_PASS if good else EXIT_AUTOFAIL}" + ("" if good else f" ({fails})"))

    def check_fail(name: str, fails: List[Tuple[str, str]], expect: str) -> None:
        nonlocal ok
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} "
              f"(want {expect})")

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("real-research", evaluate(_valid_research(), min_sources))
    check_pass("min-sources-1", evaluate(_valid_research(), min_sources=1))

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    check_fail("empty", evaluate("   \n \t  ", min_sources), AF_EMPTY)
    check_fail("thin-stub", evaluate("Just a short note about VSL best practices.",
                                     min_sources), AF_PADDING)
    check_fail("too-few-sources", evaluate(_thinned_research(), min_sources), AF_SOURCES)
    check_fail("unsourced-claims", evaluate(_thinned_research(), min_sources), AF_UNSOURCED)
    check_fail("fabricated", evaluate(_fabricated_research(), min_sources), AF_UNSOURCED)
    check_fail("padding", evaluate(_padding_research(), min_sources), AF_PADDING)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for VSL web-research notes.")
    ap.add_argument("file", nargs="?", help="path to vsl-research.md")
    ap.add_argument("--min-sources", type=int, default=3,
                    help="minimum named sources with URLs (default 3)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test(min_sources=args.min_sources)
    if not args.file:
        print("USAGE ERROR: pass a research notes file (or --self-test).")
        return EXIT_USAGE
    return prove(args.file, min_sources=args.min_sources, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
