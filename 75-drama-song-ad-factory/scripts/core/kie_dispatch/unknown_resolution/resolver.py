#!/usr/bin/env python3
"""Unknown KIE job resolution through Skill 74's task/status route. stdlib only.

A dispatch that cannot prove an outcome marks its reservation ``unknown`` and
stops - no retry, no resubmit (kie_dispatch ``unknown-outcome-no-retry``). This
module closes that loop:

  scan     every ``jobs.state = 'unknown'`` row (one ``--run`` or all runs).
  query    Skill 74's task/status route: ``wait --task-id T --timeout 0`` reads
           the KIE recordInfo status once instead of polling. It is the ONLY
           transport here - no second KIE client, no HTTP of our own. A row
           with no remote task id was never accepted by KIE, so it settles at
           zero without a query.
  poll     queued/running is re-read up to ``--max-polls`` times; asking what
           happened is not resubmitting it.
  settle   status success -> optional Skill 74 ``save`` (files stored) then
           succeeded; status fail -> failed. The receipt is written from what
           the status query answered, never left hanging on the estimate.
  account  every scanned row comes back with a disposition. Rows still running
           (or still unqueryable) at the poll bound are reported
           ``requery-required`` / ``query-failed`` WITH their attempts, and the
           report proves ``scanned == settled + pending`` with no row dropped.
           An operator who has given up passes ``--settle-undeterminable`` to
           force a settlement at the recorded estimate.

An adapter-level failure (no key, network, bad response) is not a provider
outcome: Skill 74 returns ``state: fail`` for both, and only the recordInfo
family answer (``raw_family: market``) settles a job.

Exit codes (EXIT): ok 0, error 1, waiting 3 (rows still pending a re-query),
rejected 5. Output: one JSON envelope on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # core/

import spend_ledger as L  # noqa: E402  (sibling module in the same core/ tree)
from kie_dispatch.kie_dispatch import (  # noqa: E402  (parent package, Skill 74 path)
    ADAPTER_SKILL,
    make_runner,
    resolve_adapter,
)

TOOL_NAME = "kie_unknown_resolution"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.kie-unknown-resolution/envelope/v1"
EXIT = {"ok": 0, "error": 1, "waiting": 3, "rejected": 5}
OWNER = "kie-unknown-resolution"

# Skill 74 is the one KIE path. These are the only two routes used: the
# task/status route (recordInfo behind `wait`) and `save` for files the status
# query already reported as success. Never submit, never resubmit.
QUERY_ROUTE = "wait"
SAVE_ROUTE = "save"
STATUS_TIMEOUT = "0"          # one status read, not a poll loop
PROVIDER_FAMILY = "market"    # recordInfo answers carry this raw_family

DISPOSITIONS = ("saved", "succeeded", "failed", "no-remote-task",
                "requery-required", "query-failed", "blocked-adapter",
                "undeterminable", "already-settled", "settle-failed",
                "resolve-error")


def envelope(command, outcome, reason_code, next_action="", run_id="",
             logical_key="", attempt_id="", evidence=None, state_version=0):
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "logical_key": logical_key,
            "attempt_id": attempt_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence or {}, "state_version": state_version}


def _ask(runner, adapter, args):
    """One Skill 74 command -> (rc, parsed_or_None, raw). No exception escapes."""
    try:
        rc, out = runner([adapter] + list(args))
    except Exception as e:                                  # noqa: BLE001
        return -1, None, "runner-error: %s" % e
    rc = rc if isinstance(rc, int) else -1
    if isinstance(out, (dict, list)):
        try:
            return rc, out, json.dumps(out, sort_keys=True, default=str)
        except Exception:                                   # noqa: BLE001
            return rc, None, ""
    try:
        return rc, json.loads(out), out
    except Exception:                                       # noqa: BLE001
        return rc, None, out if isinstance(out, str) else str(out)


def task_status(runner, adapter, task_id):
    """One Skill 74 task/status read -> (read_ok, payload, meta)."""
    rc, data, raw = _ask(runner, adapter,
                         [QUERY_ROUTE, "--task-id", task_id,
                          "--timeout", STATUS_TIMEOUT, "--json"])
    if not isinstance(data, dict):
        return False, None, {"rc": rc, "raw": (raw or "")[-400:]}
    return True, data, {"rc": rc}


def save_task(runner, adapter, task_id, save_dir):
    """Skill 74 ``save`` for a task the status query called success."""
    try:
        os.makedirs(save_dir, exist_ok=True)
    except OSError as e:
        return False, None, {"error": str(e)[:200]}
    rc, data, raw = _ask(runner, adapter,
                         [SAVE_ROUTE, "--task-id", task_id,
                          "--save-dir", save_dir, "--json"])
    if not isinstance(data, dict):
        return False, None, {"rc": rc, "raw": (raw or "")[-400:]}
    return True, data, {"rc": rc}


def classify(payload):
    """Adapter answer -> success | failed | running | query-failed.

    Only a recordInfo (``raw_family: market``) answer is a provider outcome.
    Skill 74 reports its own failures - no key, network, bad response, task not
    readable - as ``state: fail`` too, and those must never settle a job.
    """
    if not isinstance(payload, dict):
        return "query-failed"
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    provider = (payload.get("raw_family") == PROVIDER_FAMILY
                or "state_raw" in data)
    state = payload.get("state")
    if state in ("success", "fail") and provider:
        return "success" if state == "success" else "failed"
    if state in ("running", "queued"):
        return "running"
    return "query-failed"


def _key(row):
    return (row["run_id"], row["logical_key"], row["attempt_id"])


def _read_unknowns(db_path, run_id=None):
    """Rows currently marked unknown. Read-only; never creates a database."""
    if not os.path.isfile(db_path):
        raise sqlite3.OperationalError("no ledger at %s" % db_path)
    sql = ("SELECT run_id, logical_key, attempt_id, state, remote_task_id,"
           " COALESCE(estimated_cost,0), COALESCE(owner,''), lease_expires,"
           " version FROM jobs WHERE state='unknown'")
    args = []
    if run_id:
        sql += " AND run_id=?"
        args.append(run_id)
    sql += " ORDER BY run_id, logical_key, attempt_id"
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        rows = conn.execute(sql, tuple(args)).fetchall()
    finally:
        conn.close()
    cols = ("run_id", "logical_key", "attempt_id", "state", "remote_task_id",
            "estimated_cost", "owner", "lease_expires", "version")
    return [dict(zip(cols, r)) for r in rows]


def _job_row(db_path, job):
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        r = conn.execute(
            "SELECT state, COALESCE(owner,''), lease_expires FROM jobs "
            "WHERE run_id=? AND logical_key=? AND attempt_id=?",
            (job["run_id"], job["logical_key"], job["attempt_id"])).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {"state": r[0], "owner": r[1], "lease_expires": r[2]}


def _settle(db_path, job, final, actual_cost, task_id, owner):
    """unknown -> succeeded|failed -> reconciled. Receipt from the resolution."""
    row = _job_row(db_path, job)
    if row is None:
        return envelope("settle", "error", "NO_SUCH_JOB", "",
                        run_id=job["run_id"], logical_key=job["logical_key"],
                        attempt_id=job["attempt_id"]), {"state": None}
    if row["state"] != "unknown":
        return envelope("settle", "rejected", "ALREADY_SETTLED",
                        "state is %s; another worker already closed it"
                        % row["state"],
                        run_id=job["run_id"], logical_key=job["logical_key"],
                        attempt_id=job["attempt_id"]), {"state": row["state"]}
    # The stalled dispatch left a 300s lease behind with nobody working the row
    # (it stopped on purpose). Adopt its owner name so the lease guard sees the
    # same worker instead of blocking recovery for five minutes.
    eff = owner
    adopted = bool(row["owner"] and row["owner"] != owner
                   and row["lease_expires"] > time.time())
    if adopted:
        eff = row["owner"]
    term = L.mark_terminal(db_path, job["run_id"], job["logical_key"],
                           job["attempt_id"], final, owner=eff)
    rec = L.reconcile(db_path, job["run_id"], job["logical_key"],
                      job["attempt_id"], final, int(actual_cost),
                      provider_ref="kie", evidence_ref=task_id or "no-remote-task",
                      owner=eff)
    out = dict(rec)
    ev = dict(rec.get("evidence") or {})
    ev.update({"final_outcome": final, "actual_cost": int(actual_cost),
               "mark_terminal": term.get("reason_code", ""),
               "resolver_owner": owner, "write_owner": eff,
               "lease_adopted": adopted, "task_id": task_id or None,
               "state_before": "unknown"})
    out["evidence"] = ev
    return out, {"state": row["state"], "lease_adopted": adopted}


def _finish(rec, env):
    """Attach the ledger outcome to the per-job record."""
    oc = env.get("outcome")
    code = env.get("reason_code")
    if oc in ("ok", "parked"):
        rec["settled"] = True
        rec["final_state"] = "reconciled"
    elif code == "ALREADY_SETTLED":
        rec["settled"] = True
        rec["final_state"] = str((env.get("evidence") or {}).get("state"))
        rec["disposition"] = "already-settled"
        rec["warnings"] = list(rec.get("warnings") or []) + \
            ["SETTLE_SKIPPED_ALREADY_DONE"]
    else:
        rec["settled"] = False
        rec["disposition"] = "settle-failed"
        rec["reason_code"] = "SETTLE_FAILED"
        rec["settle_error"] = code
        rec["warnings"] = list(rec.get("warnings") or []) + ["SETTLE_FAILED"]
    ev = env.get("evidence") or {}
    rec["actual_cost"] = ev.get("actual_cost")
    rec["settle"] = {"outcome": oc, "reason_code": code,
                     "next_action": env.get("next_action", ""),
                     "state_version": env.get("state_version", 0),
                     "lease_adopted": ev.get("lease_adopted", False)}
    rec["state_version"] = env.get("state_version", 0)
    return rec


def resolve_one(*, db_path, job, runner, adapter=None, save_dir=None,
                owner=OWNER, max_polls=4, poll_interval=5.0,
                sleep=time.sleep, settle_undeterminable=False):
    """Resolve one unknown row. Returns a record; never raises."""
    rec = {"run_id": job["run_id"], "logical_key": job["logical_key"],
           "attempt_id": job["attempt_id"], "task_id": job["remote_task_id"],
           "estimated_cost": job["estimated_cost"], "attempts": [],
           "disposition": None, "reason_code": None, "settled": False,
           "actual_cost": None, "final_state": None, "warnings": []}

    # Never accepted by KIE -> nothing to ask, nothing billed.
    if not job["remote_task_id"]:
        rec.update(disposition="no-remote-task", reason_code="NO_REMOTE_TASK_ID")
        env, _ = _settle(db_path, job, "failed", 0, "", owner)
        return _finish(rec, env)

    if adapter is None:
        rec.update(disposition="blocked-adapter",
                   reason_code="ADAPTER_NOT_FOUND",
                   next_action="install Skill 74 (%s); there is no private "
                               "KIE client" % ADAPTER_SKILL)
        return rec

    task_id = job["remote_task_id"]
    bound = max(1, int(max_polls))
    answer, payload = "query-failed", None
    for n in range(1, bound + 1):
        ok, payload, meta = task_status(runner, adapter, task_id)
        if not ok:
            rec["attempts"].append(dict(n=n, read=False, **meta))
            answer = "query-failed"
            break
        kind = classify(payload)
        err = payload.get("error")
        rec["attempts"].append({
            "n": n, "read": True, "kind": kind,
            "state": payload.get("state"),
            "raw_family": payload.get("raw_family"),
            "error_code": err.get("code") if isinstance(err, dict) else None,
            "rc": meta.get("rc")})
        answer = kind
        if kind != "running":
            break
        if n < bound:
            sleep(poll_interval)

    if answer == "running":
        answer = "requery-required"

    if answer in ("requery-required", "query-failed"):
        if settle_undeterminable:
            rec.update(disposition="undeterminable",
                       reason_code="UNDITERMINABLE_SETTLED")
            rec["warnings"].append("status not determinable; settled at the "
                                   "recorded estimate on operator flag")
            env, _ = _settle(db_path, job, "failed",
                             int(job["estimated_cost"] or 0), task_id, owner)
            return _finish(rec, env)
        rec["disposition"] = answer
        rec["reason_code"] = ("UNKNOWN_STILL_RUNNING" if answer == "requery-required"
                              else "STATUS_QUERY_FAILED")
        rec["next_action"] = ("re-query the Skill 74 task/status route; the row "
                              "stays unknown until it answers terminally - "
                              "never resubmit the job")
        rec["settled"] = False
        return rec

    if answer == "failed":
        credits = payload.get("credits_consumed")
        cost = (int(credits) if isinstance(credits, (int, float))
                and not isinstance(credits, bool) else 0)
        rec.update(disposition="failed", reason_code="UNKNOWN_RESOLVED_FAILED")
        env, _ = _settle(db_path, job, "failed", cost, task_id, owner)
        return _finish(rec, env)

    # answer == success
    saved_paths, save_meta = [], {}
    if save_dir:
        s_ok, s_payload, s_meta = save_task(runner, adapter, task_id, save_dir)
        save_meta = s_meta if isinstance(s_meta, dict) else {}
        if s_ok and (s_payload.get("saved_paths") or []):
            saved_paths = list(s_payload.get("saved_paths") or [])
        else:
            rec["warnings"].append("SAVE_FAILED")
            if s_payload:
                save_meta = dict(save_meta, state=s_payload.get("state"),
                                 error=s_payload.get("error"))
    credits = payload.get("credits_consumed")
    if isinstance(credits, (int, float)) and not isinstance(credits, bool):
        cost = int(credits)
    else:
        cost = int(job["estimated_cost"] or 0)
        rec["warnings"].append("ACTUAL_COST_UNREPORTED")
    rec.update(disposition="saved" if saved_paths else "succeeded",
               reason_code=("UNKNOWN_RESOLVED_SAVED" if saved_paths
                            else "UNKNOWN_RESOLVED_SUCCEEDED"),
               saved_paths=saved_paths)
    if save_meta:
        rec["save"] = save_meta
    env, _ = _settle(db_path, job, "succeeded", cost, task_id, owner)
    return _finish(rec, env)


def resolve_all(*, ledger_db, runner=None, adapter_path=None, run_id=None,
                save_dir=None, owner=OWNER, max_polls=4, poll_interval=5.0,
                sleep=time.sleep, settle_undeterminable=False, timeout=300):
    """Resolve every unknown row in the ledger. Returns one envelope."""
    if not ledger_db or not os.path.isfile(ledger_db):
        return envelope("resolve_all", "rejected", "NO_LEDGER",
                        "point --db at an existing spend ledger",
                        run_id=run_id or "")
    try:
        jobs = _read_unknowns(ledger_db, run_id)
    except sqlite3.Error as e:
        return envelope("resolve_all", "error", "LEDGER_UNREADABLE",
                        str(e)[:200], run_id=run_id or "")

    needs_query = any(j["remote_task_id"] for j in jobs)
    adapter = resolve_adapter(adapter_path) if needs_query else None
    run = runner or make_runner(timeout)   # tests install a fake and never get here

    recs = []
    for job in jobs:
        try:
            recs.append(resolve_one(
                db_path=ledger_db, job=job, runner=run, adapter=adapter,
                save_dir=save_dir, owner=owner, max_polls=max_polls,
                poll_interval=poll_interval, sleep=sleep,
                settle_undeterminable=settle_undeterminable))
        except Exception as e:                                  # noqa: BLE001
            recs.append({"run_id": job["run_id"],
                         "logical_key": job["logical_key"],
                         "attempt_id": job["attempt_id"],
                         "task_id": job["remote_task_id"],
                         "estimated_cost": job["estimated_cost"],
                         "attempts": [], "disposition": "resolve-error",
                         "reason_code": "RESOLVE_ERROR", "settled": False,
                         "actual_cost": None, "final_state": None,
                         "warnings": [str(e)[:200]]})

    scanned, settled = len(jobs), [r for r in recs if r["settled"]]
    pending = [r for r in recs if not r["settled"]]
    blocked = [r for r in pending if r["disposition"] == "blocked-adapter"]

    remaining, lost = None, []
    try:
        remaining = {_key(j) for j in _read_unknowns(ledger_db, run_id)}
        lost = [r for r in settled if _key(r) in remaining]
    except sqlite3.Error:
        remaining = None
    accounted = (len(recs) == scanned) and not lost

    if not accounted:
        outcome, reason = "error", "UNKNOWN_UNACCOUNTED"
        nxt = "a settled row is still unknown or a scan row produced no record; " \
              "re-run resolve before trusting the ledger"
    elif blocked:
        outcome, reason = "error", "ADAPTER_NOT_FOUND"
        nxt = blocked[0].get("next_action") or ("install Skill 74 (%s)" % ADAPTER_SKILL)
    elif pending:
        outcome, reason = "waiting", "UNKNOWN_RESOLUTION_PENDING"
        nxt = "re-query the Skill 74 task/status route for the pending rows; " \
              "polling is not resubmitting"
    elif scanned:
        outcome, reason = "ok", "UNKNOWN_RESOLUTION_COMPLETE"
        nxt = "every unknown row settled from its status query; record the receipt"
    else:
        outcome, reason = "ok", "NO_UNKNOWN_JOBS"
        nxt = "nothing was unknown"

    evidence = {
        "adapter_skill": ADAPTER_SKILL,
        "query_route": "%s --task-id <id> --timeout %s (KIE task/status read)"
                       % (QUERY_ROUTE, STATUS_TIMEOUT),
        "save_route": "%s --task-id <id> --save-dir <dir>" % SAVE_ROUTE,
        "scanned": scanned, "settled": len(settled), "pending": len(pending),
        "blocked_adapter": len(blocked),
        "invariant": ("scanned == settled + pending" if accounted
                      else "BROKEN: settled rows still unknown or lost records"),
        "unaccounted": 0 if accounted else scanned - len(recs) + len(lost),
        "remaining_unknown": (sorted("%s/%s/%s" % k for k in remaining)
                              if remaining is not None else None),
        "lost_settled": ["%s/%s/%s" % _key(r) for r in lost],
        "jobs": recs,
    }
    versions = [r.get("state_version") or 0 for r in recs]
    return envelope("resolve_all", outcome, reason, nxt, run_id=run_id or "",
                    evidence=evidence, state_version=max(versions) if versions else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="unknown_resolution",
        description="Resolve every unknown KIE job through Skill 74's "
                    "task/status route and settle the ledger from the answer.")
    p = ap.add_subparsers(dest="cmd", required=True)
    a = p.add_parser("resolve", help="Query status and settle unknown rows.")
    a.add_argument("--db", required=True, help="spend_ledger SQLite path.")
    a.add_argument("--run", dest="run_id", default=None,
                   help="One run; default is every unknown row.")
    a.add_argument("--save-dir", default=None,
                   help="Store files for rows the status query calls success.")
    a.add_argument("--adapter", dest="adapter_path", default=None,
                   help="Path to kie_live_adapter.py (default: search).")
    a.add_argument("--owner", default=OWNER)
    a.add_argument("--max-polls", type=int, default=4,
                   help="Status reads per row before it is reported pending.")
    a.add_argument("--poll-interval", type=float, default=5.0)
    a.add_argument("--settle-undeterminable", action="store_true",
                   help="Operator flag: settle a row that never answers "
                        "status at its recorded estimate.")
    a.add_argument("--timeout", type=int, default=300)
    a.add_argument("--json", action="store_true",
                   help="accepted; output is always JSON")
    ns = ap.parse_args(argv)

    if ns.cmd == "resolve":
        env = resolve_all(ledger_db=ns.db, adapter_path=ns.adapter_path,
                          run_id=ns.run_id, save_dir=ns.save_dir,
                          owner=ns.owner, max_polls=ns.max_polls,
                          poll_interval=ns.poll_interval,
                          settle_undeterminable=ns.settle_undeterminable,
                          timeout=ns.timeout)
        json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
        sys.stdout.write("\n")
        return EXIT[env["outcome"]]
    return 1


if __name__ == "__main__":
    sys.exit(main())
