#!/usr/bin/env python3
"""
pr_truth_core.py -- logic engine for `pr-truth.sh <pr>`.

Three independent checks, each targeting a specific confirmed form of THE
DISEASE (status asserted from a name/pointer instead of diffed from
content):

  --zombie          form 4 (zombie PR: content merged, PR still shows open)
                     AND form 7 (GitHub's state:merged EXCLUDES manually-
                     pushed merges -- this NEVER scopes to state:merged;
                     it always does a live content diff regardless of what
                     GitHub's PR state field says).
  --stale-ref SHA   form 5 (stale-ref merge: the merge commit's non-main
                     parent is an OLDER point on the branch than its real,
                     live head -- ancestry of that older point looks
                     perfect and proves nothing about the real head).
  --supersedes PR   form 9 ("supersedes X, close X" from a stale snapshot --
                     must be diffed live, both ways, right now; must be
                     able to answer NO).

Every check operates on git tree/blob content, never on GitHub's PR
`state`/`merged` fields for its verdict (those are read only to locate the
PR's head ref) -- see each function's docstring.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "ledger_reconciler_core", _HERE / "ledger_reconciler_core.py"
)
assert _spec is not None and _spec.loader is not None
lrc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lrc)  # type: ignore

sh = lrc.sh
sh_ok = lrc.sh_ok


def gh_pr_view(owner_repo, pr_number):
    """Read-only PR metadata via `gh pr view --json`. Used ONLY to find the
    PR's baseRefName/headRefName/headRefOid and human-readable state --
    NEVER used as the source of truth for any verdict (state:merged is
    explicitly excluded from all verdicts here, per form 7)."""
    cmd = [
        "gh", "pr", "view", str(pr_number), "--repo", owner_repo,
        "--json", "number,title,state,headRefName,headRefOid,baseRefName,mergeCommit,mergedAt,url",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None, r.stderr.strip()
    try:
        return json.loads(r.stdout), None
    except Exception as e:
        return None, f"could not parse gh pr view output: {e}"


def ensure_fetched(repo_dir, refs):
    """Best-effort `git fetch` for each ref (branch name or SHA) so
    ancestry/diff operations below have the objects locally. Tolerant of
    already-local objects and of refs that no longer exist on origin
    (e.g. a deleted PR branch -- caller must handle that case using the
    SHA directly, which may still be fetchable even if the ref is gone,
    or may need `git fetch origin <sha>` support from the remote)."""
    for ref in refs:
        if not ref:
            continue
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "-q", "origin", ref],
                        capture_output=True, text=True)


def commit_exists(repo_dir, sha):
    ok, out, _ = sh_ok(repo_dir, ["rev-parse", "--verify", "-q", f"{sha}^{{commit}}"])
    return (out.strip() if ok else None)


def is_ancestor(repo_dir, sha, ref="origin/main"):
    ok, _, _ = sh_ok(repo_dir, ["merge-base", "--is-ancestor", sha, ref])
    return bool(ok)


def merge_base(repo_dir, a, b):
    ok, out, _ = sh_ok(repo_dir, ["merge-base", a, b])
    return out.strip() if ok else None


def changed_paths(repo_dir, a, b):
    out = sh(repo_dir, ["diff", "--name-only", a, b])
    return [l for l in out.splitlines() if l.strip()]


def diff_stat(repo_dir, a, b, paths=None):
    args = ["diff", "--stat", a, b]
    if paths:
        args += ["--"] + paths
    r = subprocess.run(["git", "-C", str(repo_dir)] + args, capture_output=True, text=True)
    return r.stdout.strip()


def ls_tree(repo_dir, ref):
    """{path: blob_sha} for every blob in ref's tree, recursive."""
    out = sh(repo_dir, ["ls-tree", "-r", ref])
    result = {}
    for line in out.splitlines():
        # "<mode> blob <sha>\t<path>"
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3:
            result[path] = parts[2]
    return result


# --------------------------------------------------------------------------
# --zombie : is this PR's content already on main? DEEP CONTENT DIFF, never
# ancestry alone, and NEVER scoped to GitHub's state:merged (form 7).
# --------------------------------------------------------------------------

def check_zombie(repo_dir, owner_repo, pr_number):
    meta, err = gh_pr_view(owner_repo, pr_number)
    if meta is None:
        return {"verdict": "UNKNOWN", "reason": f"gh pr view failed: {err}"}

    head_sha = meta.get("headRefOid")
    head_ref = meta.get("headRefName")
    if not head_sha:
        return {"verdict": "UNKNOWN", "reason": "PR has no headRefOid (deleted/inaccessible head)."}

    ensure_fetched(repo_dir, [head_ref, head_sha])
    resolved = commit_exists(repo_dir, head_sha)
    if not resolved:
        return {
            "verdict": "UNKNOWN",
            "reason": f"head sha {head_sha} not resolvable in local clone even after fetch "
                      f"(branch may be deleted upstream with objects pruned).",
            "gh_state": meta.get("state"),
        }

    ancestor = is_ancestor(repo_dir, resolved)
    mb = merge_base(repo_dir, resolved, "origin/main")
    touched = changed_paths(repo_dir, mb, resolved) if mb else []

    if ancestor:
        return {
            "verdict": "ZOMBIE", "confidence": "PROVED (ancestry)",
            "reason": f"head `{resolved[:8]}` is a direct ancestor of `origin/main` -- its content "
                      f"is definitionally already there, regardless of GitHub PR state "
                      f"(`{meta.get('state')}`).",
            "gh_state": meta.get("state"), "head_sha": resolved, "touched_paths": touched,
        }

    # Ancestry says NO -- this is exactly the case ancestry-only checks get
    # wrong (a real zombie whose content landed via squash/rebase/manual
    # reimplementation carries a DIFFERENT commit sha, so ancestry alone
    # reports a false "not merged"). Deep content diff: for every path the
    # PR touches, does origin/main's CURRENT version of that path already
    # match the PR head's version, byte-for-byte?
    if not mb:
        return {"verdict": "UNKNOWN", "reason": "no merge-base found between head and origin/main."}

    identical, differing, missing_on_main = [], [], []
    head_tree = ls_tree(repo_dir, resolved)
    main_tree = ls_tree(repo_dir, "origin/main")
    for path in touched:
        head_blob = head_tree.get(path)
        main_blob = main_tree.get(path)
        if main_blob is None:
            missing_on_main.append(path)
        elif head_blob == main_blob:
            identical.append(path)
        else:
            differing.append(path)

    if touched and not differing and not missing_on_main:
        verdict = "ZOMBIE"
        confidence = "PROVED (content-identical despite non-ancestor history)"
    elif identical and (differing or missing_on_main):
        verdict = "PARTIAL"
        confidence = f"{len(identical)}/{len(touched)} touched paths already content-identical on main"
    else:
        verdict = "NOT-ZOMBIE"
        confidence = "no touched path is content-identical on main"

    return {
        "verdict": verdict, "confidence": confidence,
        "reason": f"ancestry=False; deep content diff of {len(touched)} touched path(s): "
                  f"{len(identical)} identical on main, {len(differing)} differ, "
                  f"{len(missing_on_main)} entirely absent from main.",
        "gh_state": meta.get("state"), "head_sha": resolved,
        "touched_paths": touched, "identical": identical, "differing": differing,
        "missing_on_main": missing_on_main,
    }


# --------------------------------------------------------------------------
# --stale-ref <merge-sha> : does the merge commit's non-main parent match
# the PR's LIVE HEAD? Ancestry of that parent alone cannot catch this --
# the parent IS a true ancestor of main, it is simply not the real tip.
# --------------------------------------------------------------------------

def check_stale_ref(repo_dir, owner_repo, pr_number, merge_sha):
    meta, err = gh_pr_view(owner_repo, pr_number)
    if meta is None:
        return {"verdict": "UNKNOWN", "reason": f"gh pr view failed: {err}"}

    resolved_merge = commit_exists(repo_dir, merge_sha)
    if not resolved_merge:
        ensure_fetched(repo_dir, [merge_sha])
        resolved_merge = commit_exists(repo_dir, merge_sha)
    if not resolved_merge:
        return {"verdict": "UNKNOWN", "reason": f"merge-sha {merge_sha} not found in {owner_repo} after fetch."}

    parents_out = sh(repo_dir, ["log", "-1", "--format=%P", resolved_merge])
    parents = parents_out.split()
    if len(parents) < 2:
        return {
            "verdict": "UNKNOWN",
            "reason": f"{resolved_merge[:8]} has {len(parents)} parent(s) -- not a two-parent merge "
                      f"commit; --stale-ref only applies to real `git merge --no-ff` commits.",
        }

    # Use git's own, standard parent-ORDER convention to identify the
    # branch-side parent -- NOT an ancestor-of-main test. Ancestor-of-main
    # is unusable here: once `resolved_merge` itself is part of main's
    # history (which it always is, by the time anyone is running this
    # check), EVERY one of its parents is trivially an ancestor of main
    # too (a parent of a commit on main is itself always an ancestor of
    # main) -- that test cannot distinguish "was main's tip before this
    # merge" from "was the incoming branch's tip". `git merge --no-ff`
    # (and GitHub's own merge-commit construction) always records parent 1
    # as the branch that was checked out (mainline) and parent 2 as the
    # branch being merged in -- that ordering is the real signal.
    if len(parents) != 2:
        return {
            "verdict": "UNKNOWN",
            "reason": f"{resolved_merge[:8]} has {len(parents)} parents ({parents}) -- an octopus merge "
                      f"has no single well-defined 'branch-side' parent; --stale-ref only handles the "
                      f"standard two-parent `git merge --no-ff` shape.",
        }
    mainline_parent, branch_parent = parents[0], parents[1]
    if not is_ancestor(repo_dir, mainline_parent, "origin/main"):
        return {
            "verdict": "UNKNOWN",
            "reason": f"parent 1 ({mainline_parent[:8]}) of {resolved_merge[:8]} is not even an ancestor "
                      f"of origin/main -- this does not look like a standard merge-into-main commit; "
                      f"refusing to guess which parent is the branch side.",
        }

    head_sha = meta.get("headRefOid")
    head_ref = meta.get("headRefName")
    ensure_fetched(repo_dir, [head_ref, head_sha])
    resolved_head = commit_exists(repo_dir, head_sha) if head_sha else None

    if not resolved_head:
        return {
            "verdict": "UNKNOWN",
            "reason": f"PR live head ({head_sha}) not resolvable (branch deleted/pruned) -- cannot "
                      f"compare against the merge commit's branch-side parent {branch_parent[:8]}.",
            "merge_sha": resolved_merge, "branch_side_parent": branch_parent,
        }

    if resolved_head == branch_parent:
        return {
            "verdict": "NOT-STALE",
            "reason": f"merge commit `{resolved_merge[:8]}`'s branch-side parent `{branch_parent[:8]}` "
                      f"MATCHES the PR's live head `{resolved_head[:8]}` exactly -- this merge took the "
                      f"real, current tip. No staleness.",
            "merge_sha": resolved_merge, "branch_side_parent": branch_parent, "live_head": resolved_head,
        }

    # Mismatch. Is the live head a DESCENDANT of the merged (stale) parent --
    # i.e. did the merge simply take an earlier point on the same branch,
    # leaving later commits un-landed?
    head_descends_from_stale = is_ancestor(repo_dir, branch_parent, resolved_head)
    missing_commits = []
    missing_diff_stat = ""
    if head_descends_from_stale:
        log_out = sh(repo_dir, ["log", f"{branch_parent}..{resolved_head}", "--format=%H\t%s"])
        for line in log_out.splitlines():
            if "\t" in line:
                sha, subj = line.split("\t", 1)
                missing_commits.append({"sha": sha, "subject": subj})
        missing_diff_stat = diff_stat(repo_dir, branch_parent, resolved_head)
        # Confirm the missing content is REALLY missing from main right now
        # (not independently reimplemented elsewhere) via a content diff of
        # the touched paths, main-tip vs live-head.
        touched = changed_paths(repo_dir, branch_parent, resolved_head)
        head_tree = ls_tree(repo_dir, resolved_head)
        main_tree = ls_tree(repo_dir, "origin/main")
        genuinely_missing = [p for p in touched if main_tree.get(p) != head_tree.get(p)]
        return {
            "verdict": "STALE-REF",
            "reason": (
                f"merge commit `{resolved_merge[:8]}`'s branch-side parent `{branch_parent[:8]}` does "
                f"NOT match the PR's live head `{resolved_head[:8]}` -- the live head is "
                f"{len(missing_commits)} commit(s) AHEAD of what was actually merged. Ancestry of "
                f"`{branch_parent[:8]}` alone is a true ancestor of `origin/main` (looks perfect) but "
                f"main never received the live head's content. {len(genuinely_missing)}/{len(touched)} "
                f"of the missing commits' touched path(s) independently confirmed absent from "
                f"`origin/main`'s CURRENT tip via content diff (not merely ancestry)."
            ),
            "merge_sha": resolved_merge, "branch_side_parent": branch_parent, "live_head": resolved_head,
            "missing_commits": missing_commits, "missing_diff_stat": missing_diff_stat,
            "genuinely_missing_paths": genuinely_missing, "touched_paths": touched,
        }

    return {
        "verdict": "DIVERGED",
        "reason": (
            f"merge commit `{resolved_merge[:8]}`'s branch-side parent `{branch_parent[:8]}` does NOT "
            f"match the PR's live head `{resolved_head[:8]}`, AND the live head is NOT a descendant of "
            f"the merged parent either (diverged history -- e.g. branch was force-pushed/rebased after "
            f"merge). This is still a mismatch worth flagging, but it is not simple staleness."
        ),
        "merge_sha": resolved_merge, "branch_side_parent": branch_parent, "live_head": resolved_head,
    }


# --------------------------------------------------------------------------
# --supersedes <other-pr> : does THIS pr's content genuinely contain
# everything the OTHER pr's content has? Diffed live, both ways, right now.
# --------------------------------------------------------------------------

def check_supersedes(repo_dir, owner_repo, this_pr, other_pr):
    this_meta, err1 = gh_pr_view(owner_repo, this_pr)
    other_meta, err2 = gh_pr_view(owner_repo, other_pr)
    if this_meta is None or other_meta is None:
        return {"verdict": "UNKNOWN", "reason": f"gh pr view failed: {err1 or ''} {err2 or ''}".strip()}

    this_head = this_meta.get("headRefOid")
    other_head = other_meta.get("headRefOid")
    ensure_fetched(repo_dir, [this_meta.get("headRefName"), this_head, other_meta.get("headRefName"), other_head])

    this_r = commit_exists(repo_dir, this_head) if this_head else None
    other_r = commit_exists(repo_dir, other_head) if other_head else None
    if not this_r or not other_r:
        return {
            "verdict": "UNKNOWN",
            "reason": f"could not resolve both heads locally (this={this_head} -> {this_r}, "
                      f"other={other_head} -> {other_r}).",
        }

    this_tree = ls_tree(repo_dir, this_r)
    other_tree = ls_tree(repo_dir, other_r)

    missing_from_this = []   # files OTHER has that THIS completely lacks
    differing = []           # files both have, but with different content
    for path, other_blob in other_tree.items():
        this_blob = this_tree.get(path)
        if this_blob is None:
            missing_from_this.append(path)
        elif this_blob != other_blob:
            differing.append(path)

    extra_in_this = [p for p in this_tree if p not in other_tree]

    if missing_from_this:
        verdict = "NO"
        reason = (
            f"PR #{this_pr} (head `{this_r[:8]}`) does NOT contain #{other_pr}'s (head `{other_r[:8]}`) "
            f"full content: {len(missing_from_this)} file(s) present in #{other_pr}'s tree are "
            f"COMPLETELY ABSENT from #{this_pr}'s tree (not merely modified -- missing entirely). "
            f"Closing #{other_pr} on this claim would orphan that content."
        )
    elif differing:
        verdict = "PARTIAL"
        reason = (
            f"PR #{this_pr} has every path #{other_pr} has, but {len(differing)} file(s) differ in "
            f"content (present-but-modified, not missing) -- review individually before treating this "
            f"as a clean supersede."
        )
    else:
        verdict = "YES"
        reason = (
            f"Every file in #{other_pr}'s tree (head `{other_r[:8]}`) is present with IDENTICAL content "
            f"in #{this_pr}'s tree (head `{this_r[:8]}`). #{this_pr} genuinely contains everything "
            f"#{other_pr} has."
        )

    return {
        "verdict": verdict, "reason": reason,
        "this_pr": this_pr, "other_pr": other_pr,
        "this_head": this_r, "other_head": other_r,
        "missing_from_this": sorted(missing_from_this),
        "differing": sorted(differing),
        "extra_in_this_count": len(extra_in_this),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pr", type=int)
    ap.add_argument("--repo", default="trevorotts1/openclaw-onboarding",
                     help="owner/repo the PR lives in (PR numbers are per-repo; e.g. some PRs "
                          "referenced in the operator's incident history are in "
                          "trevorotts1/blackceo-command-center, not openclaw-onboarding).")
    ap.add_argument("--repo-dir", required=True, help="local git clone of --repo (fetched as needed).")
    ap.add_argument("--zombie", action="store_true")
    ap.add_argument("--stale-ref", metavar="MERGE_SHA")
    ap.add_argument("--supersedes", metavar="OTHER_PR", type=int)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if sum(1 for m in (args.zombie, bool(args.stale_ref), bool(args.supersedes)) if m) != 1:
        print("ERROR: pass exactly one of --zombie / --stale-ref MERGE_SHA / --supersedes OTHER_PR", file=sys.stderr)
        sys.exit(2)

    if args.zombie:
        result = check_zombie(args.repo_dir, args.repo, args.pr)
    elif args.stale_ref:
        result = check_stale_ref(args.repo_dir, args.repo, args.pr, args.stale_ref)
    else:
        result = check_supersedes(args.repo_dir, args.repo, args.pr, args.supersedes)

    result["pr"] = args.pr
    result["repo"] = args.repo

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"PR: #{args.pr} ({args.repo})")
        print(f"VERDICT: {result['verdict']}")
        print(f"reason: {result.get('reason', '')}")
        for k, v in result.items():
            if k in ("verdict", "reason", "pr", "repo"):
                continue
            print(f"  {k}: {v}")

    ok_verdicts = ("NOT-ZOMBIE", "NOT-STALE", "YES")
    bad_verdicts = ("ZOMBIE", "STALE-REF", "NO", "DIVERGED", "PARTIAL")
    sys.exit(0 if result["verdict"] in ok_verdicts else (1 if result["verdict"] in bad_verdicts else 3))


if __name__ == "__main__":
    main()
