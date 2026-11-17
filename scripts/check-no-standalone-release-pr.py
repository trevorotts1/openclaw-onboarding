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
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MARKERS_MANIFEST = "scripts/version-markers.json"

# Files that scripts/bump-version.sh / the release procedure rewrites but that are
# NOT in the markers manifest (they track the repo version without being one of the
# 10 drift-checked markers). A change to these that only moves version numbers is
# release ceremony. v28.0.0: a pure bump used to slip past this guard because these
# files (and the README / update-skills.sh relabel lines) counted as real code.
EXTRA_CEREMONY_FILES = {
    "release-cohort.json",
    "scripts/agent-browser-reaper.sh",
    "scripts/guard-agent-browser-managed.sh",
    "docs/interview-launch-recovery.md",
}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def release_file_set(manifest_path: Path) -> set[str]:
    """CHANGELOG.md plus every 'file' entry in the version-markers manifest.

    Falls back to CHANGELOG.md alone (and prints a loud warning) if the
    manifest is missing, rather than silently under-scoping the guard.
    """
    files = {"CHANGELOG.md"} | EXTRA_CEREMONY_FILES
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


def marker_patterns(manifest_path: Path) -> dict[str, str]:
    """file -> regex pattern for markers that can PROVE a change is ceremony-only.

    A marker file (install.sh, scripts/bump-version.sh, ...) is also ordinary
    code. Treating the whole file as a release file makes any real fix in it
    look like a release-ceremony PR. Only a change whose every added/removed
    line matches the marker's own pattern is ceremony.
    """
    out: dict[str, str] = {}
    if not manifest_path.exists():
        return out
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for marker in data.get("markers", []):
        f = marker.get("file")
        pattern = marker.get("pattern")
        if f and pattern and marker.get("type") == "regex":
            out[f] = pattern
    return out


def _version_rx(versions: list[str]):
    """Regex matching exactly the given onboarding versions (with or without a
    leading v), not as part of a longer dotted number."""
    alts = "|".join(re.escape(v.lstrip("v")) for v in versions if v)
    return re.compile(r"(?<!\d)(?<!\d\.)v?(?:" + alts + r")(?!\d)(?!\.\d)") if alts else None


def _normalize_json(node, rx):
    if isinstance(node, str):
        return rx.sub("X.Y.Z", node) if rx else node
    if isinstance(node, list):
        return [_normalize_json(n, rx) for n in node]
    if isinstance(node, dict):
        return {k: _normalize_json(v, rx) for k, v in node.items()}
    return node


def only_version_numbers_changed(file: str, base: str, head: str) -> bool:
    """True when `file` differs between base and head ONLY by the ONBOARDING
    version moving from the base /version value to the head /version value
    (with or without a leading v). Covers every line bump-version.sh writes,
    including the README / update-skills.sh relabel lines and the bumper's JSON
    re-serialisation. Any other semver change (a Command Center re-pin, a
    minVersion, the n999 version, ...) is real code, not ceremony. A file added
    or deleted by the PR is never ceremony, nor is a PR that does not move /version."""
    merge_base = git("merge-base", base, head)
    base_point = merge_base.stdout.strip() if merge_base.returncode == 0 and merge_base.stdout.strip() else base
    old_v = git("show", f"{base_point}:version")
    new_v = git("show", f"{head}:version")
    if old_v.returncode != 0 or new_v.returncode != 0:
        return False
    old_ver, new_ver = old_v.stdout.strip(), new_v.stdout.strip()
    if not old_ver or old_ver == new_ver:
        return False
    rx = _version_rx([old_ver, new_ver])
    old = git("show", f"{base_point}:{file}")
    new = git("show", f"{head}:{file}")
    if old.returncode != 0 or new.returncode != 0:
        return False
    if file.endswith(".json"):
        try:
            return _normalize_json(json.loads(old.stdout), rx) == _normalize_json(json.loads(new.stdout), rx)
        except json.JSONDecodeError:
            pass
    return rx.sub("X.Y.Z", old.stdout) == rx.sub("X.Y.Z", new.stdout)


def is_ceremony_only(file: str, pattern: str, base: str, head: str) -> bool:
    """True when every changed line in `file` matches the marker pattern."""
    merge_base = git("merge-base", base, head)
    base_point = merge_base.stdout.strip() if merge_base.returncode == 0 and merge_base.stdout.strip() else base
    diff = git("diff", "-U0", base_point, head, "--", file)
    if diff.returncode != 0:
        return False
    changed = [
        line[1:].strip()
        for line in diff.stdout.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
        and line[1:].strip()
    ]
    if not changed:
        return True
    rx = re.compile(pattern)
    return all(rx.search(line) for line in changed)


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

    patterns = marker_patterns(Path(args.manifest))
    non_release = []
    for f in files:
        if f not in release_files:
            non_release.append(f)
        elif f == "CHANGELOG.md":
            continue
        elif only_version_numbers_changed(f, args.base, args.head):
            continue
        elif f in patterns and is_ceremony_only(f, patterns[f], args.base, args.head):
            continue
        else:
            # The file IS a release file, but this PR changed more than version
            # numbers / marker lines inside it: that is real code.
            non_release.append(f)

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
