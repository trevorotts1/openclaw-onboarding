#!/usr/bin/env python3
"""Box-side bridge between the hosted intake mini-app and deck-intake-driver.py.

The mini-app is a FRONT-END to the existing intake state machine, not a second
one. This bridge:

  mint  -> POST /api/sessions (box-authenticated) and print the capability link
           the box speaks to the client in chat.
  sync  -> poll GET /api/sessions/<token>/answers?since=<cursor> and REPLAY each
           new answer through deck-intake-driver.py --answer <id> "<text>" then
           --next, so working/interview/intake_ledger.json, the provers, Gate 0
           and deck-build-guard.sh are all UNCHANGED. On completion it runs
           --complete (standard) or assembles the record and runs
           --signature --record (signature).

Degrades safely: if the Worker is unreachable, sync exits non-zero and the box
falls back to the §3 chat driver — the driver never depended on the app.

No secrets are printed. The box→worker admin token is read from env
INTAKE_ADMIN_TOKEN (never from argv, never logged).

Stdlib only (urllib) — nothing to install on a box.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

# q1..q8 for the signature record assembly.
SP_QUESTIONS = [f"q{i}" for i in range(1, 9)]


def _driver_path(explicit: str | None) -> pathlib.Path:
    """Locate deck-intake-driver.py: explicit override, else walk up from here."""
    if explicit:
        return pathlib.Path(explicit).expanduser().resolve()
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "23-ai-workforce-blueprint" / "scripts" / "deck-intake-driver.py"
        if cand.is_file():
            return cand
    # Fall back to the conventional relative location; caller errors if missing.
    return (here.parents[2] / "scripts" / "deck-intake-driver.py").resolve()


# ---- pure command builders (unit-tested offline) ----------------------------

def driver_answer_cmd(driver: str, run_dir: str, qid: str, value: str) -> list[str]:
    return [sys.executable, driver, "--run-dir", run_dir, "--answer", qid, value]


def driver_next_cmd(driver: str, run_dir: str) -> list[str]:
    return [sys.executable, driver, "--run-dir", run_dir, "--next"]


def driver_complete_cmd(driver: str, run_dir: str) -> list[str]:
    return [sys.executable, driver, "--run-dir", run_dir, "--complete"]


def driver_signature_record_cmd(driver: str, run_dir: str, record_path: str) -> list[str]:
    return [sys.executable, driver, "--signature", "--run-dir", run_dir, "--record", record_path]


def build_sp_record(answers_by_id: dict, frame: str | None) -> dict:
    """Assemble the answers_record that `--signature --record` consumes.

    Best-effort: q7's free-text answer seeds the offer-token ledger; the Buddy
    refines it in the post-form follow-up. asked_all_at_once is a RECORD-layer
    fact (the ledger is committed as one atomic block after the one-at-a-time
    web flow), NOT a claim that the client saw a batch of questions.
    """
    answers = {q: answers_by_id.get(q, "") for q in SP_QUESTIONS if answers_by_id.get(q)}
    q7 = (answers_by_id.get("q7") or "").strip()
    record = {
        "answers": answers,
        "asked_all_at_once": True,
        "one_question_per_turn": False,
        "signature_frame": (frame or answers_by_id.get("frame_selection") or "").strip().lower() or None,
        "offer_token_ledger": [q7] if q7 else [],
    }
    return record


def is_complete(session_status: str, progress: dict | None) -> bool:
    if session_status == "complete":
        return True
    return bool(progress and progress.get("complete"))


# ---- HTTP (no external deps) -------------------------------------------------

def _http(method: str, url: str, *, token: str | None = None, body: dict | None = None,
          timeout: int = 20) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw[:200]}


# ---- subcommand: mint -------------------------------------------------------

def cmd_mint(args) -> int:
    admin = os.environ.get("INTAKE_ADMIN_TOKEN", "")
    if not admin:
        print("error: INTAKE_ADMIN_TOKEN not set in env (box→worker auth)", file=sys.stderr)
        return 2
    payload = json.loads(pathlib.Path(args.questions).read_text(encoding="utf-8"))
    body = {
        "run_id": args.run_id,
        "box_id": args.box_id,
        "questions_payload": payload,
        "want_confirm_code": bool(args.confirm_code),
    }
    if args.ttl_days:
        body["ttl_days"] = args.ttl_days
    status, resp = _http("POST", args.worker_url.rstrip("/") + "/api/sessions", token=admin, body=body)
    if status not in (200, 201):
        print(f"error: mint failed (HTTP {status}): {resp.get('error')}", file=sys.stderr)
        return 3
    # Emit the machine-usable bits for the caller; never echo the admin token.
    out = {
        "token": resp.get("token"),
        "capability_url": resp.get("capability_url"),
        "reused": resp.get("reused", False),
    }
    if resp.get("confirm_code"):
        out["confirm_code"] = resp["confirm_code"]  # box speaks this in chat if used
    print(json.dumps(out, indent=2))
    return 0


# ---- subcommand: sync -------------------------------------------------------

def _run_driver(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def cmd_sync(args) -> int:
    driver = str(_driver_path(args.driver))
    if not pathlib.Path(driver).is_file():
        print(f"error: deck-intake-driver.py not found at {driver}", file=sys.stderr)
        return 2
    run_dir = str(pathlib.Path(args.run_dir).expanduser().resolve())
    base = args.worker_url.rstrip("/") + f"/api/sessions/{args.token}/answers"
    cursor = args.since
    applied: dict[str, str] = {}
    deadline = time.time() + args.max_seconds

    while True:
        try:
            status, resp = _http("GET", base + f"?since={cursor}")
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"error: worker unreachable ({e}); falling back to chat driver", file=sys.stderr)
            return 4
        if status != 200:
            print(f"error: poll failed (HTTP {status}): {resp.get('error')}", file=sys.stderr)
            return 3

        for ans in resp.get("answers", []):
            qid, value = ans.get("question_id"), ans.get("value", "")
            rc, out = _run_driver(driver_answer_cmd(driver, run_dir, qid, value))
            if rc == 0:
                applied[qid] = value
                _run_driver(driver_next_cmd(driver, run_dir))  # advance the turn-gate
                if args.verbose:
                    print(f"[bridge] applied {qid}", file=sys.stderr)
            else:
                # The Python driver is authoritative; a rejection is logged, not fatal.
                print(f"[bridge] driver rejected {qid}: {out.strip()[:160]}", file=sys.stderr)
            cursor = max(cursor, int(ans.get("id", cursor)))

        if is_complete(resp.get("session_status", ""), resp.get("progress")):
            return _finalize(args, driver, run_dir, applied)

        if args.once:
            print(json.dumps({"status": "polled", "cursor": cursor, "applied": list(applied)}))
            return 0
        if time.time() > deadline:
            print("error: sync timed out before the client completed", file=sys.stderr)
            return 5
        time.sleep(args.poll_interval)


def _finalize(args, driver: str, run_dir: str, applied: dict) -> int:
    if args.question_set == "signature":
        record = build_sp_record(applied, applied.get("frame_selection"))
        rec_path = pathlib.Path(run_dir) / "working" / "interview" / "sp_bridge_record.json"
        rec_path.parent.mkdir(parents=True, exist_ok=True)
        rec_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        rc, out = _run_driver(driver_signature_record_cmd(driver, run_dir, str(rec_path)))
        print(out.strip())
        return 0 if rc == 0 else 6
    rc, out = _run_driver(driver_complete_cmd(driver, run_dir))
    print(out.strip())
    return 0 if rc == 0 else 6


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mint", help="open a hosted intake session and print the capability link")
    m.add_argument("--worker-url", required=True)
    m.add_argument("--run-id", required=True)
    m.add_argument("--box-id", required=True)
    m.add_argument("--questions", required=True, help="path to a questions_payload.json (from build_questions_payload.py)")
    m.add_argument("--confirm-code", action="store_true", help="mint a 6-digit high-trust code")
    m.add_argument("--ttl-days", type=float, default=None)
    m.set_defaults(func=cmd_mint)

    s = sub.add_parser("sync", help="poll answers and replay them through deck-intake-driver.py")
    s.add_argument("--worker-url", required=True)
    s.add_argument("--token", required=True)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--question-set", choices=["standard", "signature"], default="standard")
    s.add_argument("--driver", default=None, help="override path to deck-intake-driver.py")
    s.add_argument("--since", type=int, default=0)
    s.add_argument("--poll-interval", type=float, default=45.0)
    s.add_argument("--max-seconds", type=float, default=7 * 24 * 3600)
    s.add_argument("--once", action="store_true", help="poll a single time (for tests/cron)")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_sync)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
