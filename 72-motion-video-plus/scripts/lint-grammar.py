#!/usr/bin/env python3
"""
Skill 72 grammar linter.

Scans a scene animation HTML/JS file against the machine-checkable parts of
references/motion-grammar.md and references/animation-contract.md.

It FLAGS violations; it never auto-fixes. Exit 0 means clean (warnings are
printed but do not fail). Exit 1 means at least one violation.

Checks:
  - window.__setTime is defined (contract requirement)
  - no CSS transitions or CSS animations (break determinism)
  - no setTimeout / setInterval driving motion (the driver owns time)
  - no unseeded Math.random (same t must give same pixels)
  - no GPU-layer tricks (translate3d, translateZ(0), will-change):
    composited layers cache rasters, so one t can paint differently
    depending on the previous frame
  - possible glow abuse: large-blur text/box shadows (warning only)

Usage:
  python3 scripts/lint-grammar.py scenes/scene-01.html
"""
import re
import sys

VIOLATIONS = [
    ("css-transition",
     re.compile(r"(?<![-a-z])transition\s*[:=]"),
     "CSS transition found: all motion must be set imperatively inside __setTime"),
    ("css-animation",
     re.compile(r"@keyframes|(?<![-a-z])animation\s*:"),
     "CSS animation found: all motion must be set imperatively inside __setTime"),
    ("timer",
     re.compile(r"\bset(TimeOut|Interval)\s*\("),
     "setTimeout/setInterval found: the frame driver owns time, the page must not advance itself"),
    ("unseeded-random",
     re.compile(r"\bMath\.random\s*\("),
     "Math.random found: use a seeded PRNG keyed off t so the same t renders identically"),
    ("gpu-layer",
     re.compile(r"translate3d\s*\(|translateZ\s*\(\s*0|will-change\s*:"),
     "GPU-layer trick found (translate3d/translateZ(0)/will-change): composited layers cache "
     "rasters, so one t can paint differently depending on the previous frame"),
]

WARNINGS = [
    ("possible-glow",
     re.compile(r"(text-shadow|box-shadow)\s*:[^;]*\b([3-9]\d|\d{3,})px"),
     "large-blur shadow found: check against the banned-cliche list (glow on chrome/type)"),
]

REQUIRED = [
    ("settime",
     re.compile(r"window\.__setTime\s*="),
     "window.__setTime(t) is not defined: the frame driver cannot render this scene"),
]


def main():
    if len(sys.argv) != 2:
        print("usage: lint-grammar.py <scene-file.html>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        print("cannot read %s: %s" % (path, e), file=sys.stderr)
        sys.exit(2)

    bad = 0
    for name, rx, msg in REQUIRED:
        if not rx.search(src):
            print("VIOLATION [%s] %s" % (name, msg))
            bad += 1
    for name, rx, msg in VIOLATIONS:
        for m in rx.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            print("VIOLATION [%s] line %d: %s" % (name, line, msg))
            bad += 1
    for name, rx, msg in WARNINGS:
        for m in rx.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            print("WARNING [%s] line %d: %s" % (name, line, msg))

    if bad:
        print("%d violation(s) in %s: fix them, the linter does not auto-fix" % (bad, path))
        sys.exit(1)
    print("grammar lint clean: %s" % path)


if __name__ == "__main__":
    main()
