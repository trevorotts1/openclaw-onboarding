#!/usr/bin/env python3
"""G-12 (fix plan C1/C2, unowned): the reading rule says read each declared dependency WHOLE.

No "read in full / read the entire file / do not skim" instruction existed in 49/SKILL.md or
83/SKILL.md; 83's "Read order" set ORDER, not completeness. An agent that knows the order but
skims the files is exactly the behaviour the complaint names.

FAILS before the change: neither skill carried a binding reading rule.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = {
    "49-signature-funnel/SKILL.md": ("whole", "entire file"),
    "83-black-friday-launcher/SKILL.md": ("whole", "entire file"),
}


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2]
    return text


def main() -> int:
    fails = []
    for rel, needles in SKILLS.items():
        p = ROOT / rel
        if not p.is_file():
            fails.append("G-12: %s is missing" % rel)
            continue
        text = body(p)
        low = text.lower()
        if "reading rule" not in low:
            fails.append("G-12: %s has no 'Reading rule' section" % rel)
        if "binding" not in low:
            fails.append("G-12: %s reading rule is not marked binding" % rel)
        for needle in needles:
            if needle not in low:
                fails.append("G-12: %s reading rule does not say %r" % (rel, needle))
        if "read everything before you touch anything" not in low:
            fails.append("G-12: %s does not carry the proven INSTALL.md:72 wording" % rel)
        if "dependency" not in low:
            fails.append("G-12: %s reading rule never names a declared dependency" % rel)

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-12: 49 and 83 both bind a whole-read rule over every declared dependency")
    return 0


if __name__ == "__main__":
    sys.exit(main())
