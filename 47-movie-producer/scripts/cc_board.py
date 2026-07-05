#!/usr/bin/env python3
"""
cc_board.py — Skill 47 (Movie Producer) PRODUCER-SIDE Command Center board caller
(FAIL-SOFT). Ported from Skill 48's cc_board.py (FIX-S36-40) so a video production
RUN actually lands on the Kanban board — one campaign with one card per DMAIC
phase — instead of finishing off-board with V-CONTROL "done" decided only by
self-written receipts.

WHY THIS EXISTS (FIX-S36-40)
  Before this file the movie-producer spine attested phases to a local process
  manifest but nothing carded the run on the Command Center, and there was no
  caller that walked the QC `review` column — so an enforcing board would strand
  every run at in_progress and a lenient one would let V-CONTROL jump straight to
  `done`, skipping review. This is the producer half that fixes that: it posts 5
  stage cards and moves each attested phase card to its target by walking the
  LEGAL status path (in_progress -> review -> done), so the QC `review` column is
  never skipped. The board is a CONVENIENCE, never a gate.

NON-NEGOTIABLE DESIGN RULES (identical contract to Skill 48's cc_board)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the
    production job CONTINUES. Every public function returns a value (campaign_id /
    bool) and NEVER raises.
  * LEGAL PATH ONLY. Cards move backlog->in_progress->review->done via the CC
    LEGAL_TRANSITIONS map; the client never issues an illegal in_progress->done
    jump that skips the QC `review` column.
  * STDLIB ONLY (urllib/hmac/hashlib/json) — zero third-party deps, mirrors the
    rest of the deterministic spine.
  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => clean no-op.
      MISSION_CONTROL_URL   base URL of the Command Center. Absent => board
                            disabled (clean no-op; the run is unaffected).
      MC_API_TOKEN          long-lived bearer (middleware layer). Optional.
      WEBHOOK_SECRET        HMAC secret (per-route layer). Optional.
      CC_BOARD_TIMEOUT      per-request timeout seconds (default 8).
      MC_CAMPAIGN_PATH      campaign resource path (default /api/campaigns) —
                            overridable so the same server family can serve video
                            runs without editing this file.

The campaign_id (== job_id server-side) and the finished MP4 path are stamped
into working/checkpoints/render-receipt.json so the run's board grouping + final
deliverable are recorded whether or not the live POST landed (degrade-to-
ungrouped is LOGGED, not silent).
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

# Mirror of the CC server's TaskStatus enum + LEGAL_TRANSITIONS map. Kept here
# ONLY to walk a minimal legal path client-side; the server is the final authority.
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
_DEFAULT_CAMPAIGN_PATH = "/api/campaigns"


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled, a
    clean no-op) when MISSION_CONTROL_URL is not set. Never raises."""
    env = env if env is not None else os.environ
    base = (env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    path = (env.get("MC_CAMPAIGN_PATH") or _DEFAULT_CAMPAIGN_PATH).strip()
    if not path.startswith("/"):
        path = "/" + path
    return {
        "base_url": base,
        "campaign_path": path.rstrip("/"),
        "token": (env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    """Single, greppable degrade line. Board failures are logged, not silent, and
    never fatal."""
    print(f"[cc_board] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex. None when no
    secret (the endpoint also no-ops in that case)."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: Optional[dict], cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None). Raises
    only urllib/OS errors, which the public callers catch (fail-soft)."""
    raw_body = b"" if payload is None else \
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    req = urllib.request.Request(url, data=(raw_body if payload is not None else None),
                                 headers=headers, method=method)
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
# CREATE — POST {campaign_path} (idempotent on job_id, server-side)
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
    """Create (or idempotently re-fetch) the production campaign + stage cards.
    Returns the echoed campaign_id on success, else None (FAIL-SOFT)."""
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
    if stages:
        payload["stages"] = [
            {"slug": s["slug"], **({"title": s["title"]} if s.get("title") else {})}
            for s in stages
            if isinstance(s, dict) and s.get("slug")
        ]

    url = f"{cfg['base_url']}{cfg['campaign_path']}"
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
# MOVE — PATCH {campaign_path}/{job_id} (one transition)
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
    url = f"{cfg['base_url']}{cfg['campaign_path']}/{job_id}"
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
    """Shortest legal status path src..dst (inclusive of dst, excluding src) over the
    CC LEGAL_TRANSITIONS map. None when unreachable. 'blocked' is reachable from any
    state in one hop. Walks e.g. in_progress->review->done rather than an illegal
    direct jump that would SKIP the QC review column."""
    if src == dst:
        return []
    if dst == "blocked":
        return ["blocked"]
    from collections import deque
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


def set_stage_status(
    job_id: str,
    stage_slug: str,
    target: str,
    *,
    reason: Optional[str] = None,
    actor: str = "skill47-movie-producer",
    blocked_reason: Optional[str] = None,
    blocked_on_human: Optional[str] = None,
    ask: Optional[str] = None,
    env: Optional[dict] = None,
) -> bool:
    """Drive ONE stage card to `target`, walking the minimal legal path from its
    current status (fetched via GET). FAIL-SOFT: returns False (never raises) on any
    board problem; the production job is unaffected. For target='blocked', supply a
    blocked_reason in {decision,approval,credential,payment} and a non-empty ask."""
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
    url = f"{cfg['base_url']}{cfg['campaign_path']}/{job_id}"
    try:
        st, body = _request("GET", url, None, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"status GET failed for {job_id} ({type(exc).__name__}: {exc}).")
        return None
    if st != 200 or not isinstance(body, dict):
        return None
    for card in (body.get("cards") or body.get("stages") or []):
        if isinstance(card, dict) and card.get("stage_slug") == stage_slug:
            return card.get("status")
    return None


# ---------------------------------------------------------------------------
# Receipt stamping — write campaign_id + the finished MP4 path into
# render-receipt.json so the run's board grouping + deliverable are recorded
# (degrade-to-ungrouped is LOGGED, not silent). MERGE-IF-EXISTS only: never mint a
# premature render receipt before V-IMPROVE has produced one.
# ---------------------------------------------------------------------------
def _render_receipt_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "render-receipt.json"


def stamp_receipt(run_dir: Path, *, campaign_id: Optional[str] = None,
                  final_mp4_path: Optional[str] = None) -> bool:
    """Merge campaign_id and/or final_mp4_path into an EXISTING render-receipt.json
    without disturbing other fields. Atomic replace. Returns True when a field was
    written. Never raises; never creates the receipt if it does not already exist."""
    if not campaign_id and not final_mp4_path:
        return False
    p = _render_receipt_path(run_dir)
    if not p.exists():
        _log("stamp_receipt skipped — render-receipt.json not present yet "
             "(will not mint a premature receipt).")
        return False
    try:
        try:
            receipt = json.loads(p.read_text())
            if not isinstance(receipt, dict):
                return False
        except (json.JSONDecodeError, OSError):
            return False
        changed = False
        if campaign_id and receipt.get("campaign_id") != campaign_id:
            receipt["campaign_id"] = campaign_id
            changed = True
        if final_mp4_path and not str(receipt.get("final_mp4_path") or "").strip():
            receipt["final_mp4_path"] = final_mp4_path
            changed = True
        if not changed:
            return False
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(receipt, indent=2))
        os.replace(tmp, p)
        return True
    except OSError as exc:
        _log(f"stamp_receipt failed ({exc}).")
        return False
