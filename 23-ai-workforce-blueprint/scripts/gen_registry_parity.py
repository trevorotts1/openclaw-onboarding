#!/usr/bin/env python3
"""FIX 36(4) — regenerate the enforcement registry's machine-checked appendix.

Reads PIPELINE-MANIFEST.json's autofails[] and rewrites the appendix table
between the BEGIN/END markers in
universal-sops/presentation-slide-craft/SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md
so the human-facing registry can never drift from the machine truth.

Usage:
    python3 23-ai-workforce-blueprint/scripts/gen_registry_parity.py            # rewrite in place
    python3 23-ai-workforce-blueprint/scripts/gen_registry_parity.py --dry-run  # print the table
    python3 ... --manifest <path> --doc <path>                                  # explicit paths

tests/test_fix36_registry_parity.py re-derives this table in --dry-run mode and
requires a byte-for-byte match — a manifest autofail change without a
regeneration fails the parity test.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
DEFAULT_DOC = REPO / "universal-sops" / "presentation-slide-craft" / "SOP-MECHANICAL-ENFORCEMENT-REGISTRY.md"

BEGIN = "<!-- BEGIN MACHINE-CHECKED PARITY TABLE -->"
END = "<!-- END MACHINE-CHECKED PARITY TABLE -->"


def build_table(manifest_path: Path) -> str:
    import json
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    for a in m.get("autofails", []):
        if not isinstance(a, dict) or not a.get("code"):
            continue
        rows.append((a["code"], a.get("enforced_by", "") or "-", a.get("py_symbol", "") or "-"))
    rows.sort(key=lambda r: r[0])
    lines = [
        "| AF code | enforced_by | py_symbol |",
        "|---|---|---|",
    ]
    for code, by, sym in rows:
        lines.append(f"| `{code}` | {by} | {sym} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate the registry parity appendix from the manifest.")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--doc", default=str(DEFAULT_DOC))
    ap.add_argument("--dry-run", action="store_true", help="print the table instead of rewriting the doc")
    args = ap.parse_args()

    table = build_table(Path(args.manifest))
    if args.dry_run:
        print(table)
        return 0

    doc = Path(args.doc)
    text = doc.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text or text.index(BEGIN) > text.index(END):
        print(f"ERROR: {doc} is missing its {BEGIN} ... {END} appendix markers", file=sys.stderr)
        return 1
    start = text.index(BEGIN) + len(BEGIN)
    stop = text.index(END)
    new_text = text[:start] + "\n" + table + "\n" + text[stop:]
    doc.write_text(new_text, encoding="utf-8")
    n_rows = table.count("\n") - 2
    print(f"rewrote the parity appendix in {doc}: {n_rows} manifest-enforced codes")
    return 0


if __name__ == "__main__":
    sys.exit(main())