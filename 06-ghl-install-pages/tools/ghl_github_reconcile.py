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

``reconcile()`` is a STRAIGHTFORWARD sweep over ONE evidence root at a time —
it is deliberately NOT a fleet-wide crawler/daemon on its own. ``sweep_base()``
(U24/B-U10) is the maintenance-window mode: it reuses the ONE canonical
evidence-root discovery ``cc_board.py``'s own reconcile (U27) already uses
(``cc_board.list_evidence_runs`` over a base dir) to sweep every run in one
pass and writes a dated JSON log proving each scheduled pass actually ran —
see SKILL.md's Reconciliation section for the `openclaw cron create` wiring.

Reuses ``ghl_receipts`` (the existing F6 store) for both reading the ledger
and, on retry, writing the updated archive receipt — no new receipt schema.

CLI
---
    python3 ghl_github_reconcile.py --evidence-root <dir> [--retry] [--json]
    python3 ghl_github_reconcile.py --sweep-base <dir> [--retry] [--json] [--no-log]

Exit code (both modes): 0 if every vercel_deploy page has a verified archive
(after retry, if requested); 1 if one or more remain missing/failed/flagged.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_receipts  # noqa: E402
import ghl_github_archive as gha  # noqa: E402
import cc_board  # noqa: E402  (U24/B-U10 — the ONE evidence-root discovery U27 already uses)


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
    """Delegates to ``ghl_github_archive.is_archive_verified`` — the ONE
    "verified" definition, shared with ``ghl_archive_receipt_gate.py``
    (U24/B-U10) so the retry sweep and the per-build FAB-QC gate can never
    silently disagree on what counts as archived."""
    return gha.is_archive_verified(receipt)


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

        try:
            result = gha.run_archive_task(task, requester=requester, env=env)
        except Exception as exc:  # noqa: BLE001 — one bad page must never abort the whole sweep
            report.flagged.append({"marker": marker, "reason": f"retry raised unexpectedly: {exc}"})
            continue
        if _archive_ok(result.get("receipt")):
            report.retried_ok.append(marker)
        else:
            report.missing_or_failed.append(marker)

    return report


# ── Multi-root sweep — the daily maintenance-window mode (U24/B-U10 item 2) ──
#
# ``reconcile()`` above is deliberately scoped to ONE evidence root at a time
# (see the module docstring: "not a fleet-wide crawler"). That is still true —
# ``sweep_base`` does not invent a new evidence-root discovery mechanism, it
# reuses the ONE canonical one U27's ``cc_board.reconcile()`` already sweeps
# (``cc_board.resolve_evidence_base`` / ``cc_board.list_evidence_runs`` — every
# ``v2-<RUN_ID>`` directory under the base that carries an intake receipt) and
# simply runs ``reconcile()`` over each one, so scheduling this as ONE cron
# entry closes the doctrine gap without a second "where does evidence live"
# definition to drift out of sync with U27's.

_SWEEP_LOG_SUBDIR = "github-archive-reconcile-logs"


@dataclass
class SweepReport:
    base_dir: str
    applicable: bool = True
    total_runs: int = 0
    runs: list = field(default_factory=list)   # [{"run": <run_id>, "report": <ReconcileReport.as_dict()>}]
    log_path: str = ""

    def all_clean(self) -> bool:
        return self.applicable and all(r["report"]["all_clean"] for r in self.runs)

    def as_dict(self) -> dict:
        return {
            "base_dir": self.base_dir,
            "applicable": self.applicable,
            "total_runs": self.total_runs,
            "runs": self.runs,
            "all_clean": self.all_clean(),
            "log_path": self.log_path,
        }


def sweep_base(base_dir: str, *, retry: bool = True,
                requester=None, env: dict | None = None,
                write_log: bool = True, clock=None) -> SweepReport:
    """Run ``reconcile()`` over EVERY Skill-6 evidence run under ``base_dir``
    and (by default) write ONE dated JSON log recording the pass — the
    on-disk proof a scheduled maintenance-window cron actually fired, every
    time it fires (never overwritten; one new timestamped file per sweep).

    Never raises. An unresolvable/absent/empty ``base_dir`` (a bare checkout,
    a fresh box with no builds yet) is ``applicable=False`` — nothing to
    sweep, not an error.
    """
    report = SweepReport(base_dir=base_dir)
    if not base_dir or not os.path.isdir(base_dir):
        report.applicable = False
        return report

    for run_dir in cc_board.list_evidence_runs(base_dir):
        run_report = reconcile(run_dir, retry=retry, requester=requester, env=env)
        report.runs.append({"run": os.path.basename(run_dir), "report": run_report.as_dict()})
    report.total_runs = len(report.runs)

    if write_log:
        _now = clock or (lambda: time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
        log_dir = os.path.join(base_dir, _SWEEP_LOG_SUBDIR)
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{_now()}.json")
        report.log_path = log_path   # set BEFORE serializing so the log's own
                                      # content self-references its own path
        tmp_path = f"{log_path}.tmp-{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(report.as_dict(), fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, log_path)

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[list] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_github_reconcile",
        description="Reconcile VERCEL_EMBED deployments against their GitHub archival receipts.",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--evidence-root",
                       help="Sweep ONE run-evidence root (same root passed to ghl_vercel.run_pipeline).")
    mode.add_argument("--sweep-base",
                       help="U24/B-U10 daily maintenance-window mode: sweep EVERY evidence run under "
                            "this base dir and write a dated log (see --no-log to suppress, testing only).")
    p.add_argument("--retry", action="store_true",
                   help="Retry any missing/failed archive using its staged source, if still present.")
    p.add_argument("--json", action="store_true", help="Print the report as JSON.")
    p.add_argument("--no-log", action="store_true",
                   help="--sweep-base only: skip writing the dated log file (testing).")
    args = p.parse_args(argv)

    if args.sweep_base:
        sweep = sweep_base(args.sweep_base, retry=args.retry, write_log=not args.no_log)
        d = sweep.as_dict()
        if args.json:
            print(json.dumps(d, indent=2))
        else:
            print(f"Base dir: {d['base_dir']}")
            print(f"Total evidence runs swept: {d['total_runs']}")
            for r in d["runs"]:
                print(f"  {r['run']}: {'CLEAN' if r['report']['all_clean'] else 'ATTENTION NEEDED'} "
                      f"(deploys={r['report']['total_deploys']})")
            print(f"Log written: {d['log_path'] or '(none — --no-log)'}")
            print("RESULT:", "CLEAN" if d["all_clean"] else "ATTENTION NEEDED")
        return 0 if sweep.all_clean() else 1

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
