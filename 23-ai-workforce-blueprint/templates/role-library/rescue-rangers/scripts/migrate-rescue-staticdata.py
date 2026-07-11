#!/usr/bin/env python3
# =============================================================================
# RESCUE RANGERS :: migrate-rescue-staticdata.py
# One-shot, IDEMPOTENT migration: n8n workflowStaticData export -> SQLite ledger.
# -----------------------------------------------------------------------------
# Topic-4 FIX 4-A migration leg. The Relay Brain kept its ticket queue + per-client
# daily counters in $getWorkflowStaticData('global') (volatile). This importer reads
# a JSON EXPORT of that staticData (or a full workflow export whose node staticData
# is nested) and folds every ticket + counter into the durable rescue_ledger.py DB.
#
# IDEMPOTENT: open_ticket is INSERT-OR-IGNORE on ticket_id, so re-running the
# migration over the same export never double-imports. Answered/resolved states in
# the export are re-applied (also idempotent). Safe to run repeatedly.
#
# TOLERANT SHAPE HANDLING (spec Open-Question 4: the exact staticData schema must be
# confirmed against a REAL export before the live cutover). This importer accepts:
#   * a bare staticData object:           {"pending":[...], "counters":{...}}
#   * a node-nested export:               {...,"staticData":{"global":{...}}}
#   * common ticket field aliases         (ticketId|id, clientName|client, box|boxName ...)
#   * counters as {client: N}             OR {client: {YYYY-MM-DD: N}}
# Unknown/extra keys are ignored, never fatal. Nothing is written to n8n.
#
# STDLIB ONLY. Calls NO model, NO network. Run:
#   python3 migrate-rescue-staticdata.py --export staticdata.json [--state-dir DIR] [--dry-run]
# Exit 0 = success (including a clean "nothing to import"), 2 = usage/parse error.
# =============================================================================
"""migrate-rescue-staticdata.py — import volatile n8n staticData into the ledger."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load_ledger_module():
    spec = importlib.util.spec_from_file_location(
        "rescue_ledger", str(_HERE / "rescue_ledger.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _first(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def _find_static_root(obj):
    """Return the {pending, counters, ...} object regardless of nesting depth in a
    full n8n export. Prefers an explicit staticData.global, else the object itself."""
    if not isinstance(obj, dict):
        return {}
    if "staticData" in obj and isinstance(obj["staticData"], dict):
        sd = obj["staticData"]
        if isinstance(sd.get("global"), dict):
            return sd["global"]
        return sd
    if isinstance(obj.get("global"), dict):
        return obj["global"]
    return obj


def _iter_pending(root):
    """Yield ticket dicts from any of the plausible queue keys."""
    for key in ("pending", "tickets", "queue", "pendingTickets", "open"):
        val = root.get(key) if isinstance(root, dict) else None
        if isinstance(val, list):
            for t in val:
                if isinstance(t, dict):
                    yield t
        elif isinstance(val, dict):
            # queue keyed by ticket id
            for tid, t in val.items():
                if isinstance(t, dict):
                    t.setdefault("ticketId", tid)
                    yield t


def _iter_counters(root):
    """Yield (client, day, count) triples from the counters map (either shape)."""
    counters = root.get("counters") if isinstance(root, dict) else None
    if not isinstance(counters, dict):
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for client, val in counters.items():
        if isinstance(val, dict):
            for day, n in val.items():
                try:
                    yield client, str(day), int(n)
                except (TypeError, ValueError):
                    continue
        else:
            try:
                yield client, today, int(val)
            except (TypeError, ValueError):
                continue


def migrate(export_path, state_dir=None, dry_run=False):
    rl = _load_ledger_module()
    try:
        raw = json.loads(Path(export_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"ERROR: cannot read/parse export {export_path}: {exc}\n")
        return 2

    root = _find_static_root(raw)
    tickets = list(_iter_pending(root))
    counters = list(_iter_counters(root))

    stats = {"tickets_seen": len(tickets), "tickets_imported": 0,
             "answers_applied": 0, "counters_seeded": 0}

    if dry_run:
        print(f"[migrate] DRY-RUN: {len(tickets)} ticket(s), {len(counters)} counter row(s) "
              f"would be imported into the ledger (nothing written).")
        for t in tickets[:10]:
            tid = _first(t, "ticketId", "ticket_id", "id", default="(no id)")
            print(f"    - {tid}: {_first(t, 'clientName', 'client', default='?')} / "
                  f"{str(_first(t, 'problem', default=''))[:50]}")
        return 0

    led = rl.Ledger(Path(state_dir) if state_dir else None)
    try:
        for t in tickets:
            tid = _first(t, "ticketId", "ticket_id", "id")
            if not tid:
                # deterministic id from content so re-runs dedupe
                import hashlib
                tid = "mig-" + hashlib.sha256(
                    json.dumps(t, sort_keys=True, default=str).encode()).hexdigest()[:16]
            created = led.open_ticket(
                str(tid),
                client=_first(t, "clientName", "client"),
                person=_first(t, "person"),
                agent_name=_first(t, "agentName", "agent"),
                box=_first(t, "boxName", "box"),
                box_type=_first(t, "boxType", "box_type"),
                oc_version=_first(t, "openclawVersion", "oc_version"),
                problem=_first(t, "problem", "message"),
                already_tried=_first(t, "alreadyTried", "already_tried"),
                return_to=_first(t, "returnTo", "return_to"),
                source="n8n-staticdata-migration",
                ts_open=_first(t, "ts_open", "opened", "createdAt"))
            if created:
                stats["tickets_imported"] += 1
            # re-apply answered/resolved state (idempotent)
            answer = _first(t, "answer")
            if answer:
                if led.record_answer(str(tid), answer, tier=_first(t, "tier"),
                                     fix_class=_first(t, "fixClass", "fix_class"),
                                     fix_mode=_first(t, "fixMode", "fix_mode")):
                    stats["answers_applied"] += 1
            status = str(_first(t, "status", default="")).lower()
            if status in ("resolved", "closed", "done"):
                led.mark_resolved(str(tid))

        # seed the durable per-client exchange counters from the volatile map, but
        # only up to the exported count MINUS what tickets already logged, so we do
        # not double count (open_ticket already logged one 'escalate' per ticket).
        for client, day, n in counters:
            have = led.count_exchanges_today(client, day=day)
            for _ in range(max(0, n - have)):
                led.record_exchange(client, "escalate", day=day)
                stats["counters_seeded"] += 1
    finally:
        led.close()

    print(f"[migrate] imported {stats['tickets_imported']}/{stats['tickets_seen']} new ticket(s), "
          f"applied {stats['answers_applied']} answer(s), seeded {stats['counters_seeded']} "
          f"counter exchange(s) into {led.db_path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import n8n rescue staticData into the SQLite ledger.")
    ap.add_argument("--export",
                    help="path to the n8n staticData JSON export (or full workflow export)")
    ap.add_argument("--state-dir", help="override the rescue state dir")
    ap.add_argument("--dry-run", action="store_true", help="parse + report, write nothing")
    ap.add_argument("--self-test", action="store_true", help="run the deterministic self-test")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.export:
        ap.error("--export is required (or use --self-test)")
    return migrate(args.export, args.state_dir, args.dry_run)


def self_test():
    import tempfile
    print("[migrate-rescue-staticdata] self-test: nested export, aliases, idempotency, counters")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sample = {
        "name": "Rescue Rangers Relay",
        "staticData": {"global": {
            "pending": [
                {"ticketId": "t-100", "clientName": "acme", "person": "Owner",
                 "agentName": "Aria", "boxName": "acme-mac", "boxType": "Mac Mini",
                 "openclawVersion": "2026.5.22", "problem": "gateway down",
                 "alreadyTried": "1) doctor", "returnTo": "123", "status": "open"},
                {"id": "t-101", "client": "beta", "problem": "MCP timeout",
                 "answer": "restart the MCP launchd job", "status": "resolved"},
            ],
            "counters": {"acme": {today: 4}, "beta": 2},
        }},
    }
    with tempfile.TemporaryDirectory() as td:
        exp = Path(td) / "export.json"
        exp.write_text(json.dumps(sample))
        sd = Path(td) / "rescue"
        assert migrate(str(exp), state_dir=sd) == 0
        rl = _load_ledger_module()
        led = rl.Ledger(sd)
        t100 = led.get_ticket("t-100")
        assert t100 and t100["client"] == "acme" and t100["box_type"] == "Mac Mini"
        t101 = led.get_ticket("t-101")
        assert t101 and t101["status"] == "resolved" and t101["answer"].startswith("restart")
        # acme counter: exported 4; open_ticket logged 1 -> seeded 3 more == 4 total
        assert led.count_exchanges_today("acme", day=today) == 4, \
            led.count_exchanges_today("acme", day=today)
        led.close()
        print("  import case: PASS (nested export + field aliases + counter reconcile)")
        # idempotent re-run imports 0 new
        assert migrate(str(exp), state_dir=sd) == 0
        led2 = rl.Ledger(sd)
        # still exactly the 4 acme exchanges (no double count on re-run)
        assert led2.count_exchanges_today("acme", day=today) == 4
        led2.close()
        print("  idempotency case: PASS (re-run imports nothing new, no double count)")
    print("[migrate-rescue-staticdata] self-test: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
