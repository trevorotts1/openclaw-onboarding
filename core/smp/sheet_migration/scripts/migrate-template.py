#!/usr/bin/env python3
"""migrate-template.py — live-sheet migration 1.2.0 -> 1.3.0 for the Skill 35
social media planner template (Owner D27 / decision 35 / plan section 6.15,
2026-10-07).

Adds the five drama-song fields to the Weekly Overview of every live client
sheet — style chosen, status, KIE cost, video link, channels posted — and
stamps schema_version 1.3.0. The bump is purely additive: no cell value, row,
tab or heading order is changed, and the technical ``_row_key`` cell moves from
column U to column Z instead of being overwritten. `migrate.lossless()` proves
it on every migration this script writes.

Interface is the same shape as Skill 35's `scripts/migrate-template.py`
(offline fixture mode, dry-run by default, backup BEFORE --apply, the live
master template refused), plus the schema-version gate.

Usage:
  python3 core/smp/sheet_migration/scripts/migrate-template.py --fixture f.json
  python3 core/smp/sheet_migration/scripts/migrate-template.py --fixture f.json --apply
  python3 core/smp/sheet_migration/scripts/migrate-template.py --sheet-id ID --apply \
      --client-title "Acme Co" --timezone America/New_York

Exit codes:
  0 = clean / already 1.3.0 / migration applied
  2 = changes pending — this was a dry-run preview, nothing was altered
  3 = nothing altered (--apply withheld: live sheet needs deployment-phase
      credentials, or the live master template was refused)
  4 = rejected (unsupported or hand-broken schema_version, no Weekly Overview)

No network call is ever made: --sheet-id paths stop before any transport and
the live master template is always refused.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

from migrate import (  # noqa: E402
    DRAMA_SONG_FIELDS,
    SCHEMA_FROM,
    SCHEMA_TO,
    MigrationError,
    lossless,
    migrate_doc,
)

LIVE_TEMPLATE_ID = "1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c"


def write_backup(path, doc, report):
    """Backup FIRST — the caller is always one copy from their own state."""
    backup_path = path + ".backup.json"
    payload = {
        "backed_up_at": datetime.now(timezone.utc).isoformat(),
        "source_file": os.path.abspath(path),
        "migrated_from": report["from_version"],
        "migrated_to": SCHEMA_TO,
        "plan": report["plan"],
        "document": doc,
    }
    with open(backup_path, "w") as f:
        json.dump(payload, f, indent=2)
    return backup_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Skill 35 planner sheet migration 1.2.0 -> 1.3.0 "
                    "(dry-run by default; additive, no data loss)")
    parser.add_argument("--fixture",
                        help="offline fixture JSON: {schema_version?, tabs: "
                             "{name: {headings, rows}}}")
    parser.add_argument("--sheet-id",
                        help="Google Sheet ID to migrate (never the live "
                             "master template implicitly)")
    parser.add_argument("--apply", action="store_true",
                        help="apply the migration (backup is written first)")
    parser.add_argument("--client-title", help="verified client/company title")
    parser.add_argument("--timezone", help="verified IANA timezone")
    parser.add_argument("--out",
                        help="output path (default: FIXTURE.migrated.json)")
    args = parser.parse_args(argv)

    if not args.fixture and not args.sheet_id:
        parser.error("one of --fixture or --sheet-id is required")

    if args.sheet_id:
        if args.sheet_id == LIVE_TEMPLATE_ID:
            print("REFUSED: the live master template is LIVE infrastructure — "
                  "application is deployment-phase (WF00). Pass a sandbox or "
                  "client-copy sheet ID.")
            return 3
        print("Live-sheet migration for %s requires Sheets credentials; this "
              "build performs fixture migrations offline. Use --fixture for "
              "dry-run/apply, or run the deployment-phase provisioner (WF00) "
              "against the live sheet." % args.sheet_id)
        return 3 if args.apply else 2

    with open(args.fixture) as f:
        original = json.load(f)

    try:
        migrated, report = migrate_doc(original)
    except MigrationError as exc:
        print("REJECTED: %s" % exc)
        return 4

    print("migrate-template.py — planner sheet %s -> %s"
          % (report["from_version"], SCHEMA_TO))
    print("drama-song fields on '%s': %s"
          % ("Weekly Overview", ", ".join(DRAMA_SONG_FIELDS)))
    if report["findings"]:
        print("%d finding(s):" % len(report["findings"]))
        for line in report["findings"]:
            print("  - %s" % line)
    else:
        print("no content change needed — version stamp only")
    print("plan:")
    for step in report["plan"]:
        print("  [%s] %s: %s" % (step["action"], step.get("tab", ""),
                                 step["detail"]))

    if report["already_current"]:
        print("ALREADY %s — nothing to migrate." % SCHEMA_TO)
        return 0

    if not args.apply:
        print("DRY-RUN PREVIEW — nothing was altered. Re-run with --apply to "
              "migrate. %d cell(s) would be added; 0 cell(s) would change."
              % report["cells_added"])
        return 2

    # Identity is provisioned BEFORE anything is written, so the migrated file
    # on disk always carries the stamped schema_version.
    identity = migrated.setdefault("identity", {})
    identity["schema_version"] = SCHEMA_TO
    if args.client_title:
        identity["client_title"] = args.client_title
    if args.timezone:
        identity["timezone"] = args.timezone

    # Prove no loss on the document we are about to write.
    ok, problems = lossless(original, migrated)
    if not ok:
        print("REJECTED: no-loss proof failed:")
        for p in problems:
            print("  - %s" % p)
        return 4

    backup_path = write_backup(args.fixture, original, report)
    out_path = args.out or (args.fixture + ".migrated.json")
    with open(out_path, "w") as f:
        json.dump(migrated, f, indent=2)

    print("NO-LOSS PROOF: passed (%d pre-existing cell value(s) verified, "
          "0 changed, %d new empty cell(s))" % (
              sum(len(r) for t in (original.get("tabs") or {}).values()
                  for r in (t.get("rows") or [])),
              report["cells_added"]))
    print("APPLIED: backup written FIRST to %s" % backup_path)
    print("migrated document written to %s" % out_path)
    if not args.client_title or not args.timezone:
        print("NOTE: identity fields not all provided — pass --client-title and "
              "--timezone to provision title/timezone from verified identity.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
