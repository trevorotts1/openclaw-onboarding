#!/usr/bin/env python3
"""Prove a unit's change reached the target branch, squash or not.

Exit 0 = content present on target; 1 = absent; 2 = instrument error.
Ancestry is tried first (the correct invocation when commits are preserved).
Otherwise the unit's patch-id fingerprint is looked for among the target's
commits that touch the same paths, which survives a squash that rewrites the sha.
"""
import argparse, subprocess, sys

T24_PATHS = [
    ".github/workflows/qc-static.yml",
    "38-conversational-ai-system/scripts/qc-pb-contracts.sh",
    "38-conversational-ai-system/tools/tests/test_pb_contracts.py",
    "38-conversational-ai-system/tools/pb_contracts.py",
]

def git(repo, *args, stdin=None):
    return subprocess.run(["git", "-C", repo, *args], input=stdin,
                          capture_output=True, text=True, errors="replace")

def patch_id(repo, rev):
    parents = git(repo, "rev-list", "--parents", "-n", "1", rev).stdout.split()
    diff_arg = ["diff", parents[1], rev] if len(parents) > 2 else ["show", "--format=", rev]
    d = git(repo, *diff_arg)
    if d.returncode != 0:
        return None
    out = git(repo, "patch-id", "--stable", stdin=d.stdout)
    line = out.stdout.strip().split()
    return line[0] if line else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--head", required=True)
    ap.add_argument("--target", default="origin/main")
    ap.add_argument("--paths", nargs="*", default=T24_PATHS)
    a = ap.parse_args()

    for rev in (a.head, a.target):
        if git(a.repo, "cat-file", "-e", rev + "^{commit}").returncode != 0:
            print("INSTRUMENT ERROR: %s does not name a commit" % rev)
            return 2

    if git(a.repo, "merge-base", "--is-ancestor", a.head, a.target).returncode == 0:
        print("LANDED: %s is an ancestor of %s (commits preserved)" % (a.head[:8], a.target))
        return 0

    wanted = patch_id(a.repo, a.head)
    if wanted is None:
        print("INSTRUMENT ERROR: cannot compute patch-id for %s" % a.head)
        return 2
    candidates = git(a.repo, "rev-list", "--no-merges", a.target, "--", *a.paths).stdout.split()
    for sha in candidates:
        if patch_id(a.repo, sha) == wanted:
            print("LANDED: %s carries %s's content fingerprint %s (sha not preserved)"
                  % (sha[:8], a.head[:8], wanted[:12]))
            return 0
    print("NOT LANDED: no commit on %s carries %s's content fingerprint %s"
          % (a.target, a.head[:8], wanted[:12]))
    return 1

if __name__ == "__main__":
    sys.exit(main())
