#!/usr/bin/env python3
"""mc_board.py — SHARED, fail-soft mc-route Command Center board card (productized skills).

One canonical helper, dropped byte-for-byte into each productized campaign skill
(49-signature-funnel, 50-email-engine, 53-book-writer, 55-product-bio,
56-sales-page-assets, 57-social-media-in-a-box). It gives every run consistent
Command Center board visibility: it lands ONE Kanban card per run via the generic
mc-route task endpoints and advances that card as the run progresses:

    run begin      -> open card (POST /api/tasks/ingest) + move backlog->in_progress
    per phase      -> card_advance(phase_id, "in_progress", note)   (heartbeat)
    run delivered  -> move ...->review   (NEVER 'done' — see THE BOARD CONTRACT)

THE BOARD CONTRACT (the review-skip root fix, FIX-XC-01a)
  A PRODUCER never posts 'done'. The Command Center lifecycle is
  `in_progress -> review -> done`; only the independent QC sweep (the auto-scorer,
  PASS >= 8.5) may promote a card from `review` to `done`. So the terminal move a
  run makes is to `review` ("certified — awaiting QC promotion"), with the
  deliverable link registered on the card. `card_advance(..., status="done")` is
  hard-blocked here exactly as Skill 6's `cc_board.update_status` and Skill 41's
  `cc_move_task` block it, so no code path can skip the QC column. This mirrors the
  server's own LEGAL_TRANSITIONS map (`48-facebook-ad-generator/scripts/cc_board.py`)
  and the Done-Gate in `32-command-center-setup/scripts/move-task.py` (a card must
  pass through `review` before `done`, and only a passing independent sign-off
  promotes it).

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

  * LEGAL-PATH WALKING. A move to a target status walks the shortest legal path
    from the card's CURRENT status (fetched via GET) over the CC LEGAL_TRANSITIONS
    map, rather than issuing an illegal direct jump — e.g. backlog->in_progress
    ->review. The server is always the final authority; this only avoids obviously
    illegal transitions client-side and keeps board state honest. Verification of
    board state is ALWAYS by querying CC rows (never file mtime — WAL lag).

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
  CC_STATUS_PATH_TEMPLATE                     status-write path with a literal '{id}'
                                              (default '/api/tasks/{id}'; route parity
                                              with Skill 6, e.g. '/api/tasks/{id}/status')
  CC_STATUS_METHOD                            status-write HTTP method (default 'PATCH')
  CC_TASK_PATH_TEMPLATE                       task-read path with a literal '{id}' used to
                                              GET the card's current status (default
                                              '/api/tasks/{id}')

PUBLIC API
  card_open(run_dir, *, slug, title, department, persona="", source="",
            description="", priority="medium", env=None)         -> task_id str | None
  card_advance(run_dir, task_id=None, *, phase_id, status, note="",
               deliverable_url="", env=None)                     -> bool
  begin_run(run_dir, *, slug, title, department, persona="", source="",
            description="", env=None)                             -> task_id str | None  (never raises)
  complete_run(run_dir, task_id=None, *, phase_id="deliver", note="",
               status="review", deliverable_url="", env=None)    -> bool                (never raises)
  block_run(run_dir, task_id=None, *, phase_id="", note="", env=None)
                                                                  -> bool                (never raises)

THE BLOCKED STATE (FIX-XC-06)
  Before this helper, a gate failure left a card stranded at `in_progress` forever
  — an invisible failure. `block_run` moves the card to the fail-soft `blocked`
  status (reachable from ANY state in one hop) with the failing phase + AF code as
  the note, so a failed run is VISIBLE on the board. `blocked` is never `done`: a
  fixed re-run may re-open it (blocked -> in_progress) and the independent QC
  scorer still owns the ONLY path to `done` (review -> done).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import List, Optional

_DEFAULT_TIMEOUT = 8

# Mirror of the CC server's TaskStatus enum + LEGAL_TRANSITIONS map, ported verbatim
# from 48-facebook-ad-generator/scripts/cc_board.py (which reads them from
# src/lib/validation.ts + src/lib/task-lifecycle.ts). Kept here ONLY to walk a
# minimal legal path client-side; the server is always the final authority. The
# producer NEVER targets 'done' (review->done is the QC sweep's job), but 'done'
# stays in the map so a legal walk from a mistakenly-'done' card is still possible.
VALID_STATUSES = ("backlog", "in_progress", "review", "blocked", "done")
_LEGAL = {
    "backlog": {"in_progress", "blocked"},
    "in_progress": {"review", "blocked", "backlog"},
    "review": {"done", "in_progress", "blocked", "backlog"},
    "done": {"backlog"},
    "blocked": {"backlog", "in_progress"},
}

# A producer helper may NEVER move a card here — only the independent QC scorer can
# (review -> done). Hard-blocked in card_advance, identical to Skill 6 / Skill 41.
_PRODUCER_FORBIDDEN = ("done",)


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
    status_tmpl = (env.get("CC_STATUS_PATH_TEMPLATE") or "/api/tasks/{id}").strip()
    if "{id}" not in status_tmpl:
        _log(f"CC_STATUS_PATH_TEMPLATE missing '{{id}}' ({status_tmpl!r}); using default '/api/tasks/{{id}}'.")
        status_tmpl = "/api/tasks/{id}"
    task_tmpl = (env.get("CC_TASK_PATH_TEMPLATE") or "/api/tasks/{id}").strip()
    if "{id}" not in task_tmpl:
        _log(f"CC_TASK_PATH_TEMPLATE missing '{{id}}' ({task_tmpl!r}); using default '/api/tasks/{{id}}'.")
        task_tmpl = "/api/tasks/{id}"
    return {
        "base_url": base,
        "token": (env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
        "status_tmpl": status_tmpl,
        "status_method": (env.get("CC_STATUS_METHOD") or "PATCH").strip().upper() or "PATCH",
        "task_tmpl": task_tmpl,
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


def _request(method: str, url: str, payload: Optional[dict], cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None). Raises
    only urllib/OS errors, which the public callers catch (fail-soft). A None
    payload issues a bodyless request (GET) signed over empty bytes."""
    raw_body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    data = raw_body if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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
# Legal-transition walking (ported from cc_board._legal_path). The server owns
# the final say; this only avoids obviously-illegal client-side direct jumps.
# ---------------------------------------------------------------------------
def _legal_path(src: str, dst: str) -> Optional[List[str]]:
    """Shortest legal status path src..dst (inclusive of dst, excluding src) over
    the CC LEGAL_TRANSITIONS map. [] when src == dst (a no-op). None when
    unreachable. 'blocked' is reachable from any state in one hop."""
    if src == dst:
        return []
    if dst == "blocked":
        return ["blocked"]
    q = deque([(src, [])])
    seen = {src}
    while q:
        node, path = q.popleft()
        for nxt in sorted(_LEGAL.get(node, ())):  # sorted => deterministic path
            if nxt in seen:
                continue
            npath = path + [nxt]
            if nxt == dst:
                return npath
            seen.add(nxt)
            q.append((nxt, npath))
    return None


# ---------------------------------------------------------------------------
# Receipt — atomic read / merge under <run_dir>/working/checkpoints/mc-board.json.
# Only written when the board is ENABLED (a disabled run touches nothing).
# ---------------------------------------------------------------------------
def _receipt_path(run_dir) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "mc-board.json"


def _read_receipt(run_dir) -> dict:
    p = _receipt_path(run_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _merge_receipt(run_dir, updates: dict) -> bool:
    """Merge `updates` into the receipt atomically. Never raises."""
    p = _receipt_path(run_dir)
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
) -> Optional[str]:
    """Open (or idempotently re-fetch) this run's board card. Returns the task_id
    string on success, else None. FAIL-SOFT — a None return never blocks the run.

    A disabled board (no COMMAND_CENTER_URL/MISSION_CONTROL_URL) is a clean no-op
    that writes NOTHING. When enabled, the task_id is stamped into the receipt so a
    later advance can recover it and a re-open reuses it (no duplicate card)."""
    if run_dir is None:
        return None
    cfg = board_config(env)
    if cfg is None:
        _log("COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — board disabled (no-op); run continues.")
        return None

    # Idempotent: reuse a task_id already recorded for this run dir.
    existing = _read_receipt(run_dir).get("mc_task_id")
    if existing:
        return str(existing)

    # Mark the attempt (receipt-backed) BEFORE the network call.
    _merge_receipt(run_dir, {"mc_register_attempted": True, "slug": slug})

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
        _merge_receipt(run_dir, {"mc_task_id": task_id})
        return task_id

    _log(f"ingest POST non-OK (HTTP {status}): {body}; run continues ungrouped.")
    return None


# ---------------------------------------------------------------------------
# Current status — GET the card and read its status (rows, not mtime). None when
# the board is unreachable or the card/status is absent.
# ---------------------------------------------------------------------------
def _current_status(tid: str, cfg: dict) -> Optional[str]:
    """GET the task and return its current board status, or None when the board is
    unreachable or the status is absent. Tolerant of a few common response shapes
    ({status}, {task:{status}}, {task:{...}})."""
    url = f"{cfg['base_url']}{cfg['task_tmpl'].format(id=tid)}"
    try:
        st, body = _request("GET", url, None, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"status GET failed for task {tid} ({type(exc).__name__}: {exc}).")
        return None
    if st != 200 or not isinstance(body, dict):
        return None
    cur = body.get("status")
    if not cur and isinstance(body.get("task"), dict):
        cur = body["task"].get("status")
    cur = (cur or "").strip().lower()
    return cur or None


# ---------------------------------------------------------------------------
# ADVANCE — move the card to (phase_id, status), walking the legal path.
# ---------------------------------------------------------------------------
def _move_once(tid: str, phase_id: str, status: str, cfg: dict,
               note: str = "", deliverable_url: str = "") -> bool:
    """Issue ONE status write honoring CC_STATUS_PATH_TEMPLATE / CC_STATUS_METHOD.
    Returns True on HTTP 200-2xx, else False. Never raises past urllib/OS."""
    payload: dict = {"phase_id": phase_id, "status": status}
    if note:
        payload["note"] = note
    if deliverable_url:
        payload["deliverable_url"] = deliverable_url
    url = f"{cfg['base_url']}{cfg['status_tmpl'].format(id=tid)}"
    try:
        st, body = _request(cfg["status_method"], url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"advance {phase_id}->{status} failed ({type(exc).__name__}: {exc}).")
        return False
    if 200 <= st < 300:
        _log(f"advance {phase_id}->{status} OK (task_id={tid}).")
        return True
    _log(f"advance {phase_id}->{status} non-OK (HTTP {st}): {body}.")
    return False


def card_advance(
    run_dir,
    task_id: Optional[str] = None,
    *,
    phase_id: str,
    status: str,
    note: str = "",
    deliverable_url: str = "",
    env: Optional[dict] = None,
) -> bool:
    """Advance this run's card to (phase_id, status), walking the shortest LEGAL
    path from its current status. FAIL-SOFT: returns False (never raises) on any
    board problem; the run is never blocked. task_id is recovered from the receipt
    when not supplied. Disabled board => no-op False.

    THE BOARD CONTRACT: a producer may never target 'done'. review->done is owned
    exclusively by the independent QC scorer, so status='done' is HARD-BLOCKED here
    (identical to Skill 6 cc_board.update_status and Skill 41 cc_move_task)."""
    cfg = board_config(env)
    if cfg is None:
        return False

    target = (status or "").strip().lower()
    if target not in VALID_STATUSES:
        _log(f"advance refused — invalid target status {status!r} "
             f"(allowed: {', '.join(VALID_STATUSES)}).")
        return False
    if target in _PRODUCER_FORBIDDEN:
        _log("advance BLOCKED — a producer must never post 'done' directly. The ONLY "
             "valid path to 'done' is review -> done via the independent QC scorer "
             "(PASS >= 8.5). Post 'review' and let the QC sweep promote the card.")
        return False

    tid = task_id or _read_receipt(run_dir).get("mc_task_id")
    if not tid:
        _log(f"advance {phase_id}->{target} skipped — no task_id (card never opened).")
        return False
    tid = str(tid)

    current = _current_status(tid, cfg)
    if current is None:
        # Card status unknown (board unreachable / card missing): attempt a single
        # direct move and let the server reject an illegal jump (fail-soft).
        return _move_once(tid, phase_id, target, cfg, note=note, deliverable_url=deliverable_url)
    if current == target:
        _log(f"advance {phase_id}->{target} no-op (card already at {target}).")
        return True
    path = _legal_path(current, target)
    if path is None:
        _log(f"no legal path {current}->{target} for task {tid}; skipping (server owns the truth).")
        return False
    ok = True
    for i, step in enumerate(path):
        last = i == len(path) - 1
        ok = _move_once(
            tid, phase_id, step, cfg,
            note=note if last else f"auto-step toward {target}",
            deliverable_url=deliverable_url if last else "",
        )
        if not ok:
            break
    return ok


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
    env: Optional[dict] = None,
) -> Optional[str]:
    """Open the run's card and move it to in_progress. Returns the task_id or None.
    Never raises — the board is a view, never a gate."""
    try:
        tid = card_open(
            run_dir, slug=slug, title=title, department=department,
            persona=persona, source=source, description=description, env=env,
        )
        if tid:
            card_advance(run_dir, tid, phase_id="run", status="in_progress",
                         note="run started", env=env)
        return tid
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        _log(f"begin_run best-effort skip ({type(exc).__name__}: {exc}).")
        return None


def complete_run(run_dir, task_id: Optional[str] = None, *, phase_id: str = "deliver",
                 note: str = "", status: str = "review", deliverable_url: str = "",
                 env: Optional[dict] = None) -> bool:
    """Move the run's card to its TERMINAL producer status — `review` by default,
    NEVER `done`. review->done is owned exclusively by the independent QC scorer
    (PASS >= 8.5); a producer that posted `done` here would skip the QC column,
    which is THE board bug this helper exists to prevent. The deliverable link, when
    supplied, is registered on the card. Recovers the task_id from the receipt when
    not supplied. Never raises — the board is a view, never a gate."""
    try:
        target = (status or "review").strip().lower() or "review"
        if target in _PRODUCER_FORBIDDEN:
            _log("complete_run refused 'done' — the terminal producer status is 'review'; "
                 "the QC scorer owns review -> done. Falling back to 'review'.")
            target = "review"
        default_note = "certified — awaiting QC promotion"
        return card_advance(run_dir, task_id, phase_id=phase_id, status=target,
                            note=note or default_note, deliverable_url=deliverable_url,
                            env=env)
    except Exception as exc:  # noqa: BLE001
        _log(f"complete_run best-effort skip ({type(exc).__name__}: {exc}).")
        return False


def block_run(run_dir, task_id: Optional[str] = None, *, phase_id: str = "",
              note: str = "", env: Optional[dict] = None) -> bool:
    """Move the run's card to the fail-soft dead-end `blocked` status when a gate
    FAILS, so a blocked run is VISIBLE on the board instead of stranding forever at
    `in_progress` (FIX-XC-06: gate failures used to leave invisible, permanently-
    in_progress cards). The failing phase + AF code (passed as `note`) are recorded
    on the card.

    `blocked` is reachable from ANY status in one hop (see _legal_path) and is NEVER
    `done`: a producer may re-open it (blocked -> in_progress) on a fixed re-run, and
    the independent QC scorer still owns the ONLY path to `done` (review -> done).
    Recovers the task_id from the receipt when not supplied. Never raises — the board
    is a view, never a gate, so a board outage can never change the run's exit code."""
    try:
        detail = (note or "").strip()
        if phase_id:
            prefix = "BLOCKED at %s (gate failed)" % phase_id
            detail = ("%s — %s" % (prefix, detail)) if detail else prefix
        elif not detail:
            detail = "run BLOCKED (a gate failed)"
        return card_advance(run_dir, task_id, phase_id=phase_id or "blocked",
                            status="blocked", note=detail, env=env)
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        _log(f"block_run best-effort skip ({type(exc).__name__}: {exc}).")
        return False
