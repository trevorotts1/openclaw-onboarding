#!/usr/bin/env python3
"""cycle_manifest_reconcile.py — Skill 35's cycle-manifest variant of the
producer-reconcile pattern (U100), generalized from B-U13/U27
(06-ghl-install-pages/tools/cc_board.py `reconcile`) and its U79 Anthology
Engine precedent (59-anthology-engine/scripts/mc_board.py `cmd_reconcile`).

WHAT THIS IS: run-publishing-cycle.sh writes ONE `cycle-manifest.json` per
publishing cycle into that cycle's workdir and, since U100, ALWAYS stamps a
`cc_board_attempt` sub-object onto it recording whether the Command Center
board was even reachable/configured (`mc_token_resolved`) and whether the
Kanban card actually landed (`ok` + `task_id`) — closing the same
SKILL.md:607-608-style blindness B-U13 closed for Skill 6: a suppressed or
failed board-ingest attempt used to look IDENTICAL to a cycle that never
tried at all.

`reconcile()` sweeps every cycle's manifest under a runs-root and classifies
it:
  clean   — cc_board_attempt present, mc_token_resolved=True, ok=True, a
            task_id landed.
  drift   — cc_board_attempt present but the board was unset/unreachable
            (mc_token_resolved=False) OR the attempt failed (ok=False).
  unwired — no cc_board_attempt at all (a pre-U100 manifest, or a cycle that
            predates this wiring). Informational only — never drift.

Non-gating, read-only, fail-soft, idempotent — safe to run repeatedly from a
health-probe cron tick or ad hoc from the CLI. NEVER mutates a manifest.

Usage:
    cycle_manifest_reconcile.py reconcile [--base-dir DIR] [--json]

Exit code is ALWAYS 0 (non-gating) — the verdict lives in the printed
report's `all_clean` / `drift` fields, never in the process exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_MANIFEST_FILENAME = "cycle-manifest.json"


def resolve_state_dir(env: Optional[dict] = None) -> str:
    """Resolve the runs-root to sweep for `reconcile`. Resolution order:
      1. ``SKILL35_EVIDENCE_BASE_DIR`` env override (explicit, highest
         precedence).
      2. ``$HOME/.openclaw/data/skill-35/runs`` — the exact runs-root
         ``run-publishing-cycle.sh`` documents for ``--workdir``'s default
         (``$HOME/.openclaw/data/skill-35/runs/<run-id>``).
      3. ``""`` — no resolvable base (CI / a bare checkout with no HOME);
         callers treat this as "not applicable", never as an error.

    Never raises; never touches the network."""
    env = env if env is not None else os.environ
    explicit = (env.get("SKILL35_EVIDENCE_BASE_DIR") or "").strip()
    if explicit:
        return explicit
    home = (env.get("HOME") or "").strip()
    if not home:
        return ""
    return os.path.join(home, ".openclaw", "data", "skill-35", "runs")


def list_evidence_runs(base_dir: str) -> List[str]:
    """Every immediate subdirectory of ``base_dir`` — one per publishing-cycle
    run-id, each a candidate to hold a ``cycle-manifest.json``. Read-only;
    never raises (an unreadable base_dir yields an empty list)."""
    runs: List[str] = []
    try:
        if not base_dir or not os.path.isdir(base_dir):
            return runs
        for name in sorted(os.listdir(base_dir)):
            run_dir = os.path.join(base_dir, name)
            if os.path.isdir(run_dir):
                runs.append(run_dir)
    except OSError:
        return runs
    return runs


def _read_manifest(run_dir: str) -> Optional[dict]:
    path = os.path.join(run_dir, _MANIFEST_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


@dataclass
class ReconcileReport:
    base_dir: str
    applicable: bool = True
    total_runs: int = 0
    clean: list = field(default_factory=list)      # run ids: attempt present + landed OK
    drift: list = field(default_factory=list)       # [{run, reason}]
    unwired: list = field(default_factory=list)       # run ids: no cc_board_attempt yet

    def all_clean(self) -> bool:
        return not self.drift

    def as_dict(self) -> dict:
        return {
            "base_dir": self.base_dir,
            "applicable": self.applicable,
            "total_runs": self.total_runs,
            "clean": self.clean,
            "drift": self.drift,
            "unwired": self.unwired,
            "all_clean": self.all_clean(),
        }


def reconcile(base_dir: Optional[str] = None, *, env: Optional[dict] = None) -> ReconcileReport:
    """Run ONE reconciliation pass (U100 — the producer-reconcile pattern
    generalized from B-U13/U27 to Skill 35's cycle-manifest variant).

    Never raises; never mutates anything; never blocks a cycle — read-only,
    idempotent, safe to run repeatedly (daily maintenance tick or ad hoc)."""
    resolved = (base_dir or "").strip() or resolve_state_dir(env)
    report = ReconcileReport(base_dir=resolved)

    if not resolved or not os.path.isdir(resolved):
        report.applicable = False
        return report

    for run_dir in list_evidence_runs(resolved):
        run_id = os.path.basename(run_dir)
        manifest = _read_manifest(run_dir)

        if manifest is None:
            # No cycle-manifest.json at all — a run dir that predates the
            # manifest write, or an unrelated directory. Informational only.
            report.unwired.append(run_id)
            continue

        attempt = manifest.get("cc_board_attempt")
        if not isinstance(attempt, dict):
            # A pre-U100 manifest: run-publishing-cycle.sh ran before this
            # unit shipped and never stamped an attempt outcome. Same
            # "unwired" treatment as B-U13's own no-receipt case — never a
            # drift finding.
            report.unwired.append(run_id)
            continue

        report.total_runs += 1

        if not attempt.get("mc_token_resolved"):
            report.drift.append({
                "run": run_id,
                "reason": "MC_API_TOKEN unresolved / MISSION_CONTROL_URL "
                          "unreachable at cycle start — card never landed",
            })
            continue

        if not attempt.get("ok") or not attempt.get("task_id"):
            report.drift.append({
                "run": run_id,
                "reason": "board reachable but ingest failed (no task_id landed)",
            })
            continue

        report.clean.append(run_id)

    return report


def _reconcile_cli(argv: Optional[list] = None) -> int:
    """``cycle_manifest_reconcile.py reconcile [--base-dir DIR] [--json]``
    (U100, cloned from cc_board.py's B-U13/U27 CLI form). ALWAYS exits 0 —
    this is a non-gating, fail-soft, read-only sweep. The verdict lives in
    the printed report's ``all_clean`` / ``drift`` fields for the caller
    (operator, cron, or the Command Center's health probe) to read — never in
    the process exit code."""
    p = argparse.ArgumentParser(
        prog="cycle_manifest_reconcile.py reconcile",
        description="U100 — sweep Skill 35's cycle-manifest run-evidence "
                     "roots for board-ingest drift (non-gating; never flips "
                     "a box red).",
    )
    p.add_argument("--base-dir", default="",
                    help="Runs-root to sweep (default: SKILL35_EVIDENCE_BASE_DIR "
                         "env, else $HOME/.openclaw/data/skill-35/runs).")
    p.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = p.parse_args(argv)

    report = reconcile(args.base_dir or None)
    d = report.as_dict()

    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print(f"Base dir: {d['base_dir']} (applicable={d['applicable']})")
        print(f"Total runs (with a cc_board_attempt): {d['total_runs']}")
        print(f"  Clean:   {len(d['clean'])} {d['clean']}")
        print(f"  Drift:   {len(d['drift'])} {d['drift']}")
        print(f"  Unwired: {len(d['unwired'])} {d['unwired']}")
        print("RESULT:", "CLEAN" if d["all_clean"] else "ATTENTION NEEDED (non-gating)")

    return 0  # non-gating — always exit 0, per B-U13/U27


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "reconcile":
        return _reconcile_cli(argv[1:])
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
