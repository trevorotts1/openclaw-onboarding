#!/usr/bin/env python3
"""U052: Validate DEPARTMENTS.md canonical IDs match department-naming-map.json."""

import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "23-ai-workforce-blueprint" / "DEPARTMENTS.md"
MAP = REPO / "23-ai-workforce-blueprint" / "department-naming-map.json"

def main():
    with open(MAP) as fh:
        map_ids = set(json.load(fh)["mandatory"].keys())
    with open(DOC) as fh:
        text = fh.read()
    pat = r"Canonical department IDs \([0-9]+ mandatory\)"
    m = re.search(pat, text)
    if not m:
        print("ERROR: section not found"); return 2
    cpat = "```\n"
    start = text.index(cpat, m.end()) + len(cpat)
    end = text.index("\n```", start)
    block = text[start:end].strip()
    doc_ids = {s.strip() for s in block.split(",") if s.strip()}
    errs = []
    if len(doc_ids) != len(map_ids):
        errs.append(f"Count mismatch: doc={len(doc_ids)} map={len(map_ids)}")
    for x in sorted(doc_ids - map_ids):
        errs.append(f"FABRICATED: {x}")
    for x in sorted(map_ids - doc_ids):
        errs.append(f"MISSING: {x}")
    if errs:
        for e in errs: print(f"[FAIL] {e}")
        return 1
    print(f"[PASS] All {len(map_ids)} IDs match")
    return 0

if __name__ == "__main__":
    sys.exit(main())
