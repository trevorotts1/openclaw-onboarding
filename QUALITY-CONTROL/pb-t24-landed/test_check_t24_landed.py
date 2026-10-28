#!/usr/bin/env python3
"""Self-check for check_t24_landed.py. Asserts only; no framework.

Run: python3 QUALITY-CONTROL/pb-t24-landed/test_check_t24_landed.py [--repo PATH]
"""
import argparse, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check_t24_landed.py")
T24_HEAD = "dc3a1503c0819cc1a7fcf05faba34e752ae50bb3"

def run(repo, *args):
    return subprocess.run([sys.executable, CHECK, "--repo", repo, *args],
                          capture_output=True, text=True)

def git(repo, *args, stdin=None):
    return subprocess.run(["git", "-C", repo, *args], input=stdin,
                          capture_output=True, text=True, errors="replace")

def dangling_commit(repo, marker):
    """A real commit object whose content is NOT on any branch."""
    blob = git(repo, "hash-object", "-w", "--stdin", stdin=marker + "\n").stdout.strip()
    tree = git(repo, "mktree", stdin="100644 blob %s\tnot-on-main.txt\n" % blob).stdout.strip()
    return git(repo, "commit-tree", tree, "-m", "negative control " + marker).stdout.strip()

def reshaped_copy(repo, rev):
    """Same tree and parent as rev, different sha: a squash of the same change."""
    tree = git(repo, "rev-parse", rev + "^{tree}").stdout.strip()
    parent = git(repo, "rev-parse", rev + "^").stdout.strip()
    return git(repo, "commit-tree", tree, "-p", parent,
               "-m", "reshaped copy of " + rev[:8]).stdout.strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.abspath(os.path.join(HERE, "..", "..")))
    a = ap.parse_args()
    repo = a.repo
    failures = []

    # 1. POSITIVE: T-24's real head must be provably on main.
    r = run(repo, "--head", T24_HEAD)
    print("positive  rc=%d %s" % (r.returncode, r.stdout.strip()))
    if r.returncode != 0:
        failures.append("T-24 head not landed (rc=%d)" % r.returncode)

    # 2. SQUASH-SHAPED POSITIVE: sha not preserved, identical content must still pass
    #    through the content-fingerprint branch (not the ancestry shortcut).
    copy = reshaped_copy(repo, T24_HEAD)
    not_ancestor = git(repo, "merge-base", "--is-ancestor", copy, "origin/main").returncode != 0
    r = run(repo, "--head", copy)
    print("reshape   rc=%d %s" % (r.returncode, r.stdout.strip()))
    if not not_ancestor:
        failures.append("reshaped copy is an ancestor; control does not test the fingerprint path")
    if r.returncode != 0 or "content fingerprint" not in r.stdout:
        failures.append("squash-shaped positive did not pass by fingerprint (rc=%d)" % r.returncode)

    # 3. NEGATIVE CONTROL: content absent from main must fail the same check.
    marker = "pbb688-negative-control-" + str(os.getpid())
    neg = dangling_commit(repo, marker)
    r = run(repo, "--head", neg)
    print("negative  rc=%d %s" % (r.returncode, r.stdout.strip()))
    if r.returncode != 1 or not r.stdout.startswith("NOT LANDED"):
        failures.append("negative control did not fail with a verdict (rc=%d)" % r.returncode)
    else:
        print("negative control FAILED the check as required, with a verdict not a crash")

    # 4. INSTRUMENT ERROR: an unresolvable sha is an abort, never a verdict.
    r = run(repo, "--head", "0" * 40)
    print("abort     rc=%d %s" % (r.returncode, r.stdout.strip()))
    if r.returncode != 2:
        failures.append("unresolvable head did not abort with 2 (rc=%d)" % r.returncode)

    # 5. The negative control's own sha must not be an ancestor of main.
    if git(repo, "merge-base", "--is-ancestor", neg, "origin/main").returncode == 0:
        failures.append("negative control is an ancestor of main; control is invalid")

    print("RESULT:", "PASS" if not failures else "FAIL: " + "; ".join(failures))
    return 0 if not failures else 1

if __name__ == "__main__":
    sys.exit(main())
