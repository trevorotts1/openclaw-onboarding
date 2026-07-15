#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""approve_paid_run.py — explicit budget-cap approval (Skill 62, U7).

Implements spec Section 10.3 items 5-6 ("budget cap exists" / "user/operator
approval is recorded") and Section 8.1 group 12 ("Approval workflow — who
approves ... budget"). This is the ONLY place in the skill that is allowed to
set ``project-manifest.json``'s ``budget.cap_usd`` / ``budget.approved`` /
``budget.approved_by`` / ``budget.approved_at`` fields, and it always writes a
matching audit entry into ``approvals[]`` in the same locked transaction — a
caller can never flip ``budget.approved`` true without leaving a real,
timestamped, named record behind (spec 25 rule 8: "do not mark done from
agent claims"; QC category 6 "safe and sound").

The recorded cap here IS the HARD CAP `scripts/state_engine.py`'s
`ProjectState.begin_task()` already enforces (it raises `BudgetExceeded`,
spec 10.4's "hard-stop before the next paid call if projected spend exceeds
the cap") — this module keeps `project-manifest.budget.cap_usd` and
`cost-ledger.budget_cap_usd` in lockstep so the cap can never drift between
the two files. `prove_budget.py`'s `evaluate_approval()` (P5-BUDGET gate) and
`evaluate_paid_call_preconditions()` (cross-cutting AF-CWFE-PAID-GATE) both
read what this module writes; they never write it themselves.

No secret value is ever accepted, stored, or logged by this module —
`approved_by` is an identity label only (e.g. "operator", "client:acme"),
never a credential.

stdlib only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import state_engine as se  # noqa: E402


class ApprovalError(Exception):
    """Base class for every error this module raises."""


class InvalidCapError(ApprovalError):
    """cap_usd is not a positive number, or would be set below cumulative
    spend already recorded against the project."""


class InvalidApproverError(ApprovalError):
    """approved_by is missing/empty, or looks like it might carry a secret
    value rather than a plain identity label."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# A conservative denylist of substrings that suggest a caller accidentally
# passed a credential instead of an identity label — fails closed rather than
# writing a secret-shaped value into an approvals[] record (spec 20 "never
# log secret values"; this module can only guess, so it only catches the
# obvious shapes; the real secret-safety boundary is that callers must never
# be passed a secret VALUE in the first place — see CLAUDE-visible doctrine
# "secrets by NAME only").
_SUSPICIOUS_APPROVER_SUBSTRINGS = ("sk-", "pit-", "api_key", "apikey", "secret", "token=", "bearer ")


def _validate_approver(approved_by: str) -> None:
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise InvalidApproverError("approved_by must be a non-empty identity label")
    lowered = approved_by.lower()
    for needle in _SUSPICIOUS_APPROVER_SUBSTRINGS:
        if needle in lowered:
            raise InvalidApproverError(
                "approved_by looks like it may contain a secret value, not a plain identity "
                f"label (matched pattern {needle!r}) — pass a name/id only, e.g. 'operator' "
                "or 'client:acme', never a credential"
            )


def approve(
    run_dir: Path,
    *,
    cap_usd: float,
    approved_by: str,
    note: str = "",
) -> Dict[str, Any]:
    """Locked. Records an explicit, named, timestamped budget-cap approval on
    both project-manifest.json (budget.* + a new approvals[] entry) and
    cost-ledger.json (budget_cap_usd/remaining_budget_usd), atomically and in
    lockstep. Returns the updated project-manifest budget block.

    Raises InvalidCapError if cap_usd is not a positive finite number, or is
    below the project's cumulative_spend_usd already recorded (a cap can
    never be retroactively set below money already actually spent).
    Raises InvalidApproverError if approved_by is empty or secret-shaped.
    Re-approving (e.g. raising the cap later) is fully supported — every call
    is itself the explicit approval event; nothing here auto-increases a cap
    without a fresh, explicit call naming the new value and the approver.
    """
    if not isinstance(cap_usd, (int, float)) or isinstance(cap_usd, bool):
        raise InvalidCapError(f"cap_usd must be a number, got {cap_usd!r}")
    if not (cap_usd > 0) or cap_usd != cap_usd or cap_usd in (float("inf"), float("-inf")):
        raise InvalidCapError(f"cap_usd must be a positive finite number, got {cap_usd!r}")
    _validate_approver(approved_by)

    state = se.ProjectState(run_dir)
    now = _now()
    with state.lock():
        manifest = state.load("project-manifest")
        ledger = state.load("cost-ledger")

        cumulative = ledger.get("cumulative_spend_usd", 0.0)
        if cap_usd < cumulative:
            raise InvalidCapError(
                f"cap_usd {cap_usd} is below cumulative_spend_usd {cumulative} already "
                "recorded for this project — a budget cap can never be set below money "
                "already spent"
            )

        manifest["budget"]["cap_usd"] = float(cap_usd)
        manifest["budget"]["approved"] = True
        manifest["budget"]["approved_by"] = approved_by
        manifest["budget"]["approved_at"] = now
        manifest["approvals"].append(
            {
                "kind": "budget",
                "approved_by": approved_by,
                "approved_at": now,
                "cap_usd": float(cap_usd),
                "note": note,
            }
        )
        manifest["updated_at"] = now
        state.save("project-manifest", manifest)

        ledger["budget_cap_usd"] = float(cap_usd)
        ledger["remaining_budget_usd"] = round(float(cap_usd) - cumulative, 6)
        ledger["updated_at"] = now
        state.save("cost-ledger", ledger)

    return manifest["budget"]


def is_approved(run_dir: Path) -> bool:
    """Read-only. True iff project-manifest.budget.approved is true AND a
    matching 'budget' kind approvals[] audit entry exists with the same
    cap_usd/approved_by/approved_at — i.e. the boolean flag and the audit
    trail agree. This is the check evaluate_approval()/
    evaluate_paid_call_preconditions() in prove_budget.py delegate to."""
    state = se.ProjectState(run_dir)
    if not state.exists("project-manifest"):
        return False
    manifest = state.load("project-manifest")
    budget = manifest.get("budget", {})
    if not budget.get("approved"):
        return False
    approved_by = budget.get("approved_by")
    approved_at = budget.get("approved_at")
    cap_usd = budget.get("cap_usd")
    for entry in manifest.get("approvals", []):
        if (
            entry.get("kind") == "budget"
            and entry.get("approved_by") == approved_by
            and entry.get("approved_at") == approved_at
            and entry.get("cap_usd") == cap_usd
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record an explicit budget-cap approval for a Cinematic and Web Funnel "
        "Engine project run directory."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--cap-usd", required=True, type=float)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(3)

    try:
        budget = approve(run_dir, cap_usd=args.cap_usd, approved_by=args.approved_by, note=args.note)
    except ApprovalError as exc:
        print(f"[FAIL] approval rejected: {exc}", file=sys.stderr)
        sys.exit(2)

    print(f"[PASS] budget approved: {json.dumps(budget, indent=2)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
