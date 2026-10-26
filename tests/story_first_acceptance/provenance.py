#!/usr/bin/env python3
"""Repository provenance for the S75-T32 acceptance cells. Stdlib only.

Round 4 proved the release claim was mintable by planting a directory: the only
identity test was `os.path.isdir(anchor)`, and the repository name was minted
from the flavour name alone. This module replaces that label with three facts
read from the root itself -- remote, revision, digest -- and refuses identity
when any of them cannot be established.

A cell may still EXECUTE without provenance. It may not claim it released a
repository, and the receipt refuses such a claim. Stdlib only; no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PINS_PATH = os.path.join(HERE, "provenance_pins.json")

_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def load_pins(path=None):
    """The declared repository, revision and digest per flavour."""
    with open(path or PINS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def normalize_remote(url):
    """`owner/repo` for any git remote spelling, or None."""
    if not url:
        return None
    value = url.strip()
    if value.startswith("git@"):
        rest = value.split("@", 1)[1]
        value = rest.replace(":", "/", 1)
    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    parts = [p for p in value.split("/") if p]
    if len(parts) < 2:
        return None
    return "/".join(parts[-2:])


def _git(path, *args):
    proc = subprocess.run(["git", "-C", path] + list(args),
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def tree_digest(top, revision, pathspec):
    """Digest of the tracked tree at `revision` under `pathspec`, or (None, why)."""
    rc, out, err = _git(top, "ls-tree", "-r", revision, "--", pathspec)
    if rc != 0:
        return None, "git ls-tree failed at %s: %s" % (revision, err or "no output")
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return None, "git ls-tree listed no blob at %s for %r" % (revision, pathspec)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(), None


def file_digest(root):
    """sha256 over (relpath, sha256(bytes)) for every file under `root`."""
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                entries.append("%s %s" % (os.path.relpath(path, root),
                                          hashlib.sha256(fh.read()).hexdigest()))
    if not entries:
        return None
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def pinned_revision_of(path):
    """The 40-hex revision an extracted tree is named by, or None."""
    probe = path
    while probe and probe != os.path.dirname(probe):
        if _HEX40.match(os.path.basename(probe)):
            return os.path.basename(probe)
        probe = os.path.dirname(probe)
    return None


def resolve(skill_root, expected_repository=None, pin=None):
    """Prove one skill root's repository identity, or refuse it with reasons.

    git worktree  -> remote from `remote.origin.url`, revision from HEAD, digest
                     from `git ls-tree` of the root at that revision.
    pinned archive -> revision from an ancestor directory name, digest from the
                     bytes on disk, and BOTH must match the declared pin. A tree
                     named by a revision but carrying unattributed bytes is
                     refused: the name is not the evidence.
    """
    out = {
        "declared_repository": expected_repository,
        "identity_proven": False,
        "proven_repository": None,
        "mode": "unresolved",
        "remote": None,
        "remote_url": None,
        "revision": None,
        "revision_source": None,
        "digest": None,
        "digest_scope": None,
        "pin": dict(pin) if pin else None,
        "refusals": [],
    }
    if not skill_root or not os.path.isdir(skill_root):
        out["refusals"].append(
            "no directory at %r, so no repository identity can be read" % (skill_root,))
        return out

    root = os.path.realpath(skill_root)
    rc, top, _ = _git(root, "rev-parse", "--show-toplevel")
    if rc == 0 and top:
        out["mode"] = "git-worktree"
        rc_url, url, _ = _git(root, "remote", "get-url", "origin")
        rc_rev, revision, _ = _git(root, "rev-parse", "HEAD")
        out["remote_url"] = url or None
        out["remote"] = normalize_remote(url) if rc_url == 0 else None
        out["revision"] = revision if _HEX40.match(revision or "") else None
        out["revision_source"] = "git worktree HEAD"
        rel = os.path.relpath(root, top) or "."
        out["digest_scope"] = "git ls-tree -r %s -- %s" % (out["revision"], rel)
        if out["revision"]:
            digest, why = tree_digest(top, out["revision"], rel)
            out["digest"] = digest
            if why:
                out["refusals"].append(why)
        if rc_url != 0 or not out["remote"]:
            out["refusals"].append("no readable origin remote in this worktree")
        if not out["revision"]:
            out["refusals"].append("HEAD is not a 40-hex revision")
    else:
        out["mode"] = "pinned-archive"
        revision = pinned_revision_of(root)
        out["revision"] = revision
        out["revision_source"] = (
            "an ancestor directory names its revision" if revision else None)
        out["digest_scope"] = "sha256 over every file under the root"
        if not revision:
            out["refusals"].append(
                "not inside a git worktree and no ancestor directory names a "
                "40-hex revision; an extracted tree must be named by its revision")
            return out
        out["digest"] = file_digest(root)
        if not out["digest"]:
            out["refusals"].append("the extracted tree holds no files to digest")
        if not pin:
            out["refusals"].append(
                "no pin record for this repository, so the extracted tree's "
                "bytes are unattributed")

    if expected_repository:
        if out["mode"] == "git-worktree" and out["remote"] \
                and out["remote"] != expected_repository:
            out["refusals"].append(
                "origin is %s, not the declared %s"
                % (out["remote"], expected_repository))
    if pin:
        if pin.get("repository") != expected_repository:
            out["refusals"].append(
                "the pin declares %r, not the declared %r"
                % (pin.get("repository"), expected_repository))
        if pin.get("revision") and pin["revision"] != out["revision"]:
            out["refusals"].append(
                "the pin names revision %s, the root is at %s"
                % (pin["revision"], out["revision"]))
        if pin.get("digest"):
            if pin["digest"] != out["digest"]:
                out["refusals"].append(
                    "tree digest %s does not match the pinned %s"
                    % (out["digest"], pin["digest"]))
        elif out["mode"] == "pinned-archive":
            out["refusals"].append(
                "the pin declares no tree digest, so this tree's bytes cannot be "
                "attributed to the repository it is named after")

    out["identity_proven"] = not out["refusals"]
    if out["identity_proven"]:
        out["proven_repository"] = out["remote"] or (pin or {}).get("repository")
    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root")
    parser.add_argument("--repository", default=None)
    parser.add_argument("--pin", default=None)
    args = parser.parse_args()
    pin = None
    if args.pin:
        pin = load_pins().get(args.pin)
    json.dump(resolve(args.skill_root, args.repository, pin),
              __import__("sys").stdout, indent=2, sort_keys=True)
    __import__("sys").stdout.write("\n")
