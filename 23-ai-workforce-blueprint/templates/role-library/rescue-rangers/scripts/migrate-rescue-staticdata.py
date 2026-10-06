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
# the export are re-applied (also idempotent: record_answer refuses an already
# answered ticket, and mark_resolved is skipped when ts_resolved is already set,
# so no second 'resolved' exchange is ever logged). Safe to run repeatedly.
#
# SHAPE HANDLING — strict where history is at stake (RR-023):
#   * a bare staticData object:           {"pending":[...], "counters":{...}}
#   * a node-nested export:               {...,"staticData":{"global":{...}}}
#   * common ticket field aliases         (ticketId|id, clientName|client, box|boxName ...)
#   * counters as {client: {YYYY-MM-DD: N}}  (dated — the supported shape)
#   * REFUSED, exit 2, writes nothing:
#       - a top-level JSON ARRAY (never the volatile queue; refusing it loudly
#         is the RR-023 fix for the silent zero-row success)
#       - an UNSUPPORTED NONEMPTY shape: any rooted doc whose pending/counters
#         come from keys this importer does not understand, or that carries a
#         non-empty unknown top-level structure (reason
#         unsupported_nonempty_schema_refused).
#       - counters as {client: N} with NO day attached (a bare int): the old code
#         billed the count to TODAY. RR-023: an undated counter is refused unless
#         the operator names --counter-day YYYY-MM-DD. Nothing bills today.
#       - dated counters spanning MORE THAN ONE distinct day: the operator must
#         pick ONE day (ambiguous history is not guessed; refuse).
#   * an EMPTY export (no tickets, no counters) is NOT a success story: it exits
#     3 with a documented retirement note (the legacy queue is retired; nothing
#     was imported because there was nothing to import) unless the operator
#     passes --allow-empty-retirement to acknowledge that explicitly.
#
# HISTORICAL FIDELITY: ticket ts_open and counter day/ts are taken from the
# export, never rewritten to "now". A migration must never bill today for
# history: counters seed exchanges with day=<export day>, ts=<export ts>.
#
# OWNERSHIP: the export's per-ticket client names are verified against the
# ledger's existing rows on a re-run (--verify-ownership CLIENT): any ticket in
# the export whose stored row belongs to a DIFFERENT client aborts the run as
# exit 3 (ownership_mismatch). Without the flag, ownership is recorded from the
# export on first import.
#
# STDLIB ONLY. Calls NO model, NO network. Run:
#   python3 migrate-rescue-staticdata.py --export staticdata.json [--state-dir DIR] [--dry-run]
#       [--counter-day YYYY-MM-DD] [--allow-empty-retirement] [--verify-ownership CLIENT]
# Exit 0 = success, 2 = usage/parse/schema error, 3 = empty-retirement or
# ownership-mismatch. Any nonzero exit writes NOTHING.
# =============================================================================
"""migrate-rescue-staticdata.py — import volatile n8n staticData into the ledger."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent

SUPPORTED_PENDING_KEYS = ("pending", "tickets", "queue", "pendingTickets", "open")
SUPPORTED_COUNTER_KEY = "counters"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _refuse(reason, detail="", write_stderr=True):
    """A loud refusal: named reason, non-zero exit, and — by construction —
    nothing written (every caller returns before any Ledger is opened)."""
    if write_stderr:
        sys.stderr.write(f"REFUSED [{reason}]: {detail}\n")
    return reason, detail


def _find_static_root(obj):
    """Return (root, provenance) for a rooted doc, or (None, reason-detail).

    A top-level ARRAY is refused outright (exit 2, unsupported_nonempty_schema
    shape): it is never the volatile queue and the old code folded it into a
    silent zero-row success.
    """
    if isinstance(obj, list):
        return None, _refuse(
            "unsupported_nonempty_schema_refused",
            f"top-level JSON array with {len(obj)} element(s) is not a staticData "
            "export; refusing instead of reporting a zero-row success")
    if not isinstance(obj, dict):
        return None, _refuse(
            "unsupported_schema", f"export root is {type(obj).__name__}, not an object")
    if "staticData" in obj and isinstance(obj["staticData"], dict):
        sd = obj["staticData"]
        if isinstance(sd.get("global"), dict):
            return sd["global"], None
        return sd, None
    if isinstance(obj.get("global"), dict):
        return obj["global"], None
    return obj, None


def _iter_pending(root):
    """Yield ticket dicts from the supported queue keys."""
    for key in SUPPORTED_PENDING_KEYS:
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


def _pending_source_keys(root):
    """Which supported queue keys actually carried rows (for the report)."""
    found = []
    if not isinstance(root, dict):
        return found
    for key in SUPPORTED_PENDING_KEYS:
        val = root.get(key)
        if isinstance(val, list) and any(isinstance(t, dict) for t in val):
            found.append(key)
        elif isinstance(val, dict) and any(isinstance(t, dict) for t in val.values()):
            found.append(key)
    return found


def _collect_counters(root, counter_day=None):
    """Return (triples, error) where triples are (client, day, count).

    Rules (RR-023):
      - dated {client: {day: n}} is the supported shape; multi-day exports are
        refused as ambiguous unless --counter-day names one day.
      - bare-int {client: n} has no day: refused unless --counter-day names it.
      - malformed day strings and non-integer counts are skipped (named in the
        report), never billed to today.
    """
    counters = root.get(SUPPORTED_COUNTER_KEY) if isinstance(root, dict) else None
    if counters is None:
        return [], None
    if not isinstance(counters, dict):
        return None, _refuse(
            "unsupported_counters_shape",
            f"'counters' is {type(counters).__name__}, expected an object")
    if counter_day is not None and not _DAY_RE.match(counter_day):
        return None, _refuse(
            "invalid_counter_day",
            f"--counter-day {counter_day!r} is not YYYY-MM-DD")
    triples = []
    skipped = []
    days_seen = set()
    needs_day = []  # bare-int clients with no --counter-day
    for client, val in counters.items():
        if isinstance(val, dict):
            for day, n in val.items():
                if not (isinstance(day, str) and _DAY_RE.match(day)):
                    skipped.append((client, day, "malformed_day"))
                    continue
                try:
                    triples.append((client, str(day), int(n)))
                    days_seen.add(str(day))
                except (TypeError, ValueError):
                    skipped.append((client, day, "non_integer_count"))
                    continue
        else:
            try:
                n = int(val)
            except (TypeError, ValueError):
                skipped.append((client, val, "non_integer_count"))
                continue
            if counter_day is None:
                needs_day.append(client)
            else:
                triples.append((client, counter_day, n))
                days_seen.add(counter_day)
    if needs_day:
        return None, _refuse(
            "undated_counter_refused",
            "counter(s) for client(s) %s carry no day; re-run with "
            "--counter-day YYYY-MM-DD so history never bills today" % sorted(needs_day))
    if len(days_seen) > 1 and counter_day is None:
        return None, _refuse(
            "ambiguous_counter_days",
            "counters span %d distinct days %s; re-run with --counter-day "
            "YYYY-MM-DD to name exactly one" % (len(days_seen), sorted(days_seen)))
    if counter_day is not None:
        # operator named one day: fold every dated row onto it is WRONG —
        # instead keep only that day's rows and refuse the rest loudly.
        other = sorted(d for d in days_seen if d != counter_day)
        if other:
            return None, _refuse(
                "ambiguous_counter_days",
                "export carries day(s) %s outside --counter-day %s; refusing "
                "rather than guessing" % (other, counter_day))
    return triples, skipped or None


def _unsupported_nonempty(root, tickets, counters):
    """Detect a rooted doc that carries a NONEMPTY shape we do not understand.

    Supported content = tickets from known queue keys + counters under
    'counters'. Anything else non-empty (a workflow nodes array, a connections
    map, unknown ticket-holding keys) makes this an unsupported nonempty
    schema: refuse, never a zero-row success. Returns a detail string or None.
    """
    if not isinstance(root, dict):
        return None
    known = set(SUPPORTED_PENDING_KEYS) | {SUPPORTED_COUNTER_KEY, "staticData", "global"}
    unknown_nonempty = []
    for k, v in root.items():
        if k in known:
            continue
        if v in (None, "", [], {}):
            continue
        unknown_nonempty.append(k)
    if unknown_nonempty and not tickets and not counters:
        return ("unsupported keys %s with no supported tickets/counters; refusing "
                "as unsupported_nonempty_schema_refused" % sorted(unknown_nonempty))
    if unknown_nonempty and ("nodes" in unknown_nonempty or "connections" in unknown_nonempty):
        return ("workflow-shaped keys %s are not staticData; refusing as "
                "unsupported_nonempty_schema_refused" % sorted(unknown_nonempty))
    return None


def _export_ts_for(day, ticket_ts=None):
    """Deterministic historical timestamp for a seeded exchange: noon UTC on
    the export day, unless the ticket already gave us a real instant."""
    if ticket_ts:
        return ticket_ts
    return f"{day}T12:00:00+00:00"


def migrate(export_path, state_dir=None, dry_run=False, counter_day=None,
            allow_empty_retirement=False, verify_ownership=None):
    try:
        raw = json.loads(Path(export_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"ERROR: cannot read/parse export {export_path}: {exc}\n")
        return 2

    root, root_err = _find_static_root(raw)
    if root_err is not None:
        # _find_static_root already wrote the REFUSED line; exit 2, wrote nothing.
        return 2
    tickets = list(_iter_pending(root))
    counters_res = _collect_counters(root, counter_day=counter_day)
    if counters_res[0] is None:
        return 2
    counters, counters_skipped = counters_res

    unsupported = _unsupported_nonempty(root, tickets, counters)
    if unsupported is not None:
        _refuse("unsupported_nonempty_schema_refused", unsupported)
        return 2

    if not tickets and not counters:
        note = ("empty export: no tickets and no counters. The legacy Relay "
                "queue is RETIRED; nothing was imported because there was "
                "nothing to import. Re-run with --allow-empty-retirement to "
                "acknowledge this explicitly.")
        if not allow_empty_retirement:
            _refuse("empty_retirement_unacknowledged", note)
            return 3
        print(f"[migrate] RETIREMENT-NOTE: {note}")
        return 0

    stats = {"tickets_seen": len(tickets), "tickets_imported": 0,
             "answers_applied": 0, "counters_seeded": 0,
             "resolved_folded": 0, "counters_skipped": counters_skipped or []}

    if dry_run:
        print(f"[migrate] DRY-RUN: {len(tickets)} ticket(s), {len(counters)} counter row(s) "
              f"would be imported into the ledger (nothing written).")
        for t in tickets[:10]:
            tid = _first(t, "ticketId", "ticket_id", "id", default="(no id)")
            print(f"    - {tid}: {_first(t, 'clientName', 'client', default='?')} / "
                  f"{str(_first(t, 'problem', default=''))[:50]}")
        return 0

    rl = _load_ledger_module()
    led = rl.Ledger(Path(state_dir) if state_dir else None)
    try:
        # ---- ownership verification (re-run safety) --------------------------
        # On first import the export IS the ownership record. On a re-run into
        # a ledger that already holds rows, --verify-ownership CLIENT aborts
        # when any exported ticket belongs to a different client on record.
        if verify_ownership is not None:
            mismatches = []
            for t in tickets:
                tid = _first(t, "ticketId", "ticket_id", "id")
                if not tid:
                    continue
                row = led.get_ticket(str(tid))
                if row is None:
                    continue
                on_record = row.get("client")
                exported = _first(t, "clientName", "client")
                if on_record and on_record != verify_ownership:
                    mismatches.append((str(tid), on_record))
                elif exported and exported != verify_ownership and on_record:
                    mismatches.append((str(tid), on_record))
            if mismatches:
                _refuse("ownership_mismatch",
                        "ticket(s) owned by another client on record: %s; expected "
                        "owner %r" % (mismatches, verify_ownership))
                return 3

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
                row = led.get_ticket(str(tid))
                if row is not None and row.get("ts_resolved"):
                    # already resolved on a prior run: FOLD, never log a second
                    # 'resolved' exchange (which would double-bill the audit).
                    stats["resolved_folded"] += 1
                else:
                    led.mark_resolved(str(tid))

        # seed the durable per-client exchange counters from the volatile map, but
        # only up to the exported count MINUS what tickets already logged, so we do
        # not double count (open_ticket already logged one 'escalate' per ticket).
        # RR-023: every seeded exchange carries the EXPORT day/ts — never today.
        for client, day, n in counters:
            have = led.count_exchanges_today(client, day=day)
            for _ in range(max(0, n - have)):
                led.record_exchange(client, "escalate", day=day,
                                    ts=_export_ts_for(day))
                stats["counters_seeded"] += 1
    finally:
        led.close()

    print(f"[migrate] imported {stats['tickets_imported']}/{stats['tickets_seen']} new ticket(s), "
          f"applied {stats['answers_applied']} answer(s), seeded {stats['counters_seeded']} "
          f"counter exchange(s) into {led.db_path}")
    if stats["resolved_folded"]:
        print(f"[migrate] folded {stats['resolved_folded']} already-resolved ticket(s) "
              f"(no duplicate resolved exchange)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import n8n rescue staticData into the SQLite ledger.")
    ap.add_argument("--export",
                    help="path to the n8n staticData JSON export (or full workflow export)")
    ap.add_argument("--state-dir", help="override the rescue state dir")
    ap.add_argument("--dry-run", action="store_true", help="parse + report, write nothing")
    ap.add_argument("--self-test", action="store_true", help="run the deterministic self-test")
    ap.add_argument("--counter-day",
                    help="YYYY-MM-DD to attribute undated {client: N} counters to; "
                         "required for undated counters so history never bills today")
    ap.add_argument("--allow-empty-retirement", action="store_true",
                    help="acknowledge an empty export as the retired-queue note (exit 0)")
    ap.add_argument("--verify-ownership", metavar="CLIENT",
                    help="abort (exit 3) when an exported ticket is owned by another "
                         "client on record")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.export:
        ap.error("--export is required (or use --self-test)")
    return migrate(args.export, args.state_dir, args.dry_run,
                   counter_day=args.counter_day,
                   allow_empty_retirement=args.allow_empty_retirement,
                   verify_ownership=args.verify_ownership)


def self_test():
    import os
    os.environ["RR_LEDGER_DRILL"] = "1"
    try:
        return _self_test_body()
    finally:
        os.environ.pop("RR_LEDGER_DRILL", None)


def _self_test_body():
    import tempfile
    print("[migrate-rescue-staticdata] self-test: nested export, aliases, idempotency, counters")
    day = "2026-06-01"
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
            "counters": {"acme": {day: 4}, "beta": {day: 2}},
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
        # acme counter: exported 4 on the EXPORT day; open_ticket logged 1 on
        # TODAY -> seeded 3 more on the export day; the export day holds exactly 4
        assert led.count_exchanges_today("acme", day=day) == 4, \
            led.count_exchanges_today("acme", day=day)
        before_today = led.count_exchanges_today("acme")
        led.close()
        print("  import case: PASS (nested export + field aliases + counter reconcile)")
        # idempotent re-run imports 0 new and logs NO second resolved exchange
        assert migrate(str(exp), state_dir=sd) == 0
        led2 = rl.Ledger(sd)
        assert led2.count_exchanges_today("acme", day=day) == 4
        t101b = led2.get_ticket("t-101")
        assert t101b and t101b["status"] == "resolved"
        resolved_rows = led2.conn.execute(
            "SELECT COUNT(*) AS n FROM exchanges WHERE ticket_id=? AND kind='resolved'",
            ("t-101",)).fetchone()["n"]
        assert resolved_rows == 1, resolved_rows
        led2.close()
        print("  idempotency case: PASS (re-run imports nothing new, no double count, "
              "exactly one resolved exchange)")
        # nothing billed to TODAY by the counters. Today legitimately holds the
        # ticket-lifecycle rows (2 open escalates + 1 answer + 1 resolved = 4);
        # the seeded history must ALL sit on the export day.
        led3 = rl.Ledger(sd)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hist_rows = led3.conn.execute(
            "SELECT COUNT(*) AS n FROM exchanges WHERE day=?", (day,)).fetchone()["n"]
        today_escalates = led3.conn.execute(
            "SELECT COUNT(*) AS n FROM exchanges WHERE day=? AND kind='escalate'",
            (today,)).fetchone()["n"]
        led3.close()
        assert hist_rows == 6, hist_rows
        assert today_escalates == 2, today_escalates
        print(f"  no-bill-today case: PASS (export day holds {hist_rows} seeded row(s), "
              f"today holds only {today_escalates} open_ticket escalate(s))")
        # unsupported nonempty (top-level array) refuses with exit 2
        arr = Path(td) / "array.json"
        arr.write_text(json.dumps([{"ticketId": "x-1"}]))
        assert migrate(str(arr), state_dir=Path(td) / "rescue-arr") == 2
        assert not (Path(td) / "rescue-arr").exists(), "refused run wrote a state dir"
        print("  unsupported-array case: PASS (exit 2, wrote nothing)")
    print("[migrate-rescue-staticdata] self-test: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
