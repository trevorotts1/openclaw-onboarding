#!/usr/bin/env python3
"""
fleet_ledger.py — the PERSISTENT PER-BOX LEDGER for a fleet sweep (FLEET-FIX 4b).

ONE file per box, at the canonical path:

    <ledger-root>/<sweep-id>/<box>.json        (ledger-root defaults to /tmp)

i.e. the doctrine path `/tmp/<sweep>/<box>.json`.

WHY THIS EXISTS
---------------
A fleet fan-out that reports green on a broken box is the exact failure mode
this closes.  Before this module there was NO durable per-box record of what a
sweep did: a wave that half-failed left nothing behind to resume from, and the
only "evidence" a box was healthy was the fan-out's own aggregate exit code —
which is the one number a partially-failed fan-out is worst at.

The ledger is therefore:

  • PERSISTENT — it survives the process that wrote it.  A wave that dies
    mid-flight leaves every completed box's row on disk.
  • PER-BOX    — one box failing can never corrupt or hide another box's row.
  • RESUMABLE  — a second pass can skip boxes that already PASSED *under the
    same expectations* (the expectations hash is part of the row; change what
    you expect and every cached PASS is invalidated).
  • APPEND-ONLY IN SPIRIT — every finalize() appends to `history`, so a box that
    was fixed on attempt 3 still shows that it failed attempts 1 and 2.
  • FAIL-CLOSED — a required check that never ran is a FAIL, not a "no data".
    There is no status that means "probably fine".  `PASS` is only ever written
    when every required check explicitly returned PASS.

STATUS MODEL (precedence FAIL > UNKNOWN > PASS)
-----------------------------------------------
  PASS     every required check ran and returned PASS
  FAIL     at least one required check returned FAIL, or never ran at all
  UNKNOWN  no FAILs, but at least one check was indeterminate (ssh timeout,
           transient error).  UNKNOWN IS NOT GREEN — it exits non-zero.
  PENDING  the row exists but the box has not been finalized yet

CLI (so a bash fan-out can write rows without any Python glue)
-------------------------------------------------------------
    python3 fleet_ledger.py record  --sweep-id S --box B --check install \
                                    --status PASS --reason "update-skills ok"
    python3 fleet_ledger.py finalize --sweep-id S --box B --required install
    python3 fleet_ledger.py rollup   --sweep-id S           # writes _sweep.json
    python3 fleet_ledger.py path     --sweep-id S --box B

Exit codes (rollup): 0 all PASS · 2 any FAIL · 3 any UNKNOWN/PENDING · 1 fatal.

AUD-58 / FLEET-FIX 4b.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = "fleet-ledger/v1"

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
PENDING = "PENDING"

VALID_STATUSES = (PASS, FAIL, UNKNOWN, PENDING)

# Precedence: the WORST status wins when rolling a box (or a sweep) up.
_PRECEDENCE = {FAIL: 3, UNKNOWN: 2, PENDING: 1, PASS: 0}

DEFAULT_LEDGER_ROOT = "/tmp"

# A box name becomes a filename — keep it boring and traversal-proof.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class LedgerError(RuntimeError):
    """Fatal, operator-visible ledger misuse (bad name, bad status, bad path)."""


# ── naming / paths ────────────────────────────────────────────────────────────

def _assert_safe(kind: str, name: str) -> str:
    if not isinstance(name, str) or not _SAFE_NAME.match(name):
        raise LedgerError(
            f"unsafe {kind} name {name!r} — must match {_SAFE_NAME.pattern} "
            "(no slashes, no '..', <=64 chars)"
        )
    return name


def ledger_root(explicit: Optional[str] = None) -> Path:
    """Root under which sweeps live.  Default /tmp; override for hermetic tests."""
    return Path(explicit or os.environ.get("FLEET_LEDGER_ROOT") or DEFAULT_LEDGER_ROOT)


def sweep_dir(sweep_id: str, root: Optional[str] = None) -> Path:
    return ledger_root(root) / _assert_safe("sweep", sweep_id)


def ledger_path(sweep_id: str, box: str, root: Optional[str] = None) -> Path:
    """The canonical per-box ledger path: <root>/<sweep>/<box>.json"""
    return sweep_dir(sweep_id, root) / f"{_assert_safe('box', box)}.json"


def sweep_rollup_path(sweep_id: str, root: Optional[str] = None) -> Path:
    return sweep_dir(sweep_id, root) / "_sweep.json"


def expectations_sha(expectations: Dict[str, Any]) -> str:
    """Stable hash of the sweep's expectations.  A cached PASS is only reusable
    while the expectations are byte-identical — change the expected repo stamp
    and every prior PASS is correctly invalidated."""
    blob = json.dumps(expectations or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ── atomic, concurrency-safe IO ───────────────────────────────────────────────

def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write via temp-file + os.replace so a killed process can never leave a
    half-written (and therefore silently-parsed-as-broken) ledger row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)          # atomic within the same filesystem
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def _box_lock(path: Path):
    """Per-box advisory lock.  Two workers touching the SAME box (a retry racing
    a sweep) serialize; different boxes never contend."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    fh = open(lock, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── the row ───────────────────────────────────────────────────────────────────

def new_row(sweep_id: str, box: str, expect_sha: str = "") -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "sweep_id": _assert_safe("sweep", sweep_id),
        "box": _assert_safe("box", box),
        "status": PENDING,
        "attempts": 0,
        "expectations_sha": expect_sha,
        "created_at": _now(),
        "updated_at": _now(),
        "checks": {},
        "reasons": [],
        "history": [],
    }


def load_row(sweep_id: str, box: str, root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load a persisted row.  A corrupt/truncated row is NOT silently discarded —
    it is returned as a FAIL row so the box can never be mistaken for green."""
    path = ledger_path(sweep_id, box, root)
    if not path.exists():
        return None
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        row = new_row(sweep_id, box)
        row["status"] = FAIL
        row["reasons"] = [f"ledger row CORRUPT ({exc}) — treated as FAIL, never as green"]
        return row
    if not isinstance(row, dict) or row.get("schema") != SCHEMA:
        bad = new_row(sweep_id, box)
        bad["status"] = FAIL
        bad["reasons"] = [f"ledger row has unknown schema {row.get('schema') if isinstance(row, dict) else type(row).__name__!r} — treated as FAIL"]
        return bad
    return row


def save_row(row: Dict[str, Any], root: Optional[str] = None) -> Path:
    path = ledger_path(row["sweep_id"], row["box"], root)
    row["updated_at"] = _now()
    _atomic_write_json(path, row)
    return path


def record_check(
    sweep_id: str,
    box: str,
    check: str,
    status: str,
    reason: str = "",
    observed: Optional[Dict[str, Any]] = None,
    root: Optional[str] = None,
    expect_sha: str = "",
) -> Dict[str, Any]:
    """Upsert ONE check row on ONE box.  Unknown status = LedgerError (a typo'd
    status must never quietly become green)."""
    if status not in VALID_STATUSES:
        raise LedgerError(f"invalid status {status!r} — must be one of {VALID_STATUSES}")
    path = ledger_path(sweep_id, box, root)
    with _box_lock(path):
        row = load_row(sweep_id, box, root) or new_row(sweep_id, box, expect_sha)
        if expect_sha:
            row["expectations_sha"] = expect_sha
        row["checks"][check] = {
            "status": status,
            "reason": reason,
            "observed": observed or {},
            "ts": _now(),
        }
        save_row(row, root)
    return row


def finalize(
    sweep_id: str,
    box: str,
    required: Iterable[str],
    root: Optional[str] = None,
    expect_sha: str = "",
) -> Dict[str, Any]:
    """Compute the box verdict from its checks and append to history.

    FAIL-CLOSED: a required check with NO row is a FAIL ("never ran"), not a
    silent skip.  This is the single most important line in this file — it is
    what makes the harness a gate rather than a report.
    """
    required = list(required)
    path = ledger_path(sweep_id, box, root)
    with _box_lock(path):
        row = load_row(sweep_id, box, root) or new_row(sweep_id, box, expect_sha)
        if expect_sha:
            row["expectations_sha"] = expect_sha

        reasons: List[str] = []
        worst = PASS
        for check in required:
            entry = row["checks"].get(check)
            if entry is None:
                row["checks"][check] = {
                    "status": FAIL,
                    "reason": "REQUIRED CHECK NEVER RAN — fail-closed (a gate that fails open is not a gate)",
                    "observed": {},
                    "ts": _now(),
                }
                entry = row["checks"][check]
            st = entry.get("status")
            if st not in VALID_STATUSES:
                entry["status"] = st = FAIL
                entry["reason"] = f"invalid recorded status {st!r} — fail-closed"
            if st in (FAIL, UNKNOWN, PENDING):
                reasons.append(f"{check}: {st} — {entry.get('reason') or 'no reason recorded'}")
            if _PRECEDENCE[st] > _PRECEDENCE[worst]:
                worst = st
        if worst == PENDING:      # a required check left PENDING is not green
            worst = FAIL

        row["status"] = worst
        row["reasons"] = reasons
        row["attempts"] = int(row.get("attempts", 0)) + 1
        row["required"] = required
        row["history"].append({
            "ts": _now(),
            "attempt": row["attempts"],
            "status": worst,
            "failed": [c for c in required if row["checks"].get(c, {}).get("status") != PASS],
        })
        save_row(row, root)
    return row


def should_skip(row: Optional[Dict[str, Any]], expect_sha: str) -> bool:
    """--resume semantics: skip ONLY a box that already PASSED under the SAME
    expectations.  A PASS recorded against different expectations is worthless."""
    if not row:
        return False
    return row.get("status") == PASS and bool(expect_sha) and row.get("expectations_sha") == expect_sha


# ── sweep rollup ──────────────────────────────────────────────────────────────

def list_box_rows(sweep_id: str, root: Optional[str] = None) -> List[Dict[str, Any]]:
    d = sweep_dir(sweep_id, root)
    if not d.is_dir():
        return []
    rows = []
    for p in sorted(d.glob("*.json")):
        if p.name.startswith("_"):
            continue
        rows.append(load_row(sweep_id, p.stem, root) or {})
    return [r for r in rows if r]


def rollup(sweep_id: str, root: Optional[str] = None, expected_boxes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Aggregate every per-box row into <sweep>/_sweep.json.

    If `expected_boxes` is given, a box with NO row on disk is counted as FAIL
    (missing = failed, never = fine)."""
    rows = list_box_rows(sweep_id, root)
    by_box = {r["box"]: r for r in rows}
    if expected_boxes:
        for b in expected_boxes:
            if b not in by_box:
                by_box[b] = {
                    "box": b,
                    "status": FAIL,
                    "reasons": ["NO LEDGER ROW WRITTEN — box never reported; fail-closed"],
                    "checks": {},
                }
    counts = {PASS: 0, FAIL: 0, UNKNOWN: 0, PENDING: 0}
    for r in by_box.values():
        counts[r.get("status", PENDING) if r.get("status") in VALID_STATUSES else FAIL] += 1

    if counts[FAIL]:
        verdict = FAIL
    elif counts[UNKNOWN] or counts[PENDING]:
        verdict = UNKNOWN
    elif counts[PASS]:
        verdict = PASS
    else:
        verdict = FAIL          # zero boxes reported is a FAILED sweep, not a green one

    doc = {
        "schema": SCHEMA,
        "sweep_id": sweep_id,
        "verdict": verdict,
        "counts": counts,
        "boxes": {
            b: {"status": r.get("status", PENDING), "reasons": r.get("reasons", [])}
            for b, r in sorted(by_box.items())
        },
        "updated_at": _now(),
    }
    _atomic_write_json(sweep_rollup_path(sweep_id, root), doc)
    return doc


def exit_code_for(verdict: str) -> int:
    return {PASS: 0, FAIL: 2, UNKNOWN: 3, PENDING: 3}.get(verdict, 1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="per-box fleet ledger (/tmp/<sweep>/<box>.json)")
    ap.add_argument("command", choices=["record", "finalize", "rollup", "path", "show"])
    ap.add_argument("--sweep-id", required=True)
    ap.add_argument("--box")
    ap.add_argument("--check")
    ap.add_argument("--status", choices=list(VALID_STATUSES))
    ap.add_argument("--reason", default="")
    ap.add_argument("--observed", default="", help="JSON object of observed values")
    ap.add_argument("--required", action="append", default=[], help="required check id (repeatable)")
    ap.add_argument("--expect-box", action="append", default=[], help="box expected to have reported (rollup)")
    ap.add_argument("--expectations-sha", default="")
    ap.add_argument("--ledger-root", default=None)
    args = ap.parse_args(argv)

    try:
        if args.command == "path":
            if not args.box:
                raise LedgerError("--box required")
            print(ledger_path(args.sweep_id, args.box, args.ledger_root))
            return 0

        if args.command == "show":
            if not args.box:
                raise LedgerError("--box required")
            row = load_row(args.sweep_id, args.box, args.ledger_root)
            if row is None:
                print(json.dumps({"box": args.box, "status": FAIL,
                                  "reasons": ["NO LEDGER ROW — fail-closed"]}, indent=2))
                return 2
            print(json.dumps(row, indent=2))
            return exit_code_for(row.get("status", PENDING))

        if args.command == "record":
            if not (args.box and args.check and args.status):
                raise LedgerError("--box, --check and --status are required for `record`")
            observed = json.loads(args.observed) if args.observed else {}
            row = record_check(args.sweep_id, args.box, args.check, args.status,
                               args.reason, observed, args.ledger_root, args.expectations_sha)
            print(f"[ledger] {args.box}/{args.check} = {args.status} -> "
                  f"{ledger_path(args.sweep_id, args.box, args.ledger_root)}")
            return 0 if row else 1

        if args.command == "finalize":
            if not args.box:
                raise LedgerError("--box required")
            if not args.required:
                raise LedgerError("--required <check> is MANDATORY: finalizing with no required "
                                  "checks would mark an unprobed box PASS (fail-open)")
            row = finalize(args.sweep_id, args.box, args.required, args.ledger_root, args.expectations_sha)
            print(f"[ledger] {args.box} = {row['status']}"
                  + ("" if row["status"] == PASS else "  " + " | ".join(row["reasons"])))
            return exit_code_for(row["status"])

        if args.command == "rollup":
            doc = rollup(args.sweep_id, args.ledger_root, args.expect_box or None)
            print(json.dumps(doc, indent=2))
            return exit_code_for(doc["verdict"])
    except LedgerError as exc:
        print(f"[ledger] FATAL: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(_main())
