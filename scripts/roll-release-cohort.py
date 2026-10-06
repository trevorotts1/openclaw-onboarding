#!/usr/bin/env python3
"""roll-release-cohort.py — keep release-cohort.json's onb_version/cc_version
in lockstep with the repo's own /version and cc-compat.json pinnedTag.

WHY: release-cohort.json (spec 14.8/17.4) pins the tested onb_version +
cc_version pair that shared-utils/decision_engine_train/train.py's
check_release_cohort()/promote() gate JEV promotion on. Nothing rolled it on
a version bump, so it drifted stale on every release (caught by
tests/unit/test_release_cohort_manifest.py::test_instance_versions_match_live_repo_contracts).
This script is the roll step; scripts/bump-version.sh calls it (without
--onb-sha/--cc-sha) right after /version is rewritten, exactly like the
existing README "Paired Command Center" token derived from cc-compat.json's
pinnedTag a few lines above it.

onb_sha/cc_sha are NOT rolled automatically — they are set at release time
(once the release is actually tested) via --onb-sha/--cc-sha to the tested
ONB main tip and the peeled SHA of the pinned CC tag. A bump only refreshes
the two version strings; the SHA pair is a separate, deliberate act.

Usage:
  roll-release-cohort.py --repo-root DIR [--onb-sha SHA] [--cc-sha SHA] [--check]

--check: report drift only. Writes nothing to disk. Exit 1 with a one-line
         diff if release-cohort.json is stale against /version and
         cc-compat.json (and, when given, --onb-sha/--cc-sha); exit 0 if
         current.

Exit codes:
  0  rolled (or, under --check, already current)
  1  --check found drift
  2  usage error, or a required input is missing/unreadable/malformed
     (repo-root, /version, cc-compat.json, its pinnedTag, release-cohort.json
     itself, or a --onb-sha/--cc-sha that is not exactly 40 lowercase hex
     characters)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

COHORT_RELPATH = "release-cohort.json"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _die(msg: str) -> "NoReturn":
    print(f"roll-release-cohort: {msg}", file=sys.stderr)
    sys.exit(2)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        _die(f"cannot read {path}: {exc}")


def _read_version(repo_root: str) -> str:
    path = os.path.join(repo_root, "version")
    value = _read_text(path).strip()
    if not value:
        _die(f"{path} is empty")
    return value


def _read_pinned_tag(repo_root: str) -> str:
    path = os.path.join(repo_root, "cc-compat.json")
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        _die(f"{path} is not valid JSON: {exc}")
    tag = (data.get("commandCenter") or {}).get("pinnedTag")
    if not isinstance(tag, str) or not tag:
        _die(f"{path} missing commandCenter.pinnedTag")
    return tag


def _read_cohort(repo_root: str) -> dict:
    path = os.path.join(repo_root, COHORT_RELPATH)
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        _die(f"{path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        _die(f"{path} must be a JSON object")
    return data


def _validate_sha(flag: str, value: str) -> None:
    if not _HEX40.match(value or ""):
        _die(f"--{flag} must be exactly 40 lowercase hex characters, got {value!r}")


def _write_atomic(path: str, payload: dict) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".release-cohort.", dir=directory)
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
    parser.add_argument("--onb-sha")
    parser.add_argument("--cc-sha")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root
    if not os.path.isdir(repo_root):
        _die(f"--repo-root {repo_root!r} is not a directory")

    if args.onb_sha is not None:
        _validate_sha("onb-sha", args.onb_sha)
    if args.cc_sha is not None:
        _validate_sha("cc-sha", args.cc_sha)

    onb_version = _read_version(repo_root)
    cc_version = _read_pinned_tag(repo_root)
    cohort = _read_cohort(repo_root)

    # dict() copy preserves the original's key ORDER; reassigning an existing
    # key in place never moves it, so untouched keys (contract, notes, and
    # onb_sha/cc_sha when not supplied) keep their position and their value.
    updated = dict(cohort)
    updated["onb_version"] = onb_version
    updated["cc_version"] = cc_version
    if args.onb_sha is not None:
        updated["onb_sha"] = args.onb_sha
    if args.cc_sha is not None:
        updated["cc_sha"] = args.cc_sha

    diffs = []
    for key in ("onb_version", "cc_version", "onb_sha", "cc_sha"):
        if key in updated and cohort.get(key) != updated[key]:
            diffs.append(f"{key}: {cohort.get(key)!r} -> {updated[key]!r}")

    if args.check:
        if diffs:
            print("release-cohort.json stale: " + "; ".join(diffs))
            return 1
        print(f"release-cohort.json up to date (onb_version={onb_version} cc_version={cc_version})")
        return 0

    if not diffs:
        print(f"release-cohort.json already current (onb_version={onb_version} cc_version={cc_version})")
        return 0

    _write_atomic(os.path.join(repo_root, COHORT_RELPATH), updated)
    print("release-cohort.json rolled: " + "; ".join(diffs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
