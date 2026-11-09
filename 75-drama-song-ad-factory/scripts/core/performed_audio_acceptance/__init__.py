#!/usr/bin/env python3
"""E01 performed-audio acceptance: fail-closed reader (dossier ITEM 58).

Script metadata, captions and container duration are not listening. A
complete review needs, per spend-ledger audio job, the saved audio bound by
sha256 plus every performance measure (hooks, voices, timing,
intelligibility, ending) taken by a listening/analysis evaluator against the
CURRENT sheet and method. Anything else is refused with a named code.

Refusal codes: AUDIO_MISSING, AUDIO_HASH_MISMATCH, MEASURE_UNAVAILABLE,
MEASURE_FAILED, LABEL_AS_LISTENING, STALE_BINDING, STALE_MEASUREMENT,
JOB_OMITTED, JOB_NOT_IN_LEDGER, NO_AUDIO_JOBS, RISK_HIDES_FAIL.

Ledger rule: a job is in-ledger when state == 'succeeded', or state ==
'reconciled' with final_outcome == 'succeeded' (mirrors spend_ledger).
Caller contract: feed real spend_ledger rows through ledger_jobs_from_rows()
/ ledger_jobs_from_db(); job_id = logical_key + '/' + attempt_id and
output_sha256 = results.sha256 (None when unrecorded, which refuses).

This module only judges a record; it never calls a provider, never measures
audio itself, and a live PASS still needs a real evaluator run under Trevor's
paid-audio authorization (P09 executes, P10 accepts). stdlib only.
"""
from __future__ import annotations

import hashlib
import os

REQUIRED = ("hooks", "voices", "timing", "intelligibility", "ending")
# Only these sources count as hearing/analysing the audio itself.
LISTENED = ("listened", "analysis")
MAX_AGE_S = 7 * 24 * 3600  # ponytail: fixed window, make it a method field if runs need more


class AcceptanceRefused(Exception):
    def __init__(self, reasons):
        self.reasons = reasons
        super().__init__(",".join(r["code"] for r in reasons))


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _succeeded(j):
    return j.get("state") == "succeeded" or (
        j.get("state") == "reconciled" and j.get("final_outcome") == "succeeded")


def ledger_jobs_from_rows(job_rows, result_rows, stage="audio"):
    """Map real spend_ledger rows to [{job_id, state, final_outcome, output_sha256}].

    job_rows: dicts with logical_key, attempt_id, stage, state, final_outcome
    (spend_ledger.jobs). result_rows: dicts with logical_key, attempt_id,
    sha256 (spend_ledger.results). Only rows whose stage == `stage` are kept.
    """
    sha = {(r["logical_key"], r["attempt_id"]): r.get("sha256") for r in result_rows}
    return [{"job_id": "%s/%s" % (j["logical_key"], j["attempt_id"]),
             "state": j["state"], "final_outcome": j.get("final_outcome"),
             "output_sha256": sha.get((j["logical_key"], j["attempt_id"]))}
            for j in job_rows if j.get("stage") == stage]


def ledger_jobs_from_db(db_path, run_id, stage="audio"):
    """Read-only sqlite adapter over a real spend_ledger DB for one run."""
    import sqlite3
    c = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    c.row_factory = sqlite3.Row
    try:
        jobs = [dict(r) for r in c.execute("SELECT * FROM jobs WHERE run_id=?", (run_id,))]
        res = [dict(r) for r in c.execute("SELECT * FROM results WHERE run_id=?", (run_id,))]
    finally:
        c.close()
    return ledger_jobs_from_rows(jobs, res, stage)


def refusals(record, ledger_jobs, method_sha256, sheet_sha256, now):
    """Return a list of {code, job_id, detail}; empty means complete review."""
    out = []

    def add(code, job, detail=""):
        out.append({"code": code, "job_id": job, "detail": detail})

    if record.get("method_sha256") != method_sha256 or record.get("sheet_sha256") != sheet_sha256:
        add("STALE_BINDING", None, "receipt not bound to current method/sheet")
    t = record.get("measured_at")
    if not isinstance(t, (int, float)) or now - t > MAX_AGE_S or t > now:
        add("STALE_MEASUREMENT", None, "measured_at missing, future or older than window")

    led = {j["job_id"]: j for j in ledger_jobs if _succeeded(j)}
    jobs = {j.get("job_id"): j for j in record.get("jobs", [])}
    if not led or not jobs:  # empty/empty must never be a vacuous PASS
        add("NO_AUDIO_JOBS", None, "no succeeded ledger audio jobs or no jobs in record")
    for jid in led:
        if jid not in jobs:
            add("JOB_OMITTED", jid, "succeeded ledger job absent from acceptance record")
    for jid in jobs:
        if jid not in led:
            add("JOB_NOT_IN_LEDGER", jid, "acceptance job has no succeeded ledger entry")

    for jid, j in jobs.items():
        p, want = j.get("audio_path"), j.get("audio_sha256")
        if not p or not want or not os.path.isfile(p):
            add("AUDIO_MISSING", jid, "saved audio path/hash absent or file not on disk")
        elif _sha(p) != want or (jid in led and led[jid].get("output_sha256") != want):
            add("AUDIO_HASH_MISMATCH", jid, "file, record and ledger hashes disagree")
        m = j.get("measures") or {}
        for k in REQUIRED:
            e = m.get(k) or {}
            st = e.get("status")
            if st == "failed":
                add("MEASURE_FAILED", jid, k)
            elif st != "measured":
                add("MEASURE_UNAVAILABLE", jid, k)  # missing/unavailable/duration-only
            elif e.get("source") not in LISTENED or not e.get("evaluator"):
                add("LABEL_AS_LISTENING", jid, "%s source=%r" % (k, e.get("source")))
    return out


def accept(record, ledger_jobs, method_sha256, sheet_sha256, now):
    """Raise AcceptanceRefused unless the review is complete; else 'PASS'.

    A client accepted-risk record must keep the underlying FAIL (never PASS).
    """
    r = refusals(record, ledger_jobs, method_sha256, sheet_sha256, now)
    claim = record.get("claimed_verdict")
    if claim == "ACCEPTED_RISK":
        if record.get("underlying_verdict") != "FAIL" or not record.get("client_choice"):
            r.append({"code": "RISK_HIDES_FAIL", "job_id": None, "detail": "accepted-risk must retain FAIL + client choice"})
        if r and any(x["code"] == "RISK_HIDES_FAIL" for x in r):
            raise AcceptanceRefused(r)
        return "ACCEPTED_RISK"  # retained FAIL; never converted to PASS
    if r:
        raise AcceptanceRefused(r)
    return "PASS"
