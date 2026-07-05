#!/usr/bin/env python3
"""mc_board.py — SHARED, fail-soft mc-route Command Center board card (productized skills).

One canonical helper, dropped byte-for-byte into each productized campaign skill
(49-signature-funnel, 50-email-engine, 53-book-writer, 55-product-bio,
56-sales-page-assets, 57-social-media-in-a-box). It gives every run consistent
Command Center board visibility: it lands ONE Kanban card per run via the generic
mc-route task endpoints and advances that card as the run progresses:

    run begin      -> open card (POST /api/tasks/ingest) + move in_progress
    run delivered  -> move done   (PATCH /api/tasks/{task_id})

It is a direct port of the proven Skill-48 (ad_director/cc_board) and presentations
(build_deck/_board_patch_phase, v17.0.6) pattern, generalized so any skill supplies
its own department / persona / source.

NON-NEGOTIABLE DESIGN RULES (mirrored verbatim from the reference)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP error,
    a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the run
    CONTINUES. Boarding the run is a convenience, NEVER a gate. Every public
    function returns a value (task_id / bool) and NEVER raises.

  * NO-OP WHEN DISABLED. With no COMMAND_CENTER_URL / MISSION_CONTROL_URL the whole
    module is a clean no-op that writes NOTHING into the run dir — a run on a box
    without a Command Center is byte-for-byte identical to one without this module.

  * RECEIPT-BACKED (only when the board is enabled). The task_id is written into
    <run_dir>/working/checkpoints/mc-board.json so a later advance can recover it
    and repeated opens are idempotent.

  * AUTH PARITY with the CC endpoint (same as cc_board.py):
      - Authorization: Bearer <CC_API_TOKEN|MC_API_TOKEN>   (global middleware; no-op if unset)
      - x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (per-route; no-op if unset)
    We sign the EXACT bytes we send, so a configured secret matches byte-for-byte.

  * STDLIB ONLY (urllib) — zero third-party deps. It calls NO LLM and NO delivery
    provider; the Command Center is internal ops infrastructure, contacted best-effort.

Config (env; absent base URL => board disabled, clean no-op):
  COMMAND_CENTER_URL / MISSION_CONTROL_URL   base URL of the Command Center (either name)
  CC_API_TOKEN / MC_API_TOKEN                 long-lived bearer (optional)
  WEBHOOK_SECRET / CC_WEBHOOK_SECRET          HMAC secret (optional)
  CC_BOARD_TIMEOUT                            per-request timeout seconds (default 8)

PUBLIC API
  card_open(run_dir, *, slug, title, department, persona="", source="",
            description="", priority="medium", env=None)         -> task_id str | None
  card_advance(run_dir, task_id=None, *, phase_id, status, note="", env=None) -> bool
  begin_run(run_dir, *, slug, title, department, persona="", source="",
            description="")                                       -> task_id str | None  (never raises)
  complete_run(run_dir, task_id=None, *, phase_id="deliver", note="") -> bool            (never raises)
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


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled, a
    clean no-op) when neither COMMAND_CENTER_URL nor MISSION_CONTROL_URL is set.
    Never raises."""
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
        "token": (env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    """Single, greppable degrade line. Board failures are logged, not silent,
    and never fatal."""
    print(f"[mc_board] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex — byte-for-
    byte parity with the route handler. None when no secret (endpoint no-ops too)."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: dict, cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None). Raises
    only urllib/OS errors, which the public callers catch (fail-soft)."""
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
# Receipt — atomic read / merge under <run_dir>/<receipt_subdir>/mc-board.json.
# The subdir is PARAMETERIZED (default working/checkpoints, the shared productized
# layout) so a skill whose documented run layout differs can pin its own — Skill 53
# passes ("run", "checkpoints") to keep the board receipt inside the SAME
# run/checkpoints/ dir that holds the front-door nonce. Only written when the board
# is ENABLED (a disabled run touches nothing).
# ---------------------------------------------------------------------------
_DEFAULT_RECEIPT_SUBDIR = ("working", "checkpoints")


def _receipt_path(run_dir, receipt_subdir=None) -> Path:
    parts = receipt_subdir or _DEFAULT_RECEIPT_SUBDIR
    return Path(run_dir).joinpath(*parts) / "mc-board.json"


def _read_receipt(run_dir, receipt_subdir=None) -> dict:
    p = _receipt_path(run_dir, receipt_subdir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _merge_receipt(run_dir, updates: dict, receipt_subdir=None) -> bool:
    """Merge `updates` into the receipt atomically. Never raises."""
    p = _receipt_path(run_dir, receipt_subdir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        receipt = _read_receipt(run_dir)
        receipt.update(updates)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(receipt, indent=2))
        os.replace(tmp, p)
        return True
    except OSError as exc:
        _log(f"receipt write failed ({exc}).")
        return False


# ---------------------------------------------------------------------------
# CREATE — POST /api/tasks/ingest (idempotent on idempotency_key server-side).
# ---------------------------------------------------------------------------
def card_open(
    run_dir,
    *,
    slug: str,
    title: str,
    department: str,
    persona: str = "",
    source: str = "",
    description: str = "",
    priority: str = "medium",
    env: Optional[dict] = None,
    receipt_subdir=None,
) -> Optional[str]:
    """Open (or idempotently re-fetch) this run's board card. Returns the task_id
    string on success, else None. FAIL-SOFT — a None return never blocks the run.

    A disabled board (no COMMAND_CENTER_URL/MISSION_CONTROL_URL) is a clean no-op
    that writes NOTHING. When enabled, the task_id is stamped into the receipt so a
    later advance can recover it and a re-open reuses it (no duplicate card).
    `receipt_subdir` pins the receipt location (default working/checkpoints)."""
    if run_dir is None:
        return None
    cfg = board_config(env)
    if cfg is None:
        _log("COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — board disabled (no-op); run continues.")
        return None

    # Idempotent: reuse a task_id already recorded for this run dir.
    existing = _read_receipt(run_dir, receipt_subdir).get("mc_task_id")
    if existing:
        return str(existing)

    # Mark the attempt (receipt-backed) BEFORE the network call.
    _merge_receipt(run_dir, {"mc_register_attempted": True, "slug": slug}, receipt_subdir)

    source_ref = slug or source or "run"
    idem_input = f"{source_ref}{title}".encode("utf-8")
    idempotency_key = hashlib.sha256(idem_input).hexdigest()

    payload: dict = {
        "title": title,
        "description": description or title,
        "priority": priority,
        "source": source or "productized-skill",
        "source_ref": source_ref,
        "department_slug": department,
        "external_session_id": source_ref,
        "idempotency_key": idempotency_key,
    }
    if persona:
        payload["persona"] = persona

    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"ingest POST failed ({type(exc).__name__}: {exc}); run continues ungrouped.")
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        _log(f"card {'deduped (reused)' if deduped else 'created'}: task_id={task_id} slug={slug}")
        _merge_receipt(run_dir, {"mc_task_id": task_id}, receipt_subdir)
        return task_id

    _log(f"ingest POST non-OK (HTTP {status}): {body}; run continues ungrouped.")
    return None


# ---------------------------------------------------------------------------
# ADVANCE — PATCH /api/tasks/{task_id} (one transition).
# ---------------------------------------------------------------------------
def card_advance(
    run_dir,
    task_id: Optional[str] = None,
    *,
    phase_id: str,
    status: str,
    note: str = "",
    env: Optional[dict] = None,
    receipt_subdir=None,
) -> bool:
    """Advance this run's card to (phase_id, status). FAIL-SOFT: returns False
    (never raises) on any board problem; the run is never blocked. task_id is
    recovered from the receipt when not supplied. Disabled board => no-op False."""
    cfg = board_config(env)
    if cfg is None:
        return False
    tid = task_id or _read_receipt(run_dir, receipt_subdir).get("mc_task_id")
    if not tid:
        _log(f"advance {phase_id}->{status} skipped — no task_id (card never opened).")
        return False

    payload: dict = {"phase_id": phase_id, "status": status}
    if note:
        payload["note"] = note

    url = f"{cfg['base_url']}/api/tasks/{tid}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"advance {phase_id}->{status} failed ({type(exc).__name__}: {exc}).")
        return False
    if st == 200:
        _log(f"advance {phase_id}->{status} OK (task_id={tid}).")
        return True
    _log(f"advance {phase_id}->{status} non-OK (HTTP {st}): {body}.")
    return False


# ---------------------------------------------------------------------------
# Convenience wrappers — the ONE-LINE seam each orchestrator wires in. These are
# GUARANTEED non-raising (belt-and-suspenders on top of the fail-soft internals),
# so a caller can invoke them without its own try/except and still never crash.
# ---------------------------------------------------------------------------
def begin_run(
    run_dir,
    *,
    slug: str,
    title: str,
    department: str,
    persona: str = "",
    source: str = "",
    description: str = "",
    receipt_subdir=None,
) -> Optional[str]:
    """Open the run's card and move it to in_progress. Returns the task_id or None.
    Never raises — the board is a view, never a gate."""
    try:
        tid = card_open(
            run_dir, slug=slug, title=title, department=department,
            persona=persona, source=source, description=description,
            receipt_subdir=receipt_subdir,
        )
        if tid:
            card_advance(run_dir, tid, phase_id="run", status="in_progress",
                         note="run started", receipt_subdir=receipt_subdir)
        return tid
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        _log(f"begin_run best-effort skip ({type(exc).__name__}: {exc}).")
        return None


def complete_run(run_dir, task_id: Optional[str] = None, *, phase_id: str = "deliver",
                 note: str = "", receipt_subdir=None) -> bool:
    """Move the run's card to done. Recovers the task_id from the receipt when not
    supplied. Never raises — the board is a view, never a gate."""
    try:
        return card_advance(run_dir, task_id, phase_id=phase_id, status="done",
                            note=note or "run delivered", receipt_subdir=receipt_subdir)
    except Exception as exc:  # noqa: BLE001
        _log(f"complete_run best-effort skip ({type(exc).__name__}: {exc}).")
        return False
