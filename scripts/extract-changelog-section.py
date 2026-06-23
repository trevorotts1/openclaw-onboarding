#!/usr/bin/env python3
"""extract-changelog-section.py — print the CHANGELOG.md section for one version.

Used by scripts/release.sh (Step 8) to draw GitHub Release notes from the
CHANGELOG entry for the version being released. Header-format agnostic: matches
both "## v13.8.2 — ..." (em-dash) and "## [v13.8.1]  -  ..." (bracketed dash)
styles that appear in this repo's CHANGELOG.

Usage:
    extract-changelog-section.py vX.Y.Z [path/to/CHANGELOG.md]

Prints the section (from its "## " header up to the next "## " header) to
stdout. Exits 2 if the section is not found.
"""
import os
import re
import sys


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: extract-changelog-section.py vX.Y.Z [CHANGELOG.md]\n")
        return 2
    ver = sys.argv[1]
    if len(sys.argv) >= 3:
        changelog = sys.argv[2]
    else:
        # Default to CHANGELOG.md at the repo root (one level up from scripts/).
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        changelog = os.path.join(repo_root, "CHANGELOG.md")

    try:
        with open(changelog, encoding="utf-8") as fh:
            content = fh.read()
    except OSError as exc:
        sys.stderr.write(f"cannot read {changelog}: {exc}\n")
        return 2

    lines = content.split("\n")
    # Match "## vX.Y.Z" or "## [vX.Y.Z]" followed by a space, dash, or em-dash.
    pat = re.compile(r"^##\s+\[?" + re.escape(ver) + r"\]?[\s—-]")
    start = next((i for i, ln in enumerate(lines) if pat.match(ln)), None)
    if start is None:
        sys.stderr.write(f"section for {ver} not found in {changelog}\n")
        return 2

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break

    section = "\n".join(lines[start:end]).strip()
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
