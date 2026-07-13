#!/usr/bin/env python3
"""ghl_github_reconcile.py — reconciliation sweep for VERCEL_EMBED -> GitHub archival.

WHAT THIS CHECKS
----------------
``ghl_vercel.run_pipeline`` fires GitHub archival (``ghl_github_archive``) in a
DETACHED subprocess so a Vercel deploy never waits on GitHub. That means a
build can finish, report PASS, and its archive can still be in flight — or it
can have silently failed (no token, GitHub API error, box rebooted before the
subprocess finished, etc.). This sweep is the honesty check:

    list every page that went through the VERCEL_EMBED path (the
    ``vercel_deploy`` F6 receipts ``ghl_vercel.run_pipeline`` writes)
        -> confirm each one has a matching ``vercel_github_archive`` receipt
           with ``verify.ok == True`` (i.e. the code actually landed in GitHub)
        -> RETRY (if the staged source is still on disk under the evidence
           root) or FLAG (if it is not, or the retry itself fails).

This is a STRAIGHTFORWARD sweep over ONE evidence root at a time (or a set of
roots passed on the command line) — it is deliberately NOT a fleet-wide
crawler/daemon that auto-discovers every run-evidence root on a box. Wiring
this into a periodic cron / fleet-wide gate is an operator decision left open
(see SKILL.md's Reconciliation section) — scoped out here to avoid building a
new subsystem nobody asked for yet.

Reuses ``ghl_receipts`` (the existing F6 store) for both reading the ledger
and, on retry, writing the updated archive receipt — no new receipt schema.

CLI
---
    python3 ghl_github_reconcile.py --evidence-root <dir> [--retry] [--json]

Exit code: 0 if every vercel_deploy page has a verified archive (after retry,
if requested); 1 if one or more remain missing/failed/flagged.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_receipts  # noqa: E402
import ghl_github_archive as gha  # noqa: E402


@dataclass
class ReconcileReport:
    evidence_root: str
    total_deploys: int = 0
    archived_ok: list = field(default_factory=list)
    retried_ok: list = field(default_factory=list)
    missing_or_failed: list = field(default_factory=list)
    flagged: list = field(default_factory=list)

    def all_clean(self) -> bool:
        return not self.missing_or_failed and not self.flagged

    def as_dict(self) -> dict:
        return {
            "evidence_root": self.evidence_root,
            "total_deploys": self.total_deploys,
            "archived_ok": self.archived_ok,
            "retried_ok": self.retried_ok,
            "missing_or_failed": self.missing_or_failed,
            "flagged": self.flagged,
            "all_clean": self.all_clean(),
        }


def _archive_ok(receipt: Optional[dict]) -> bool:
    if not receipt:
        return False
    if receipt.get("action") not in ("created", "reused"):
        return False
    return bool(receipt.get("verify", {}).get("ok"))


def reconcile(evidence_root: str, *, retry: bool = False,
              requester=None, env: dict | None = None) -> ReconcileReport:
    """Run one reconciliation pass over ``evidence_root``.

    With ``retry=True``: for every deploy missing a verified archive, look for
    the staged source ``ghl_github_archive`` already wrote at build time
    (``<evidence_root>/vercel-github-archive/<marker>/task.json``) and, if
    present, re-run the archive job SYNCHRONOUSLY (blocking here is correct —
    this is an explicit maintenance sweep, not the live build path). If no
    staged source exists (e.g. a pre-existing page built before this feature
    shipped, or the evidence root was pruned), the page is FLAGGED — there is
    no source to re-push and reconciliation must never fabricate one.
    """
    report = ReconcileReport(evidence_root=evidence_root)

    all_receipts = ghl_receipts.list_receipts(evidence_root)
    deploy_receipts = [r for r in all_receipts if r.get("object_type") == gha.DEPLOY_RECEIPT_TYPE]
    archive_by_slug = {
        r["slug"]: r for r in all_receipts if r.get("object_type") == gha.ARCHIVE_RECEIPT_TYPE
    }

    report.total_deploys = len(deploy_receipts)

    for dep in deploy_receipts:
        marker = dep.get("slug")
        archive = archive_by_slug.get(marker)

        if _archive_ok(archive):
            report.archived_ok.append(marker)
            continue

        if not retry:
            report.missing_or_failed.append(marker)
            continue

        task_path = os.path.join(evidence_root, gha.ARCHIVE_SUBDIR, marker, "task.json")
        if not os.path.isfile(task_path):
            report.flagged.append({
                "marker": marker,
                "reason": "no staged source found (task.json missing) — cannot retry without fabricating source",
            })
            continue

        try:
            task = gha.read_task_file(task_path)
        except Exception as exc:  # noqa: BLE001
            report.flagged.append({"marker": marker, "reason": f"task.json unreadable: {exc}"})
            continue

        result = gha.run_archive_task(task, requester=requester, env=env)
        if _archive_ok(result.get("receipt")):
            report.retried_ok.append(marker)
        else:
            report.missing_or_failed.append(marker)

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[list] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_github_reconcile",
        description="Reconcile VERCEL_EMBED deployments against their GitHub archival receipts.",
    )
    p.add_argument("--evidence-root", required=True,
                   help="The run-evidence root to sweep (same root passed to ghl_vercel.run_pipeline).")
    p.add_argument("--retry", action="store_true",
                   help="Retry any missing/failed archive using its staged source, if still present.")
    p.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = p.parse_args(argv)

    report = reconcile(args.evidence_root, retry=args.retry)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        d = report.as_dict()
        print(f"Evidence root: {d['evidence_root']}")
        print(f"Total VERCEL_EMBED deploys: {d['total_deploys']}")
        print(f"  Archived OK:      {len(d['archived_ok'])} {d['archived_ok']}")
        print(f"  Retried OK:       {len(d['retried_ok'])} {d['retried_ok']}")
        print(f"  Missing/Failed:   {len(d['missing_or_failed'])} {d['missing_or_failed']}")
        print(f"  Flagged:          {len(d['flagged'])} {d['flagged']}")
        print("RESULT:", "CLEAN" if d["all_clean"] else "ATTENTION NEEDED")

    return 0 if report.all_clean() else 1


if __name__ == "__main__":
    sys.exit(main())
