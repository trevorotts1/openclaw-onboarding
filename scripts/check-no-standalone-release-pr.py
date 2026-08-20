#!/usr/bin/env python3
"""check-no-standalone-release-pr.py -- reject a PR whose ONLY changed files
are CHANGELOG.md and/or a /version marker (scripts/version-markers.json),
i.e. a release-ceremony-only PR that carries no code.

WHY THIS EXISTS
---------------
2026-08-19/20: six version tags were cut in ~21h (v22.0.51 -> v22.0.56), each
demanding a CHANGELOG-entry-then-annotated-tag two-step. That produced THREE
pure-CHANGELOG PRs -- #942, #944, #951 -- each changing exactly one file,
CHANGELOG.md, and nothing else. #944 sat 14.4h open->merged (opened
2026-08-19T22:20:32Z, merged 2026-08-20T12:43:23Z) and blocked TWO real fixes
(#945, #946) behind it in the single-merge-writer serialization this repo
uses. Separately, main going untagged blocked the G1b gate on EVERY open PR
seven separate times 2026-08-18 -> 2026-08-20, because G1b walks main's whole
release history, not any one PR's diff. See CONTROL/DELAY-DIAGNOSIS-FABLE.md
Section 2 D3, Section 4(b), Section 7 item 3 (Recommendation R3).

THE RULE
--------
The CHANGELOG entry and the version bump ride in the SAME PR as the fix they
document. A PR whose entire diff sits inside {CHANGELOG.md} union {the files
listed in scripts/version-markers.json} carries zero code and should never
have been opened on its own -- fold it into the fix PR instead (see
scripts/bundle-release-in-branch.sh).

WHAT THIS DOES NOT BLOCK
-------------------------
A PR that touches CHANGELOG.md / version markers ALONGSIDE any other file is
fine -- that is the batched shape this guard exists to require. Only a diff
that is a NON-EMPTY SUBSET of the release-file set fails. An empty diff (no
changed files at all) also passes -- nothing to check.

Usage:
  check-no-standalone-release-pr.py --base <ref> --head <ref> [--manifest PATH]
Exit 0 = pass (not a standalone release PR), 1 = violation, 2 = internal/usage error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_MARKERS_MANIFEST = "scripts/version-markers.json"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def release_file_set(manifest_path: Path) -> set[str]:
    """CHANGELOG.md plus every 'file' entry in the version-markers manifest.

    Falls back to CHANGELOG.md alone (and prints a loud warning) if the
    manifest is missing, rather than silently under-scoping the guard.
    """
    files = {"CHANGELOG.md"}
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: could not parse {manifest_path}: {exc}")
            sys.exit(2)
        for marker in data.get("markers", []):
            f = marker.get("file")
            if f:
                files.add(f)
    else:
        print(f"WARNING: {manifest_path} not found -- falling back to CHANGELOG.md only. "
              "This guard's release-file set is narrower than intended.")
    return files


def changed_files(base: str, head: str) -> list[str]:
    """Files changed on `head` relative to its merge-base with `base`.

    Mirrors G3's (skill-content-without-version-bump) approach in
    version-consistency.yml: diff against the merge-base, not a raw
    base..head range, so a head branch that is behind base on unrelated
    commits does not pick up noise.
    """
    merge_base = git("merge-base", base, head)
    base_point = merge_base.stdout.strip() if merge_base.returncode == 0 and merge_base.stdout.strip() else base
    out = git("diff", "--name-only", "--diff-filter=ACMR", base_point, head)
    if out.returncode != 0:
        print(f"ERROR: git diff failed: {out.stderr.strip()}")
        sys.exit(2)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="base ref (e.g. origin/main)")
    ap.add_argument("--head", default="HEAD", help="head ref (default HEAD)")
    ap.add_argument("--manifest", default=DEFAULT_MARKERS_MANIFEST)
    args = ap.parse_args()

    if git("rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}").returncode != 0:
        print(f"ERROR: --base '{args.base}' does not resolve.")
        return 2
    if git("rev-parse", "--verify", "--quiet", f"{args.head}^{{commit}}").returncode != 0:
        print(f"ERROR: --head '{args.head}' does not resolve.")
        return 2

    release_files = release_file_set(Path(args.manifest))
    files = changed_files(args.base, args.head)

    if not files:
        print("No changed files between base and head -- nothing to check.")
        return 0

    non_release = [f for f in files if f not in release_files]

    print(f"Changed files ({len(files)}): {', '.join(files)}")

    if non_release:
        print(f"\n✓ PR touches {len(non_release)} non-release file(s) -- not a standalone release PR.")
        return 0

    print("\nERROR: this PR's ENTIRE diff is release-ceremony files "
          f"(CHANGELOG.md and/or version markers from {args.manifest}) and carries no code.")
    print("\nThis is the exact shape of PRs #942, #944, #951 (2026-08-19/20 delay audit,")
    print("Recommendation R3): #944 alone sat 14.4h open and blocked two real fixes behind")
    print("it, for a one-line CHANGELOG entry.")
    print("\nFIX: fold this CHANGELOG entry + version bump into the PR that carries the fix")
    print("it documents. Run:")
    print('  scripts/bundle-release-in-branch.sh vX.Y.Z "description"')
    print("inside that PR's branch instead of opening a separate release PR. The annotated")
    print("tag is then cut automatically on merge by auto-tag-on-merge.yml -- do not open a")
    print("second PR for it. See CONTRIBUTING.md 'Release Ceremony Batching' for the full rule.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
