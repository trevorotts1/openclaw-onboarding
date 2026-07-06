#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE :: INTAKE LEDGER (atomic claim + dedup + quarantine)
# webhook-design.md Section 3.2 / 3.3 / 4.2.5
# -----------------------------------------------------------------------------
# A persistent, per-client, one-file-per-job ledger on the CLIENT'S BOX. This is
# durable pipeline state, not scratch, so it never lives in /tmp:
#
#   ~/.openclaw/state/podcast-engine/intake-ledger/<job_key>.json          (record, 0600)
#   ~/.openclaw/state/podcast-engine/intake-ledger/<job_key>.payload.json  (canonical, 0600)
#   ~/.openclaw/state/podcast-engine/quarantine/<stamp>-<rand>.json        (tenant mismatch)
#
# The atomic claim is an EXCLUSIVE CREATE (O_CREAT|O_EXCL): the filesystem is the
# lock, which also settles the race between two concurrent deliveries of one
# submission (exactly one claims; the other reads the existing file and answers as
# a duplicate). The record state enum IS the client dashboard's status vocabulary
# plus the queue states, so the dashboard reads this ledger with no separate data
# entry step. This file ledger is the webhook layer's atomic claim mechanism; the
# SQLite database (podcast_state.py, a separate slice) is the single queryable
# source for the dashboard and kanban. podcast_state.py keeps the two in lockstep.
#
# EXIT: 0 OK / 2 corruption (fail closed, operator alert) / 3 usage.
# USAGE:
#   python3 ledger.py claim   --job JOBKEY --canonical FILE [--state received] [--base DIR]
#   python3 ledger.py read    --job JOBKEY [--base DIR] [--json]
#   python3 ledger.py sweep   --base DIR [--days 90]
#   python3 ledger.py quarantine --raw FILE --reason TEXT [--base DIR]
#   python3 ledger.py --self-test
# =============================================================================
"""Intake ledger with atomic exclusive-create claim, dedup, and quarantine."""

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

EXIT_OK = 0
EXIT_CORRUPTION = 2
EXIT_USAGE = 3

STATES = ("received", "needs_input", "researching", "writing", "qc", "art", "audio",
          "publishing", "enrolling", "complete", "queued_credit_out", "aged_out",
          "failed", "test")
TERMINAL = ("complete", "failed", "aged_out")

# Only safe metadata is copied into the record file; answer text (potential PII)
# lives only in the sibling .payload.json, so a dashboard read never sees answers.
RECORD_META_FIELDS = ("contact_id", "location_id", "podcast_id", "mode", "style", "episode_type")

_STATE_ENV = "PODCAST_ENGINE_STATE_DIR"
_DEFAULT_RETENTION_DAYS = 90


class LedgerCorruption(Exception):
    """Raised when a ledger record cannot be parsed. Fail closed, alert operator."""


def _iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def base_dir(base=None):
    if base:
        root = Path(base)
    elif os.environ.get(_STATE_ENV):
        root = Path(os.environ[_STATE_ENV])
    else:
        root = Path.home() / ".openclaw" / "state" / "podcast-engine"
    return root


def ledger_dir(base=None):
    return base_dir(base) / "intake-ledger"


def quarantine_dir(base=None):
    return base_dir(base) / "quarantine"


def _ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def record_path(job_key, base=None):
    return ledger_dir(base) / ("%s.json" % job_key)


def payload_path(job_key, base=None):
    return ledger_dir(base) / ("%s.payload.json" % job_key)


def _write_private(path, text):
    """Write a 0600 file via a temp sibling + atomic replace (idempotent)."""
    tmp = path.with_suffix(path.suffix + ".tmp-%s" % secrets.token_hex(4))
    fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        try:
            os.unlink(str(tmp))
        finally:
            raise
    os.replace(str(tmp), str(path))


def read_record(job_key, base=None):
    path = record_path(job_key, base)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerCorruption("ledger record %s unreadable: %s" % (path.name, exc))


def _new_record(job_key, canonical, state):
    rec = {
        "job_key": job_key,
        "state": state,
        "received_at": _iso_now(),
        "updated_at": _iso_now(),
        "attempts": {"delivery_count": 1, "qc_failures": 0},
        "canonical_payload_path": str(payload_path(job_key, None).name),
        "flow_id": None,
        "podbean_permalink": None,
        "notes": [],
    }
    for field in RECORD_META_FIELDS:
        if canonical.get(field) is not None:
            rec[field] = canonical.get(field)
    return rec


def _persist_record(job_key, rec, base=None):
    _write_private(record_path(job_key, base), json.dumps(rec, indent=2, sort_keys=True))


def claim(job_key, canonical, state="received", base=None):
    """Atomic exclusive-create claim. Returns (claimed, record). Writes the
    canonical payload sibling first (idempotent), then exclusive-creates the record
    file which is the lock. On a lost race returns (False, existing_record)."""
    if state not in STATES:
        raise ValueError("unknown state %r" % state)
    _ensure_dir(ledger_dir(base))
    # payload sibling first; both racers write identical bytes, so overwrite is safe
    ppath = payload_path(job_key, base)
    ptmp = ppath.with_suffix(ppath.suffix + ".tmp-%s" % secrets.token_hex(4))
    with os.fdopen(os.open(str(ptmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w",
                   encoding="utf-8") as fh:
        fh.write(json.dumps(canonical, indent=2, sort_keys=True))
    os.replace(str(ptmp), str(ppath))

    rec = _new_record(job_key, canonical, state)
    rec["canonical_payload_path"] = ppath.name
    try:
        fd = os.open(str(record_path(job_key, base)), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False, read_record(job_key, base)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=2, sort_keys=True))
    return True, rec


def register_duplicate(job_key, base=None):
    """Increment delivery_count and touch updated_at. Nothing else changes."""
    rec = read_record(job_key, base)
    if rec is None:
        raise LedgerCorruption("duplicate of a missing record %s" % job_key)
    rec.setdefault("attempts", {}).setdefault("delivery_count", 1)
    rec["attempts"]["delivery_count"] += 1
    rec["updated_at"] = _iso_now()
    _persist_record(job_key, rec, base)
    return rec


def register_retry(job_key, base=None):
    """Operator-sanctioned retry of a failed job (retry:true canonical field).
    Resets state to received so the flow can be re-triggered; records the reason."""
    rec = read_record(job_key, base)
    if rec is None:
        raise LedgerCorruption("retry of a missing record %s" % job_key)
    rec.setdefault("attempts", {}).setdefault("delivery_count", 1)
    rec["attempts"]["delivery_count"] += 1
    rec["state"] = "received"
    rec["updated_at"] = _iso_now()
    rec.setdefault("notes", []).append({"at": _iso_now(), "note": "operator-sanctioned retry"})
    _persist_record(job_key, rec, base)
    return rec


def update_state(job_key, state, base=None, flow_id=None, podbean_permalink=None, note=None):
    """Advance a webhook-owned state (received, needs_input, test) or record a
    pipeline hand-off value. The pipeline's own transitions go through
    podcast_state.py, which calls back here to keep the file ledger in lockstep."""
    if state is not None and state not in STATES:
        raise ValueError("unknown state %r" % state)
    rec = read_record(job_key, base)
    if rec is None:
        raise LedgerCorruption("update of a missing record %s" % job_key)
    if state is not None:
        rec["state"] = state
    if flow_id is not None:
        rec["flow_id"] = flow_id
    if podbean_permalink is not None:
        rec["podbean_permalink"] = podbean_permalink
    if note:
        rec.setdefault("notes", []).append({"at": _iso_now(), "note": note})
    rec["updated_at"] = _iso_now()
    _persist_record(job_key, rec, base)
    return rec


def dedup_claim(job_key, canonical, state="received", retry_flag=False, base=None):
    """The full Section 3.3 dedup decision. Returns a verdict dict:
       {decision, state, record, created}. decision in accepted | duplicate | retry."""
    existing = read_record(job_key, base)
    if existing is None:
        claimed, rec = claim(job_key, canonical, state=state, base=base)
        if claimed:
            return {"decision": "accepted", "state": rec["state"], "record": rec, "created": True}
        existing = rec  # lost the race; fall through to the duplicate/retry path
    if existing is not None and existing.get("state") == "failed":
        if retry_flag:
            rec = register_retry(job_key, base)
            return {"decision": "retry", "state": rec["state"], "record": rec, "created": False}
    rec = register_duplicate(job_key, base)
    return {"decision": "duplicate", "state": rec["state"], "record": rec, "created": False}


def quarantine(raw_body, reason, base=None):
    """Persist a rejected (wrong-tenant or corrupt) raw payload for audit. Returns
    the quarantine file path. Never processed, never fed to the pipeline."""
    _ensure_dir(quarantine_dir(base))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    name = "%s-%s.json" % (stamp, secrets.token_hex(4))
    path = quarantine_dir(base) / name
    envelope = {"quarantined_at": _iso_now(), "reason": reason, "raw": raw_body}
    _write_private(path, json.dumps(envelope, indent=2, sort_keys=True))
    return str(path)


def sweep(base=None, retention_days=_DEFAULT_RETENTION_DAYS, purge_tests=False):
    """Retention sweep. Deletes TERMINAL records (and their payload sibling) older
    than retention_days; keeps everything at least that long (Section 3.2). When
    purge_tests is set, test records are removed regardless of age (Section 8
    cleanup deletes test ledger records after verification)."""
    removed = []
    lpath = ledger_dir(base)
    if not lpath.is_dir():
        return {"removed": removed, "count": 0}
    cutoff = time.time() - retention_days * 86400
    for rec_file in sorted(lpath.glob("*.json")):
        if rec_file.name.endswith(".payload.json"):
            continue
        try:
            rec = json.loads(rec_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # corrupt files are left for operator review, never auto-deleted
        state = rec.get("state")
        job = rec.get("job_key", rec_file.stem)
        is_test = state == "test"
        is_old_terminal = state in TERMINAL and rec_file.stat().st_mtime < cutoff
        if (purge_tests and is_test) or is_old_terminal:
            for p in (rec_file, payload_path(job, base)):
                try:
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass
            removed.append(job)
    return {"removed": removed, "count": len(removed)}


# =============================================================================
# CLI
# =============================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description="Podcast Engine intake ledger.")
    ap.add_argument("cmd", nargs="?", choices=("claim", "read", "sweep", "quarantine", "duplicate"))
    ap.add_argument("--job")
    ap.add_argument("--canonical")
    ap.add_argument("--raw")
    ap.add_argument("--reason")
    ap.add_argument("--state", default="received")
    ap.add_argument("--base")
    ap.add_argument("--days", type=int, default=_DEFAULT_RETENTION_DAYS)
    ap.add_argument("--purge-tests", action="store_true")
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.cmd:
        ap.error("a command is required or --self-test")

    try:
        if args.cmd == "claim":
            if not args.job or not args.canonical:
                ap.error("claim needs --job and --canonical")
            canonical = json.loads(Path(args.canonical).read_text(encoding="utf-8"))
            verdict = dedup_claim(args.job, canonical, state=args.state,
                                  retry_flag=args.retry, base=args.base)
            print(json.dumps({k: v for k, v in verdict.items() if k != "record"}, indent=2))
            return EXIT_OK
        if args.cmd == "duplicate":
            if not args.job:
                ap.error("duplicate needs --job")
            rec = register_duplicate(args.job, args.base)
            print(json.dumps({"delivery_count": rec["attempts"]["delivery_count"]}))
            return EXIT_OK
        if args.cmd == "read":
            if not args.job:
                ap.error("read needs --job")
            rec = read_record(args.job, args.base)
            print(json.dumps(rec, indent=2, sort_keys=True) if rec else "null")
            return EXIT_OK
        if args.cmd == "sweep":
            print(json.dumps(sweep(args.base, args.days, args.purge_tests), indent=2))
            return EXIT_OK
        if args.cmd == "quarantine":
            if not args.raw or not args.reason:
                ap.error("quarantine needs --raw and --reason")
            raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
            print(json.dumps({"quarantined_to": quarantine(raw, args.reason, args.base)}))
            return EXIT_OK
    except LedgerCorruption as exc:
        print("FATAL: %s" % exc, file=sys.stderr)
        return EXIT_CORRUPTION
    except (OSError, ValueError) as exc:
        print("FATAL: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    return EXIT_USAGE


# =============================================================================
# SELF-TEST (temp base dir; never touches the real ~/.openclaw state)
# =============================================================================
def self_test():
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", name))

    tmp = tempfile.mkdtemp(prefix="pd-ledger-")
    canonical = {"contact_id": "CNT1", "location_id": "LOC1", "podcast_id": "pb-1",
                 "mode": "interview_style_podcast", "style": "vulnerable",
                 "q1_answer": "secret answer text that must stay out of the record"}
    job = "pd-CNT1-0123456789abcdef"

    v1 = dedup_claim(job, canonical, base=tmp)
    check("first delivery accepted", v1["decision"] == "accepted" and v1["created"] is True)
    check("state received", v1["state"] == "received")
    check("delivery_count 1", v1["record"]["attempts"]["delivery_count"] == 1)

    # record file is 0600 and carries NO answer text (PII isolation)
    rp = record_path(job, tmp)
    mode = oct(rp.stat().st_mode & 0o777)
    check("record file mode 0600", mode == "0o600")
    rec_text = rp.read_text(encoding="utf-8")
    check("no answer text in record", "secret answer text" not in rec_text)
    check("payload sibling exists", payload_path(job, tmp).is_file())
    check("payload carries the answer", "secret answer text" in payload_path(job, tmp).read_text())

    # identical redelivery -> duplicate, delivery_count increments, no new record
    v2 = dedup_claim(job, canonical, base=tmp)
    check("redelivery is duplicate", v2["decision"] == "duplicate")
    check("delivery_count now 2", v2["record"]["attempts"]["delivery_count"] == 2)

    # concurrent-claim simulation: direct claim on an existing job loses the race
    claimed, _ = claim(job, canonical, base=tmp)
    check("second claim loses the race", claimed is False)

    # failed job: redelivery without retry -> duplicate; with retry -> retry+reset
    update_state(job, "failed", base=tmp)
    v3 = dedup_claim(job, canonical, base=tmp, retry_flag=False)
    check("failed + no retry -> duplicate", v3["decision"] == "duplicate")
    v4 = dedup_claim(job, canonical, base=tmp, retry_flag=True)
    check("failed + retry -> retry, reset to received", v4["decision"] == "retry" and v4["state"] == "received")

    # a DIFFERENT job key coexists independently
    job2 = "pd-CNT1-fedcba9876543210"
    v5 = dedup_claim(job2, canonical, base=tmp)
    check("distinct job key claims independently", v5["decision"] == "accepted")

    # quarantine writes an audit envelope, never a ledger record
    qp = quarantine({"location_id": "WRONGTENANT", "note": "cross-tenant"}, "tenant_mismatch", base=tmp)
    check("quarantine file written", Path(qp).is_file())
    check("quarantine mode 0600", oct(Path(qp).stat().st_mode & 0o777) == "0o600")
    check("quarantine records the reason", "tenant_mismatch" in Path(qp).read_text())

    # corruption is detected (fail closed), never silently overwritten
    rp.write_text("{ this is not json", encoding="utf-8")
    raised = False
    try:
        read_record(job, tmp)
    except LedgerCorruption:
        raised = True
    check("corrupt record raises LedgerCorruption", raised)

    # sweep: terminal + old is removed; fresh is kept; test purge works
    tmp2 = tempfile.mkdtemp(prefix="pd-sweep-")
    dedup_claim("pd-OLD-aaaaaaaaaaaaaaaa", canonical, base=tmp2)
    update_state("pd-OLD-aaaaaaaaaaaaaaaa", "complete", base=tmp2)
    old_rp = record_path("pd-OLD-aaaaaaaaaaaaaaaa", tmp2)
    old_time = time.time() - 100 * 86400
    os.utime(str(old_rp), (old_time, old_time))
    dedup_claim("pd-NEW-bbbbbbbbbbbbbbbb", canonical, base=tmp2)
    update_state("pd-NEW-bbbbbbbbbbbbbbbb", "complete", base=tmp2)
    dedup_claim("pd-TST-cccccccccccccccc", canonical, state="test", base=tmp2)
    swept = sweep(tmp2, retention_days=90, purge_tests=True)
    check("old terminal record swept", "pd-OLD-aaaaaaaaaaaaaaaa" in swept["removed"])
    check("fresh terminal record kept", "pd-NEW-bbbbbbbbbbbbbbbb" not in swept["removed"])
    check("test record purged", "pd-TST-cccccccccccccccc" in swept["removed"])

    print("== ledger self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
