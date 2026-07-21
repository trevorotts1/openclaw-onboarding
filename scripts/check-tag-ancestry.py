#!/usr/bin/env python3
"""G4 — every v11+ annotated version tag must point at a commit on main.

WHY THIS EXISTS
---------------
Version tags are cut and pushed from a machine whose LOCAL tag namespace is
shared by many concurrent agents. `git push origin vX.Y.Z` resolves the NAME
against whatever local tag happens to exist, so one agent can push another
agent's tag, which points at a commit on an UNMERGED branch. The result is an
"orphaned" remote tag: a released-looking version whose content never landed on
main.

That is not a cosmetic problem. G2 (every v11+ annotated tag must have a
CHANGELOG entry) trusts tag existence as proof of release. An orphaned tag makes
G2 demand a CHANGELOG entry that only exists on the unmerged branch, which turns
main AND every open pull request red until the branch merges or the tag is
removed. One mis-push jams the whole merge lane.

WHAT THIS CHECKS
----------------
For every annotated tag matching vX.Y.Z with major >= 11 (identical scope to G2,
so the two guards can never disagree about which tags matter): the commit the tag
resolves to must be an ancestor of main.

Tags listed in .github/known-orphan-tags.txt are pre-existing debt and are
exempt. That ledger is enforced in BOTH directions:
  * an orphan that is NOT in the ledger fails the build (catches new mis-pushes);
  * a ledger entry that is no longer an orphan ALSO fails the build (forces the
    ledger to shrink as debt is repaid, so it can never rot into a blanket
    exemption that quietly swallows real regressions).

Scope note: the v11 floor mirrors G2. Pre-v11 tags predate tag discipline and
gating them retroactively would fail every build without fixing anything.

Usage:
  scripts/check-tag-ancestry.py [--main-ref origin/main] [--ledger PATH]
Exit 0 = pass, 1 = violation, 2 = internal/usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
MIN_MAJOR = 11
DEFAULT_LEDGER = ".github/known-orphan-tags.txt"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def resolve_main(candidates: list[str]) -> str:
    """Return the first ref that exists. CI and local checkouts disagree on
    whether main is 'origin/main' or just 'main', so try both rather than
    silently passing on a ref that does not resolve."""
    for ref in candidates:
        if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0:
            return ref
    print(f"ERROR (G4): none of these refs resolve: {', '.join(candidates)}")
    print("  Ensure the workflow checks out full history (fetch-depth: 0).")
    sys.exit(2)


def load_ledger(path: Path) -> dict[str, str]:
    """Parse the grandfather ledger: 'vX.Y.Z  # reason' per line."""
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


def annotated_version_tags() -> list[tuple[str, str]]:
    """Return [(tagname, target_commit_sha)] for annotated vX.Y.Z tags, major >= 11.

    %(*objectname) is the dereferenced commit for an annotated tag and empty for
    a lightweight one, which is exactly how we tell the two apart.
    """
    out = git(
        "for-each-ref",
        "--format=%(refname:short)%09%(objecttype)%09%(*objectname)",
        "refs/tags",
    )
    if out.returncode != 0:
        print(f"ERROR (G4): git for-each-ref failed: {out.stderr.strip()}")
        sys.exit(2)

    tags: list[tuple[str, str]] = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, objtype, target = parts
        if objtype != "tag" or not target:
            continue  # lightweight tags are G1's problem, not ours
        m = TAG_RE.match(name)
        if not m or int(m.group(1)) < MIN_MAJOR:
            continue
        tags.append((name, target))
    return tags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-ref", default=None, help="ref to test ancestry against")
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    args = ap.parse_args()

    main_ref = (
        args.main_ref
        if args.main_ref
        else resolve_main(["origin/main", "refs/remotes/origin/main", "main"])
    )
    if git("rev-parse", "--verify", "--quiet", f"{main_ref}^{{commit}}").returncode != 0:
        print(f"ERROR (G4): --main-ref '{main_ref}' does not resolve.")
        return 2

    ledger = load_ledger(Path(args.ledger))
    tags = annotated_version_tags()
    if not tags:
        print("ERROR (G4): no v11+ annotated version tags found — tags were not fetched.")
        print("  Ensure the workflow uses fetch-depth: 0 (tags must be present).")
        return 2

    orphans: list[str] = []
    for name, target in tags:
        if git("merge-base", "--is-ancestor", target, main_ref).returncode != 0:
            orphans.append(name)

    new_orphans = [t for t in orphans if t not in ledger]
    repaid = [t for t in ledger if t not in orphans]

    print(f"Checked {len(tags)} v11+ annotated version tags against {main_ref}.")
    print(f"Orphans found: {len(orphans)} | grandfathered in ledger: {len(ledger)}")

    if ledger:
        print("\nOutstanding orphaned-tag debt (grandfathered, still unresolved):")
        for tag in sorted(ledger):
            if tag in orphans:
                print(f"  {tag}  — {ledger[tag]}")

    failed = False

    if new_orphans:
        failed = True
        print("\nERROR (G4): version tag(s) point at commits that are NOT on main:")
        for tag in new_orphans:
            target = next(t for n, t in tags if n == tag)
            print(f"  {tag} -> {target[:12]} (not an ancestor of {main_ref})")
        print("\nThis usually means a tag was pushed BY NAME from a shared local tag")
        print("namespace and resolved to another agent's unmerged branch commit.")
        print("\nFIX (do NOT rewrite the remote tag yourself — that is a force op):")
        print("  1. If the tag's branch is still open, merge it; the tag becomes valid.")
        print("  2. Otherwise ask the operator to delete and re-cut it:")
        print("       git push origin :refs/tags/<tag>")
        print("       git tag -a <tag> <merge-sha> -m '<tag> — <description>'")
        print("       git push origin refs/tags/<tag>")
        print("\nPREVENTION: publish tags with scripts/push-version-tag.sh, which")
        print("resolves the tag to an explicit SHA and refuses to push a non-ancestor.")

    if repaid:
        failed = True
        print("\nERROR (G4): these tags are in the orphan ledger but are NO LONGER orphaned:")
        for tag in sorted(repaid):
            print(f"  {tag}")
        print(f"\nFIX: delete those lines from {args.ledger}. The ledger records")
        print("outstanding debt only; stale entries would hide future regressions.")

    if failed:
        return 1

    print("\n✓ Every v11+ annotated version tag points at a commit on main.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
