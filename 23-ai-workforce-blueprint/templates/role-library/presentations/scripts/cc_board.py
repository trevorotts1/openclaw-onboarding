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

  PATCH    PATCH {base}/api/tasks/{task_id}
    body:  {phase_id, status, note?, process_certificate_sha?}
    return: 200 -> {task}

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
  stamp_task_id(run_dir, task_id) -> bool
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

_DEFAULT_TIMEOUT = 8
_DEPARTMENT_SLUG = "presentations"
_PERSONA = "Director of Presentations"


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
    """PATCH the CC task card for a phase boundary.

    On status 'done' or 'delivered': automatically reads
    delivery/*-FINAL/PROCESS-CERTIFICATE.json (if it exists in run_dir) and
    includes its certificate_sha as process_certificate_sha in the PATCH body,
    closing the CC done-gate contract (Fix 2b from the spec).

    FAIL-SOFT: returns False (never raises) on any board problem; the deck
    build is never blocked by this function."""
    cfg = board_config(env)
    if cfg is None:
        return False
    if not task_id:
        _log("patch_phase skipped — task_id missing.")
        return False

    payload: dict = {
        "phase_id": phase_id,
        "status": status,
    }
    if note:
        payload["note"] = note

    # On done/delivered: attach the process certificate SHA if prove-deck.py
    # has written the PROCESS-CERTIFICATE.json (Fix 2a / Fix 2b).
    if status in ("done", "delivered") and run_dir is not None:
        cert_sha = _read_certificate_sha(run_dir)
        if cert_sha:
            payload["process_certificate_sha"] = cert_sha
            _log(f"patch_phase attaching process_certificate_sha={cert_sha[:16]}...")

    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"patch_phase {phase_id}->{status} failed ({type(exc).__name__}: {exc}).")
        return False

    if st == 200:
        _log(f"patch_phase {phase_id}->{status} OK (task_id={task_id}).")
        return True

    _log(f"patch_phase {phase_id}->{status} non-OK (HTTP {st}): {body}.")
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
