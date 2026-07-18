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
  1. UNPARSEABLE LEDGERS. `ledgers/skill58-podbean-proxy-2026-07-16.md` uses
     a row shape with NO leg-requirement tag (`id | desc | label | status |
     evidence | timestamp`), so the tool returns a generic UNKNOWN for its
     rows. Worse: that file runs its OWN U-numbering for a different build
     campaign, so its `U5` is NOT the kanban ledger's `U5` -- running the
     tool on it would silently judge the WRONG unit's row (the tool finds
     the first matching row id across all ledgers). Rows in these files are
     therefore NOT ENFORCED: they fail the gate with a clearly labeled
     "human review required" notice, never a generic failure, never a pass.
     Add any future ledger with its own numbering/unparseable shape to
     UNPARSEABLE_LEDGER_FILES below.
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

# Ledgers whose row format unit-status.sh cannot parse and/or whose
# U-numbering belongs to a different campaign (id collision = the tool would
# judge the wrong unit's row). Detected by FILENAME, never guessed from
# content. Candidates in these files get a labeled NOT-ENFORCED failure.
UNPARSEABLE_LEDGER_FILES = frozenset({
    "skill58-podbean-proxy-2026-07-16.md",
})

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


def run_unit_status(unit_id, cc_dir):
    """Run the tool. Returns (parsed_json_or_None, human_error_or_None).

    The tool prints its JSON to stdout on every verdict path (exit 0 = DONE,
    1 = NOT-DONE, 3 = UNKNOWN). A crash, timeout, or unparseable stdout is a
    tool ERROR -- fail closed, never guess."""
    cmd = ["./unit-status.sh", unit_id, "--cc-dir", cc_dir, "--json"]
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
    not_enforced = []        # (path, unit_id, status_cell)
    for path in files:
        basename = Path(path).name
        for unit_id, status in added_verified_rows(args.base, args.head, path):
            if basename in UNPARSEABLE_LEDGER_FILES:
                not_enforced.append((path, unit_id, status))
            else:
                candidates.setdefault(unit_id, []).append((path, status))

    if not candidates and not not_enforced:
        print(f"ledger-truth gate: {len(files)} ledger file(s) changed, but no added row claims")
        print("verified/done -- nothing to gate. PASS.")
        return

    print(f"ledger-truth gate: {len(candidates)} candidate unit(s) claiming verified/done"
          + (f", {len(not_enforced)} row(s) in unparseable ledger file(s)" if not_enforced else ""))
    print(f"diff range: {args.base[:12]}..{args.head[:12]}")

    failures = []   # human-readable failure blocks
    passes = []     # unit ids with a real git-verified DONE
    zero_leg = []   # unit ids whose DONE is NOT independently checked

    for unit_id in sorted(candidates, key=lambda u: int(u[1:])):
        where = ", ".join(sorted({p for p, _ in candidates[unit_id]}))
        result, error = run_unit_status(unit_id, args.cc_dir)
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
    for path, unit_id, status in not_enforced:
        print(f"NOT ENFORCED -- HUMAN REVIEW REQUIRED: {unit_id} in {path}")
        print(f"  row claims '{status}', but this ledger's row format cannot be parsed by the tool")
        print("  (and its U-numbering belongs to a different campaign -- the tool would judge the")
        print("  WRONG unit's row). This is not a caught false stamp and not a pass: a human must")
        print("  verify this row by hand.")

    failed = bool(failures) or bool(not_enforced)
    if failures:
        print("\nFAILURES:")
        for block in failures:
            print(block)
    print(f"\nGATE RESULT: {'FAIL -- see the named units above; every one needs a human decision before merge.' if failed else 'PASS.'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
