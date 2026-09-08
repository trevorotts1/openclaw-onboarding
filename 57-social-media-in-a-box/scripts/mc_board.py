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
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_DEFAULT_TIMEOUT = 8

# U100 — the producer-reconcile pattern generalized from B-U13/U27
# (06-ghl-install-pages/tools/cc_board.py) to this "mc_board six" producer.
# Fixed subdir + filename for the opt-in board-ingest receipt `reconcile`
# sweeps; distinct from the existing `working/checkpoints/mc-board.json`
# per-run receipt above so this is purely additive (see _write_board_ingest_
# receipt's own no-op-when-evidence_root-is-None contract).
_EVIDENCE_ROUTING_SUBDIR = "routing"
_BOARD_INGEST_RECEIPT_FILENAME = "board-ingest-receipt.json"


def _ts() -> str:
    """UTC timestamp, matches cc_board.py's ``_ts()`` byte-for-byte."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

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
# P2-07 hardening: last-resort department_slug routing. An UNRECOGNIZED
# department_slug (a typo, a regressed hardcoded fake slug like the historical
# "funnels"/"books"/"email" family, or an empty string) must never be sent to
# the Command Center unchanged and never silently dropped — the CC's own
# unrecognized-slug handling is exactly the silent-drop that enabled that fake-
# slug family (v18.0.6-v18.1.1). It re-routes client-side to the general-task
# catch-all instead, so the card is ALWAYS visible somewhere on the board.
#
# This mirrors — does NOT import — the 22 HARDCODED_MANDATORY + 6
# HARDCODED_UNIVERSAL_PRIMARY canonical department ids plus their known variant
# aliases from 23-ai-workforce-blueprint/scripts/department-floor.py:116-158
# (v2.6.1 naming map). mc_board.py stays STDLIB-ONLY / zero-deps and is dropped
# byte-for-byte into skill dirs with no shared relative path to that file, so
# the canonical ids are mirrored here exactly like VALID_STATUSES/_LEGAL mirror
# the CC server's enum above. general-task is always a member of this set — it
# is both a real floor department and the re-route target.
_CANONICAL_MANDATORY_DEPARTMENTS = (
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement", "personal-assistant",
    "general-task", "project-architecture-office",
    "bugs", "healer", "quality-control",
)
_CANONICAL_UNIVERSAL_PRIMARY_DEPARTMENTS = (
    "presentations", "scheduling-dispatch", "logistics-fulfillment",
    "engineering", "account-management", "podcast",
)
_CANONICAL_VARIANT_ALIASES = {
    "billing-finance": ("finance", "finance-ops", "billing", "finance-billing", "accounting"),
    "customer-support": ("support", "customer-service", "cs", "client-success"),
    "web-development": ("web-dev", "webdev", "website", "web"),
    "app-development": ("app-dev", "appdev", "mobile", "application-development"),
    "legal": ("legal-compliance", "compliance", "legal-ops", "risk-compliance"),
    "graphics": ("graphics-design", "design", "creative", "graphic-design"),
    "openclaw-maintenance": ("openclaw", "maintenance", "ops", "platform-maintenance"),
    "paid-advertisement": ("paid-ads", "paid-advertising", "ads", "advertising", "paid-media"),
    "social-media": ("social", "smm", "social-media-management"),
    "crm": ("crm-ops", "customer-relationship-management"),
    "communications": ("comms", "communication", "pr", "public-relations"),
    "video": ("video-production", "video-content", "video-editing"),
    "audio": ("audio-production", "audio-content", "sound", "podcast"),
}


def _known_department_slugs() -> frozenset:
    known = set(_CANONICAL_MANDATORY_DEPARTMENTS) | set(_CANONICAL_UNIVERSAL_PRIMARY_DEPARTMENTS)
    for aliases in _CANONICAL_VARIANT_ALIASES.values():
        known.update(aliases)
    return frozenset(known)


KNOWN_DEPARTMENT_SLUGS = _known_department_slugs()
GENERAL_TASK_SLUG = "general-task"


def _normalize_department_slug(dep: Optional[str]) -> str:
    return (dep or "").strip().lower()


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


def _write_board_ingest_receipt(
    evidence_root: Optional[str],
    *,
    mc_url_set: bool,
    ok: bool,
    task_id: Optional[str],
    department_slug: Optional[str] = None,
    source: Optional[str] = None,
    reason: str = "",
) -> None:
    """U100 — the producer-reconcile pattern generalized from B-U13/U27's
    ``_write_board_ingest_receipt`` (06-ghl-install-pages/tools/cc_board.py).
    Persists ONE receipt per ``card_open()`` call recording whether the board
    was even configured and whether the card landed, so ``mc_board.py
    reconcile`` can later distinguish "no card because nothing to build" from
    "no card because the board was unreachable/unconfigured and the build
    silently continued unregistered".

    Best-effort / fail-soft: ``evidence_root=None`` (the default — every
    EXISTING caller of ``card_open``/``begin_run`` is unaffected, matching the
    module's own NO-OP-WHEN-DISABLED contract) is a clean no-op; any OSError
    writing the receipt is swallowed. NEVER raises; NEVER changes
    ``card_open()``'s return value."""
    if not evidence_root:
        return
    try:
        receipt_dir = os.path.join(evidence_root, _EVIDENCE_ROUTING_SUBDIR)
        os.makedirs(receipt_dir, exist_ok=True)
        record = {
            "attempted_at": _ts(),
            "mc_url_set": bool(mc_url_set),
            "ok": bool(ok),
            "task_id": task_id,
            "department_slug": department_slug,
            "source": source,
            "reason": reason,
        }
        final_path = os.path.join(receipt_dir, _BOARD_INGEST_RECEIPT_FILENAME)
        tmp_path = final_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        os.replace(tmp_path, final_path)
    except OSError:
        pass  # receipt is best-effort; card_open()'s return value is unaffected


# ---------------------------------------------------------------------------
# BOARD OUTBOX (F12, social-planner-september-eighth / WF05) — a durable outbox
# for pending board writes during a Command Center outage.
#
# Before this: a board outage dropped the ingest POST (and any status write)
# entirely — the run continued unregistered and the completed artifacts had no
# card, or a half-registered run stalled at an early status with no recovery
# beyond `reconcile`'s read-only report. Now every FAILED write is persisted
# to <run_dir>/working/checkpoints/board-outbox.jsonl (one JSON line per op,
# deduped on a stable op_id) and REPLAYED ONCE on recovery — opportunistically
# on the next board touch for the same run, or explicitly via
# `replay_outbox()` / `mc_board.py replay --run-dir DIR`.
#
# Replay is idempotent end to end, so recovery produces ONE consistent card
# with truthful status:
#   - ingest ops re-POST /api/tasks/ingest — the server dedupes on the same
#     stable idempotency_key, so a replay can never create a second card;
#   - status ops GET the card first and only re-issue a move the card has not
#     already reached (walking the same legal path), so a replay never
#     double-moves or moves backwards.
# Fail-soft throughout: an outbox write/read failure NEVER raises and NEVER
# changes a return value — the pre-F12 contracts hold exactly when the disk
# itself is unavailable.
# ---------------------------------------------------------------------------

_OUTBOX_FILENAME = "board-outbox.jsonl"


def _outbox_path(run_dir) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / _OUTBOX_FILENAME


def _outbox_op_id(method: str, path: str, payload: Optional[dict]) -> str:
    """Stable identity for one pending board op — identical retries collapse."""
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True) if payload is not None else ""
    return hashlib.sha256(f"{method} {path} {canonical}".encode("utf-8")).hexdigest()[:24]


def _outbox_read(run_dir) -> List[dict]:
    """Every pending op (oldest first), skipping corrupt lines. Never raises."""
    p = _outbox_path(run_dir)
    ops: List[dict] = []
    try:
        if not p.exists():
            return ops
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("op_id") and rec.get("path") and rec.get("method"):
                ops.append(rec)
    except OSError:
        pass
    return ops


def _outbox_append(run_dir, *, method: str, path: str, payload: Optional[dict], reason: str) -> bool:
    """Persist ONE failed board op for later replay. Deduped on op_id, so a
    repeated failure of the same write never grows the file. Never raises."""
    try:
        existing_ids = {op.get("op_id") for op in _outbox_read(run_dir)}
        op_id = _outbox_op_id(method, path, payload)
        if op_id in existing_ids:
            return True  # already pending — one line per logical op
        record = {
            "op_id": op_id,
            "method": method,
            "path": path,
            "payload": payload,
            "queued_at": _ts(),
            "attempts": 0,
            "last_error": (reason or "")[:200],
        }
        p = _outbox_path(run_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
        return True
    except OSError as exc:
        _log(f"outbox append failed ({exc}).")
        return False


def _outbox_rewrite(run_dir, ops: List[dict]) -> bool:
    """Atomically rewrite the outbox with the surviving (unreplayed) ops."""
    try:
        p = _outbox_path(run_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for op in ops:
                f.write(json.dumps(op, separators=(",", ":")) + "\n")
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def replay_outbox(run_dir, *, env: Optional[dict] = None) -> dict:
    """Replay ONE pass of the run's board outbox (F12).

    Returns ``{"applicable", "replayed", "removed", "remaining", "failed"}``.
    Each pending op is attempted at most once per call:
      - ingest ops: re-POST (server-side idempotency_key dedupe ⇒ one card);
        success backfills the receipt's mc_task_id when absent;
      - status ops: GET the card; a card already AT the target (or past it)
        drops the op without a write — never double-moves, never moves
        backwards; otherwise the move is re-issued.
    Successful ops are removed from the outbox; failed ops survive (with an
    incremented attempt count) for a later pass. NEVER raises — a disabled
    board or any OSError degrades to a report, never a run failure."""
    if run_dir is None:
        return {"applicable": False, "replayed": 0, "removed": 0, "remaining": 0, "failed": 0}
    cfg = board_config(env)
    ops = _outbox_read(run_dir)
    if cfg is None:
        return {"applicable": False, "replayed": 0, "removed": 0,
                "remaining": len(ops), "failed": 0}
    if not ops:
        return {"applicable": True, "replayed": 0, "removed": 0, "remaining": 0, "failed": 0}

    surviving: List[dict] = []
    replayed = removed = 0
    for op in ops:
        method = str(op.get("method") or "POST").upper()
        path = str(op.get("path") or "")
        payload = op.get("payload") if isinstance(op.get("payload"), (dict, type(None))) else None
        op["attempts"] = int(op.get("attempts") or 0) + 1
        op["last_attempt_at"] = _ts()
        try:
            if method == "POST" and path.endswith("/api/tasks/ingest"):
                # Ingest replay: re-POST — the server dedupes on the stable
                # idempotency_key, so recovery collapses to ONE card.
                status, body = _request(method, f"{cfg['base_url']}{path}", payload, cfg)
                ok = status in (200, 201, 204)
                if ok:
                    # Backfill the receipt with the real task id.
                    tid = str(((body or {}) if isinstance(body, dict) else {}).get("task_id") or "")
                    if tid:
                        if not _read_receipt(run_dir).get("mc_task_id"):
                            _merge_receipt(run_dir, {"mc_task_id": tid})
                        _merge_receipt(run_dir, {"mc_outbox_replay_task_id": tid,
                                                 "mc_outbox_replay_at": _ts()})
            else:
                # Status-write replay is TRUTHFUL first: GET the card BEFORE
                # issuing any write. A card already AT the target — or one that
                # moved FORWARD past it during the outage — drops the op with
                # no write: never double-moves, never regresses.
                tid = path.rstrip("/").rsplit("/", 1)[-1]
                target = (payload or {}).get("status") if isinstance(payload, dict) else None
                current = _current_status(tid, cfg) if target else None
                if current is None:
                    # Card unreadable (still down / missing) — keep the op.
                    op["last_error"] = "status GET unavailable during replay"
                    surviving.append(op)
                    continue
                if current == str(target or "").strip().lower():
                    ok = True  # already there — nothing to move (no double move)
                elif current in ("review", "done") and str(target or "").strip().lower() == "in_progress":
                    ok = True  # card moved FORWARD during the outage — never regress it
                elif current in _LEGAL and target in _LEGAL.get(current, ()):  # direct legal hop
                    status, body = _request(method, f"{cfg['base_url']}{path}", payload, cfg)
                    ok = status in (200, 201, 204)
                else:
                    # Illegal direct hop (e.g. backlog->review): walk the legal
                    # path the same way card_advance does, then replay the tail.
                    walk = _legal_path(current, str(target or "").strip().lower())
                    if walk is None:
                        op["last_error"] = f"no legal path {current}->{target}"
                        surviving.append(op)
                        continue
                    ok = True
                    for step in walk:
                        step_payload = dict(payload or {})
                        step_payload["status"] = step
                        status, body = _request(method, f"{cfg['base_url']}{path}", step_payload, cfg)
                        if status not in (200, 201, 204):
                            ok = False
                            op["last_error"] = f"HTTP {status} during legal-path replay"
                            break
            if ok:
                replayed += 1
                removed += 1
            else:
                op["last_error"] = op.get("last_error") or f"HTTP {status}"
                surviving.append(op)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            op["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
            surviving.append(op)

    _outbox_rewrite(run_dir, surviving)
    return {"applicable": True, "replayed": replayed, "removed": removed,
            "remaining": len(surviving), "failed": len(ops) - removed}


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
    evidence_root: Optional[str] = None,
) -> Optional[str]:
    """Open (or idempotently re-fetch) this run's board card. Returns the task_id
    string on success, else None. FAIL-SOFT — a None return never blocks the run.

    A disabled board (no COMMAND_CENTER_URL/MISSION_CONTROL_URL) is a clean no-op
    that writes NOTHING. When enabled, the task_id is stamped into the receipt so a
    later advance can recover it and a re-open reuses it (no duplicate card).

    ``evidence_root`` (U100, opt-in, default None): when a caller passes a
    per-run evidence directory, ONE board-ingest receipt is ALSO written there
    (``<evidence_root>/routing/board-ingest-receipt.json``) recording whether
    the board was even configured and whether the card landed — the run-
    evidence ledger ``mc_board.py reconcile`` sweeps. Every EXISTING caller
    (evidence_root=None) is completely unaffected — this preserves the
    module's own NO-OP-WHEN-DISABLED / byte-for-byte-identical contract."""
    if run_dir is None:
        return None
    cfg = board_config(env)
    if cfg is None:
        _log("COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — board disabled (no-op); run continues.")
        _write_board_ingest_receipt(
            evidence_root, mc_url_set=False, ok=False, task_id=None,
            department_slug=department, source=source or "productized-skill",
            reason="COMMAND_CENTER_URL/MISSION_CONTROL_URL unset",
        )
        return None

    # Idempotent: reuse a task_id already recorded for this run dir.
    existing = _read_receipt(run_dir).get("mc_task_id")
    if existing:
        return str(existing)

    # Mark the attempt (receipt-backed) BEFORE the network call.
    _merge_receipt(run_dir, {"mc_register_attempted": True, "slug": slug})

    # P2-07: last-resort department_slug hardening. An UNRECOGNIZED slug (typo,
    # regressed hardcoded fake slug, or empty string) is NEVER sent through
    # unchanged and NEVER silently dropped — log loudly and re-route to the
    # general-task catch-all, annotating the card with the original bad slug.
    original_bad_slug: Optional[str] = None
    department_slug = department
    if _normalize_department_slug(department) not in KNOWN_DEPARTMENT_SLUGS:
        original_bad_slug = department
        _log(
            f"UNRECOGNIZED department_slug {department!r} for slug={slug!r} — "
            f"re-routing card to '{GENERAL_TASK_SLUG}' (never silently dropped; "
            f"this is the last-resort catch-all)."
        )
        department_slug = GENERAL_TASK_SLUG
        _merge_receipt(run_dir, {
            "department_slug_rerouted": True,
            "original_department_slug": original_bad_slug,
        })

    source_ref = slug or source or "run"
    idem_input = f"{source_ref}{title}".encode("utf-8")
    idempotency_key = hashlib.sha256(idem_input).hexdigest()

    base_description = description or title
    if original_bad_slug is not None:
        base_description = (
            f"[AUTO-REROUTED — unrecognized department_slug {original_bad_slug!r} -> "
            f"'{GENERAL_TASK_SLUG}'] {base_description}"
        )

    payload: dict = {
        "title": title,
        "description": base_description,
        "priority": priority,
        "source": source or "productized-skill",
        "source_ref": source_ref,
        "department_slug": department_slug,
        "external_session_id": source_ref,
        "idempotency_key": idempotency_key,
    }
    if persona:
        payload["persona"] = persona

    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"ingest POST failed ({type(exc).__name__}: {exc}); queued in the board outbox for replay.")
        _outbox_append(run_dir, method="POST", path="/api/tasks/ingest", payload=payload,
                       reason=f"{type(exc).__name__}: {exc}")
        _write_board_ingest_receipt(
            evidence_root, mc_url_set=True, ok=False, task_id=None,
            department_slug=department_slug, source=source or "productized-skill",
            reason=f"{type(exc).__name__}: {exc}",
        )
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        _log(f"card {'deduped (reused)' if deduped else 'created'}: task_id={task_id} slug={slug}")
        _merge_receipt(run_dir, {"mc_task_id": task_id})
        _write_board_ingest_receipt(
            evidence_root, mc_url_set=True, ok=True, task_id=task_id,
            department_slug=department_slug, source=source or "productized-skill",
            reason="deduped" if deduped else "created",
        )
        # F12: recovery first — replay anything an outage parked before this
        # success (idempotent; never blocks this card from returning).
        try:
            replay_outbox(run_dir, env=env)
        except Exception as exc:  # noqa: BLE001 — outbox replay must never surface here
            _log(f"outbox replay skip ({type(exc).__name__}: {exc}).")
        return task_id

    _log(f"ingest POST non-OK (HTTP {status}): {body}; run continues ungrouped.")
    # F12: a 5xx is an outage class — park the op for replay; a 4xx is a
    # permanent caller fault (replaying it can never succeed) so it is NOT queued.
    if status >= 500 or status == 0:
        _outbox_append(run_dir, method="POST", path="/api/tasks/ingest", payload=payload,
                       reason=f"HTTP {status}")
    _write_board_ingest_receipt(
        evidence_root, mc_url_set=True, ok=False, task_id=None,
        department_slug=department_slug, source=source or "productized-skill",
        reason=f"HTTP {status}: {body}",
    )
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
               note: str = "", deliverable_url: str = "",
               run_dir=None, env: Optional[dict] = None) -> bool:
    """Issue ONE status write honoring CC_STATUS_PATH_TEMPLATE / CC_STATUS_METHOD.
    Returns True on HTTP 200-2xx, else False. Never raises past urllib/OS.
    F12: on an outage-class failure (transport error / 5xx) the op is parked in
    the run's board outbox for one idempotent replay on recovery."""
    payload: dict = {"phase_id": phase_id, "status": status}
    if note:
        payload["note"] = note
    if deliverable_url:
        payload["deliverable_url"] = deliverable_url
    url = f"{cfg['base_url']}{cfg['status_tmpl'].format(id=tid)}"
    try:
        st, body = _request(cfg["status_method"], url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"advance {phase_id}->{status} failed ({type(exc).__name__}: {exc}); queued in the board outbox.")
        if run_dir is not None:
            _outbox_append(run_dir, method=cfg["status_method"], path=cfg["status_tmpl"].format(id=tid),
                           payload=payload, reason=f"{type(exc).__name__}: {exc}")
        return False
    if 200 <= st < 300:
        _log(f"advance {phase_id}->{status} OK (task_id={tid}).")
        return True
    _log(f"advance {phase_id}->{status} non-OK (HTTP {st}): {body}.")
    if st >= 500 and run_dir is not None:
        _outbox_append(run_dir, method=cfg["status_method"], path=cfg["status_tmpl"].format(id=tid),
                       payload=payload, reason=f"HTTP {st}")
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
        return _move_once(tid, phase_id, target, cfg, note=note, deliverable_url=deliverable_url,
                          run_dir=run_dir, env=env)
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
            run_dir=run_dir, env=env,
        )
        if not ok:
            break
    # F12: after ANY advance, opportunistically replay parked ops so a recovery
    # collapses the outbox to one consistent card with truthful status.
    if ok:
        try:
            replay_outbox(run_dir, env=env)
        except Exception as exc:  # noqa: BLE001 — outbox replay must never surface here
            _log(f"outbox replay skip ({type(exc).__name__}: {exc}).")
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
    evidence_root: Optional[str] = None,
) -> Optional[str]:
    """Open the run's card and move it to in_progress. Returns the task_id or None.
    Never raises — the board is a view, never a gate.

    ``evidence_root`` (U100, opt-in, default None): forwarded to ``card_open``
    — see its docstring."""
    try:
        tid = card_open(
            run_dir, slug=slug, title=title, department=department,
            persona=persona, source=source, description=description, env=env,
            evidence_root=evidence_root,
        )
        if tid:
            note = "run started"
            reroute = _read_receipt(run_dir).get("original_department_slug")
            if reroute:
                note = (
                    f"run started (auto-rerouted from unrecognized department_slug "
                    f"{reroute!r} to '{GENERAL_TASK_SLUG}')"
                )
            card_advance(run_dir, tid, phase_id="run", status="in_progress",
                         note=note, env=env)
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


# ---------------------------------------------------------------------------
# RECONCILE (U100) — the producer-reconcile pattern generalized from B-U13/U27
# to this "mc_board six" producer. Sweeps every run-evidence root a caller has
# opted into (evidence_root= passed to card_open/begin_run) and reports
# clean/drift/unwired per run. Read-only, non-gating, fail-soft, idempotent —
# safe to run repeatedly (a health-probe cron tick or ad hoc from the CLI).
# ---------------------------------------------------------------------------
def resolve_state_dir(env: Optional[dict] = None) -> str:
    """Resolve the run-evidence root to sweep for `reconcile` (U100 — cloned
    from Skill 6's `resolve_evidence_base()`, B-U13/U27). Resolution order:
      1. ``MC_BOARD_EVIDENCE_BASE_DIR`` env override (explicit, highest
         precedence).
      2. ``$HOME/.openclaw/data/<skill-dir-name>/runs`` — the productized-
         skill runs-root convention (mirrors Skill 35's own
         ``$HOME/.openclaw/data/skill-35/runs/<run-id>``). ``<skill-dir-name>``
         is derived from this file's own containing directory (e.g.
         ``49-signature-funnel``) so this module stays byte-for-byte identical
         across every skill that vendors it.
      3. ``""`` — no resolvable base (CI / a bare checkout with no HOME);
         callers treat this as "not applicable", never as an error.

    Never raises; never touches the network."""
    env = env if env is not None else os.environ
    explicit = (env.get("MC_BOARD_EVIDENCE_BASE_DIR") or "").strip()
    if explicit:
        return explicit
    home = (env.get("HOME") or "").strip()
    if not home:
        return ""
    try:
        skill_dir_name = Path(__file__).resolve().parents[1].name
    except (IndexError, OSError):
        skill_dir_name = "unknown-skill"
    return os.path.join(home, ".openclaw", "data", skill_dir_name, "runs")


def list_evidence_runs(base_dir: str) -> List[str]:
    """Every immediate subdirectory of ``base_dir`` — the run-evidence ledger
    roots `reconcile` sweeps (each one is an ``evidence_root`` a caller may
    have passed to ``card_open``/``begin_run``). Read-only; never raises (an
    unreadable base_dir yields an empty list, never an exception)."""
    runs: List[str] = []
    try:
        if not base_dir or not os.path.isdir(base_dir):
            return runs
        for name in sorted(os.listdir(base_dir)):
            run_dir = os.path.join(base_dir, name)
            if os.path.isdir(run_dir):
                runs.append(run_dir)
    except OSError:
        return runs
    return runs


def _read_board_ingest_receipt(run_dir: str) -> Optional[dict]:
    path = os.path.join(run_dir, _EVIDENCE_ROUTING_SUBDIR, _BOARD_INGEST_RECEIPT_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


@dataclass
class ReconcileReport:
    base_dir: str
    applicable: bool = True
    total_runs: int = 0
    clean: list = field(default_factory=list)       # run ids: receipt present + landed OK
    drift: list = field(default_factory=list)        # [{run, reason}]
    unwired: list = field(default_factory=list)       # run ids: no board-ingest receipt

    def all_clean(self) -> bool:
        return not self.drift

    def as_dict(self) -> dict:
        return {
            "base_dir": self.base_dir,
            "applicable": self.applicable,
            "total_runs": self.total_runs,
            "clean": self.clean,
            "drift": self.drift,
            "unwired": self.unwired,
            "all_clean": self.all_clean(),
        }


def reconcile(base_dir: Optional[str] = None, *, env: Optional[dict] = None) -> ReconcileReport:
    """Run ONE reconciliation pass (U100 — the producer-reconcile pattern
    generalized from B-U13/U27 to this productized-skill's mc_board.py).

    Never raises; never mutates anything; never blocks a build — this is a
    read-only diagnostic sweep, safe to run repeatedly (idempotent) in the
    daily maintenance window or ad hoc from the CLI."""
    resolved = (base_dir or "").strip() or resolve_state_dir(env)
    report = ReconcileReport(base_dir=resolved)

    if not resolved or not os.path.isdir(resolved):
        report.applicable = False
        return report

    for run_dir in list_evidence_runs(resolved):
        run_id = os.path.basename(run_dir)
        receipt = _read_board_ingest_receipt(run_dir)

        if receipt is None:
            # No board-ingest receipt: either a caller that has not threaded
            # evidence_root= through to card_open()/begin_run() yet, or a run
            # this producer never tried to board at all. Informational only —
            # never counted as drift (mirrors B-U13's module note).
            report.unwired.append(run_id)
            continue

        report.total_runs += 1

        if not receipt.get("mc_url_set"):
            report.drift.append({
                "run": run_id,
                "reason": "COMMAND_CENTER_URL/MISSION_CONTROL_URL unset at "
                          "ingest — card never landed",
            })
            continue

        if not receipt.get("ok") or not receipt.get("task_id"):
            report.drift.append({
                "run": run_id,
                "reason": f"board configured but ingest failed: {receipt.get('reason', 'unknown')}",
            })
            continue

        report.clean.append(run_id)

    return report


def _replay_cli(argv: Optional[list] = None) -> int:
    """``mc_board.py replay --run-dir DIR [--json]`` (F12) — explicit outbox
    replay for one run (or every run under the evidence root when --run-dir is
    omitted). ALWAYS exits 0 — fail-soft, non-gating; the printed report carries
    the verdict."""
    import argparse

    p = argparse.ArgumentParser(
        prog="mc_board.py replay",
        description="F12 — replay parked board writes (board outbox) once; "
                    "idempotent, one consistent card, truthful status.",
    )
    p.add_argument("--run-dir", default="",
                   help="One run directory to replay (default: sweep every run "
                        "under the resolved evidence root).")
    p.add_argument("--base-dir", default="",
                   help="Run-evidence root (used when --run-dir is omitted).")
    p.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = p.parse_args(argv)

    results: dict = {}
    if args.run_dir:
        results[os.path.basename(args.run_dir.rstrip("/")) or args.run_dir] = replay_outbox(args.run_dir)
    else:
        base = args.base_dir or resolve_state_dir()
        for run_dir in list_evidence_runs(base):
            report = replay_outbox(run_dir)
            if report.get("replayed") or report.get("remaining"):
                results[os.path.basename(run_dir)] = report
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(json.dumps(results, indent=2))
    return 0  # non-gating — always exit 0


def _reconcile_cli(argv: Optional[list] = None) -> int:
    """``mc_board.py reconcile [--base-dir DIR] [--json]`` (U100, cloned from
    cc_board.py's B-U13/U27 CLI form). ALWAYS exits 0 — this is a non-gating,
    fail-soft, read-only sweep. The verdict lives in the printed report's
    ``all_clean`` / ``drift`` fields for the caller (operator, cron, or the
    Command Center's health probe) to read — never in the process exit code.
    """
    import argparse

    p = argparse.ArgumentParser(
        prog="mc_board.py reconcile",
        description="U100 — sweep this producer's run-evidence roots for "
                     "board-ingest drift (non-gating; never flips a box red).",
    )
    p.add_argument("--base-dir", default="",
                    help="Run-evidence root to sweep (default: "
                         "MC_BOARD_EVIDENCE_BASE_DIR env, else "
                         "$HOME/.openclaw/data/<skill-dir>/runs).")
    p.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = p.parse_args(argv)

    report = reconcile(args.base_dir or None)
    d = report.as_dict()

    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print(f"Base dir: {d['base_dir']} (applicable={d['applicable']})")
        print(f"Total runs (with a board-ingest receipt): {d['total_runs']}")
        print(f"  Clean:   {len(d['clean'])} {d['clean']}")
        print(f"  Drift:   {len(d['drift'])} {d['drift']}")
        print(f"  Unwired: {len(d['unwired'])} {d['unwired']}")
        print("RESULT:", "CLEAN" if d["all_clean"] else "ATTENTION NEEDED (non-gating)")

    return 0  # non-gating — always exit 0, per B-U13/U27


if __name__ == "__main__":
    # U100 — literal ``mc_board.py reconcile [--base-dir DIR] [--json]``
    # subcommand (cloned from cc_board.py's B-U13/U27 CLI form). This module
    # previously had no CLI entrypoint at all (library-only, imported by each
    # producer's orchestrator) — reconcile is purely additive.
    # F12 — ``mc_board.py replay [--run-dir DIR] [--base-dir DIR] [--json]``:
    # explicit outbox replay pass, same fail-soft/non-gating contract.
    if len(sys.argv) > 1 and sys.argv[1] == "reconcile":
        sys.exit(_reconcile_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "replay":
        sys.exit(_replay_cli(sys.argv[2:]))
