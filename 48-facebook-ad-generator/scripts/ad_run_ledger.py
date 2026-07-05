#!/usr/bin/env python3
"""
ad_run_ledger.py — the RUN-ID NO-DOUBLE-CHARGE LEDGER (net-new).

Gives each run its receipt-number (run-id) and records every PAID result (each image
task-id, each uploaded link) under it, so a retry SKIPS paid work and never charges
twice. The offline checker `ad_build_check._chk_run_ledger` reads this file; nothing
here makes a live network call.

Writes are ATOMIC (write-to-temp-then-rename) so a crash mid-run never erases the
record and causes a re-charge. The running spend tally lives here too — the cheap LOCAL
arithmetic the foreman gates on (AF-FBAD-TALLY-CROSS), NOT a balance lookup per image.

Ledger shape (working/checkpoints/ad_run_ledger.json):
    { "run_id": "<run-id>", "spent_usd": 0.0, "ceiling_usd": 5.0,
      "events": [ { "kind": "image|upload", "key": "<idempotency key>",
                    "usd": 0.05, "result": {...}, "at": "<iso>" } ],
      "qc_sessions": [ { "gate": "copy|prompt|image|targeting|package",
                         "grader": "<registered role slug>",
                         "session_id": "<grading session id>", "at": "<iso>" } ] }

The qc_sessions[] list is the CONDUCTOR's independent record of each grading session it
dispatched; ad_build_check._chk_qc_independence cross-checks every scorecard's
grader_session_id against it so a self-attested grade the ledger never saw fails closed.

CLI:
    python3 ad_run_ledger.py --run-dir DIR init --run-id ID --ceiling 5.0
    python3 ad_run_ledger.py --run-dir DIR record --kind image --key img-3 --usd 0.05 \
        --result '{"kie_task_id":"abc","width":1500,"height":1500,"model":"gpt-image-2-text-to-image"}'
    python3 ad_run_ledger.py --run-dir DIR done --key img-3      # -> "DONE" or "PENDING"
    python3 ad_run_ledger.py --run-dir DIR can-spend --usd 0.05  # -> "OK" / "WOULD_CROSS"
    python3 ad_run_ledger.py --run-dir DIR qc-session --gate copy \
        --grader qc-role--paid-advertisement --session-id sess-copy-01
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "ad_run_ledger.json"


def load(run_dir: Path) -> dict:
    p = _ledger_path(run_dir)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _atomic_write(run_dir: Path, obj: dict) -> None:
    """Write-to-temp-then-rename so a crash never leaves a half-written ledger."""
    p = _ledger_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, p)  # atomic on POSIX


def init(run_dir: Path, run_id: str, ceiling_usd: float) -> dict:
    """Idempotent: if a ledger with this run_id already exists, return it unchanged."""
    cur = load(run_dir)
    if cur.get("run_id") == run_id:
        return cur
    obj = {"run_id": run_id, "spent_usd": 0.0, "ceiling_usd": float(ceiling_usd),
           "events": []}
    _atomic_write(run_dir, obj)
    return obj


def is_done(run_dir: Path, key: str) -> bool:
    """True when a paid event with this idempotency key is already recorded (a retry
    must SKIP it — never re-pay / re-upload)."""
    for e in load(run_dir).get("events", []):
        if isinstance(e, dict) and e.get("key") == key:
            return True
    return False


def can_spend(run_dir: Path, usd: float) -> bool:
    """Cheap LOCAL arithmetic: would the next paid item cross the ceiling? (NOT a
    balance call.) True = safe to spend; False = STOP."""
    led = load(run_dir)
    spent = float(led.get("spent_usd", 0.0) or 0.0)
    cap = led.get("ceiling_usd")
    if not isinstance(cap, (int, float)):
        return True  # no ceiling recorded here -> the cost-ceiling gate owns it
    return (spent + float(usd)) <= float(cap)


def record(run_dir: Path, kind: str, key: str, usd: float, result: dict) -> dict:
    """Record a paid result under the run-id. Idempotent on `key`: a repeat is a no-op
    (returns the existing event) so a retry never double-charges or double-records."""
    led = load(run_dir)
    if not led:
        raise RuntimeError("ledger not initialized — call init first")
    for e in led.get("events", []):
        if isinstance(e, dict) and e.get("key") == key:
            return e  # already recorded; do not re-add or re-charge
    event = {"kind": kind, "key": key, "usd": float(usd), "result": result,
             "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    led.setdefault("events", []).append(event)
    led["spent_usd"] = round(float(led.get("spent_usd", 0.0) or 0.0) + float(usd), 6)
    _atomic_write(run_dir, led)
    return event


def result_for(run_dir: Path, key: str):
    """Return the stored `result` payload of a recorded event with this key, or None
    when no such event exists. Lets a RESUME recover an already-hosted/already-paid
    entry from the durable ledger (e.g. the delivered[] entry for an image whose upload
    was recorded but whose receipt was lost) instead of dropping it — never re-uploading
    or re-charging."""
    for e in load(run_dir).get("events", []):
        if isinstance(e, dict) and e.get("key") == key:
            return e.get("result")
    return None


def record_qc_session(run_dir: Path, gate: str, grader: str, session_id: str) -> dict:
    """Record — INDEPENDENTLY of the maker/grader — that the conductor dispatched a
    grading session for `gate`. Idempotent on `gate`: a repeat updates that gate's
    entry. This qc_sessions[] list is what ad_build_check._chk_qc_independence
    cross-checks a scorecard's grader_session_id against, so a self-attested grade the
    ledger never saw fails closed. Never charges (a QC dispatch is not a paid Kie call)."""
    led = load(run_dir)
    if not led:
        raise RuntimeError("ledger not initialized — call init first")
    sessions = led.setdefault("qc_sessions", [])
    entry = {"gate": str(gate), "grader": str(grader), "session_id": str(session_id),
             "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    for i, s in enumerate(sessions):
        if isinstance(s, dict) and str(s.get("gate")) == str(gate):
            sessions[i] = entry
            break
    else:
        sessions.append(entry)
    _atomic_write(run_dir, led)
    return entry


def qc_sessions(run_dir: Path) -> list:
    """The recorded independent grading sessions [{gate, grader, session_id, at}]."""
    led = load(run_dir)
    return [s for s in led.get("qc_sessions", []) if isinstance(s, dict)]


def main():
    ap = argparse.ArgumentParser(description="Run-id no-double-charge ledger.")
    ap.add_argument("--run-dir", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("init"); pi.add_argument("--run-id", required=True); pi.add_argument("--ceiling", type=float, default=0.0)
    pr = sub.add_parser("record")
    for a in ("--kind", "--key"):
        pr.add_argument(a, required=True)
    pr.add_argument("--usd", type=float, required=True)
    pr.add_argument("--result", default="{}")
    pd = sub.add_parser("done"); pd.add_argument("--key", required=True)
    pc = sub.add_parser("can-spend"); pc.add_argument("--usd", type=float, required=True)
    pq = sub.add_parser("qc-session")
    for a in ("--gate", "--grader", "--session-id"):
        pq.add_argument(a, required=True)
    args = ap.parse_args()
    rd = Path(args.run_dir).resolve()

    if args.cmd == "init":
        print(json.dumps(init(rd, args.run_id, args.ceiling), indent=2))
    elif args.cmd == "record":
        try:
            res = json.loads(args.result)
        except json.JSONDecodeError as exc:
            print(f"FATAL: --result is not JSON: {exc}", file=sys.stderr); sys.exit(2)
        print(json.dumps(record(rd, args.kind, args.key, args.usd, res), indent=2))
    elif args.cmd == "done":
        print("DONE" if is_done(rd, args.key) else "PENDING")
    elif args.cmd == "can-spend":
        print("OK" if can_spend(rd, args.usd) else "WOULD_CROSS")
    elif args.cmd == "qc-session":
        print(json.dumps(record_qc_session(rd, args.gate, args.grader, args.session_id),
                         indent=2))


if __name__ == "__main__":
    main()
