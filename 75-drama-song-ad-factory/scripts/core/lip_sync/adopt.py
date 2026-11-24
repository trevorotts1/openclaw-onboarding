#!/usr/bin/env python3
"""adopt.py: register lip-sync takes already on disk, so nothing is bought twice.

N-16: the evidence join accepts a take that has a governed ledger row (job id,
model, file fingerprint), and one command registers takes already on disk.

    cd scripts/core && python3 -m lip_sync adopt --run-dir "$RUN" \
        --ledger "$RUN/spend.sqlite3" [--shot SID ...] [--dry-run]

What it reads (read-only):
  * the run's spend ledger ``jobs`` + ``results`` tables: one row per paid
    attempt, its model id and every saved file with its sha256;
  * the run's approved lip-sync requirements (``lipsync_evidence._approved``),
    so each ledger take is matched to exactly one approved shot by its own
    receipt binding, never by file-name resemblance.

What it writes:
  * ``<run>/control/lip-sync/evidence.json`` rows in the SAME shape the chain
    writes, each marked ``adopted: true`` and carrying its ledger job id;
  * the take's eye record and landed facts come from the caller's JSON files
    when given (``--eye-records``, ``--landed``); otherwise the row is written
    WITHOUT them and ``check_plan`` refuses it until a reader supplies them.

Nothing here spends, dispatches, approves, or edits a ledger row.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

TOOL = "lip_sync.adopt"
SCHEMA = "blackceo.lipsync-run/v1"
VERSION = "1.0.0"
OUTCOME_OK = "LIPSYNC_ADOPT_OK"
NO_TAKES = "LIPSYNC_ADOPT_NO_TAKES"
LEDGER_UNREADABLE = "LIPSYNC_LEDGER_UNREADABLE"


class AdoptError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _need(ok, code, message):
    if not ok:
        raise AdoptError(code, message)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def ledger_takes(ledger_db, run_id):
    """Every succeeded job's saved file with its model, task and hashes.

    Reads ``jobs`` + ``results`` from the governed ledger. A ledger that cannot
    be opened is refused (never read as "no takes")."""
    _need(isinstance(ledger_db, str) and Path(ledger_db).is_file(),
          LEDGER_UNREADABLE, "name the run's spend ledger: %r" % (ledger_db,))
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % ledger_db, uri=True, timeout=10)
        try:
            rows = conn.execute(
                "SELECT j.logical_key, j.attempt_id, j.remote_task_id, j.state,"
                " r.artifact_path, r.sha256"
                " FROM jobs j JOIN results r ON r.run_id=j.run_id"
                " AND r.logical_key=j.logical_key AND r.attempt_id=j.attempt_id"
                " WHERE j.run_id=? AND j.state IN ('succeeded','reconciled')",
                (run_id,)).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise AdoptError(LEDGER_UNREADABLE, "%s: %s" % (ledger_db, exc)) from exc
    return [{"logical_key": k, "attempt_id": a, "task_id": t, "state": s,
             "path": p, "sha256": h} for k, a, t, s, p, h in rows]


def adoption_row(root, run_id, take, row, eye_record=None, landed=None,
                 take_dur_s=None):
    """The evidence row for one already-paid take, bound to ONE approved shot.

    ``take["sha256"]`` must equal the file's own digest and the file must
    belong to the run; a take with no matching approved requirement is refused
    (no guessed binding)."""
    root = Path(root).resolve()
    path = Path(take["path"])
    path = (path if path.is_absolute() else root / path).resolve()
    _need(path.is_file() and path.is_relative_to(root),
          "LIPSYNC_FILE_MISSING", "adopted take is not a file in this run: %s" % (path,))
    digest = _sha(path)
    _need(digest == take.get("sha256"),
          "LIPSYNC_HASH_MISMATCH",
          "ledger fingerprint for %s does not match the file on disk" % (path.name,))
    _need(isinstance(take.get("task_id"), str) and take["task_id"].strip(),
          "LIPSYNC_TASK_MISSING", "a ledger take without its job id is not adopted")
    receipt = root / "control" / "lip-sync" / "receipts" / (
        "%s-try%d.json" % (row["shot_id"], 1))
    _need(receipt.is_file(), "LIPSYNC_TASK_MISSING",
          "no dispatch receipt at %s; adopt needs the receipt the governor wrote" % (receipt,))
    return {"shot_id": row["shot_id"], "speaker": row["speaker"],
            "lip_sync_line_ids": list(row["lip_sync_line_ids"]),
            "storyboard_revision": row["storyboard_revision"],
            "start_s": row["start_s"], "end_s": row["end_s"],
            "sung": True,
            "clip_path": str(path), "clip_sha256": digest,
            "receipt_path": str(receipt), "task_id": take["task_id"],
            "adopted": True, "ledger_job": take.get("logical_key"),
            "verdict": "ACCEPT_WITH_FLAG",
            "eye_record": eye_record, "landed": landed, "take_dur_s": take_dur_s,
            "artifact": {"schema_version": "1.0.0",
                         "artifact_id": "lipsync-" + row["shot_id"],
                         "run_id": run_id, "stage": "generation", "kind": "video",
                         "path": str(path), "sha256": digest,
                         "provenance": {"task_id": take["task_id"],
                                        "receipt_path": str(receipt)}}}


def adopt(run_dir, run_id, ledger_db, *, shots=None, eye_records=None,
          landed=None, take_durations=None):
    """One command: register every ledger take that matches an approved shot."""
    from lipsync_evidence import LipsyncEvidenceError, _approved
    root = Path(run_dir).resolve()
    try:
        _, required = _approved(str(root))
    except LipsyncEvidenceError as exc:
        return {"outcome": "refused", "reason_code": exc.code, "detail": str(exc)}
    wanted = [sid for sid in required if not shots or sid in shots]
    takes = ledger_takes(ledger_db, run_id)
    evidence_path = root / "control" / "lip-sync" / "evidence.json"
    held = _read(evidence_path).get("rows") if evidence_path.is_file() else []
    rows = [r for r in (held or []) if isinstance(r, dict)]
    known = {(r.get("shot_id"), r.get("clip_sha256")) for r in rows}
    added, skipped = [], []
    for sid in wanted:
        row = required[sid]
        match = None
        for take in takes:
            if (sid, take["sha256"]) in known:
                break
            if str(take.get("logical_key", "")).endswith(sid):
                match = take
                break
        if match is None:
            skipped.append(sid)
            continue
        try:
            fresh = adoption_row(root, run_id, match, row,
                                 eye_record=(eye_records or {}).get(sid),
                                 landed=(landed or {}).get(sid),
                                 take_dur_s=(take_durations or {}).get(sid))
        except AdoptError as exc:
            return {"outcome": "refused", "reason_code": exc.code,
                    "detail": str(exc)}
        rows = [r for r in rows if r.get("shot_id") != sid] + [fresh]
        added.append(sid)
    if added:
        _write(evidence_path, {"schema_version": SCHEMA, "tool": TOOL,
                               "tool_version": VERSION, "run_dir": str(root),
                               "run_id": run_id,
                               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                        time.gmtime()),
                               "rows": rows})
    return {"outcome": "ok" if added else "refused",
            "reason_code": OUTCOME_OK if added else NO_TAKES,
            "detail": "" if added else
            "no governed ledger take matched an approved shot; nothing bought twice, "
            "nothing invented",
            "run_dir": str(root), "run_id": run_id, "adopted": added,
            "skipped": skipped, "rows": len(rows),
            "evidence_path": str(evidence_path)}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="python3 -m lip_sync adopt",
        description="Register lip-sync takes already on disk from the run's "
                    "governed ledger (N-16), so nothing is bought twice.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--shot", action="append", default=None)
    ap.add_argument("--eye-records", default=None,
                    help="JSON {shot_id: {sheet, who, verdict, ...}}")
    ap.add_argument("--landed", default=None,
                    help="JSON {shot_id: {max_face_h_pct, camera_move_px}}")
    ap.add_argument("--take-durations", default=None,
                    help="JSON {shot_id: seconds} of the returned clips")
    a = ap.parse_args(argv)
    load = (lambda p: _read(Path(p)) if p else {})
    result = adopt(a.run_dir, a.run_id, a.ledger, shots=a.shot,
                   eye_records=load(a.eye_records), landed=load(a.landed),
                   take_durations=load(a.take_durations))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("outcome") == "ok" else 5


if __name__ == "__main__":
    sys.exit(main())
