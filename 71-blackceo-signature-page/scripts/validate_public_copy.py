#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

PATTERNS = [
    ("private section label", re.compile(r"^\s*(?:#+\s*)?SECTION\s+\d+[A-Z]?\s*[:.\-]", re.I | re.M)),
    ("private part label", re.compile(r"^\s*(?:#+\s*)?PART\s+\d+[A-Z]?\s*[:.\-]", re.I | re.M)),
    ("CTA production marker", re.compile(r"\bCTA\s+BUTTON\b", re.I)),
    ("image prompt marker", re.compile(r"\bIMAGE\s+PROMPT\b", re.I)),
    ("QC score marker", re.compile(r"\bQC\s+SCORE\b", re.I)),
    ("internal review marker", re.compile(r"\bINTERNAL\s+REVIEW\b", re.I)),
    ("private note marker", re.compile(r"\bPRIVATE\s+NOTE\b", re.I)),
    ("founder-letter part marker", re.compile(r"\bFOUNDER\s+LETTER\s+PART\b", re.I)),
    ("prompt ID marker", re.compile(r"\bPROMPT\s+ID\b", re.I)),
]
COMMENT_PATTERN = re.compile(r"<!--(?:(?!-->).)*(?:private|internal|prompt|qc score|section\s+\d)(?:(?!-->).)*-->", re.I | re.S)


def line_number(text, index):
    return text.count("\n", 0, index) + 1


def scan(text):
    hits = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            hits.append((line_number(text, match.start()), label, match.group(0).strip()))
    for match in COMMENT_PATTERN.finditer(text):
        hits.append((line_number(text, match.start()), "private/internal HTML comment", match.group(0)[:120].replace("\n", " ")))
    return sorted(hits)


def main():
    parser = argparse.ArgumentParser(description="Lint intended public copy/HTML for definite BlackCEO production-label leakage.")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()

    all_hits = []
    for path in args.files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"FAIL: could not read {path}: {exc}")
            return 2
        for hit in scan(text):
            all_hits.append((path, *hit))

    if all_hits:
        print("FAIL: private production markers detected.")
        for path, line, label, sample in all_hits:
            print(f"- {path}:{line}: {label}: {sample}")
        return 1
    print("PASS: no definite private production markers detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
