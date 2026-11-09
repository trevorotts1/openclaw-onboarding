#!/usr/bin/env python3
"""G-13 (fix plan C1/C2, unowned): the reading rule says grepping is not reading.

The fix plan recorded ZERO anti-grep matches in AGENTS.md, TOOLS.md, Start Here.md,
QC-PROTOCOL.md and TERMINOLOGY.md, and none in 49/SKILL.md or 83/SKILL.md. Agents grepped
instead of reading because nothing forbade it.

FAILS before the change: neither skill carried an anti-grep rule.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ("49-signature-funnel/SKILL.md", "83-black-friday-launcher/SKILL.md")


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2]
    return text


def main() -> int:
    fails = []
    for rel in TARGETS:
        p = ROOT / rel
        if not p.is_file():
            fails.append("G-13: %s is missing" % rel)
            continue
        low = body(p).lower()
        if "grepping is not reading" not in low:
            fails.append("G-13: %s does not state 'GREPPING IS NOT READING'" % rel)
        if "no grepping allowed" not in low:
            fails.append("G-13: %s does not carry the proven 'No grepping allowed' rule" % rel)
        if "pointer" not in low:
            fails.append("G-13: %s does not explain that a search hit is a pointer, not knowledge" % rel)

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-13: 49 and 83 both forbid grepping and require the file to be read end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
