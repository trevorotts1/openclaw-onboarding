#!/usr/bin/env python3
"""G2-EXT — every annotated version tag in the WHOLE history needs a CHANGELOG
entry, or a documented reason it can never have one.

WHY THIS EXISTS
----------------
G2 (version-consistency.yml, scripts embedded inline) already requires a
CHANGELOG.md entry for every annotated vX.Y.Z tag with major >= 11, and is
deliberately scoped there: pre-v11 tags predate the CHANGELOG-on-tag
discipline, so gating them retroactively would fail every build without
fixing anything real. A 2026-09-28 audit confirmed that is not a hypothetical
edge case -- all 40 annotated pre-v11 tags (v0.1.12 through v10.15.48;
lightweight vX.Y.Z-looking refs in that range are correctly excluded, same as
G2/G4) have zero matching CHANGELOG.md header. That is the whole pre-v11 era,
not a few stragglers.

G2's v11 floor means a gap ANYWHERE below v11 is invisible to CI forever, and
a NEW gap below v11 (e.g. a stray legacy-format tag pushed by mistake) would
also go unnoticed. This guard removes the floor entirely and walks every
annotated tag in the repo, using the SAME header matcher as G2. The known
pre-v11 backlog is grandfathered through .github/known-changelog-gap-tags.txt
-- exactly the ledger pattern G1b (known-untagged-releases.txt) and G4
(known-orphan-tags.txt) already use in this repo -- so the guard can be
strict about NEW gaps without being asked to fail on 40 tags nobody can fix.

ENFORCED IN BOTH DIRECTIONS, same as those two ledgers:
  * a tag with no CHANGELOG entry that is NOT in the ledger fails the build
    (catches a new gap, at any version, not just below v11);
  * a ledger entry that NOW has a matching CHANGELOG entry ALSO fails the
    build, so the ledger is forced to shrink as backlog is repaid and can
    never rot into a blanket exemption that swallows a real regression.

Usage:
  scripts/check-changelog-full-history.py [--changelog PATH] [--ledger PATH]
Exit 0 = pass, 1 = violation, 2 = internal/usage error.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
DEFAULT_LEDGER = ".github/known-changelog-gap-tags.txt"
DEFAULT_CHANGELOG = "CHANGELOG.md"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def load_ledger(path: Path) -> dict[str, str]:
    """Parse 'vX.Y.Z  # reason' per line, same format as the sibling ledgers."""
    entries: dict[str, str] = {}
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tag, _, reason = line.partition("#")
        entries[tag.strip()] = reason.strip() or "(no reason recorded)"
    return entries


def annotated_version_tags() -> list[str]:
    """Every annotated vX.Y.Z tag in the repo (no floor)."""
    out = git("for-each-ref", "--format=%(refname:short)\t%(objecttype)", "refs/tags")
    if out.returncode != 0:
        print(f"ERROR (G2-EXT): git for-each-ref failed: {out.stderr.strip()}")
        sys.exit(2)
    tags = []
    for line in out.stdout.splitlines():
        name, _, objtype = line.partition("\t")
        if objtype == "tag" and TAG_RE.match(name):
            tags.append(name)
    return tags


def has_changelog_entry(tagname: str, changelog_text: str) -> bool:
    # Same matcher as G2: "## [vX.Y.Z]" or "## vX.Y.Z" (bracket optional).
    return re.search(rf"^## \[?{re.escape(tagname)}\]?([ \t]|$)", changelog_text, re.M) is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--changelog", default=DEFAULT_CHANGELOG)
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    args = ap.parse_args()

    changelog_path = Path(args.changelog)
    if not changelog_path.exists():
        print(f"ERROR (G2-EXT): {args.changelog} not found.")
        return 2
    changelog_text = changelog_path.read_text(encoding="utf-8")

    ledger = load_ledger(Path(args.ledger))
    tags = annotated_version_tags()
    if not tags:
        print("ERROR (G2-EXT): no annotated vX.Y.Z tags found — tags were not fetched.")
        print("  Ensure the workflow uses fetch-depth: 0 (tags must be present).")
        return 2

    missing = [t for t in tags if not has_changelog_entry(t, changelog_text)]
    new_gaps = [t for t in missing if t not in ledger]
    repaid = [t for t in ledger if t not in missing]

    print(f"Checked {len(tags)} annotated version tags (full history) against {args.changelog}.")
    print(f"Missing CHANGELOG entries: {len(missing)} | grandfathered in ledger: {len(ledger)}")

    failed = False

    if new_gaps:
        failed = True
        print("\nERROR (G2-EXT): these annotated tags have NO CHANGELOG.md entry and are")
        print("NOT in the grandfather ledger:")
        for t in sorted(new_gaps, key=lambda s: [int(p) for p in s[1:].split(".")]):
            print(f"  {t}")
        print(f"\nFIX: add a header to {args.changelog} for each tag:")
        print("  ## [vX.Y.Z]  -  YYYY-MM-DD  -  <description>")
        print("  or")
        print("  ## vX.Y.Z — <description> — YYYY-MM-DD")
        print(f"\nIf the tag genuinely predates CHANGELOG coverage and cannot be given a")
        print(f"truthful entry, add it to {args.ledger} with a reason instead.")

    if repaid:
        failed = True
        print(f"\nERROR (G2-EXT): these tags are in {args.ledger} but NOW have a")
        print("matching CHANGELOG.md entry:")
        for t in sorted(repaid):
            print(f"  {t}")
        print(f"\nFIX: delete those lines from {args.ledger}. The ledger records")
        print("outstanding backlog only; stale entries would hide future regressions.")

    if failed:
        return 1

    print("\n✓ Every annotated version tag has a CHANGELOG entry or a documented gap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
