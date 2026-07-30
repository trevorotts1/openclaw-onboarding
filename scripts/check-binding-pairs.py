#!/usr/bin/env python3
"""check-binding-pairs.py -- enforce SPEC's "Same commit as: X -- binding" pairs.

WHAT THIS IS
------------
SPEC/INDEX.md (a Super-Spec planning document that lives OUTSIDE this git
repository -- a sibling of repos/openclaw-onboarding, not tracked here) has a
table titled "Units that must land in the SAME commit": pairs of build units
whose Touches: files must change together, plus one landing-ORDER constraint
(U073 before U057/U056). Individual SPEC/units/<ID>.md cards repeat the same
declaration, sometimes on both sides of the pair, sometimes -- as the U011 /
U069 pair showed -- on only one side.

Before this script, nothing referenced these pairs: not .githooks/, not the
~100 workflows in .github/workflows/, not scripts/, not CONTROL/. Three of
the four verifiable pairs were violated at landing time. This script is the
first thing that reads the declaration and checks a real diff against it.

DATA SOURCE
-----------
scripts/binding-pairs.json is the repo-local, hand-maintained transcription
of SPEC/INDEX.md's table (SPEC/ cannot be read from CI -- it is not part of
this repository). Groups are stored as unordered sets of unit ids, so a pair
declared on only one card's "Same commit as:" line is still enforced in both
directions -- the graph edge only needs to be recorded once, wherever it was
found. See binding-pairs.json's own "_purpose" / "_edge_symmetry_note" for
how to add a new group.

LAYER: THIS RUNS IN CI ON A PULL REQUEST, NOT AS A PRE-COMMIT HOOK
-------------------------------------------------------------------
A pre-commit hook only ever sees the ONE commit being made right now, on the
machine making it. A same-commit binding is a property of a whole PR (or, in
this repo's own convention, a single squash-style "Land Uxxx" merge commit --
but the merge-writer builds that merge commit FROM a PR/branch whose full
diff is what actually needs checking). Two units built on separate branches
by separate builders and only reconciled at merge time are invisible to any
individual commit's pre-commit hook -- pre-commit would have to guess the
*other* branch's future content, which it cannot do. CI, triggered on
`pull_request`, sees the full base...head diff and can compare it against
both units' Touches: sets in one pass. That is why this is a scripts/ +
workflow layer, not a .githooks/pre-commit rule (Rule 3.8 / this project's
own "enforcement, not description" doctrine: a check that cannot see the
condition it is supposed to enforce is decoration, not enforcement).

WHAT "ENFORCE" MEANS HERE, AND WHY MOST GROUPS ARE NOT ENFORCED TODAY
----------------------------------------------------------------------
Every group in binding-pairs.json carries an "enforce" flag.
  enforce: true  -> a partial touch (one side's files changed, the other's
                     did not, in the diff being checked) is a hard FAIL.
  enforce: false -> the group is reported for visibility (AUDIT) but never
                     fails the build.

All SIX same-commit rows currently in SPEC/INDEX.md, and the one ordering
row, describe units that are ALREADY FULLY LANDED (verified on disk in this
repo as of 2026-07-30 -- every Touches: path for U002, U009, U011, U069,
U012, U013, U073, U056 and U057 exists). Flipping them to "enforce": true
now would not protect anything real (there is nothing left to co-land) and
WOULD create exactly the false-positive risk this project was warned against:
a routine future edit to, say, sync_check.py (U002's file) for a reason that
has nothing to do with U009 would suddenly be forced to also touch
PIPELINE-MANIFEST.json, or be blocked. That is firing on legitimate work --
worse than no guard at all, per this repo's own chmod-600/update-skills.sh
lesson. So the six rows are recorded with "enforce": false, "status":
"landed" -- kept for the audit trail (see `audit-history` below, which is
how this script proves what SPEC/INDEX.md's own six-pair table says against
real git history), not as a live gate.

The mechanism is real and general-purpose, not a demo shell: the NEXT time
SPEC/INDEX.md gains a same-commit row for units that have not shipped yet,
a maintainer adds a group here with "enforce": true, "status": "pending",
and it blocks a PR that lands one side without the other -- proven by this
script's own --selftest, which plants exactly that PR shape on a throwaway
git repo and asserts the exit codes.

WHAT THIS DOES NOT CATCH (read before trusting it blindly)
-------------------------------------------------------------
1. It matches on FILE PATHS (Touches: globs), not on semantic content. Two
   units that happen to touch the same file (U011's package-wide
   presentation_job/** glob overlaps U069's phases.py/report.py) will look
   "both touched" the instant EITHER one's file changes, even on a commit
   that only did one of the two units' work. Overlapping Touches: sets make
   the pairing check for the overlapping files vacuous; only the
   non-overlapping files in each side's set carry real signal.
2. It cannot see a same-commit pair that was never transcribed into
   binding-pairs.json. SPEC/ is outside the repo; nothing scans it
   automatically. A newly declared pair is invisible until a human adds it
   here -- this script enforces the manifest, not SPEC/INDEX.md directly.
3. Landing-ORDER constraints ("U073 BEFORE U057/U056") are audited over
   history but are NOT hard-enforced at PR time as a full "X must have
   already landed" gate beyond a same-base-ref file-existence check (see
   `check --mode order` below): it asks "does <before>'s file exist on the
   PR's base ref", which is cheap, reliable, and monotonic (it can only
   regress via an actual revert of the before-unit, which is exactly the
   case worth catching) -- but it is a weaker claim than "the before-unit's
   fix is semantically complete", which this script cannot evaluate.
4. It cannot stop a PR from being merged with `--admin`/branch-protection
   overrides, and it cannot rewrite history: a violation that already
   landed (all three real ones did) is recorded, never retroactively
   reverted or blocked.
5. It has no opinion on WHY a partner didn't change -- a legitimate
   same-commit revert of BOTH sides together is fine and passes; this script
   only flags an imbalance, not intent.

USAGE
-----
  check-binding-pairs.py check   --base <ref> --head <ref> [--manifest PATH]
  check-binding-pairs.py order   --base <ref> [--manifest PATH]
  check-binding-pairs.py audit-history --since <ref> [--manifest PATH]
  check-binding-pairs.py --selftest

Exit codes: 0 = no enforced violation. 1 = an enforced group/order constraint
was violated. 2 = usage / setup error (bad ref, missing manifest, git failure).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent


def run_git(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo)] + args,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def path_matches(path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif fnmatch.fnmatch(path, pat):
            return True
    return False


def unit_touched(unit_id: str, units: dict, changed: set[str]) -> list[str]:
    patterns = units[unit_id]["touches"]
    return [p for p in changed if path_matches(p, patterns)]


def changed_files(repo: Path, base: str, head: str, use_merge_base: bool) -> set[str]:
    rng = f"{base}...{head}" if use_merge_base else f"{base}..{head}"
    out = run_git(repo, ["diff", "--name-only", rng])
    return {line for line in out.splitlines() if line.strip()}


# --------------------------------------------------------------------------
# check: PR/commit-range mode -- the live gate.
# --------------------------------------------------------------------------
def cmd_check(args) -> int:
    repo = Path(args.repo)
    manifest = load_manifest(Path(args.manifest))
    units = manifest["units"]
    groups = manifest.get("same_commit_groups", [])

    try:
        changed = changed_files(repo, args.base, args.head, not args.no_merge_base)
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if not changed:
        print("No files changed in range -- nothing to check.")
        return 0

    print(f"Changed files in range ({len(changed)}):")
    for f in sorted(changed):
        print(f"  {f}")
    print()

    exit_code = 0
    for group in groups:
        gid = group["id"]
        hit = {u: unit_touched(u, units, changed) for u in group["units"]}
        touched_units = [u for u, files in hit.items() if files]
        untouched_units = [u for u, files in hit.items() if not files]

        if not touched_units:
            continue  # ordinary commit/PR, this group is irrelevant -- silent, no output.

        label = "ENFORCE" if group.get("enforce") else "AUDIT (not blocking)"

        if untouched_units:
            msg = (
                f"[{label}] {gid}: PARTIAL -- {', '.join(touched_units)} changed "
                f"({sum(len(v) for v in hit.values())} file(s)) but "
                f"{', '.join(untouched_units)} did not.\n"
                f"    {group.get('why', '')}\n"
                f"    Source: {group.get('spec_ref', 'unknown')}"
            )
            print(msg)
            if group.get("enforce"):
                print(
                    f"    FAIL: {gid} is a binding same-commit pair "
                    f"(enforce: true) and only "
                    f"{'/'.join(touched_units)} landed in this range."
                )
                exit_code = 1
        else:
            print(f"[{label}] {gid}: all of {', '.join(group['units'])} changed together -- OK.")

    if exit_code:
        print("\nRESULT: FAIL -- one or more binding same-commit pairs were split.")
    else:
        print("\nRESULT: PASS.")
    return exit_code


# --------------------------------------------------------------------------
# order: PR/commit-range mode for the one landing-order constraint class.
# Weaker claim, deliberately: "before"-unit's files must already exist on
# the PR's base ref if this PR touches an "at_or_after" unit's files.
# --------------------------------------------------------------------------
def cmd_order(args) -> int:
    repo = Path(args.repo)
    manifest = load_manifest(Path(args.manifest))
    units = manifest["units"]
    constraints = manifest.get("order_constraints", [])

    try:
        changed = changed_files(repo, args.base, args.head, not args.no_merge_base)
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    exit_code = 0
    for c in constraints:
        cid = c["id"]
        after_units = c["at_or_after"]
        hit_after = [u for u in after_units if unit_touched(u, units, changed)]
        if not hit_after:
            continue  # this PR doesn't touch the gated side -- irrelevant, silent.

        before_unit = c["before"]
        before_patterns = units[before_unit]["touches"]
        missing = []
        for pat in before_patterns:
            if pat.endswith("/**"):
                # directory glob: ask git if anything under it exists at base.
                prefix = pat[:-3]
                try:
                    listing = run_git(repo, ["ls-tree", "-r", "--name-only", args.base, "--", prefix])
                except RuntimeError:
                    listing = ""
                if not listing.strip():
                    missing.append(pat)
            else:
                try:
                    run_git(repo, ["cat-file", "-e", f"{args.base}:{pat}"])
                except RuntimeError:
                    missing.append(pat)

        label = "ENFORCE" if c.get("enforce") else "AUDIT (not blocking)"
        if missing:
            print(
                f"[{label}] {cid}: this range touches {', '.join(hit_after)}, but "
                f"{before_unit}'s files are missing at base ref {args.base}: "
                f"{', '.join(missing)}"
            )
            print(f"    {c.get('why', '')}\n    Source: {c.get('spec_ref', 'unknown')}")
            if c.get("enforce"):
                print(f"    FAIL: {before_unit} must land before {', '.join(after_units)}.")
                exit_code = 1
        else:
            print(f"[{label}] {cid}: {before_unit}'s files are present at base ref -- order satisfied.")

    print("\nRESULT:", "FAIL" if exit_code else "PASS")
    return exit_code


# --------------------------------------------------------------------------
# audit-history: report what SPEC/INDEX.md's pairs say against what actually
# happened -- informational only, never fails, never blocks a build.
#
# NOTE ON METHOD: most of these units MODIFY files that already existed
# long before the unit was built (sync_check.py, PIPELINE-MANIFEST.json,
# phases.py -- all pre-date the fix). A naive "first commit anywhere in
# history that touches this Touches: path" would report the file's original
# authoring commit, not the unit's landing commit. This repo's own
# merge-writer convention titles the landing commit "Land U<id>[+U<id>]: ..."
# (or, for units folded into an unrelated PR, the unit id still appears as a
# token in the subject/body -- e.g. U069 never got a "Land" ceremony commit
# at all, it landed via "fix/u069-report-dispatch-shell-injection"). So the
# search below finds candidate commits by UNIT-ID TOKEN in the commit
# subject, then keeps only the ones that also actually touch >=1 of that
# unit's Touches: files (sanity cross-check -- a commit that merely mentions
# the id in passing, e.g. a ticket-file-only commit, does not count), and
# reports the topologically-first such commit as "when this unit landed".
# --------------------------------------------------------------------------
import re


def _first_landing_commit(repo: Path, unit_id: str, units: dict, commits: list[tuple[str, str, str]]):
    pattern = re.compile(rf"\b{re.escape(unit_id)}\b")
    for sha, ci, subject in commits:
        if not pattern.search(subject):
            continue
        try:
            files_out = run_git(repo, ["show", "--name-only", "--format=", sha])
        except RuntimeError:
            continue
        files = {f for f in files_out.splitlines() if f.strip()}
        if unit_touched(unit_id, units, files):
            return (sha, ci, subject)
    return None


def cmd_audit_history(args) -> int:
    repo = Path(args.repo)
    manifest = load_manifest(Path(args.manifest))
    units = manifest["units"]
    groups = manifest.get("same_commit_groups", [])
    order_constraints = manifest.get("order_constraints", [])

    since_range = args.since if ".." in args.since else f"{args.since}..HEAD"
    log = run_git(repo, ["log", "--reverse", "--format=%H|%ci|%s", since_range])
    commits = []
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, ci, subject = line.split("|", 2)
        commits.append((sha, ci, subject))
    print(f"Walked {len(commits)} commits in range {since_range}.")

    for group in groups:
        gid = group["id"]
        unit_ids = group["units"]
        landing = {u: _first_landing_commit(repo, u, units, commits) for u in unit_ids}

        print(f"\n=== {gid} ({group.get('spec_ref', '?')}) ===")
        for u in unit_ids:
            lc = landing[u]
            if lc is None:
                print(f"  {u}: no landing commit found by id-token+file-touch search in this range")
            else:
                print(f"  {u}: landed at {lc[0][:8]}  ({lc[1]})  -- \"{lc[2]}\"")

        found = {u: landing[u][0] for u in unit_ids if landing[u]}
        if len(found) < len(unit_ids):
            print("  VERDICT: incomplete (one side not found in this range) -- cannot judge.")
        elif len(set(found.values())) == 1:
            print(f"  VERDICT: HONORED -- both landed in the same commit ({list(found.values())[0][:8]}).")
        else:
            t = {u: landing[u][1] for u in unit_ids}
            order = sorted(unit_ids, key=lambda u: landing[u][1])
            first_u, second_u = order[0], order[1]
            print(f"  VERDICT: VIOLATED -- {first_u} landed at {t[first_u]}, {second_u} landed at {t[second_u]} (different commits).")
            n_between = None
            try:
                between = run_git(repo, ["log", "--oneline", f"{found[first_u]}..{found[second_u]}"])
                n_between = len([l for l in between.splitlines() if l.strip()])
            except RuntimeError:
                pass
            if n_between is not None:
                print(f"    {n_between} other commits landed on main between the two.")

    if order_constraints:
        print("\n--- landing-order constraints ---")
    for c in order_constraints:
        cid = c["id"]
        before_u = c["before"]
        before_lc = _first_landing_commit(repo, before_u, units, commits)
        print(f"\n=== {cid} ({c.get('spec_ref', '?')}) ===")
        if before_lc is None:
            print(f"  {before_u}: no landing commit found")
        else:
            print(f"  {before_u} (must land first): landed at {before_lc[0][:8]}  ({before_lc[1]})  -- \"{before_lc[2]}\"")
        for au in c["at_or_after"]:
            au_lc = _first_landing_commit(repo, au, units, commits)
            if au_lc is None:
                print(f"  {au}: no landing commit found")
                continue
            print(f"  {au}: landed at {au_lc[0][:8]}  ({au_lc[1]})  -- \"{au_lc[2]}\"")
            if before_lc is not None:
                if before_lc[1] <= au_lc[1]:
                    print(f"    VERDICT: order honored -- {before_u} landed before {au}.")
                else:
                    print(f"    VERDICT: ORDER VIOLATED -- {au} landed before {before_u}.")

    return 0


# --------------------------------------------------------------------------
# selftest: prove the mechanism on a disposable scratch git repo.
# --------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    return run_git(repo, list(args))


def _init_scratch_repo(tmp: Path) -> Path:
    repo = tmp / "scratch"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "selftest@example.invalid")
    _git(repo, "config", "user.name", "selftest")
    (repo / "unrelated.txt").write_text("hello\n")
    (repo / "unitA.py").write_text("A v1\n")
    (repo / "unitB.json").write_text("{\"v\": 1}\n")
    _git(repo, "add", "unrelated.txt", "unitA.py", "unitB.json")
    _git(repo, "commit", "-q", "-m", "base commit")
    return repo


def _write_selftest_manifest(repo: Path) -> Path:
    manifest = {
        "units": {
            "UA": {"touches": ["unitA.py"]},
            "UB": {"touches": ["unitB.json"]},
        },
        "same_commit_groups": [
            {
                "id": "UA+UB",
                "units": ["UA", "UB"],
                "enforce": True,
                "status": "pending",
                "spec_ref": "selftest-fixture",
                "why": "synthetic pairing for the self-test",
            }
        ],
        "order_constraints": [],
    }
    path = repo / "selftest-manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def cmd_selftest(args) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="binding-pairs-selftest-"))
    ok = True
    try:
        repo = _init_scratch_repo(tmp)
        manifest_path = _write_selftest_manifest(repo)
        base_sha = _git(repo, "rev-parse", "HEAD").strip()

        # --- Case 1: change UA's file only -> must FAIL ---
        (repo / "unitA.py").write_text("A v2\n")
        _git(repo, "commit", "-aq", "-m", "touch unitA only")
        head1 = _git(repo, "rev-parse", "HEAD").strip()
        rc1 = cmd_check(argparse.Namespace(
            repo=str(repo), manifest=str(manifest_path),
            base=base_sha, head=head1, no_merge_base=False,
        ))
        print(f"\n--- selftest case 1 (partial touch) exit={rc1}, expected 1 ---")
        if rc1 != 1:
            ok = False

        # --- Case 2: same change, now WITH the partner's file -> must PASS ---
        (repo / "unitB.json").write_text("{\"v\": 2}\n")
        _git(repo, "commit", "-aq", "-m", "touch unitB to complete the pair")
        head2 = _git(repo, "rev-parse", "HEAD").strip()
        rc2 = cmd_check(argparse.Namespace(
            repo=str(repo), manifest=str(manifest_path),
            base=base_sha, head=head2, no_merge_base=False,
        ))
        print(f"\n--- selftest case 2 (both sides present) exit={rc2}, expected 0 ---")
        if rc2 != 0:
            ok = False

        # --- Case 3: ordinary commit touching neither -> must NOT fire ---
        (repo / "unrelated.txt").write_text("hello again\n")
        _git(repo, "commit", "-aq", "-m", "ordinary unrelated change")
        head3 = _git(repo, "rev-parse", "HEAD").strip()
        rc3 = cmd_check(argparse.Namespace(
            repo=str(repo), manifest=str(manifest_path),
            base=head2, head=head3, no_merge_base=False,
        ))
        print(f"\n--- selftest case 3 (ordinary commit) exit={rc3}, expected 0 ---")
        if rc3 != 0:
            ok = False

        print("\n=== SELFTEST", "PASS" if ok else "FAIL", "===")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=str(REPO_ROOT_DEFAULT), help="repo root (default: this script's repo)")
    parser.add_argument("--manifest", default=str(REPO_ROOT_DEFAULT / "scripts" / "binding-pairs.json"))
    parser.add_argument("--selftest", action="store_true", help="run the built-in self-test and exit")

    sub = parser.add_subparsers(dest="mode")

    p_check = sub.add_parser("check", help="check a base..head range for split same-commit pairs")
    p_check.add_argument("--base", required=True)
    p_check.add_argument("--head", required=True)
    p_check.add_argument("--no-merge-base", action="store_true", help="use base..head instead of base...head")

    p_order = sub.add_parser("order", help="check a base..head range for order-constraint violations")
    p_order.add_argument("--base", required=True)
    p_order.add_argument("--head", required=True)
    p_order.add_argument("--no-merge-base", action="store_true")

    p_audit = sub.add_parser("audit-history", help="walk full history and report on same-commit groups")
    p_audit.add_argument("--since", required=True, help="starting ref for git log, e.g. the repo's root commit or a tag")

    args = parser.parse_args()

    if args.selftest:
        return cmd_selftest(args)

    if args.mode == "check":
        args.repo = args.repo
        return cmd_check(args)
    if args.mode == "order":
        return cmd_order(args)
    if args.mode == "audit-history":
        return cmd_audit_history(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
