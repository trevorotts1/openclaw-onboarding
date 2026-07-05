#!/usr/bin/env python3
"""
cc_board.py — Presentations dept PRODUCER-SIDE Command Center board caller (FAIL-SOFT).

Port of the proven Skill-48 cc_board.py pattern, adapted to the presentations
pipeline endpoints from SOP-00-Owner-Task-Routing. Lands a deck build on the CC
Kanban board as ONE task and advances that task through phase boundaries as the
pipeline progresses.

NON-NEGOTIABLE DESIGN RULES (mirrored verbatim from Skill-48)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the
    deck build CONTINUES. Boarding the run is a convenience, never a gate. The
    ONLY thing that actually fails a deck job for "not on the board" is the
    offline _chk_cc_registered() check (AF-CC-UNREGISTERED) in build_deck.py —
    and that check is satisfied by a LOGGED ATTEMPT even when transport failed
    (fail-soft on transport; fail-CLOSED only on never-attempted). So every
    public function here returns a value (task_id / bool) and NEVER raises.

  * AUTH PARITY with the CC endpoint:
      - ``Authorization: Bearer <CC_API_TOKEN>``  — global middleware layer.
        No-op when CC_API_TOKEN / MC_API_TOKEN is unset.
      - ``x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` hex —
        per-route layer copied verbatim from /api/tasks/ingest. Endpoint
        no-ops the check when WEBHOOK_SECRET is unset (dev mode). We sign the
        EXACT bytes we send, so a configured secret matches byte-for-byte.

  * STDLIB ONLY (urllib) — zero third-party deps.

  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => fail-soft no-op.
      COMMAND_CENTER_URL   base URL of the Command Center (preferred name).
      MISSION_CONTROL_URL  fallback alias; accepted when COMMAND_CENTER_URL absent.
      CC_API_TOKEN         long-lived bearer (middleware layer). Optional.
      MC_API_TOKEN         alias for CC_API_TOKEN. Optional.
      WEBHOOK_SECRET       HMAC secret (per-route layer). Optional.
      CC_WEBHOOK_SECRET    alias for WEBHOOK_SECRET. Optional.
      CC_BOARD_TIMEOUT     per-request timeout seconds (default 8).

REQUEST CONTRACT (matched to the live /api/tasks/ingest endpoint):

  CREATE   POST {base}/api/tasks/ingest
    body:  {title, description, priority, source, source_ref,
            department_slug:"presentations", persona:"Director of Presentations",
            external_session_id, idempotency_key:sha256(source_ref+title)}
    return: {ok, task_id, deduped}

  PATCH    PATCH {base}/api/tasks/{task_id}   (task-level STATUS change)
    body:  {phase_id, status, note?, process_certificate_sha?}
    return: 200 -> {task}
    status vocabulary is the authoritative CC TaskStatus enum (UpdateTaskSchema in
    src/lib/validation.ts): backlog | inbox | planning | in_progress | assigned |
    review | testing | blocked | pending_dispatch | done. There is NO 'delivered'
    status — a COMPLETED deck closes with status='done' + process_certificate_sha
    (the minted PROCESS-CERTIFICATE sha); the word "delivered" belongs in the note.

  ACTIVITY POST {base}/api/tasks/{task_id}/activities   (mid-run phase PROGRESS)
    body:  {activity_type:"updated", message}
    return: 201 -> {activity}
    Mid-run phase boundaries (P4-RENDER complete, P8-ASSEMBLE complete) are logged
    as ACTIVITIES, never as task-level status changes: a mid-run status='done'
    422s the presentations cert done-gate (no PROCESS-CERTIFICATE exists yet) and
    would wrongly close a non-presentation card.

MOVEMENT RECEIPT — every advance ATTEMPT (status change or activity post) plus its
HTTP status / body is appended to working/checkpoints/cc-board.json (mirroring the
campaign skills' mc-board.json receipt) so a failed advance is VISIBLE on disk.
Recording is fail-soft; it never raises and never blocks the deck build.

The task_id AND cc_register_attempted=True are written into
``working/checkpoints/process_manifest.json`` so the offline AF-CC-UNREGISTERED
check in build_deck._chk_cc_registered passes whether or not the live POST
succeeded:
  - PASS  when cc_task_id is set (successful registration).
  - PASS  when cc_register_attempted is True (transport failed, attempt logged).
  - FAIL  when neither field exists (this module was never called for this run).

PUBLIC API
  ingest_deck_task(run_dir, deck_slug, title, description, priority="medium")
      -> task_id str | None
  patch_phase(run_dir, task_id, phase_id, status, note="") -> bool
      # task-level STATUS change; on status='done' auto-attaches the cert sha.
  post_activity(run_dir, task_id, phase_id, note, activity_type="updated") -> bool
      # mid-run phase PROGRESS via the /activities endpoint (NOT a status change).
  stamp_task_id(run_dir, task_id) -> bool
  count_successful_advances(run_dir) -> int
  assert_min_one_advance(run_dir) -> bool
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
_DEPARTMENT_SLUG = "presentations"
_PERSONA = "Director of Presentations"

# Authoritative Command Center TaskStatus enum — the 10 values of UpdateTaskSchema
# in the CC repo src/lib/validation.ts. Kept here as the single source of truth on
# the producer side; the contract test (test_cc_contract.py) fails if this drifts
# from the CC enum or if build_deck.py / this module emit a status outside it.
# NB: there is NO 'delivered' status — a completed deck closes with 'done'.
CC_TASK_STATUSES = frozenset({
    "backlog",
    "inbox",
    "planning",
    "in_progress",
    "assigned",
    "review",
    "testing",
    "blocked",
    "pending_dispatch",
    "done",
})


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled,
    a clean no-op) when neither COMMAND_CENTER_URL nor MISSION_CONTROL_URL is
    set — the graceful-degradation contract. Never raises."""
    env = env if env is not None else os.environ
    base = (
        env.get("COMMAND_CENTER_URL") or env.get("MISSION_CONTROL_URL") or ""
    ).strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    return {
        "base_url": base,
        "token": (
            env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or ""
        ).strip(),
        "secret": (
            env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or ""
        ).strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    """Single, greppable degrade line. Board failures are logged, not silent,
    and never fatal."""
    print(f"[cc_board/presentations] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex — byte-
    for-byte parity with verifyWebhookSignature() in the route handlers. None
    when no secret (the endpoint also no-ops in that case)."""
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
    except urllib.error.HTTPError as exc:  # 4xx/5xx — read the body for context
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# process_manifest.json helpers — atomic read / merge / write.
# ---------------------------------------------------------------------------
def _manifest_path(run_dir) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "process_manifest.json"


def _read_manifest(run_dir) -> dict:
    """Read process_manifest.json; return {} on any error. Never raises."""
    p = _manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _merge_manifest(run_dir, updates: dict) -> bool:
    """Merge `updates` into process_manifest.json atomically.
    Returns True on success, False on error. Never raises."""
    p = _manifest_path(run_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        manifest = _read_manifest(run_dir)
        manifest.update(updates)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2))
        os.replace(tmp, p)
        return True
    except OSError as exc:
        _log(f"manifest write failed ({exc}).")
        return False


# ---------------------------------------------------------------------------
# MOVEMENT RECEIPT — working/checkpoints/cc-board.json. Mirrors the campaign
# skills' mc-board.json pattern: every board advance ATTEMPT (a task-level status
# change or an activity post) is appended with its HTTP status/body so a failed
# advance is VISIBLE on disk. successful_advances is recomputed on every append.
# Recording is fail-soft — it never raises and never blocks the deck build.
# ---------------------------------------------------------------------------
def _movements_path(run_dir) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "cc-board.json"


def _now() -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001 — a clock hiccup must not break a receipt
        return ""


def _record_movement(run_dir, entry: dict) -> None:
    """Append one advance-attempt receipt to working/checkpoints/cc-board.json.
    Never raises. A no-op when run_dir is None."""
    if run_dir is None:
        return
    p = _movements_path(run_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
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
            1 for m in movements if isinstance(m, dict) and m.get("ok")
        )
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, p)
    except OSError as exc:
        _log(f"movement receipt write failed ({exc}).")


def count_successful_advances(run_dir) -> int:
    """Number of board advances that returned OK for this run (0 when the receipt
    is absent / unreadable / board disabled). Never raises."""
    if run_dir is None:
        return 0
    p = _movements_path(run_dir)
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


def assert_min_one_advance(run_dir) -> bool:
    """Lightweight gate: a completed run should have recorded >= 1 SUCCESSFUL board
    advance. Returns True/False; NEVER raises and never blocks — the caller decides
    whether to warn (a disabled board legitimately records none)."""
    return count_successful_advances(run_dir) >= 1


# ---------------------------------------------------------------------------
# CREATE — POST /api/tasks/ingest (idempotent on idempotency_key server-side)
# ---------------------------------------------------------------------------
def ingest_deck_task(
    run_dir,
    deck_slug: str,
    title: str,
    description: str,
    priority: str = "medium",
    env: Optional[dict] = None,
) -> Optional[str]:
    """Ingest (or idempotently re-fetch) a deck task on the CC board.

    Always stamps cc_register_attempted=True in process_manifest.json BEFORE
    the HTTP call so a transport crash or URL-absent no-op is treated as
    fail-soft (not never-attempted) by build_deck._chk_cc_registered.

    Returns the task_id string on success, else None. FAIL-SOFT — a None
    return never blocks the deck build; the offline gate is satisfied by the
    cc_register_attempted flag.

    Idempotency key is sha256(source_ref + title) — deterministic per deck."""
    if run_dir is None:
        return None

    # Mark the attempt FIRST — before any network call — so a crash looks
    # like transport failure (soft) rather than never-attempted (hard fail).
    if not _merge_manifest(run_dir, {"cc_register_attempted": True}):
        _log("could not stamp cc_register_attempted; continuing anyway.")

    cfg = board_config(env)
    if cfg is None:
        _log(
            "COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — CC board disabled "
            "(no-op); run continues ungrouped. cc_register_attempted=True logged."
        )
        return None

    source_ref = deck_slug or "deck"
    idem_input = f"{source_ref}{title}".encode("utf-8")
    idempotency_key = hashlib.sha256(idem_input).hexdigest()

    payload: dict = {
        "title": title,
        "description": description,
        "priority": priority,
        "source": "build_deck",
        "source_ref": source_ref,
        "department_slug": _DEPARTMENT_SLUG,
        "persona": _PERSONA,
        "external_session_id": source_ref,
        "idempotency_key": idempotency_key,
    }

    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(
            f"ingest POST failed ({type(exc).__name__}: {exc}); "
            "run continues ungrouped. cc_register_attempted=True already logged."
        )
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        _log(
            f"task {'deduped (reused)' if deduped else 'created'}: "
            f"task_id={task_id} deck_slug={deck_slug}"
        )
        stamp_task_id(run_dir, task_id)
        return task_id

    _log(
        f"ingest POST non-OK (HTTP {status}): {body}; "
        "run continues ungrouped. cc_register_attempted=True already logged."
    )
    return None


# ---------------------------------------------------------------------------
# PATCH — advance the task card at a phase boundary.
# ---------------------------------------------------------------------------
def patch_phase(
    run_dir,
    task_id: str,
    phase_id: str,
    status: str,
    note: str = "",
    env: Optional[dict] = None,
) -> bool:
    """PATCH the CC task card to a task-level STATUS at a phase boundary.

    Use this for real status transitions only: the P4-RENDER START
    (backlog->in_progress) and the TERMINAL close of a completed deck
    (status='done'). Mid-run phase PROGRESS must go through post_activity()
    instead — a mid-run status='done' 422s the presentations cert done-gate.

    On status 'done': automatically reads delivery/*-FINAL/PROCESS-CERTIFICATE.json
    (the sha prove-deck.py minted) and includes it as process_certificate_sha in the
    PATCH body, satisfying the CC presentations no-skip done-gate. The word
    "delivered" is NOT a status — pass it in `note`, never as `status`.

    Every attempt (disabled board, missing id, transport error, non-200, 200) is
    recorded to the movement receipt (working/checkpoints/cc-board.json) so a failed
    advance is visible. FAIL-SOFT: returns False (never raises); the deck build is
    never blocked by this function."""
    endpoint = "PATCH /api/tasks/{id}"
    cfg = board_config(env)
    if cfg is None:
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "status", "target": status,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL unset)",
        })
        return False
    if not task_id:
        _log("patch_phase skipped — task_id missing.")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "status", "target": status,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "task_id missing",
        })
        return False

    payload: dict = {
        "phase_id": phase_id,
        "status": status,
    }
    if note:
        payload["note"] = note

    # On the terminal 'done' close: attach the process certificate SHA if
    # prove-deck.py has written the PROCESS-CERTIFICATE.json (Fix 2a / Fix 2b).
    if status == "done" and run_dir is not None:
        cert_sha = _read_certificate_sha(run_dir)
        if cert_sha:
            payload["process_certificate_sha"] = cert_sha
            _log(f"patch_phase attaching process_certificate_sha={cert_sha[:16]}...")

    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"patch_phase {phase_id}->{status} failed ({type(exc).__name__}: {exc}).")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "status", "target": status,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        })
        return False

    ok = st == 200
    _record_movement(run_dir, {
        "phase_id": phase_id, "kind": "status", "target": status,
        "endpoint": endpoint, "http_status": st, "ok": ok,
        "detail": "OK" if ok else str(body)[:300],
    })
    if ok:
        _log(f"patch_phase {phase_id}->{status} OK (task_id={task_id}).")
        return True

    _log(f"patch_phase {phase_id}->{status} non-OK (HTTP {st}): {body}.")
    return False


def post_activity(
    run_dir,
    task_id: str,
    phase_id: str,
    note: str,
    activity_type: str = "updated",
    env: Optional[dict] = None,
) -> bool:
    """POST a mid-run phase-PROGRESS activity to /api/tasks/{task_id}/activities.

    This is how P4-RENDER-complete and P8-ASSEMBLE-complete are recorded — as
    ACTIVITIES, NOT task-level status changes. A mid-run status='done' would 422 the
    presentations cert done-gate (no PROCESS-CERTIFICATE exists mid-run) and would
    wrongly close a non-presentation card; an activity carries the phase in its
    message without touching the card's column.

    Body matches the CC CreateActivitySchema: activity_type in
    {spawned,updated,completed,file_created,status_changed} + a non-empty message
    (the phase id is embedded in the message). Every attempt is recorded to the
    movement receipt. FAIL-SOFT: returns False (never raises)."""
    endpoint = "POST /api/tasks/{id}/activities"
    cfg = board_config(env)
    if cfg is None:
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "activity", "target": activity_type,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "board disabled (COMMAND_CENTER_URL/MISSION_CONTROL_URL unset)",
        })
        return False
    if not task_id:
        _log("post_activity skipped — task_id missing.")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "activity", "target": activity_type,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": "task_id missing",
        })
        return False

    message = (f"[{phase_id}] {note}".strip() if note else f"[{phase_id}]")
    payload: dict = {"activity_type": activity_type, "message": message}

    url = f"{cfg['base_url']}/api/tasks/{task_id}/activities"
    try:
        st, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"post_activity {phase_id} failed ({type(exc).__name__}: {exc}).")
        _record_movement(run_dir, {
            "phase_id": phase_id, "kind": "activity", "target": activity_type,
            "endpoint": endpoint, "http_status": None, "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        })
        return False

    ok = st in (200, 201)
    _record_movement(run_dir, {
        "phase_id": phase_id, "kind": "activity", "target": activity_type,
        "endpoint": endpoint, "http_status": st, "ok": ok,
        "detail": "OK" if ok else str(body)[:300],
    })
    if ok:
        _log(f"post_activity {phase_id} OK (task_id={task_id}).")
        return True

    _log(f"post_activity {phase_id} non-OK (HTTP {st}): {body}.")
    return False


def _read_certificate_sha(run_dir) -> Optional[str]:
    """Glob delivery/*-FINAL/PROCESS-CERTIFICATE.json and return the first
    certificate_sha found, or None. Never raises."""
    try:
        delivery = Path(run_dir) / "delivery"
        if not delivery.is_dir():
            return None
        for cert_path in delivery.glob("*-FINAL/PROCESS-CERTIFICATE.json"):
            try:
                data = json.loads(cert_path.read_text())
                if isinstance(data, dict) and data.get("certificate_sha"):
                    return str(data["certificate_sha"])
            except (json.JSONDecodeError, OSError):
                continue
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Receipt stamping — write task_id into process_manifest.json so the offline
# AF-CC-UNREGISTERED check passes (degrade-to-ungrouped is logged, not
# silent). Mirrors Skill-48's stamp_campaign_id pattern at cc_board.py:370-401.
# ---------------------------------------------------------------------------
def stamp_task_id(run_dir, task_id: str) -> bool:
    """Merge cc_task_id into process_manifest.json without disturbing other
    fields. Atomic replace. Returns True on success. Never raises."""
    if not task_id or run_dir is None:
        return False
    ok = _merge_manifest(run_dir, {"cc_task_id": task_id})
    if not ok:
        _log(f"stamp_task_id failed for task_id={task_id}.")
    return ok


# ---------------------------------------------------------------------------
# RECONCILE — replay the last failed board advance (FIX-PRES-08b).
# ---------------------------------------------------------------------------
def reconcile(run_dir) -> int:
    """Replay the LAST outstanding failed board advance from the movement receipt
    (working/checkpoints/cc-board.json).

    WHY: a transport-failed TERMINAL close (run_signature_deck._board_close_delivery
    is fail-soft) otherwise leaves a delivered deck's card stuck at in_progress
    forever, with no retry. This reads cc_task_id from the manifest and the last
    ok:false STATUS movement that was NOT superseded by a later OK, and re-issues
    that patch_phase (which, for status='done', re-attaches the process_certificate_sha).

    Returns 0 on success or a clean no-op (nothing to reconcile / board consistent /
    board disabled), 1 when a replay was attempted but still failed. FAIL-SOFT:
    never raises — the board is a view, never a gate."""
    try:
        tid = _read_manifest(run_dir).get("cc_task_id")
        if not tid:
            _log("reconcile: no cc_task_id in manifest — nothing to reconcile.")
            return 0
        p = _movements_path(run_dir)
        if not p.exists():
            _log("reconcile: no movement receipt — nothing to reconcile.")
            return 0
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            _log("reconcile: movement receipt unreadable — nothing to reconcile.")
            return 0
        movements = data.get("movements") if isinstance(data, dict) else None
        if not isinstance(movements, list) or not movements:
            _log("reconcile: empty movement receipt — nothing to reconcile.")
            return 0
        # Walk in order: a later OK status advance supersedes an earlier failure.
        last_failed = None
        for m in movements:
            if not isinstance(m, dict) or m.get("kind") != "status":
                continue
            if m.get("ok"):
                last_failed = None
            else:
                last_failed = m
        if last_failed is None:
            _log("reconcile: no outstanding failed status advance — board is consistent.")
            return 0
        phase_id = last_failed.get("phase_id")
        status = last_failed.get("target") or last_failed.get("status")
        if not phase_id or not status:
            _log("reconcile: last failed movement missing phase_id/status — cannot replay.")
            return 0
        _log(f"reconcile: replaying failed advance {phase_id}->{status} (task_id={tid}).")
        ok = patch_phase(
            run_dir, str(tid), str(phase_id), str(status),
            note="reconcile: replay of a transport-failed advance",
        )
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001 — reconcile is best-effort, never a gate
        _log(f"reconcile raised ({exc}) — non-fatal.")
        return 0


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser(
        description="Presentations Command Center board helper (fail-soft).")
    _ap.add_argument(
        "--reconcile", metavar="RUN_DIR",
        help="Replay the last failed board advance from RUN_DIR's movement receipt "
             "(FIX-PRES-08b). Exit 0 = success/clean no-op, 1 = replay still failed.")
    _args = _ap.parse_args()
    if _args.reconcile:
        sys.exit(reconcile(_args.reconcile))
    _ap.print_help()
    sys.exit(0)
