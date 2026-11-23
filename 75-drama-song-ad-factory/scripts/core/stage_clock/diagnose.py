"""diagnose.py - N-108: the overrun diagnosis runs beside the run (10D).

One agent starts at 60 minutes, 2 hours 30 minutes and 3 hours. It reads the
stage clock, ledger, job times, remake reasons, check results and fresh memory
readings; names the cause exactly; applies the fix right away; tells the
owner; and writes the cause to the ledger and the lessons file. It never
lowers a quality rule, never marks a MAJOR as passed, and never stops the run.

The decision function is pure; ``record`` writes the two records.
"""
import json
import os
import time

SCHEMA = "blackceo.overrun-diagnosis/v1"


def _cause(code, detail, fix, actions):
    return {"code": code, "detail": detail, "fix": fix, "actions": actions}


def diagnose(evidence):
    """Name the cause(s) and the fix. ``evidence`` keys are optional."""
    evidence = evidence or {}
    causes = []
    jobs = evidence.get("jobs") or []
    stuck = [j for j in jobs
             if j.get("state") not in ("done", "failed")
             and isinstance(j.get("age_s"), (int, float))
             and isinstance(j.get("limit_s"), (int, float))
             and j["age_s"] > 2 * j["limit_s"]]
    if stuck:
        causes.append(_cause(
            "STUCK_JOBS",
            "%d job(s) past twice their 9-in-10 time: %s"
            % (len(stuck), ", ".join(str(j.get("id", "?")) for j in stuck[:6])),
            "re-send each once under a new key; the first to land wins",
            [{"action": "resend", "job": j.get("id")} for j in stuck]))

    counted = {}
    for row in evidence.get("check_results") or []:
        if row.get("ok") is False:
            counted[row.get("line")] = counted.get(row.get("line"), 0) + 1
    repeat = sorted(line for line, count in counted.items() if line and count >= 3)
    if repeat:
        causes.append(_cause(
            "TEMPLATE_FAILING",
            "the same check line fails on every item: %s" % ", ".join(repeat),
            "correct the broken prompt template through the Prompt Builder and resend",
            [{"action": "fix_template", "line": line} for line in repeat]))

    backlog = evidence.get("checker_backlog") or 0
    checkers = max(1, int(evidence.get("checkers") or 1))
    if backlog > checkers * 3:
        causes.append(_cause(
            "CHECKERS_QUEUED",
            "%d items wait on %d checker(s)" % (backlog, checkers),
            "raise the fan-out to one checker per 2 items",
            [{"action": "raise_fanout", "to": max(checkers * 2, 1)}]))

    expired = [u for u in (evidence.get("uploads") or [])
               if (u.get("age_hours") or 0) > 23]
    if expired:
        causes.append(_cause(
            "EXPIRED_LINK",
            "%d uploaded link(s) older than 23 hours" % len(expired),
            "re-upload the expired links before the next burst",
            [{"action": "reupload", "name": u.get("name")} for u in expired]))

    pressure = evidence.get("memory_pressure") or 0
    if pressure > 0.85:
        causes.append(_cause(
            "MEMORY_PRESSURE",
            "fresh memory pressure is %.0f%%" % (pressure * 100),
            "hold new local workers; a running worker is never killed",
            [{"action": "hold_workers"}]))

    if evidence.get("provider_errors"):
        causes.append(_cause(
            "PROVIDER_ERRORS",
            "%d provider error(s)" % int(evidence["provider_errors"]),
            "resubmit the failed jobs (failures cost 0)",
            [{"action": "resubmit_failed"}]))

    if not causes:
        causes.append(_cause(
            "NO_EXACT_CAUSE_YET",
            "no rule matched this tick's evidence",
            "collect one more tick of evidence and read again",
            [{"action": "collect_evidence"}]))
    actions = [a for c in causes for a in c["actions"]]
    return {"schema": SCHEMA, "causes": causes, "actions": actions,
            "never_stops_run": True, "quality_rules_lowered": [],
            "owner_message": _message(causes, evidence),
            "at_unix": time.time()}


def _message(causes, evidence):
    lead = causes[0]
    elapsed = evidence.get("elapsed_min")
    when = (" at %.0f minutes" % elapsed) if isinstance(elapsed, (int, float)) else ""
    return ("Overrun diagnosis%s: %s. Fix applied: %s. The run keeps working; "
            "no quality rule is lowered." % (when, lead["detail"], lead["fix"]))


def record(run_dir, result, now=None):
    """Write the diagnosis and append the cause to the ledger and lessons."""
    os.makedirs(os.path.join(run_dir, "control"), exist_ok=True)
    doc = dict(result, recorded_at=float(now if now is not None else time.time()))
    path = os.path.join(run_dir, "control", "overrun-diagnosis.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    line = {"event": "overrun-diagnosis", "at_unix": doc["recorded_at"],
            "cause": doc["causes"][0]["code"],
            "detail": doc["causes"][0]["detail"],
            "fix": doc["causes"][0]["fix"]}
    for name in ("ledger.jsonl", "lessons.jsonl"):
        with open(os.path.join(run_dir, "control", name), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=True) + "\n")
    return doc
