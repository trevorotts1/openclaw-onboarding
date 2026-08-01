#!/usr/bin/env python3
"""G1b — every version ever RELEASED on main must have a truthful annotated tag.

WHY THIS EXISTS
---------------
G1 (version-consistency.yml, "version file change requires a matching annotated
tag") is TRANSIENT BY CONSTRUCTION. It compares HEAD against HEAD^1 and fires
only on the single push where /version changed:

    if [ "$CURRENT_VER" = "$PREV_VER" ]; then
      echo "Version unchanged ($CURRENT_VER) — no tag required for this push."
      exit 0
    fi

So the instant ANY next commit lands on main, CURRENT_VER == PREV_VER, G1 exits
0, and the missing tag is never looked at again. G2 cannot cover the gap either:
G2 iterates TAGS, and an untagged release has no tag to iterate. G4 iterates
tags too. A release that misses its tag therefore falls out of every existing
guard permanently, and main goes green over the hole.

That is not hypothetical. On 2026-07-31 a walk of main's first-parent history
found SIX untagged releases in the v21.4 series — v21.4.39, v21.4.40, v21.4.41
and v21.4.42 CONSECUTIVELY — with main fully green and three separate earlier
passes having hand-backfilled v21.4.32, v21.4.33 and v21.4.38 without anyone
noticing the defect was structural. Backfilling is treating the symptom; this
guard is the cause.

WHAT THIS CHECKS
----------------
Walk main's first-parent history for every commit that changed /version. Each
distinct version string that appears is, by definition, a version that SHIPPED
on main. For each such version V at or above the floor:

  1. an ANNOTATED tag V must exist (lightweight is not a release tag); and
  2. the commit that tag resolves to must itself carry /version == V.

Assertion 2 is the truthfulness half, and it is deliberately ref-independent so
it behaves identically on main and on a PR checkout. It catches the failure mode
where a tag name exists but points at a commit that never carried that version
string — a tag that cannot be made truthful by retagging, only by admitting the
release was never version-stamped.

This guard does NOT re-check tag-to-main ancestry: that is G4
(tag-ancestry-guard.yml / check-tag-ancestry.py), which walks the tag set. G1b
walks the RELEASE set. The two directions together are what close the loop:

  G1  — /version bumped        -> an annotated tag must exist            (this push)
  G1b — /version EVER bumped   -> an annotated + truthful tag must exist (durably)
  G2  — a tag exists           -> CHANGELOG.md must document it
  G4  — a tag exists           -> it must point at a commit on main

EXPECTED RED WINDOW — THIS IS THE POINT, NOT A BUG
--------------------------------------------------
Between "a version-bump merge lands on main" and "its tag is pushed", this guard
fails. G1 already fails in exactly that window, so this adds no new class of
redness. What it changes is that the failure no longer EVAPORATES on the next
commit. Push the tag with scripts/push-version-tag.sh and the guard goes green
on the next run; ignore it and it stays red. A guard that stops noticing is
what produced the four consecutive untagged releases above.

FLOOR AND LEDGER
----------------
FLOOR_VERSION is the oldest release this invariant is enforced from. Releases
older than the floor predate the guard and carry 253 untagged versions going
back to v5; several of them can no longer be tagged truthfully at all, and
gating them would fail every build without repairing anything — the same
rationale G2 and G4 already use for their v11 floor.

Above the floor, exemptions live in .github/known-untagged-releases.txt and are
enforced in BOTH directions, exactly as G4's orphan ledger is:
  * an untagged release NOT in the ledger fails the build (catches regressions);
  * a ledger entry that is NO LONGER untagged ALSO fails the build, so the
    ledger is forced to shrink as debt is repaid and can never rot into a
    blanket exemption that quietly swallows the next real defect.
The ledger ships EMPTY: all six in-scope releases were repaired rather than
grandfathered.

Usage:
  scripts/check-released-versions-tagged.py [--ref origin/main] [--ledger PATH]
                                            [--floor v21.4.15]
Exit 0 = pass, 1 = violation, 2 = internal/usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

# Oldest release this invariant is enforced from. See FLOOR AND LEDGER above.
# v21.4.15 is the oldest untagged release repaired by the change that added
# this guard, so the floor and the repair are the same event.
FLOOR_VERSION = "v21.4.15"

DEFAULT_LEDGER = ".github/known-untagged-releases.txt"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = VERSION_RE.match(text.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def resolve_ref(candidates: list[str]) -> str:
    """Return the first ref that exists. CI and local checkouts disagree on
    whether main is 'origin/main' or just 'main', so try both rather than
    silently passing on a ref that does not resolve."""
    for ref in candidates:
        if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0:
            return ref
    print(f"ERROR (G1b): none of these refs resolve: {', '.join(candidates)}")
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
        version, _, reason = line.partition("#")
        entries[version.strip()] = reason.strip() or "(no reason recorded)"
    return entries


def read_blobs(specs: list[str]) -> dict[str, str]:
    """Batch-read many <rev>:<path> blobs in one git process.

    One subprocess per commit would be ~800 forks on this repo's history. The
    --batch protocol answers all of them in a single pass; a missing object
    prints '<spec> missing' instead of a header, which we skip.
    """
    if not specs:
        return {}
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=("\n".join(specs) + "\n").encode(),
        capture_output=True,
    )
    if proc.returncode != 0:
        print(f"ERROR (G1b): git cat-file --batch failed: {proc.stderr.decode(errors='replace').strip()}")
        sys.exit(2)

    out: dict[str, str] = {}
    data = proc.stdout
    pos = 0
    for spec in specs:
        nl = data.find(b"\n", pos)
        if nl == -1:
            break
        header = data[pos:nl].decode(errors="replace")
        pos = nl + 1
        parts = header.split()
        if len(parts) != 3:
            # "<spec> missing" / "<spec> ambiguous" — no body follows.
            continue
        size = int(parts[2])
        out[spec] = data[pos : pos + size].decode(errors="replace").strip()
        pos += size + 1  # body plus its trailing newline
    return out


def released_versions(ref: str) -> dict[str, str]:
    """Map version string -> first-parent commit on `ref` that introduced it.

    A commit on main's first-parent history that CHANGED /version is a release
    of whatever /version then said. Later entries win only if a version was
    re-bumped, which is why the walk is oldest-last and we keep the newest.
    """
    out = git("log", "--first-parent", "--format=%H", ref, "--", "version")
    if out.returncode != 0:
        print(f"ERROR (G1b): git log failed on {ref}: {out.stderr.strip()}")
        sys.exit(2)

    commits = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    if not commits:
        print(f"ERROR (G1b): no commits on {ref} touch /version — history is shallow.")
        print("  Ensure the workflow uses fetch-depth: 0.")
        sys.exit(2)

    blobs = read_blobs([f"{sha}:version" for sha in commits])
    released: dict[str, str] = {}
    for sha in commits:
        raw = blobs.get(f"{sha}:version")
        if raw is None:
            continue
        version = raw.splitlines()[0].strip() if raw else ""
        if parse_version(version) is None:
            continue
        released.setdefault(version, sha)
    return released


def tag_state(version: str) -> tuple[str, str]:
    """Return (objecttype, dereferenced-commit) for refs/tags/<version>.

    %(*objectname) is the dereferenced commit for an annotated tag and empty for
    a lightweight one, which is exactly how the two are told apart.
    """
    out = git(
        "for-each-ref",
        "--format=%(objecttype)%09%(*objectname)",
        f"refs/tags/{version}",
    )
    line = out.stdout.strip()
    if out.returncode != 0 or not line:
        return ("missing", "")
    parts = line.split("\t")
    objtype = parts[0]
    target = parts[1] if len(parts) > 1 else ""
    return (objtype, target)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None, help="ref whose release history to walk")
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--floor", default=FLOOR_VERSION, help="oldest release enforced")
    args = ap.parse_args()

    floor = parse_version(args.floor)
    if floor is None:
        print(f"ERROR (G1b): --floor '{args.floor}' is not a vX.Y.Z version.")
        return 2

    ref = args.ref or resolve_ref(
        ["origin/main", "refs/remotes/origin/main", "main", "HEAD"]
    )
    if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        print(f"ERROR (G1b): --ref '{ref}' does not resolve.")
        return 2

    ledger = load_ledger(Path(args.ledger))
    released = released_versions(ref)

    in_scope = {
        version: sha
        for version, sha in released.items()
        if (pv := parse_version(version)) is not None and pv >= floor
    }
    if not in_scope:
        print(f"ERROR (G1b): no releases at or above the floor {args.floor} found on {ref}.")
        print("  Either tags/history were not fetched, or the floor is set past the tip.")
        return 2

    untagged: list[tuple[str, str, str]] = []   # (version, release_sha, why)
    for version in sorted(in_scope, key=lambda v: parse_version(v) or (0, 0, 0)):
        release_sha = in_scope[version]
        objtype, target = tag_state(version)

        if objtype == "missing":
            untagged.append((version, release_sha, "no tag of that name exists"))
            continue
        if objtype != "tag" or not target:
            untagged.append(
                (version, release_sha, f"tag exists but is LIGHTWEIGHT (type={objtype})")
            )
            continue

        blob = read_blobs([f"{target}:version"]).get(f"{target}:version", "")
        tagged_version = blob.splitlines()[0].strip() if blob else ""
        if tagged_version != version:
            untagged.append(
                (
                    version,
                    release_sha,
                    f"tag points at {target[:12]}, whose /version says "
                    f"'{tagged_version or '(unreadable)'}' — not {version}",
                )
            )

    broken = {version for version, _, _ in untagged}
    new_violations = [row for row in untagged if row[0] not in ledger]
    repaid = [v for v in ledger if v not in broken]

    print(f"Walked {len(released)} released versions on {ref}; "
          f"{len(in_scope)} at or above the floor {args.floor}.")
    print(f"Untagged/untruthful: {len(untagged)} | grandfathered in ledger: {len(ledger)}")

    if ledger:
        print("\nOutstanding untagged-release debt (grandfathered, still unresolved):")
        for version in sorted(ledger, key=lambda v: parse_version(v) or (0, 0, 0)):
            if version in broken:
                print(f"  {version}  — {ledger[version]}")

    failed = False

    if new_violations:
        failed = True
        print("\nERROR (G1b): version(s) shipped on main without a truthful annotated tag:")
        for version, release_sha, why in new_violations:
            print(f"  {version}  released at {release_sha[:12]}  — {why}")
        print("\nWhy this is not cosmetic: update-skills.sh ships ONBOARDING_VERSION to")
        print("every box, and any audit that resolves a release by tag gets nothing back")
        print("for these versions. G1 cannot catch them because it only looks at the one")
        print("push where /version changed; G2 and G4 cannot, because they iterate tags.")
        print("\nFIX — publish the tag at the commit that actually carries the version:")
        for version, release_sha, _ in new_violations:
            print(f"  scripts/push-version-tag.sh {version} {release_sha[:12]}")
        print("\nUse that script, not a bare `git push origin <tag>`: it resolves the tag")
        print("to an explicit SHA and refuses to publish a commit that is not on main.")
        print(f"\nIf a release genuinely cannot be tagged truthfully (no commit ever")
        print(f"carried the string), record it in {args.ledger} with the reason.")

    if repaid:
        failed = True
        print(f"\nERROR (G1b): these versions are in {args.ledger} but are NO LONGER untagged:")
        for version in sorted(repaid, key=lambda v: parse_version(v) or (0, 0, 0)):
            print(f"  {version}")
        print(f"\nFIX: delete those lines from {args.ledger}. The ledger records")
        print("outstanding debt only; stale entries would hide future regressions.")

    if failed:
        return 1

    print(f"\n✓ Every release at or above {args.floor} has a truthful annotated tag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
