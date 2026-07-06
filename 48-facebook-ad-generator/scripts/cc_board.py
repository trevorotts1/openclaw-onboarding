#!/usr/bin/env python3
"""
cc_board.py — Skill 48 PRODUCER-SIDE Command Center board caller (FAIL-SOFT).

This is the producer half of the board hookup whose server half is
``POST /api/ad-campaigns`` (+ ``PATCH /api/ad-campaigns/[id]``) in
trevorotts1/blackceo-command-center (>= v4.50.0). It lands a Skill 48
Facebook/Instagram ad run on the Kanban board as ONE campaign with one card per
phase, and moves those cards through the lifecycle as the run progresses.

NON-NEGOTIABLE DESIGN RULES
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the
    ad job CONTINUES. Boarding the run is a convenience, never a gate. The ONLY
    thing that actually fails an ad job for "not on the board" is the offline
    ``_chk_board`` check (AF-FBAD-BOARD) reading ``campaign_id`` out of
    ``s7-deliver-receipt.json`` — and even that "degrade-to-ungrouped is logged,
    not silent." So every public function here returns a value (campaign_id /
    bool) and NEVER raises.

  * AUTH PARITY with the endpoint (read verbatim from the route handlers):
      - ``Authorization: Bearer <MC_API_TOKEN>``  — the global middleware layer
        (src/middleware.ts). No-op for same-origin / when MC_API_TOKEN is unset.
      - ``x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` hex — the
        per-route layer copied verbatim from /api/tasks/ingest. The endpoint
        no-ops the check when WEBHOOK_SECRET is unset (dev mode). We sign the
        EXACT bytes we send, so a configured secret matches byte-for-byte.

  * STDLIB ONLY (urllib) — zero third-party deps, mirrors ad_build_check's Kie
    balance call and the rest of the deterministic spine.

  * CREDENTIALS FROM ENV, never hardcoded; absent => fail-soft no-op.
      MISSION_CONTROL_URL   base URL of the Command Center (e.g.
                            https://<client>.zerohumanworkforce.com). Absent =>
                            board disabled (clean no-op; the run is unaffected).
      MC_API_TOKEN          long-lived bearer (middleware layer). Optional.
      WEBHOOK_SECRET        HMAC secret (per-route layer). Optional.
      CC_BOARD_TIMEOUT      per-request timeout seconds (default 8).

REQUEST CONTRACT (matched to the live endpoint — see module docstring of
src/lib/ad-campaigns.ts and src/lib/validation.ts):

  CREATE   POST {base}/api/ad-campaigns
    headers: Authorization: Bearer <MC_API_TOKEN> (if set),
             x-webhook-signature: <hmac> (if WEBHOOK_SECRET set),
             Content-Type: application/json
    body:    {job_id, show_name, owner?, department?, workspace?, agent_id?,
              money_ceiling_usd?, estimated_cost_usd?, show_date?,
              stages?: [{slug, title?}]}
    return:  201 (created) / 200 (idempotent re-call) ->
             {ok, created, campaign_id, parent_id, stages:[{slug,id,status}]}

  MOVE     PATCH {base}/api/ad-campaigns/{job_id}
    headers: same as CREATE
    body:    {stage_slug, status, reason?, actor?,
              blocked_reason?, blocked_on_human?, ask?}
    return:  200 -> {task}
    status vocabulary (CC TaskStatus): backlog | in_progress | review | blocked | done
    legal moves (CC LEGAL_TRANSITIONS): backlog->in_progress; in_progress->review;
             review->done; *->blocked; blocked->{backlog,in_progress}; done->backlog
    blocked REQUIRES blocked_reason in {decision,approval,credential,payment}
             AND a non-empty ask.

The campaign_id (== job_id) is written into
``working/checkpoints/s7-deliver-receipt.json`` so the offline AF-FBAD-BOARD
check passes whether or not the live POST succeeded against a degraded board:
when the board is reachable we use its echoed campaign_id; when it is not, we
still record the deterministic job_id (the receipt-number) and log the degrade.
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

# Mirror of the CC server's TaskStatus enum + LEGAL_TRANSITIONS map
# (src/lib/validation.ts + src/lib/task-lifecycle.ts). Kept here ONLY to walk a
# minimal legal path client-side; the server is always the final authority.
VALID_STATUSES = ("backlog", "in_progress", "review", "blocked", "done")
_LEGAL = {
    "backlog": {"in_progress", "blocked"},
    "in_progress": {"review", "blocked", "backlog"},
    "review": {"done", "in_progress", "blocked", "backlog"},
    "done": {"backlog"},
    "blocked": {"backlog", "in_progress"},
}
VALID_BLOCKED_REASONS = ("decision", "approval", "credential", "payment")

_DEFAULT_TIMEOUT = 8


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled,
    a clean no-op) when MISSION_CONTROL_URL is not set — exactly the
    INSTALL.md "graceful degradation" contract. Never raises."""
    env = env if env is not None else os.environ
    base = (env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    return {
        "base_url": base,
        "token": (env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    """Single, greppable degrade line. Board failures are logged, not silent,
    and never fatal."""
    print(f"[cc_board] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex — byte-for-
    byte parity with verifyWebhookSignature() in the route handlers. None when no
    secret (the endpoint also no-ops in that case)."""
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
# CREATE — POST /api/ad-campaigns (idempotent on job_id, server-side)
# ---------------------------------------------------------------------------
def create_campaign(
    job_id: str,
    show_name: str,
    *,
    stages: Optional[list] = None,
    owner: Optional[str] = None,
    department: Optional[str] = None,
    workspace: Optional[str] = None,
    agent_id: Optional[str] = None,
    money_ceiling_usd: Optional[float] = None,
    estimated_cost_usd: Optional[float] = None,
    show_date: Optional[str] = None,
    env: Optional[dict] = None,
) -> Optional[str]:
    """Create (or idempotently re-fetch) the ad-run campaign + stage cards.
    Returns the echoed campaign_id on success, else None (FAIL-SOFT — a None
    return never blocks the ad job; the caller falls back to the deterministic
    job_id as the receipt-number)."""
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled (no-op); run continues ungrouped.")
        return None
    if not job_id or not show_name:
        _log("create skipped — job_id/show_name missing.")
        return None

    payload: dict = {"job_id": job_id, "show_name": show_name}
    if owner:
        payload["owner"] = owner
    if department:
        payload["department"] = department
    if workspace:
        payload["workspace"] = workspace
    if agent_id:
        payload["agent_id"] = agent_id  # provenance ONLY (never assigned_agent_id)
    if isinstance(money_ceiling_usd, (int, float)):
        payload["money_ceiling_usd"] = money_ceiling_usd
    if isinstance(estimated_cost_usd, (int, float)):
        payload["estimated_cost_usd"] = estimated_cost_usd
    if show_date:
        payload["show_date"] = show_date
    # Always create an "epic" rollup stage card FIRST so the end-of-run
    # set_stage_status(job_id, "epic", "done") (ad_director closes the whole campaign
    # here) targets a REAL card, never a phantom the server never created.
    stage_list = list(stages or [])
    if not any(isinstance(s, dict) and s.get("slug") == "epic" for s in stage_list):
        stage_list.insert(0, {"slug": "epic", "title": f"{show_name} — campaign"})
    payload["stages"] = [
        {"slug": s["slug"], **({"title": s["title"]} if s.get("title") else {})}
        for s in stage_list
        if isinstance(s, dict) and s.get("slug")
    ]

    url = f"{cfg['base_url']}/api/ad-campaigns"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"create POST failed ({type(exc).__name__}: {exc}); run continues ungrouped.")
        return None
    if status in (200, 201) and isinstance(body, dict) and body.get("campaign_id"):
        _log(f"campaign {'created' if body.get('created') else 'reused'}: "
             f"campaign_id={body['campaign_id']} ({len(body.get('stages', []))} cards).")
        return str(body["campaign_id"])
    _log(f"create POST non-OK (HTTP {status}): {body}; run continues ungrouped.")
    return None


# ---------------------------------------------------------------------------
# MOVE — PATCH /api/ad-campaigns/{job_id} (one transition)
# ---------------------------------------------------------------------------
def _move_once(
    job_id: str,
    stage_slug: str,
    status: str,
    cfg: dict,
    *,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    blocked_on_human: Optional[str] = None,
    ask: Optional[str] = None,
) -> bool:
    payload: dict = {"stage_slug": stage_slug, "status": status}
    if reason:
        payload["reason"] = reason
    if actor:
        payload["actor"] = actor
    if status == "blocked":
        payload["blocked_reason"] = blocked_reason
        if blocked_on_human:
            payload["blocked_on_human"] = blocked_on_human
        payload["ask"] = ask
    url = f"{cfg['base_url']}/api/ad-campaigns/{job_id}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"move {stage_slug}->{status} failed ({type(exc).__name__}: {exc}).")
        return False
    if st == 200:
        return True
    _log(f"move {stage_slug}->{status} non-OK (HTTP {st}): {body}.")
    return False


def _legal_path(src: str, dst: str) -> Optional[list]:
    """Shortest legal status path src..dst (inclusive of dst, excluding src) over
    the CC LEGAL_TRANSITIONS map. None when unreachable. 'blocked' is reachable
    from any state in one hop. Used to walk e.g. backlog->in_progress->review->done
    rather than issue an illegal direct jump."""
    if src == dst:
        return []
    if dst == "blocked":
        return ["blocked"]
    # BFS
    from collections import deque
    q = deque([(src, [])])
    seen = {src}
    while q:
        node, path = q.popleft()
        for nxt in _LEGAL.get(node, ()):  # deterministic enough for our small map
            if nxt in seen:
                continue
            npath = path + [nxt]
            if nxt == dst:
                return npath
            seen.add(nxt)
            q.append((nxt, npath))
    return None


def set_stage_status(
    job_id: str,
    stage_slug: str,
    target: str,
    *,
    reason: Optional[str] = None,
    actor: str = "skill48-producer",
    blocked_reason: Optional[str] = None,
    blocked_on_human: Optional[str] = None,
    ask: Optional[str] = None,
    env: Optional[dict] = None,
) -> bool:
    """Drive ONE stage card to `target`, walking the minimal legal path from its
    current status (fetched via GET). FAIL-SOFT: returns False (never raises) on
    any board problem; the ad job is unaffected. For target='blocked', supply a
    blocked_reason in {decision,approval,credential,payment} and a non-empty ask
    (the endpoint rejects a blocked move without them)."""
    cfg = board_config(env)
    if cfg is None:
        return False
    if target not in VALID_STATUSES:
        _log(f"set_stage_status refused — invalid target {target!r}.")
        return False
    if target == "blocked":
        if blocked_reason not in VALID_BLOCKED_REASONS or not (ask or "").strip():
            _log("set_stage_status(blocked) refused — needs blocked_reason "
                 "in {decision,approval,credential,payment} + non-empty ask.")
            return False

    current = _current_status(job_id, stage_slug, cfg)
    if current is None:
        # Card status unknown (board unreachable / card missing): attempt a single
        # direct move and let the server reject an illegal jump (fail-soft).
        return _move_once(job_id, stage_slug, target, cfg, reason=reason, actor=actor,
                          blocked_reason=blocked_reason, blocked_on_human=blocked_on_human,
                          ask=ask)
    path = _legal_path(current, target)
    if path is None:
        _log(f"no legal path {current}->{target} for {stage_slug}; skipping.")
        return False
    ok = True
    for i, step in enumerate(path):
        last = i == len(path) - 1
        ok = _move_once(
            job_id, stage_slug, step, cfg,
            reason=reason if last else f"auto-step toward {target}",
            actor=actor,
            blocked_reason=blocked_reason if step == "blocked" else None,
            blocked_on_human=blocked_on_human if step == "blocked" else None,
            ask=ask if step == "blocked" else None,
        )
        if not ok:
            break
    return ok


def _current_status(job_id: str, stage_slug: str, cfg: dict) -> Optional[str]:
    """GET the run and return one stage card's status, or None when the board is
    unreachable or the card is absent."""
    url = f"{cfg['base_url']}/api/ad-campaigns/{job_id}"
    raw_body = b""
    headers = {"Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        _log(f"status GET failed for {job_id} ({type(exc).__name__}: {exc}).")
        return None
    for card in (body.get("cards") or []) if isinstance(body, dict) else []:
        if isinstance(card, dict) and card.get("stage_slug") == stage_slug:
            return card.get("status")
    return None


# ---------------------------------------------------------------------------
# Receipt stamping — write campaign_id into s7-deliver-receipt.json so the
# offline AF-FBAD-BOARD check passes (degrade-to-ungrouped is logged, not silent).
# ---------------------------------------------------------------------------
def _deliver_receipt_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "s7-deliver-receipt.json"


def stamp_campaign_id(run_dir: Path, campaign_id: str) -> bool:
    """Merge campaign_id into s7-deliver-receipt.json without disturbing other
    fields. Atomic replace. Returns True on success. Never raises."""
    if not campaign_id:
        return False
    p = _deliver_receipt_path(run_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        receipt = {}
        if p.exists():
            try:
                receipt = json.loads(p.read_text())
                if not isinstance(receipt, dict):
                    receipt = {}
            except (json.JSONDecodeError, OSError):
                receipt = {}
        receipt["campaign_id"] = campaign_id
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(receipt, indent=2))
        os.replace(tmp, p)
        return True
    except OSError as exc:
        _log(f"stamp_campaign_id failed ({exc}).")
        return False
