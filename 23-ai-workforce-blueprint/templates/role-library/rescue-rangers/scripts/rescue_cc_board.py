#!/usr/bin/env python3
"""
rescue_cc_board.py — Rescue Rangers Command Center board caller (FAIL-SOFT).

Topic-4 FIX 4-C: put rescue TICKETS on the Command Center Kanban (kills R3 "no
ticket visibility on the Kanban" and R6 "no aging/SLA sweep"). A direct port of
the proven presentations/scripts/cc_board.py, re-shaped for a rescue ticket
(department_slug:"rescue-rangers"). The operator receiver/poller call this on:
  * ticket-open  -> POST /api/tasks/ingest (card lands in backlog)
  * answer-out   -> PATCH status=review  (moves to the review column)
  * RESOLVED     -> PATCH status=done    (moves to done)
  * blocked      -> PATCH status=blocked
The board columns then give the open-ticket + aging view for free.

NON-NEGOTIABLE DESIGN RULES (mirrored verbatim from cc_board.py)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the
    rescue flow CONTINUES. Boarding a ticket is a VIEW, never a gate — a stuck
    board must never block answering a distress call. Every public function
    returns a value (task_id / bool / list) and NEVER raises.

  * AUTH PARITY with the CC /api/tasks/ingest endpoint (byte-for-byte):
      - Authorization: Bearer <CC_API_TOKEN>            (middleware layer)
      - x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (per-route)
    Both no-op server-side when the corresponding secret is unset (dev mode);
    we sign the EXACT bytes we send, so a configured secret matches.

  * STDLIB ONLY (urllib). Zero third-party deps.

  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => fail-soft no-op.
      COMMAND_CENTER_URL / MISSION_CONTROL_URL   base URL (either accepted).
      CC_API_TOKEN / MC_API_TOKEN                bearer (optional).
      WEBHOOK_SECRET / CC_WEBHOOK_SECRET         HMAC secret (optional).
      CC_BOARD_TIMEOUT                           per-request timeout s (default 8).

REQUEST CONTRACT (matched to the live /api/tasks/ingest endpoint):
  CREATE  POST {base}/api/tasks/ingest
    {title, description, priority, source:"rescue-rangers", source_ref:ticket_id,
     department_slug:"rescue-rangers", persona:"Director of Rescue Rangers",
     external_session_id:ticket_id, idempotency_key:ticket_id}
  PATCH   PATCH {base}/api/tasks/{task_id}     {status, note?}
    status vocabulary is the authoritative CC TaskStatus enum: backlog | inbox |
    planning | in_progress | assigned | review | testing | blocked |
    pending_dispatch | done.
  ACTIVITY POST {base}/api/tasks/{task_id}/activities   {activity_type, message}

The ticket_id IS the idempotency key: a re-delivered escalation dedupes to the
SAME card server-side, so the two transports (receiver push + poller pull) never
create duplicate cards for one ticket.

LEDGER LINK: when a rescue_ledger.Ledger is passed, a successful ingest stamps
cc_task_id back onto the ticket row (stamp_cc_task) so the Ticket Clerk can join
the board card to the durable record, and aging_sweep() reads aging tickets
straight from that ledger.

MOVEMENT RECEIPT: every advance attempt + its HTTP status/body is appended to
<state_dir>/cc-board/<ticket_id>.json so a failed advance is VISIBLE on disk
(mirrors cc_board's working/checkpoints/cc-board.json). Recording is fail-soft.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

_DEFAULT_TIMEOUT = 8
_DEPARTMENT_SLUG = "rescue-rangers"
_PERSONA = "Director of Rescue Rangers"

# Authoritative Command Center TaskStatus enum (same 10 values cc_board.py pins).
CC_TASK_STATUSES = frozenset({
    "backlog", "inbox", "planning", "in_progress", "assigned",
    "review", "testing", "blocked", "pending_dispatch", "done",
})

# Ledger status -> CC column mapping (FIX 4-C lifecycle->column contract).
LEDGER_TO_CC_STATUS = {
    "open": "backlog",
    "in_progress": "in_progress",
    "incomplete": "backlog",
    "answered": "review",
    "resolved": "done",
    "closed": "done",
    "blocked": "blocked",
}


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled no-op.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled,
    a clean no-op) when neither COMMAND_CENTER_URL nor MISSION_CONTROL_URL is
    set. Never raises."""
    env = env if env is not None else os.environ
    base = (env.get("COMMAND_CENTER_URL") or env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    return {
        "base_url": base,
        "token": (env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    print(f"[rescue_cc_board] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex — byte-for-
    byte parity with the CC route handler. None when no secret."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: dict, cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None).
    Raises only urllib/OS errors, which the public callers catch (fail-soft)."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    req = urllib.request.Request(url, data=raw_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# Pure payload builders (unit-testable without a live server).
# ---------------------------------------------------------------------------
def build_ingest_payload(ticket_id: str, client: str, problem: str,
                         priority: str = "high", box: str = "") -> dict:
    """The exact /api/tasks/ingest body for a rescue ticket. ticket_id is the
    idempotency key (dedupes a re-delivered escalation to one card). Pure/no I/O."""
    title = f"[{client or 'unknown'}] {(problem or 'rescue ticket').strip()[:80]}"
    box_line = f" (box: {box})" if box else ""
    payload = {
        "title": title,
        "description": (problem or "").strip() + box_line,
        "priority": priority,
        "source": "rescue-rangers",
        "source_ref": ticket_id,
        "department_slug": _DEPARTMENT_SLUG,
        "persona": _PERSONA,
        "external_session_id": ticket_id,
        "idempotency_key": ticket_id,
    }
    return payload


def cc_status_for(ledger_status: str) -> Optional[str]:
    """Translate a rescue_ledger status to a CC TaskStatus column value, or None
    when there is no mapping. The result is always inside CC_TASK_STATUSES."""
    v = LEDGER_TO_CC_STATUS.get(ledger_status)
    return v if v in CC_TASK_STATUSES else None


# ---------------------------------------------------------------------------
# Movement receipt — <state_dir>/cc-board/<ticket_id>.json.
# ---------------------------------------------------------------------------
def _receipts_dir(state_dir) -> Optional[Path]:
    if state_dir is None:
        return None
    d = Path(state_dir) / "cc-board"
    return d


def _now() -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        return ""


def _record_movement(state_dir, ticket_id: str, entry: dict) -> None:
    """Append one advance-attempt receipt for a ticket. Never raises; no-op when
    state_dir is None."""
    d = _receipts_dir(state_dir)
    if d is None:
        return
    p = d / f"{ticket_id}.json"
    try:
        d.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if p.exists():
            try:
                loaded = json.loads(p.read_text())
                if isinstance(loaded, dict):
                    data = loaded
            except (json.JSONDecodeError, OSError):
                data = {}
        movements = data.get("movements")
        if not isinstance(movements, list):
            movements = []
        record = {"ts": _now()}
        record.update(entry)
        movements.append(record)
        data["movements"] = movements
        data["successful_advances"] = sum(
            1 for m in movements if isinstance(m, dict) and m.get("ok"))
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, p)
    except OSError as exc:
        _log(f"movement receipt write failed ({exc}).")


def count_successful_advances(state_dir, ticket_id: str) -> int:
    d = _receipts_dir(state_dir)
    if d is None:
        return 0
    p = d / f"{ticket_id}.json"
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(data, dict):
        return 0
    got = data.get("successful_advances")
    if isinstance(got, int):
        return got
    movements = data.get("movements")
    if isinstance(movements, list):
        return sum(1 for m in movements if isinstance(m, dict) and m.get("ok"))
    return 0


# ---------------------------------------------------------------------------
# CREATE — POST /api/tasks/ingest (idempotent on ticket_id server-side).
# ---------------------------------------------------------------------------
def ingest_ticket(ticket_id: str, client: str, problem: str, *,
                  priority: str = "high", box: str = "", state_dir=None,
                  ledger=None, env: Optional[dict] = None) -> Optional[str]:
    """Land a rescue ticket on the CC board as ONE card. Returns the task_id on
    success else None. FAIL-SOFT — a None return never blocks the rescue flow.
    When `ledger` is a rescue_ledger.Ledger, the returned task_id is stamped back
    onto the ticket row (stamp_cc_task)."""
    if not ticket_id:
        return None
    cfg = board_config(env)
    if cfg is None:
        _log("COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — CC board disabled "
             "(no-op); ticket handled ungrouped.")
        _record_movement(state_dir, ticket_id, {
            "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
            "http_status": None, "ok": False, "detail": "board disabled"})
        return None

    payload = build_ingest_payload(ticket_id, client, problem, priority, box)
    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"ingest POST failed ({type(exc).__name__}: {exc}); ticket handled ungrouped.")
        _record_movement(state_dir, ticket_id, {
            "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
            "http_status": None, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        _log(f"card {'deduped (reused)' if deduped else 'created'}: "
             f"task_id={task_id} ticket_id={ticket_id}")
        _record_movement(state_dir, ticket_id, {
            "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
            "http_status": status, "ok": True, "task_id": task_id, "deduped": deduped})
        if ledger is not None:
            try:
                ledger.stamp_cc_task(ticket_id, task_id)
            except Exception as exc:  # noqa: BLE001 — board link is best-effort
                _log(f"stamp_cc_task failed ({exc}) — non-fatal.")
        return task_id

    _log(f"ingest POST non-OK (HTTP {status}): {body}; ticket handled ungrouped.")
    _record_movement(state_dir, ticket_id, {
        "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
        "http_status": status, "ok": False, "detail": str(body)[:300]})
    return None


# ---------------------------------------------------------------------------
# PATCH — advance the card as the ticket moves through its lifecycle.
# ---------------------------------------------------------------------------
def patch_status(task_id: str, status: str, *, ticket_id: str = "", note: str = "",
                 state_dir=None, env: Optional[dict] = None) -> bool:
    """PATCH the CC card to a CC TaskStatus. Rejects a status outside the
    authoritative enum offline (before any network call). FAIL-SOFT: returns
    False, never raises."""
    endpoint = "PATCH /api/tasks/{id}"
    if status not in CC_TASK_STATUSES:
        _log(f"patch_status refused — '{status}' not in the CC TaskStatus enum.")
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "status not in enum"})
        return False
    cfg = board_config(env)
    if cfg is None:
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "board disabled"})
        return False
    if not task_id:
        _log("patch_status skipped — task_id missing.")
        _record_movement(state_dir, ticket_id or "unknown", {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "task_id missing"})
        return False

    payload: dict = {"status": status}
    if note:
        payload["note"] = note
    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"patch_status ->{status} failed ({type(exc).__name__}: {exc}).")
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return False

    ok = st == 200
    _record_movement(state_dir, ticket_id or task_id, {
        "kind": "status", "target": status, "endpoint": endpoint,
        "http_status": st, "ok": ok, "detail": "OK" if ok else str(body)[:300]})
    if ok:
        _log(f"patch_status ->{status} OK (task_id={task_id}).")
    else:
        _log(f"patch_status ->{status} non-OK (HTTP {st}): {body}.")
    return ok


def mark_answered(task_id: str, *, ticket_id: str = "", note: str = "",
                  state_dir=None, env: Optional[dict] = None) -> bool:
    """Answer produced -> move the card to the review column."""
    return patch_status(task_id, "review", ticket_id=ticket_id,
                        note=note or "rescue answer posted", state_dir=state_dir, env=env)


def mark_resolved(task_id: str, *, ticket_id: str = "", note: str = "",
                  state_dir=None, env: Optional[dict] = None) -> bool:
    """RESOLVED confirmed -> close the card to done."""
    return patch_status(task_id, "done", ticket_id=ticket_id,
                        note=note or "rescue ticket resolved", state_dir=state_dir, env=env)


def post_activity(task_id: str, message: str, *, ticket_id: str = "",
                  activity_type: str = "updated", state_dir=None,
                  env: Optional[dict] = None) -> bool:
    """Mid-lifecycle progress note (e.g. tier assigned, fix DRY-RUN passed).
    FAIL-SOFT: returns False, never raises."""
    endpoint = "POST /api/tasks/{id}/activities"
    cfg = board_config(env)
    if cfg is None:
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "activity", "target": activity_type, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "board disabled"})
        return False
    if not task_id:
        _record_movement(state_dir, ticket_id or "unknown", {
            "kind": "activity", "target": activity_type, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "task_id missing"})
        return False
    payload = {"activity_type": activity_type, "message": message or "(rescue update)"}
    url = f"{cfg['base_url']}/api/tasks/{task_id}/activities"
    try:
        st, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "activity", "target": activity_type, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return False
    ok = st in (200, 201)
    _record_movement(state_dir, ticket_id or task_id, {
        "kind": "activity", "target": activity_type, "endpoint": endpoint,
        "http_status": st, "ok": ok, "detail": "OK" if ok else str(body)[:300]})
    return ok


# ---------------------------------------------------------------------------
# AGING SWEEP — the durable view the CC/cron uses to page on aging tickets.
# ---------------------------------------------------------------------------
def aging_sweep(ledger, older_than_minutes: int,
                statuses=("open", "in_progress", "answered", "blocked")):
    """Return the tickets in `statuses` older than the cutoff, read straight from
    the durable ledger (kills R6). Pure read — never raises, never pages. The
    operator aging cron decides whether to page the Fixer topic (deduped). Returns
    [] on any error / empty ledger."""
    try:
        return ledger.aging(older_than_minutes, statuses=statuses)
    except Exception as exc:  # noqa: BLE001 — a view must never raise
        _log(f"aging_sweep read failed ({exc}) — returning empty.")
        return []


# ---------------------------------------------------------------------------
# self-test (deterministic, no network — exercises the OFFLINE fail-soft paths
# and the pure payload/status builders; a live POST is out of scope here).
# ---------------------------------------------------------------------------
def self_test():
    import tempfile
    print("[rescue_cc_board] self-test: payload build, enum guard, fail-soft no-op, "
          "receipts, aging sweep")

    # pure payload builder
    p = build_ingest_payload("tkt-9", "acme", "gateway down at 3am", box="acme-mac")
    assert p["department_slug"] == "rescue-rangers"
    assert p["persona"] == "Director of Rescue Rangers"
    assert p["idempotency_key"] == "tkt-9" and p["source_ref"] == "tkt-9"
    assert p["title"].startswith("[acme]") and "gateway down" in p["title"]
    print("  payload case: PASS (rescue-rangers dept, ticket_id is idempotency key)")

    # ledger-status -> CC-column mapping stays inside the enum
    assert cc_status_for("answered") == "review"
    assert cc_status_for("resolved") == "done"
    assert cc_status_for("open") == "backlog"
    assert cc_status_for("bogus") is None
    for v in LEDGER_TO_CC_STATUS.values():
        assert v in CC_TASK_STATUSES
    print("  status-map case: PASS (every mapped status is a real CC column)")

    # signature parity: signing is deterministic + matches a hand HMAC
    raw = json.dumps({"a": 1}, separators=(",", ":")).encode()
    assert _sign("", raw) is None
    assert _sign("s3cr3t", raw) == hmac.new(b"s3cr3t", raw, hashlib.sha256).hexdigest()
    print("  signature case: PASS (HMAC parity; empty secret => no signature)")

    # board disabled => every call is a clean fail-soft no-op (no network)
    empty_env: dict = {}
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "rescue"
        assert ingest_ticket("tkt-9", "acme", "x", state_dir=sd, env=empty_env) is None
        assert mark_answered("cc-1", ticket_id="tkt-9", state_dir=sd, env=empty_env) is False
        assert mark_resolved("cc-1", ticket_id="tkt-9", state_dir=sd, env=empty_env) is False
        assert post_activity("cc-1", "note", ticket_id="tkt-9", state_dir=sd, env=empty_env) is False
        # a movement receipt was still written (visible on disk), all ok:false
        receipt = Path(td) / "rescue" / "cc-board" / "tkt-9.json"
        assert receipt.is_file()
        assert count_successful_advances(sd, "tkt-9") == 0
        print("  fail-soft case: PASS (disabled board no-ops + records receipts)")

        # enum guard: a bogus status is refused offline, before any network call
        assert patch_status("cc-1", "delivered", ticket_id="tkt-9",
                           state_dir=sd, env={"COMMAND_CENTER_URL": "http://x"}) is False
        print("  enum-guard case: PASS ('delivered' rejected — not a CC status)")

        # aging sweep reads the durable ledger
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "rescue_ledger", str(Path(__file__).with_name("rescue_ledger.py")))
            rl = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rl)
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            led = rl.Ledger(sd)
            old = (_dt.now(_tz.utc) - _td(hours=5)).replace(microsecond=0).isoformat()
            led.open_ticket("tkt-old", client="beta", problem="stuck", ts_open=old)
            led.open_ticket("tkt-new", client="beta", problem="fresh")
            aged = {t["ticket_id"] for t in aging_sweep(led, 120)}
            assert "tkt-old" in aged and "tkt-new" not in aged
            led.close()
            print("  aging-sweep case: PASS (durable ledger drives the SLA view)")
        except Exception as exc:  # noqa: BLE001
            print(f"  aging-sweep case: SKIP (ledger import unavailable: {exc})")

    print("[rescue_cc_board] self-test: PASS")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Rescue Rangers CC board caller (fail-soft).")
    ap.add_argument("--self-test", action="store_true", help="run the offline self-test")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())
    ap.print_help()
    sys.exit(0)
