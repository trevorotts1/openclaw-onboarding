#!/usr/bin/env python3
"""pin-cc-tag.py — move the Command Center pin in BOTH files in one shot.

WHY: the CC pin lives in two files that must never disagree —
cc-compat.json commandCenter.pinnedTag (read by shared-utils/cc_compat.py for
fleet-refresh + the skill-32 installer) and release-cohort.json cc_version
(the tested pair the decision-engine trainer gates promotion on). Nothing
wrote pinnedTag: scripts/bump-version.sh rolls release-cohort's cc_version
FROM cc-compat.json (step 14 via scripts/roll-release-cohort.py), so a hand
edit of either file can silently leave the pair split. This is the roll step
for the pin itself, the same way roll-release-cohort.py is the roll step for
the cohort versions.

The tag value is the ONE input the release step supplies (the CC release is
cut in a different repo, trevorotts1/blackceo-command-center):

  scripts/pin-cc-tag.py --repo-root . v7.6.91

Both files are rewritten atomically (temp file + os.replace, the repo's
convention — see roll-release-cohort.py _write_atomic), and if the second write
fails the first is rolled back from memory, so the pair is never left split.
Git holds the previous bytes (`git checkout -- cc-compat.json release-cohort.json`
undoes a bump). The pin never moves below cc-compat.json's commandCenter.minVersion
(cc_compat.assert_min_version); a minVersion move is a separate, reviewed release
decision, not a side effect.

Derived tokens are rolled by scripts/bump-version.sh in the release step:
README.md "Paired Command Center: **vX.Y.Z**" (step 13) and release-cohort.json
cc_version (step 14, idempotent against this script). Two hand-authored doc
lines are NOT auto-rolled by anything — after a real bump, edit them and run
the guards: DIRECT-TO-AGENT-UPDATE-MESSAGE.md "pairs with Command Center
vX.Y.Z" and docs/interview-launch-recovery.md "Paired releases: ... Command
Center vX.Y.Z" (scripts/check-doc-currency-guards.sh), plus
scripts/check-readme-current-release.sh.

Usage:
  pin-cc-tag.py --repo-root DIR <new-tag>   # vX.Y.Z, exact
  pin-cc-tag.py --repo-root DIR --check     # report only; writes nothing

Exit codes:
  0  pin moved (or already current, or --check found the pair agreeing)
  1  --check found the two files disagreeing
  2  usage error, refusal (bad tag, tag < minVersion), or a write failed
     (the pair was rolled back to its previous, agreeing value)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")


def _die(msg: str) -> "NoReturn":
    print(f"pin-cc-tag: {msg}", file=sys.stderr)
    sys.exit(2)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        _die(f"cannot read {path}: {exc}")


def _write_atomic(path: str, payload: dict) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2))
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("tag", nargs="?", help="new CC tag, exact vX.Y.Z (the value the release step supplies)")
    parser.add_argument("--check", action="store_true", help="report the pair's agreement only; write nothing")
    args = parser.parse_args(argv)

    repo_root = args.repo_root
    if not os.path.isdir(repo_root):
        _die(f"--repo-root {repo_root!r} is not a directory")
    if args.check and args.tag:
        _die("--check takes no tag (it writes nothing)")

    compat_path = os.path.join(repo_root, "cc-compat.json")
    cohort_path = os.path.join(repo_root, "release-cohort.json")
    for p in (compat_path, cohort_path):
        if not os.path.isfile(p):
            _die(f"{p} not found")

    # Validate cc-compat.json through the repo's single source of truth.
    sys.path.insert(0, os.path.join(repo_root, "shared-utils"))
    try:
        from cc_compat import load_cc_compat, assert_min_version  # type: ignore
    except ImportError as exc:
        _die(f"cannot import shared-utils/cc_compat.py: {exc}")

    try:
        compat = load_cc_compat(Path(repo_root))
    except (ValueError, FileNotFoundError) as exc:
        _die(f"cc-compat.json is not valid: {exc}")
    pinned = compat["commandCenter"].get("pinnedTag")
    if not isinstance(pinned, str) or not pinned:
        _die("cc-compat.json commandCenter.pinnedTag is missing; bump it by hand once, then this tool keeps it in lockstep")

    try:
        cohort = json.loads(_read_text(cohort_path))
    except json.JSONDecodeError as exc:
        _die(f"{cohort_path} is not valid JSON: {exc}")
    if not isinstance(cohort, dict):
        _die(f"{cohort_path} must be a JSON object")
    cur_cc = cohort.get("cc_version")

    if args.check:
        if pinned == cur_cc:
            print(f"pin files agree: cc-compat.json pinnedTag == release-cohort.json cc_version == {pinned}")
            return 0
        print(f"DRIFT: cc-compat.json pinnedTag={pinned!r} != release-cohort.json cc_version={cur_cc!r}")
        return 1

    tag = args.tag
    if not tag:
        _die("a new tag is required: pin-cc-tag.py --repo-root DIR vX.Y.Z")
    if not _TAG_RE.match(tag):
        _die(f"tag must be an exact vX.Y.Z (the CC release tag as cut), got {tag!r}")
    try:
        assert_min_version(tag, compat)
    except ValueError as exc:
        _die(f"refusing {tag}: {exc} "
             "(the pin never moves below minVersion; move minVersion only in a reviewed release step)")

    if pinned == tag and cur_cc == tag:
        print(f"pin already {tag} in both files; nothing to do")
        return 0

    raw_compat = json.loads(_read_text(compat_path))
    new_compat = dict(raw_compat)
    new_compat["commandCenter"] = dict(raw_compat["commandCenter"])
    new_compat["commandCenter"]["pinnedTag"] = tag
    new_cohort = dict(cohort)
    new_cohort["cc_version"] = tag

    _write_atomic(compat_path, new_compat)
    try:
        _write_atomic(cohort_path, new_cohort)
    except BaseException as exc:
        _write_atomic(compat_path, raw_compat)  # roll the first file back; the pair still agrees
        _die(f"writing release-cohort.json failed ({exc}); cc-compat.json was rolled back to {pinned!r} "
             "— the pair still agrees on the previous value")

    # Prove both landed on the same value before reporting success.
    after_compat = json.loads(_read_text(compat_path))["commandCenter"].get("pinnedTag")
    after_cohort = json.loads(_read_text(cohort_path)).get("cc_version")
    if after_compat != tag or after_cohort != tag:
        _write_atomic(compat_path, raw_compat)
        _write_atomic(cohort_path, cohort)
        _die(f"post-write check failed (pinnedTag={after_compat!r} cc_version={after_cohort!r}); both files rolled back")

    print(f"cc-compat.json: pinnedTag {pinned!r} -> {tag!r}")
    print(f"release-cohort.json: cc_version {cur_cc!r} -> {tag!r}")
    print("REMINDER: run scripts/bump-version.sh in the release step (rolls README + release-cohort from the pin), "
          "edit the two hand-authored doc lines (DIRECT-TO-AGENT-UPDATE-MESSAGE.md, docs/interview-launch-recovery.md), "
          "then run scripts/check-doc-currency-guards.sh and scripts/check-readme-current-release.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
