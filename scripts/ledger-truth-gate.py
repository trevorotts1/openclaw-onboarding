#!/usr/bin/env python3
"""
ledger-truth-gate.py -- CI helper for .github/workflows/ledger-truth-gate.yml

MISSION IN ONE SENTENCE: verify a claim by its content (real git history,
real check-run history), never by trusting a name or a status label someone
typed.

WHAT THIS SCRIPT DOES:
  1. Diffs BASE..HEAD (PR: pull_request.base.sha..pull_request.head.sha;
     push to main: before..after) for changed files under ledgers/.
  2. Collects every ADDED ledger row (a new row, or the new side of a
     modified row) whose status cell claims `verified` or `done`
     (case-insensitive). Rows that merely stay pending/in_progress/blocked
     are not completion claims and are ignored. Re-checking an
     already-passing unit is cheap; trusting a row is not an option.
  3. Runs the repo's own independent checker for each candidate:
         ./unit-status.sh <UNIT-ID> --cc-dir <cc-checkout> --json
     (no --onb-dir: this script lives in the repo checkout, so the default
     is already correct; no --skip-ci: catching stamps that ignore failing
     checks is the entire point). unit-status.sh re-derives each required
     leg from live git ancestry + paginated check-run history and NEVER
     trusts the ledger's own status cell. Requires GH_TOKEN in the
     environment for its internal `gh api` check-run calls.
  4. Fails (exit 1) if ANY candidate comes back NOT-DONE or UNKNOWN, or the
     tool itself errors, or a candidate row lives in a ledger whose row
     format the tool cannot parse (see UNPARSEABLE_LEDGER_FILES below).

THE THREE KNOWN BLIND SPOTS (each handled explicitly, never silently):
  1. CROSS-CAMPAIGN LEDGERS. `ledgers/skill58-podbean-proxy-2026-07-16.md`
     runs its OWN U-numbering for a different build campaign, so its `U12`
     is NOT the kanban ledger's `U12` -- unit-status.sh's DEFAULT search
     (no --ledger given) always checks the kanban ledger first, so calling
     it with no scoping on one of this file's unit ids silently judges the
     WRONG unit's row (empirically confirmed live: U21's real S58 row reads
     `pending`/NOT STARTED, but the default search resolves it against the
     kanban ledger's own, unrelated, already-verified `U21` and reports a
     false DONE). PR #646 landed leg-requirement tags (`(ONB + n8n, P#)`,
     `(live, P#)`, etc.) on every row in this file, so unit_status_core.py
     CAN now correctly classify and resolve every row's leg requirement --
     the row SHAPE was never the real blind spot once tags exist; the
     collision from the tool's default multi-ledger SEARCH ORDER is. The
     fix is `--ledger` SCOPING, not a bypass: run_unit_status() passes an
     explicit `--ledger <path>` naming the EXACT file a candidate row's diff
     came from whenever that file is a member of UNPARSEABLE_LEDGER_FILES
     (see scoped_ledger_for() below) -- this makes find_ledger_row() search
     ONLY that one file, so it can never resolve to a different campaign's
     same-numbered row. NO_OWN_BRANCH_PREFIX_LEDGERS in unit_status_core.py
     (a sibling fix, same root cause, landed in the same PR) additionally
     disables the kanban ledger's `skill6-v2/<id>` own-branch-name lookup
     for this file's rows, since S58 units ship on independently-named
     branches (PR-cited merge SHAs quoted directly in the row's own prose)
     -- cross-reference/token-scan resolve them correctly on their own.
     Once scoped, a candidate row in this file is enforced exactly like any
     other ledger's row: a real DONE/NOT-DONE/UNKNOWN verdict, never a
     canned "unparseable, human review required" notice. Add any future
     ledger with its own numbering to UNPARSEABLE_LEDGER_FILES below so its
     rows get the same explicit scoping.

     ZERO_LEG_OVERRIDES is a narrower, separate, PRE-EXISTING optimization
     this fix leaves untouched: this ledger's OWN header states its status
     vocabulary directly: "`verified` is a GIT state ... or a LIVE-API state
     (n8n legs: fresh API re-read)". Its own CONCURRENCY MAP table further
     names, explicitly, EXACTLY which units carry a repo leg at all ("Repo
     `openclaw-onboarding` | U12 (repo leg), U14, U15, U16, U17, U21"). Every
     OTHER unit in that file (U2/U4/U5/U8 among them) has NO repo leg to
     check, even in principle -- there is no branch, no merge, no check-run
     unit-status.sh could ever find for a data-table seed or a live webhook
     header-auth flip; ZERO_LEG_OVERRIDES names, per ledger file, the
     SPECIFIC unit ids a human has individually confirmed (by reading that
     file's own CONCURRENCY MAP, never inferred at runtime) to be genuinely
     zero-leg, and trusts a `verified`/`done` claim for one of those ids
     from the ledger's own status cell WITHOUT invoking unit-status.sh at
     all -- a cheap, already-tested fast path this fix does not need to
     touch, since resolve_required_legs()'s own zero-leg mode (see blind
     spot 3 below) would independently reach the identical trusted-DONE
     verdict for these same four ids if it ran. Any unit id in an
     UNPARSEABLE_LEDGER_FILES member that is NOT on its ZERO_LEG_OVERRIDES
     allowlist -- including a genuinely false claim, a repo-leg unit like
     U12/U14-U17/U21, or any future unit nobody has reviewed yet -- now
     falls through to real, scoped enforcement (see classify_ledger_row()
     below): a git-provable false claim is still mechanically caught as
     NOT-DONE, never silently passed. Extending ZERO_LEG_OVERRIDES remains a
     deliberate, reviewed, one-line code change per unit id, never automatic
     -- and repo-leg units (U12/U14/U15/U16/U17/U21) must NEVER be added to
     it: that allowlist exists ONLY for units with no repo leg to check in
     principle, and adding a repo-leg unit to it would skip the exact git
     verification this fix now makes possible for it.
  2. UNKNOWN IS NOT A PASS. Compound leg tags like `(CC (+ONB), P#)` only
     get their PRIMARY leg checked (the secondary hint has no consistent
     grammar -- the tool says so in its own comments), and any tag shape the
     tool doesn't recognize returns UNKNOWN by design ("fail closed, not a
     guess"). This script treats every UNKNOWN as "could not verify --
     needs human review": a gate failure with the tool's reason quoted.
  3. ZERO-LEG UNITS. A unit whose work is all live-system/doc (no repo leg)
     cannot be git-verified at all; the tool reads the ledger's own claim
     and reports DONE. That DONE is allowed to pass (the design rule is
     "tool says DONE -> pass"), but the output says PLAINLY that it is not
     independently checked -- nobody should mistake it for a git-proven
     DONE.

CI STATUS WORDS (surfaced, not re-implemented): the tool's own verdict
logic already folds in its CI classification correctly -- only `red-live`
(a check failing on the leg's commit that ALSO fails, same check name, on
current main) forces NOT-DONE. `red-fossil` (now genuinely passing on
main) is stale history and correctly passes. `red-check-removed` and
`red-main-unverifiable` do not fail the verdict but ARE surfaced here as
NOTEs so a human sees them without re-running anything.

DESIGN RULE: fail LOUD for a human to look at, never fail OPEN, but never a
brittle wall. A red X means "a human reads the named unit + quoted evidence
and decides": real false stamp (fix the row) or evidence-trail gap (work is
real but nothing points the tool at it -- e.g. content cherry-picked onto
main under a different commit than any branch/citation names; the human
override path, with reasoning recorded). The goal is "no false stamp merges
unnoticed", not "block every disputed row forever".

No client names, no emails, no secret values anywhere in this file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Ledgers whose U-numbering belongs to a different campaign than the kanban
# ledger's -- id collision = unit-status.sh's DEFAULT multi-ledger search
# (no --ledger given) would judge the wrong unit's row, because the kanban
# ledger is always searched first. Detected by FILENAME, never guessed from
# content. A candidate row in one of these files is never handed to
# run_unit_status() without an explicit --ledger scoped to its own file (see
# scoped_ledger_for() below) -- UNLESS the unit id is also listed in
# ZERO_LEG_OVERRIDES below, in which case unit-status.sh is not invoked at
# all for it (see classify_ledger_row()).
UNPARSEABLE_LEDGER_FILES = frozenset({
    "skill58-podbean-proxy-2026-07-16.md",
})

# Per UNPARSEABLE_LEDGER_FILES member, the unit ids a human has individually
# confirmed -- by reading THAT FILE'S OWN CONCURRENCY MAP table -- carry no
# repository leg at all, so a `verified`/`done` claim for one of them can
# only ever be the ledger's own documented LIVE-API state, never a
# git-checkable one (see the module docstring's "blind spot 1" section for
# the full reasoning). A candidate whose (basename, unit_id) pair is listed
# here is trusted from the ledger's own status cell and PASSES WITH
# DISCLAIMER -- never silently, always printed, and never independently
# git-verified (identical to unit_status_core.py's own zero-leg mode
# elsewhere in this repo) -- and unit-status.sh is never invoked for it at
# all, since there is no repo leg to check in principle. Every other unit id
# in an UNPARSEABLE_LEDGER_FILES member -- including ones this repo's own
# CONCURRENCY MAP names as carrying a REAL repo leg (U12, U14, U15, U16,
# U17, U21 in the podbean file) -- is deliberately NOT listed here and now
# gets REAL, --ledger-scoped enforcement instead (see classify_ledger_row()
# and scoped_ledger_for()) -- never a bypass, never a blanket pass. This is
# a hand-maintained ALLOWLIST, never a computed one: a table-parsing
# shortcut that inferred this set from the concurrency map at runtime could
# silently mis-derive it (a parsing bug, a reformatted table), and
# defaulting "not in the repo-leg list" to trusted would let a FUTURE unit
# added to this file with a genuine, un-reviewed repo leg slip through
# trusted (bypassing git verification) instead of actually being checked.
# Extend this set only unit-by-unit, only after a human has actually read
# the concurrency map and confirmed it -- and NEVER for a unit id the
# concurrency map itself names as carrying a repo leg (U12/U14/U15/U16/
# U17/U21): those must always go through real git verification, now that
# --ledger scoping makes that verification correct.
#
# skill58-podbean-proxy-2026-07-16.md's own CONCURRENCY MAP table (the
# "Repo `openclaw-onboarding`" row) names ONLY U12/U14/U15/U16/U17/U21 as
# carrying a repo leg. U2 (data-table seed), U4 (webhook header-auth flip),
# U5 (roster/identity gate node), and U8 (idempotency via data-table) are
# each 100% live n8n/data-table state with no repo artifact whatsoever --
# confirmed both by that table and by reading every one of their own row
# texts (each cites live API reads / execution ids, never a PR, branch, or
# merge commit).
ZERO_LEG_OVERRIDES = {
    "skill58-podbean-proxy-2026-07-16.md": frozenset({"U2", "U4", "U5", "U8"}),
}


def classify_ledger_row(basename, unit_id):
    """Route a single candidate (verified/done) row to exactly one bucket:
      "enforce"            -- run the normal git+check-run verification path
                               (unit-status.sh, candidates dict). This is
                               EVERY row except the ZERO_LEG_OVERRIDES
                               allowlist below -- including every unit id in
                               an UNPARSEABLE_LEDGER_FILES member, which used
                               to get an unconditional "not_enforced" bypass
                               before this fix (see the module docstring's
                               "blind spot 1"). Those rows are still
                               enforced correctly: the caller (main()) passes
                               unit-status.sh an explicit --ledger scoped to
                               the exact file the row's diff came from (see
                               scoped_ledger_for()), which eliminates the
                               cross-campaign collision the old bypass
                               existed to avoid -- so real, git-derived
                               enforcement is now safe for these rows too.
      "zero_leg_override"  -- basename is in UNPARSEABLE_LEDGER_FILES AND
                               unit_id is on that file's ZERO_LEG_OVERRIDES
                               allowlist: trust the ledger's own status cell,
                               PASS WITH DISCLAIMER, never independently
                               git-checked (unit-status.sh is never invoked
                               for this row at all -- there is no repo leg
                               to check in principle, so a subprocess call
                               would only add cost, never proof; see the
                               module docstring's "blind spot 1" section).
    A pure function (no I/O) so it is trivially unit-testable in isolation
    from git/subprocess -- see tests/unit/ledger-truth-gate.test.py."""
    if unit_id in ZERO_LEG_OVERRIDES.get(basename, frozenset()):
        return "zero_leg_override"
    return "enforce"


def scoped_ledger_for(paths):
    """`paths`: the set of distinct ledger file paths a single unit id's
    ADDED verified/done row(s) came from in this diff (usually exactly one).
    Returns the single ledger path unit-status.sh's --ledger flag should be
    scoped to, or None to let the tool use its own default multi-ledger
    search (today: the kanban ledger first, then every other ledgers/*.md
    file -- unchanged from before this fix for every ledger NOT in
    UNPARSEABLE_LEDGER_FILES).

    Scoping is the actual fix for the cross-campaign U-numbering collision
    (module docstring "blind spot 1"): passing --ledger <path> makes
    unit_status_core.find_ledger_row() search ONLY that one file, so it can
    never resolve a unit id against a different campaign's same-numbered
    row. Only applied when the row's file is a known cross-campaign ledger
    (UNPARSEABLE_LEDGER_FILES) AND every changed row for this unit id in
    this diff came from that SAME single file -- a unit id whose changed
    rows span more than one ledger file in one diff is a separate, far
    stranger scenario this fix does not attempt to silently resolve; the
    tool's ordinary default search runs for it, exactly as it did before
    this fix existed."""
    if len(paths) != 1:
        return None
    (path,) = paths
    return path if Path(path).name in UNPARSEABLE_LEDGER_FILES else None


# A ledger unit row: `| U108 | ...`. Matches every known ledger shape --
# including the unparseable ones, which still start with `| U<id> |`.
ROW_RE = re.compile(r"^\|\s*(U\d+)\s*\|")

# Standard + podbean row shapes both place the status cell at index 3:
#   | unit | description | assignee-label | STATUS | evidence | timestamp |
# (unit_status_core.py reads the same index -- keep in sync with it.)
STATUS_CELL_INDEX = 3

VERIFIED_CLAIM_RE = re.compile(r"^\s*(verified|done)\b", re.IGNORECASE)

# CI statuses that never gate a failure by themselves but must be VISIBLE.
CI_NOTE_STATUSES = ("red-check-removed", "red-main-unverifiable")

TOOL_TIMEOUT_SECONDS = 600


def sh(args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"GATE ERROR: command failed: {' '.join(args)}")
        print(r.stderr.strip()[:500])
        sys.exit(1)
    return r


def ref_resolves(ref):
    r = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def changed_ledger_files(base, head):
    r = sh(["git", "diff", "--name-only", "--diff-filter=AMR", base, head, "--", "ledgers/"])
    return [line.strip() for line in r.stdout.splitlines() if line.strip().endswith(".md")]


def added_verified_rows(base, head, path):
    """Every ADDED row in `path` claiming verified/done -> list of (unit_id, status_cell).

    Reads the unified diff with zero context: new rows and the new side of
    modified rows both appear as `+` lines. File-header `+++` lines are
    excluded. Rows whose status cell does not claim completion are dropped."""
    r = sh(["git", "diff", "-U0", base, head, "--", path])
    out = []
    for line in r.stdout.splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        text = line[1:].strip()
        m = ROW_RE.match(text)
        if not m:
            continue
        cells = [c.strip() for c in text.strip("|").split("|")]
        status = cells[STATUS_CELL_INDEX] if len(cells) > STATUS_CELL_INDEX else ""
        if VERIFIED_CLAIM_RE.match(status):
            out.append((m.group(1), status))
    return out


def run_unit_status(unit_id, cc_dir, ledger_path=None):
    """Run the tool. Returns (parsed_json_or_None, human_error_or_None).

    `ledger_path`, when given (see scoped_ledger_for()), is passed through
    as an explicit `--ledger <ledger_path>` -- this makes unit-status.sh
    search ONLY that one file for the unit's row, instead of its own default
    multi-ledger search (kanban ledger first, then every other ledgers/*.md
    file). This is the fix for the cross-campaign U-numbering collision
    described in this module's docstring ("blind spot 1"): without it, a
    unit id that also exists in the kanban ledger (e.g. U12, U14, U21) would
    silently resolve against the KANBAN ledger's unrelated row instead of
    the real one, because the kanban ledger is always searched first when no
    --ledger is given. `ledger_path` is None for every other ledger file
    (unchanged default multi-ledger search, exactly as before this fix).

    The tool prints its JSON to stdout on every verdict path (exit 0 = DONE,
    1 = NOT-DONE, 3 = UNKNOWN). A crash, timeout, or unparseable stdout is a
    tool ERROR -- fail closed, never guess."""
    cmd = ["./unit-status.sh", unit_id, "--cc-dir", cc_dir]
    if ledger_path:
        cmd += ["--ledger", ledger_path]
    cmd += ["--json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return None, f"tool timed out after {TOOL_TIMEOUT_SECONDS}s"
    except OSError as e:
        return None, f"tool failed to launch: {e}"
    try:
        return json.loads(r.stdout), None
    except json.JSONDecodeError:
        tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
        return None, f"tool exited {r.returncode} with non-JSON output: {tail.strip()[:400]}"


def print_unit_report(unit_id, result):
    """Human-legible per-unit detail: verdict, per-leg evidence, CI notes."""
    verdict = result.get("verdict", "???")
    mode = result.get("mode")
    print(f"\n  unit {unit_id}: verdict={verdict}" + (f"  mode={mode}" if mode else ""))
    if result.get("reason"):
        print(f"    reason: {result['reason']}")
    for leg, legres in (result.get("legs") or {}).items():
        print(f"    leg {leg}: satisfied={legres.get('satisfied')} method={legres.get('method')}")
        ev = legres.get("evidence")
        if ev:
            print(f"      evidence: {ev}")
        ci = legres.get("ci")
        if ci:
            print(f"      CI: {ci.get('status')} (head_sha={ci.get('head_sha')})")
            if ci.get("status") in CI_NOTE_STATUSES:
                for fc in ci.get("failing_checks", []):
                    print(f"      NOTE: check {fc.get('name')!r}: {fc.get('note')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="base sha of the diff range")
    ap.add_argument("--head", required=True, help="head sha of the diff range")
    ap.add_argument("--cc-dir", required=True, help="path to the blackceo-command-center checkout")
    args = ap.parse_args()

    if not Path("./unit-status.sh").is_file():
        print("GATE ERROR: ./unit-status.sh not found -- this script must run from the repo root.")
        sys.exit(1)
    if not Path(args.cc_dir).is_dir():
        print(f"GATE ERROR: --cc-dir '{args.cc_dir}' is not a directory -- the workflow must check out")
        print("blackceo-command-center before running this script.")
        sys.exit(1)
    for ref, name in ((args.base, "base"), (args.head, "head")):
        if not ref_resolves(ref):
            print(f"GATE ERROR: {name} sha '{ref}' does not resolve to a commit in this checkout")
            print("(force-push or shallow fetch?). Cannot establish the diff range -- failing closed;")
            print("a human must review this ledger change by hand.")
            sys.exit(1)

    files = changed_ledger_files(args.base, args.head)
    if not files:
        print("ledger-truth gate: no ledger files changed in this range -- nothing to gate. PASS.")
        return

    candidates = {}          # unit_id -> list of (path, status_cell)
    zero_leg_override = []   # (path, unit_id, status_cell) -- reviewed, trusted, PASS WITH DISCLAIMER
    for path in files:
        basename = Path(path).name
        for unit_id, status in added_verified_rows(args.base, args.head, path):
            route = classify_ledger_row(basename, unit_id)
            if route == "zero_leg_override":
                zero_leg_override.append((path, unit_id, status))
            else:
                candidates.setdefault(unit_id, []).append((path, status))

    if not candidates and not zero_leg_override:
        print(f"ledger-truth gate: {len(files)} ledger file(s) changed, but no added row claims")
        print("verified/done -- nothing to gate. PASS.")
        return

    print(f"ledger-truth gate: {len(candidates)} candidate unit(s) claiming verified/done"
          + (f", {len(zero_leg_override)} row(s) on the reviewed zero-leg override allowlist" if zero_leg_override else ""))
    print(f"diff range: {args.base[:12]}..{args.head[:12]}")

    failures = []   # human-readable failure blocks
    passes = []     # unit ids with a real git-verified DONE
    zero_leg = []   # unit ids whose DONE is NOT independently checked

    for unit_id in sorted(candidates, key=lambda u: int(u[1:])):
        unit_paths = sorted({p for p, _ in candidates[unit_id]})
        where = ", ".join(unit_paths)
        ledger_path = scoped_ledger_for(set(unit_paths))
        result, error = run_unit_status(unit_id, args.cc_dir, ledger_path=ledger_path)
        if error is not None:
            failures.append(f"  unit {unit_id} ({where}): TOOL ERROR -- {error}\n"
                            f"    Failing closed: the gate could not verify this row. Human review required.")
            continue
        print_unit_report(unit_id, result)
        verdict = result.get("verdict")
        if verdict == "DONE":
            if result.get("mode") == "zero-leg":
                zero_leg.append(unit_id)
            else:
                passes.append(unit_id)
        elif verdict == "NOT-DONE":
            failures.append(f"  unit {unit_id} ({where}): NOT-DONE -- the ledger claims verified/done but\n"
                            f"    git + check-run history CANNOT prove it. See the evidence above.\n"
                            f"    If this is a real false stamp: fix the row, do not merge as-is.\n"
                            f"    If the work is real but the evidence trail cannot reach it (e.g. content\n"
                            f"    landed under a different commit than any branch or citation names): a human\n"
                            f"    may override with their reasoning recorded -- same as any required-check override.")
        else:  # UNKNOWN or anything unexpected -- never a pass
            failures.append(f"  unit {unit_id} ({where}): verdict={verdict} -- could NOT be verified.\n"
                            f"    UNKNOWN is not a pass (unparseable or partially-checkable leg tag, or no\n"
                            f"    evidence trail). Human review required; see the reason above.")

    print("\n" + "=" * 72)
    print("LEDGER-TRUTH GATE -- SUMMARY")
    print("=" * 72)
    if passes:
        print(f"PASS (git-verified DONE): {', '.join(passes)}")
    for unit_id in zero_leg:
        print(f"PASS WITH DISCLAIMER: {unit_id} -- this unit has no repository leg to verify;")
        print("  its DONE status is NOT independently checked, only the ledger's own claim was read.")
    for path, unit_id, status in zero_leg_override:
        print(f"PASS WITH DISCLAIMER (reviewed zero-leg override): {unit_id} in {path}")
        print(f"  row claims '{status}'. This unit is on ZERO_LEG_OVERRIDES for {Path(path).name} -- a")
        print("  human has confirmed, from that ledger's own CONCURRENCY MAP table, that this unit id")
        print("  carries no repository leg at all (a live n8n/data-table claim, not a git-checkable")
        print("  one). Trusted from the ledger's own status cell, exactly like any other zero-leg unit")
        print("  elsewhere in this repo -- NOT independently git-verified, and never silently.")

    failed = bool(failures)
    if failures:
        print("\nFAILURES:")
        for block in failures:
            print(block)
    print(f"\nGATE RESULT: {'FAIL -- see the named units above; every one needs a human decision before merge.' if failed else 'PASS.'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
