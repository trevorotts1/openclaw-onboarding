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

F24 items 5 and 12 add the 'sources' block: the release record must identify
the compatible onboarding, 999, shared launch contract and Command Center
versions, not only the ONB/CC pair. --n999-version/--n999-sha and
--cc-tag-object-sha are release-time inputs like --onb-sha; the
'command_center' and 'onboarding' entries are kept in lockstep with the
top-level fields rather than allowed to drift, and --check refuses a record
whose 'sources' block disagrees with them or omits a required distribution.
--verify-cc-tag proves cc_version's tag really peels to cc_sha on the live
remote, which is the check that would have caught the previous instance
naming v7.6.126 while carrying the v7.6.112 merge commit.

Usage:
  roll-release-cohort.py --repo-root DIR [--onb-sha SHA] [--cc-sha SHA]
                                  [--cc-tag-object-sha SHA]
                                  [--n999-version V] [--n999-sha SHA]
                                  [--check | --verify-cc-tag]

--check: report drift only. Writes nothing to disk. Exit 1 with a one-line
         diff if release-cohort.json is stale against /version and
         cc-compat.json (and, when given, --onb-sha/--cc-sha), if the
         'sources' block disagrees with the top-level fields, or if a
         required source distribution is missing; exit 0 if current.

--verify-cc-tag: consult the live remote for cc_version's tag and require its
         peeled commit to equal cc_sha. Writes nothing. Exit 0 when the tag
         peels to cc_sha, 1 when it does not (naming both), 2 on a tooling or
         network failure.

Exit codes:
  0  rolled (or, under --check, already current; or, under
     --verify-cc-tag, the tag peels to cc_sha)
  1  --check found drift (or --verify-cc-tag found a different commit)
  2  usage error, or a required input is missing/unreadable/malformed
     (repo-root, /version, cc-compat.json, its pinnedTag, release-cohort.json
     itself, or a SHA input that is not exactly 40 lowercase hex characters)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

COHORT_RELPATH = "release-cohort.json"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
# F24 item 5: the four distributions a launch release must name.
REQUIRED_SOURCES = ("onboarding", "n999", "command_center",
                    "shared_launch_contract")
_DOTTED = re.compile(r"^\d+(?:\.\d+)+$")


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


def _read_cc_repo(repo_root: str) -> str:
    path = os.path.join(repo_root, "cc-compat.json")
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        _die(f"{path} is not valid JSON: {exc}")
    repo = (data.get("commandCenter") or {}).get("repo")
    if not isinstance(repo, str) or "/" not in repo:
        _die(f"{path} missing commandCenter.repo (owner/name)")
    return repo


def _sources_drift(cohort: dict, onb_version: str, cc_version: str) -> list:
    """Every way the 'sources' block disagrees with the record (F24 items 5/12).

    The block is the record's own claim about WHICH distributions were tested,
    so it must not be able to describe a different set than the top-level
    fields it sits beside.
    """
    problems = []
    sources = cohort.get("sources")
    if not isinstance(sources, dict):
        return ["sources: missing (required by F24 item 5)"]
    for name in REQUIRED_SOURCES:
        if not isinstance(sources.get(name), dict):
            problems.append(f"sources.{name}: missing")
    onb = sources.get("onboarding") or {}
    cc = sources.get("command_center") or {}
    n999 = sources.get("n999") or {}
    shared = sources.get("shared_launch_contract") or {}
    if onb.get("version") != onb_version:
        problems.append(f"sources.onboarding.version: {onb.get('version')!r} "
                        f"!= onb_version {onb_version!r}")
    if onb.get("sha") != cohort.get("onb_sha"):
        problems.append(f"sources.onboarding.sha: {onb.get('sha')!r} "
                        f"!= onb_sha {cohort.get('onb_sha')!r}")
    if cc.get("version") != cc_version:
        problems.append(f"sources.command_center.version: "
                        f"{cc.get('version')!r} != cc_version {cc_version!r}")
    if cc.get("sha") != cohort.get("cc_sha"):
        problems.append(f"sources.command_center.sha: {cc.get('sha')!r} "
                        f"!= cc_sha {cohort.get('cc_sha')!r}")
    if not _HEX40.match(str(cc.get("tag_object_sha") or "")):
        problems.append("sources.command_center.tag_object_sha: must be exact "
                        "40-hex (the annotated tag object of cc_version)")
    if not _DOTTED.match(str(n999.get("version") or "")):
        problems.append("sources.n999.version: must be a dotted version")
    if not _HEX40.match(str(n999.get("sha") or "")):
        problems.append("sources.n999.sha: must be exact 40-hex")
    for key in ("launch_plan", "approval_record"):
        if not isinstance(shared.get(key), str) or not shared.get(key):
            problems.append(f"sources.shared_launch_contract.{key}: "
                            "must be a non-empty string")
    if not isinstance(shared.get("command_center_launch"), int):
        problems.append("sources.shared_launch_contract.command_center_launch: "
                        "must be an integer")
    return problems


def _peeled_tag_sha(repo: str, tag: str):
    """(tag_object_sha, peeled_commit_sha) for ``tag`` on the live remote.

    Uses `git ls-remote` so the check needs no clone and no credentials for a
    public repository. A lightweight tag shows the same SHA twice (the ref IS
    the commit); a missing tag returns (None, None).
    """
    url = f"https://github.com/{repo}.git"
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", url, f"refs/tags/{tag}*"],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        _die(f"cannot query {url}: {exc}")
    if proc.returncode != 0:
        _die(f"git ls-remote {url} failed: {proc.stderr.strip()}")
    direct = peeled = None
    for line in proc.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref == f"refs/tags/{tag}":
            direct = sha.strip()
        elif ref == f"refs/tags/{tag}^{{}}":
            peeled = sha.strip()
    if direct is None:
        return None, None
    return direct, (peeled or direct)


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
    parser.add_argument("--cc-tag-object-sha")
    parser.add_argument("--n999-version")
    parser.add_argument("--n999-sha")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verify-cc-tag", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root
    if not os.path.isdir(repo_root):
        _die(f"--repo-root {repo_root!r} is not a directory")

    for flag, value in (("onb-sha", args.onb_sha), ("cc-sha", args.cc_sha),
                        ("cc-tag-object-sha", args.cc_tag_object_sha),
                        ("n999-sha", args.n999_sha)):
        if value is not None:
            _validate_sha(flag, value)
    if args.n999_version is not None and not _DOTTED.match(args.n999_version):
        _die(f"--n999-version must be a dotted version, got "
             f"{args.n999_version!r}")

    onb_version = _read_version(repo_root)
    cc_version = _read_pinned_tag(repo_root)
    cohort = _read_cohort(repo_root)

    if args.verify_cc_tag:
        repo = _read_cc_repo(repo_root)
        tag_object, peeled = _peeled_tag_sha(repo, cc_version)
        if peeled is None:
            print(f"verify-cc-tag: {repo} has no tag {cc_version}")
            return 1
        recorded = cohort.get("cc_sha")
        print(f"verify-cc-tag: {repo} {cc_version} tag_object={tag_object} "
              f"peeled={peeled} recorded_cc_sha={recorded}")
        if peeled != recorded:
            print(f"verify-cc-tag: MISMATCH — {cc_version} peels to {peeled}, "
                  f"release-cohort.json records cc_sha {recorded}")
            return 1
        print(f"verify-cc-tag: OK — cc_sha is the peeled commit of "
              f"{cc_version}")
        return 0

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

    # F24 item 5: keep the 'sources' block derived from the top-level fields
    # instead of letting two descriptions of the same release drift apart.
    sources = dict(updated.get("sources") or {})
    onboarding = dict(sources.get("onboarding") or {})
    onboarding["version"] = updated.get("onb_version")
    onboarding["sha"] = updated.get("onb_sha")
    sources["onboarding"] = onboarding
    command_center = dict(sources.get("command_center") or {})
    command_center["version"] = updated.get("cc_version")
    command_center["sha"] = updated.get("cc_sha")
    if args.cc_tag_object_sha is not None:
        command_center["tag_object_sha"] = args.cc_tag_object_sha
    sources["command_center"] = command_center
    if args.n999_version is not None or args.n999_sha is not None:
        n999 = dict(sources.get("n999") or {})
        if args.n999_version is not None:
            n999["version"] = args.n999_version
        if args.n999_sha is not None:
            n999["sha"] = args.n999_sha
        sources["n999"] = n999
    updated["sources"] = sources

    diffs = []
    for key in ("onb_version", "cc_version", "onb_sha", "cc_sha"):
        if key in updated and cohort.get(key) != updated[key]:
            diffs.append(f"{key}: {cohort.get(key)!r} -> {updated[key]!r}")
    if cohort.get("sources") != updated["sources"]:
        diffs.append("sources: updated")

    problems = _sources_drift(updated, onb_version, cc_version)

    if args.check:
        if problems:
            print("release-cohort.json sources incomplete: "
                  + "; ".join(problems))
            return 1
        if diffs:
            print("release-cohort.json stale: " + "; ".join(diffs))
            return 1
        print(f"release-cohort.json up to date (onb_version={onb_version} "
              f"cc_version={cc_version} n999="
              f"{updated['sources']['n999'].get('version')})")
        return 0

    if problems:
        _die("release-cohort.json sources incomplete for a roll: "
             + "; ".join(problems))

    if not diffs:
        print(f"release-cohort.json already current (onb_version={onb_version} "
              f"cc_version={cc_version})")
        return 0

    _write_atomic(os.path.join(repo_root, COHORT_RELPATH), updated)
    print("release-cohort.json rolled: " + "; ".join(diffs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
