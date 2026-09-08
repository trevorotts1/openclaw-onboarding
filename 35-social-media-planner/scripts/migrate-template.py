#!/usr/bin/env python3
"""migrate-template.py — F22 clean-template migration for Social Media Planner
sheets (Skill 35 / Skill 57).

Migrates an existing planner sheet (or a template copy) to the clean template
contract in config/sheet-template.schema.json:

  - detects duplicate headings (the U:AN pattern found in the live master
    template's Weekly Overview),
  - detects legacy template starter content: old campaigns with
    Complete/Scheduled/Published statuses, demo brand names, publication
    claims,
  - in the DRY-RUN PREVIEW (the default) reports exactly what would change and
    NOTHING is altered,
  - with --apply: backs up the affected ranges to a local JSON backup file
    BEFORE altering anything, blanks ONLY template starter content, and
    preserves legitimate client rows and notes untouched,
  - provisions identity (client/company title, timezone, schema_version) from
    verified identity arguments (--client-title, --timezone).

The live master template 1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c is LIVE
infrastructure: this script never edits it implicitly. It runs against a sheet
ID you explicitly pass (a sandbox or a client copy), and template application
is a deployment-phase (WF00) step.

Offline fixture mode (used by the test suite and for previewing without
credentials): pass --fixture FILE instead of --sheet-id; FILE is a JSON
document {tabs: {name: {headings: [...], rows: [[...], ...]}}}. With --apply
the migrated fixture is written to FILE.migrated.json and the backup to
FILE.backup.json.

Usage:
  python3 35-social-media-planner/scripts/migrate-template.py --fixture f.json
  python3 35-social-media-planner/scripts/migrate-template.py --sheet-id ID --apply \
      --client-title "Acme Co" --timezone America/New_York

Exit 0 = clean (or migrated); exit 2 = findings that need a reviewed dry-run;
exit 3 = nothing altered (--apply withheld).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BASE, "config", "sheet-template.schema.json")

LIVE_TEMPLATE_ID = "1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c"
DEFAULT_TAB = "Weekly Overview"
EXAMPLE_TAB_MARKERS = ("example", "demo")

# Legacy template starter content markers (F22 finding basis: an old campaign
# with completed/scheduled/published statuses in the master template's starter
# rows). Publication CLAIMS in a starter row are template content, not client
# history — a fresh sheet must never open claiming progress it has not made.
STATUS_VALUES = {"complete", "failed", "qc review", "scheduled", "published",
                 "needs attention", "posted", "approved"}
LEGACY_BRAND_MARKERS = re.compile(
    r"(your brand|sample|demo|example brand|acme|template brand|placeholder)",
    re.I)


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def is_blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def is_example_tab(name):
    lowered = name.lower()
    return any(m in lowered for m in EXAMPLE_TAB_MARKERS)


def find_duplicate_headings(headings):
    seen, dupes = set(), []
    for h in headings:
        key = str(h).strip().lower()
        if not key:
            continue
        if key in seen and str(h).strip() not in dupes:
            dupes.append(str(h).strip())
        seen.add(key)
    return dupes


def classify_row(row_index, row, headings):
    """Classify a data row as template starter content vs legitimate client row.

    Returns (is_starter, reasons). Starter rows are EMPTY of any brand,
    campaign or publication content per the contract; a row that carries a
    publication status, a legacy brand marker, or demo campaign copy IS
    starter content. Client rows (any other non-empty content — notes, real
    work) are preserved.
    """
    if all(is_blank(c) for c in row):
        return False, []  # an empty row is nothing to migrate
    reasons = []
    for cell_index, cell in enumerate(row):
        text = str(cell).strip() if not is_blank(cell) else ""
        if not text:
            continue
        heading = str(headings[cell_index]).strip() if cell_index < len(headings) else ""
        if heading.lower() in {"qc", "overall", "state", "status"} and text.lower() in STATUS_VALUES:
            reasons.append(f"row {row_index}: publication status '{text}' in '{heading}' (starter claim)")
        elif LEGACY_BRAND_MARKERS.search(text):
            reasons.append(f"row {row_index}: legacy brand/demo marker in '{heading}': {text[:60]!r}")
    return bool(reasons), reasons


def migrate_tabs(doc, schema):
    """Compute the migration plan. Returns (plan, findings, migrated_doc)."""
    plan = []
    findings = []
    migrated = copy.deepcopy(doc)
    tabs = doc.get("tabs", {})

    for tab_name, tab in tabs.items():
        headings = tab.get("headings", [])
        rows = tab.get("rows", [])
        if is_example_tab(tab_name):
            plan.append({"tab": tab_name, "action": "keep",
                         "detail": "example tab is never copied into a live client planner — content untouched"})
            continue
        dupes = find_duplicate_headings(headings)
        if dupes:
            findings.append(f"tab '{tab_name}': duplicate headings (U:AN pattern): {dupes}")
            plan.append({"tab": tab_name, "action": "dedupe_headings",
                         "detail": f"duplicate heading columns detected: {dupes}"})
        starter_rows = []
        for i, row in enumerate(rows):
            is_starter, reasons = classify_row(i, row, headings)
            if is_starter:
                starter_rows.append(i)
                findings.extend(f"tab '{tab_name}': {r}" for r in reasons)
        if starter_rows:
            plan.append({"tab": tab_name, "action": "blank_starter_rows",
                         "rows": starter_rows,
                         "detail": f"{len(starter_rows)} template starter row(s) would be blanked: {starter_rows}"})
            if tab_name in migrated.get("tabs", {}):
                for i in starter_rows:
                    migrated["tabs"][tab_name]["rows"][i] = ["" for _ in rows[i]]
        client_rows = [i for i in range(len(rows))
                       if i not in starter_rows and not all(is_blank(c) for c in rows[i])]
        if client_rows:
            plan.append({"tab": tab_name, "action": "preserve_client_rows",
                         "rows": client_rows,
                         "detail": f"{len(client_rows)} legitimate client row(s) preserved untouched: {client_rows}"})

    # Identity provisioning (verified identity, never a template placeholder).
    plan.append({"action": "provision_identity",
                 "detail": "client/company title, IANA timezone and schema_version are provisioned from verified identity args (--client-title/--timezone) or flagged for deployment-phase provisioning"})
    return plan, findings, migrated


def write_backup(path, doc, planned_changes):
    backup_path = path + ".backup.json"
    payload = {
        "backed_up_at": datetime.now(timezone.utc).isoformat(),
        "source_file": os.path.abspath(path),
        "planned_changes": planned_changes,
        "document": doc,
    }
    with open(backup_path, "w") as f:
        json.dump(payload, f, indent=2)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description="F22 clean-template migration (dry-run default)")
    parser.add_argument("--fixture", help="offline fixture JSON: {tabs: {name: {headings, rows}}}")
    parser.add_argument("--sheet-id", help="Google Sheet ID to migrate (never the live template implicitly)")
    parser.add_argument("--apply", action="store_true", help="apply the migration (backup is written first)")
    parser.add_argument("--client-title", help="verified client/company title to provision")
    parser.add_argument("--timezone", help="verified IANA timezone to provision")
    args = parser.parse_args()

    schema = load_schema()
    schema_version = schema.get("schema_version", "0")

    if args.sheet_id:
        if args.sheet_id == LIVE_TEMPLATE_ID:
            print("REFUSED: the live master template is LIVE infrastructure — "
                  "application is deployment-phase (WF00). Pass a sandbox or client-copy sheet ID.")
            return 3
        print(f"Live-sheet migration for {args.sheet_id} requires Sheets credentials; "
              "this build performs fixture previews offline. Use --fixture for dry-run/apply, "
              "or run the deployment-phase provisioner (WF00) against the live sheet.")
        return 3 if args.apply else 2

    if not args.fixture:
        parser.error("one of --fixture or --sheet-id is required")

    with open(args.fixture) as f:
        doc = json.load(f)

    plan, findings, migrated = migrate_tabs(doc, schema)
    identity = {"schema_version": schema_version}
    if args.client_title:
        identity["client_title"] = args.client_title
    if args.timezone:
        identity["timezone"] = args.timezone
    if args.apply:
        migrated.setdefault("identity", {}).update(identity)

    print(f"migrate-template.py — template contract v{schema_version}")
    if findings:
        print(f"{len(findings)} finding(s):")
        for fnd in findings:
            print(f"  - {fnd}")
    else:
        print("no legacy content or duplicate headings found — nothing to migrate")
    print("plan:")
    for step in plan:
        print(f"  [{step['action']}] {step.get('tab', '')}: {step['detail']}")

    if not args.apply:
        print("DRY-RUN PREVIEW — nothing was altered. Re-run with --apply to migrate.")
        return 2 if findings else 0

    # BACKUP BEFORE ALTERING — the caller is always one copy from their own state.
    backup_path = write_backup(args.fixture, doc, plan)
    out_path = args.fixture + ".migrated.json"
    with open(out_path, "w") as f:
        json.dump(migrated, f, indent=2)
    print(f"APPLIED: backup written FIRST to {backup_path}")
    print(f"migrated document written to {out_path}")
    if not args.client_title or not args.timezone:
        print("NOTE: identity fields not all provided — pass --client-title and "
              "--timezone to provision title/timezone from verified identity.")
    return 0


if __name__ == "__main__":
    sys.exit(main())