#!/usr/bin/env python3
"""
cc_board.py — Skill 69 (archify) PRODUCER-SIDE Command Center board caller
(FAIL-SOFT).

This is the producer half of the board hookup whose server half is
``POST /api/archify-runs`` (+ ``PATCH /api/archify-runs/[id]``) in
trevorotts1/blackceo-command-center. It lands an archify diagram run on the
Kanban board as ONE run grouping with one card per lifecycle phase, and moves
those cards through the lifecycle as the run progresses — so a run that renders
off-board still leaves a truthful, visible trail (received -> authoring ->
validate -> render -> deliver) instead of a silently empty lane.

WHY THIS EXISTS (WS-D)
  archify is a zero-dependency Node CLI (``69-archify/bin/archify.mjs``: doctor,
  validate, render) that authors, validates and renders JSON-IR diagrams.
  Nothing carded those runs on the Command Center, so a run was invisible to the
  operator: no grouping, no per-phase state, and no "blocked with an ask" card
  when a validate or render failed. This file is the fail-soft producer caller
  that fixes that. The board is a CONVENIENCE, never a gate.

NON-NEGOTIABLE DESIGN RULES (identical contract to the fleet cc_board.py callers
in Skill 47 / Skill 48 / Skill 58)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the
    archify job CONTINUES. Every public function here returns a value (run id /
    phase / bool / None) and NEVER raises. The CLI exits 0 on every board
    problem; only a usage error (missing or invalid args) exits 2.
  * LEGAL PATH ONLY. Cards move backlog->in_progress->review->done via the CC
    LEGAL_TRANSITIONS map; the client never issues an illegal jump that skips a
    column. The server is always the final authority.
  * STDLIB ONLY (urllib/hmac/hashlib/json/argparse) — zero third-party deps,
    mirrors the rest of the deterministic spine. ``selftest`` proves it offline
    by parsing this file's own AST.
  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => clean no-op.
      MISSION_CONTROL_URL   base URL of the Command Center (e.g.
                            https://<client>.zerohumanworkforce.com). Absent =>
                            board disabled (clean no-op; the run is unaffected).
      MC_API_TOKEN          long-lived bearer (middleware layer). Optional.
      WEBHOOK_SECRET        HMAC secret (per-route layer). Optional.
      CC_BOARD_TIMEOUT      per-request timeout seconds (default 8).
      MC_ARCHIFY_PATH       run resource path (default /api/archify-runs) —
                            overridable so a server-side rename does not require
                            editing this file.
      CC_BOARD_STATE_FILE   run_id -> board id map (default
                            ~/.openclaw/archify/board-map.json, 0600 where the
                            filesystem allows it).
  * AUTH PARITY with the endpoints (read verbatim from the route handlers):
      - ``Authorization: Bearer <MC_API_TOKEN>`` — the global middleware layer
        (src/middleware.ts). No-op for same-origin / when MC_API_TOKEN is unset.
      - ``x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` hex — the
        per-route layer. The endpoint no-ops the check when WEBHOOK_SECRET is
        unset (dev mode). We sign the EXACT bytes we send, so a configured
        secret matches byte-for-byte.
  * IDEMPOTENT. The caller's own run id (``run_id``) IS the external /
    idempotency id: it is sent on CREATE, so a retried call cannot
    double-create a grouping on the board. Whatever id the server echoes back is
    propagated and persisted, and later PATCHes address the server's id when
    known (falling back to the external run_id, which the server keys on).

ARCHIFY LIFECYCLE (module-level, ordered — ``PHASES``)
  received -> authoring -> validate -> render -> deliver
  One card per phase, created together with the run grouping. ``advance_run()``
  is the phase-by-phase helper: it closes every phase before the target and
  opens the target, so the board walks the lifecycle without the caller
  hand-sequencing PATCHes.

ARCHIFY DIAGRAM TYPES (``DIAGRAM_TYPES``)
  architecture | workflow | sequence | dataflow | lifecycle
  The type is sent as its own field AND embedded in the run description, so a
  card can be labelled with it.

REQUEST CONTRACT (the Command Center agent implements the server half)

  CREATE   POST {base}/api/archify-runs
    headers: Authorization: Bearer <MC_API_TOKEN> (if set),
             x-webhook-signature: <hmac> (if WEBHOOK_SECRET set),
             Content-Type: application/json
    body:    {run_id, idempotency_key, title, diagram_type, description,
              phases: [{slug, title}],
              source_path?, quality?,
              owner?, department?, workspace?, agent_id?}
    return:  201 (created) / 200 (idempotent re-call) ->
             {ok, created, run_id, grouping_id?, phases: [{slug, id, status}]}
             The producer is LIBERAL in what it reads and CANONICAL in what it
             sends: the echoed id may arrive as run_id / archify_run_id /
             grouping_id / id / task_id / campaign_id / parent_id, at the top
             level or nested under run / data / grouping / result. The phase
             array may arrive as phases / stages / cards.

  MOVE     PATCH {base}/api/archify-runs/{id}
    headers: same as CREATE
    body:    {phase, status, reason?, actor?, note?,
              blocked_reason?, blocked_on_human?, ask?}
    return:  200 -> {task} / the updated run
    status vocabulary (CC TaskStatus): backlog | in_progress | review | blocked | done
    legal moves (CC LEGAL_TRANSITIONS): backlog->in_progress; in_progress->review;
             review->done; *->blocked; blocked->{backlog,in_progress}; done->backlog
    blocked REQUIRES blocked_reason in {decision,approval,credential,payment}
             AND a non-empty ask.

  READ     GET {base}/api/archify-runs/{id}
    headers: same as CREATE (HMAC over the empty body)
    return:  200 -> the run object (carries per-phase `status`)
    Used to walk the minimal LEGAL path and to resolve the current phase.

CLI (run standalone for a smoke test; every board problem exits 0)
  selftest | --selftest   offline self-check, NO network; exit 0 = contract holds
  run-begin --run-id --diagram-type [--title] [--source] [--quality] [--owner]
            [--department] [--workspace] [--agent-id]
  phase     --run-id --phase --status [--note] [--reason]
  advance   --run-id [--to-phase] [--note]
  close     --run-id --status done|blocked [--phase] [--note] [--reason]
            [--blocked-on-human] [--ask]
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# The archify lifecycle, ordered. One board card per phase, created together as
# ONE run grouping; ``advance_run()`` walks it phase by phase. This tuple is the
# single client-side source of truth for the phase vocabulary.
PHASES = ("received", "authoring", "validate", "render", "deliver")

# The five diagram types archify produces (architecture / workflow / sequence /
# dataflow / lifecycle). The type labels the run and its cards.
DIAGRAM_TYPES = ("architecture", "workflow", "sequence", "dataflow", "lifecycle")

# Mirror of the CC server's TaskStatus enum + LEGAL_TRANSITIONS map. Kept here
# ONLY to walk a minimal legal path client-side; the server is the final
# authority.
VALID_STATUSES = ("backlog", "in_progress", "review", "blocked", "done")
_LEGAL = {
    "backlog": {"in_progress", "blocked"},
    "in_progress": {"review", "blocked", "backlog"},
    "review": {"done", "in_progress", "blocked", "backlog"},
    "done": {"backlog"},
    "blocked": {"backlog", "in_progress"},
}
VALID_BLOCKED_REASONS = ("decision", "approval", "credential", "payment")

# Human-facing card titles, one per lifecycle phase.
_PHASE_TITLES = {
    "received": "Received",
    "authoring": "Authoring",
    "validate": "Validate",
    "render": "Render",
    "deliver": "Deliver",
}

_DEFAULT_TIMEOUT = 8
_DEFAULT_RUN_PATH = "/api/archify-runs"
_DEFAULT_ACTOR = "skill69-archify"

# Response keys the server's echoed run/grouping id may arrive under (read
# liberally — the server half is implemented in parallel).
_ID_KEYS = ("run_id", "archify_run_id", "grouping_id", "id", "task_id",
            "campaign_id", "parent_id")
_ID_CONTAINERS = ("run", "data", "grouping", "result")
_PHASE_ARRAY_KEYS = ("phases", "stages", "cards")
_PHASE_SLUG_KEYS = ("slug", "phase", "phase_slug", "stage_slug", "name")

_STATE_FILENAME = "board-map.json"
_STATE_SUBDIR = ("archify",)


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled,
    a clean no-op) when MISSION_CONTROL_URL is not set. Never raises."""
    env = env if env is not None else os.environ
    base = (env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    path = (env.get("MC_ARCHIFY_PATH") or _DEFAULT_RUN_PATH).strip()
    if not path.startswith("/"):
        path = "/" + path
    return {
        "base_url": base,
        "run_path": path.rstrip("/"),
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


def _request(method: str, url: str, payload: Optional[dict], cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None).
    Raises only urllib/OS errors, which the public callers catch (fail-soft)."""
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


def _request_with_retry(method: str, url: str, payload: Optional[dict], cfg: dict):
    """One signed JSON request with ONE retry on NETWORK error only (never on a
    4xx/5xx — a refused transition must not be replayed). CREATE is idempotent on
    the external run_id and MOVEs are legal-path walked, so a single retry is
    safe. Returns (status_code, parsed_json_or_None)."""
    try:
        return _request(method, url, payload, cfg)
    except (urllib.error.URLError, OSError) as exc:
        _log(f"{method} {url} network error ({type(exc).__name__}: {exc}); retrying once.")
        return _request(method, url, payload, cfg)


# ---------------------------------------------------------------------------
# State persistence — run_id <-> board id mapping (0600), so `phase` / `advance`
# / `close` find the grouping in a later process invocation. Fail-soft: an
# unwritable state file degrades to "address the server by the external
# run_id", which the server keys on idempotently.
# ---------------------------------------------------------------------------
def _state_file() -> Optional[Path]:
    """The board-map path: CC_BOARD_STATE_FILE override, else
    ~/.openclaw/archify/board-map.json. None when no home directory resolves."""
    override = (os.environ.get("CC_BOARD_STATE_FILE") or "").strip()
    if override:
        return Path(override)
    try:
        return Path.home().joinpath(".openclaw", *_STATE_SUBDIR, _STATE_FILENAME)
    except (RuntimeError, OSError):
        return None


def _load_map() -> dict:
    """Load the board-map state file. Returns an empty dict on any error. Never
    raises."""
    path = _state_file()
    if path is None:
        return {}
    try:
        if path.exists():
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        _log(f"board-map load failed ({exc}); starting with an empty map.")
    return {}


def _chmod(path: Path, mode: int, what: str) -> None:
    """Best-effort permission hardening. A chmod the filesystem refuses (e.g. a
    caller-supplied CC_BOARD_STATE_FILE inside a shared directory such as /tmp,
    which this process does not own) is LOGGED and IGNORED — persisting the
    run_id -> board id mapping matters more than the mode bits, and losing the
    mapping must never look like a board failure. Never raises."""
    try:
        path.chmod(mode)
    except OSError as exc:
        _log(f"could not chmod {what} to {oct(mode)} ({exc}); continuing.")


def _save_map(data: dict) -> None:
    """Atomically write the board-map state file (0600 where the filesystem
    allows it). Never raises."""
    path = _state_file()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log(f"board-map directory unavailable ({exc}); state not persisted.")
        return
    _chmod(path.parent, 0o700, "state dir")  # ensure the directory is private
    try:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        _chmod(tmp, 0o600, "state file")
        os.replace(tmp, path)
    except OSError as exc:
        _log(f"board-map save failed ({exc}).")


def _get_board_id(run_id: str) -> Optional[str]:
    """Look up the server's board id for an external run_id. None when unmapped.
    Never raises."""
    mapped = _load_map().get(run_id)
    return str(mapped) if isinstance(mapped, (str, int)) and str(mapped).strip() else None


def _set_board_id(run_id: str, board_id: str) -> None:
    """Persist the run_id -> board id mapping. Never raises."""
    data = _load_map()
    data[run_id] = board_id
    _save_map(data)


def board_id_for(run_id: str, env: Optional[dict] = None) -> str:
    """The id to address PATCH/GET with: the server-echoed board id when the
    mapping is known, else the external run_id itself (the server keys on it
    idempotently). Always returns a string; never raises; never touches the
    network."""
    return _get_board_id(run_id) or (run_id or "")


# ---------------------------------------------------------------------------
# PURE payload builders — no network, no env, no state. The offline self-check
# proves these directly.
# ---------------------------------------------------------------------------
def phase_index(phase: str) -> Optional[int]:
    """Position of ``phase`` in the archify lifecycle, or None when unknown.
    Never raises."""
    try:
        return PHASES.index(phase)
    except (ValueError, TypeError):
        return None


def next_phase(phase: str) -> Optional[str]:
    """The phase after ``phase``, or None when it is the terminal phase (or
    unknown). Never raises."""
    idx = phase_index(phase)
    if idx is None or idx + 1 >= len(PHASES):
        return None
    return PHASES[idx + 1]


def build_phases(label: Optional[str] = None) -> list:
    """The one-card-per-phase array sent on CREATE:
    ``[{"slug": "received", "title": "<label> — Received"}, ...]`` in lifecycle
    order. Pure: no network, no env, no state."""
    prefix = (label or "archify").strip() or "archify"
    return [{"slug": slug, "title": f"{prefix} — {_PHASE_TITLES[slug]}"} for slug in PHASES]


def _default_description(run_id: str, diagram_type: str,
                         source_path: Optional[str] = None,
                         quality: Optional[str] = None) -> str:
    """Run description. The DIAGRAM TYPE is always present (so a card is
    labelled with it) alongside the lifecycle the cards walk."""
    lines = [
        f"archify run {run_id}",
        f"diagram_type: {diagram_type}",
        f"lifecycle: {' -> '.join(PHASES)}",
    ]
    if source_path:
        lines.append(f"source: {source_path}")
    if quality:
        lines.append(f"quality: {quality}")
    return "\n".join(lines)


def build_run_payload(
    run_id: str,
    *,
    diagram_type: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    source_path: Optional[str] = None,
    quality: Optional[str] = None,
    owner: Optional[str] = None,
    department: Optional[str] = None,
    workspace: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> dict:
    """Build the CREATE body for ONE archify run grouping with one card per
    phase. Pure: no network, no env, no state, never raises.

    ``run_id`` is the external/idempotency id: it is sent as ``run_id`` AND as
    ``idempotency_key`` so a retried CREATE cannot double-create a grouping.
    Optional fields are omitted entirely when not supplied (never sent empty)."""
    dt = (diagram_type or "").strip().lower()
    rid = (run_id or "").strip()
    resolved_title = (title or "").strip() or f"archify {dt or 'diagram'} — {rid}"
    payload: dict = {
        "run_id": rid,
        "idempotency_key": f"archify:run:{rid}",
        "title": resolved_title,
        "diagram_type": dt,
        "description": (description or "").strip()
        or _default_description(rid, dt, source_path, quality),
        "phases": build_phases(resolved_title),
    }
    if source_path:
        payload["source_path"] = source_path
    if quality:
        payload["quality"] = quality
    if owner:
        payload["owner"] = owner
    if department:
        payload["department"] = department
    if workspace:
        payload["workspace"] = workspace
    if agent_id:
        payload["agent_id"] = agent_id  # provenance ONLY (never assigned_agent_id)
    return payload


def build_move_payload(
    phase: str,
    status: str,
    *,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
    note: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    blocked_on_human: Optional[str] = None,
    ask: Optional[str] = None,
) -> dict:
    """Build the MOVE body for one phase card. Pure: no network, no env, no
    state, never raises. A ``blocked`` move carries the full CC triad
    (blocked_reason + blocked_on_human + ask) because the endpoint rejects a
    blocked move without a reason and a non-empty ask."""
    payload: dict = {"phase_slug": phase, "status": status}
    if reason:
        payload["reason"] = reason
    if actor:
        payload["actor"] = actor
    if note:
        payload["note"] = note
    if status == "blocked":
        payload["blocked_reason"] = blocked_reason
        if blocked_on_human:
            payload["blocked_on_human"] = blocked_on_human
        payload["ask"] = ask
    return payload


# ---------------------------------------------------------------------------
# Response readers (liberal — the server half is implemented in parallel)
# ---------------------------------------------------------------------------
def _extract_run_id(body) -> Optional[str]:
    """Pull the echoed run/grouping id out of a CREATE response. Returns None
    when no id is present. Never raises."""
    if not isinstance(body, dict):
        return None
    for key in _ID_KEYS:
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, int):
            return str(val)
    for key in _ID_CONTAINERS:
        inner = body.get(key)
        if isinstance(inner, dict):
            found = _extract_run_id(inner)
            if found:
                return found
    return None


def _phase_entries(body) -> list:
    """The per-phase card array from a run object, under any accepted key.
    Never raises."""
    if not isinstance(body, dict):
        return []
    for key in _PHASE_ARRAY_KEYS:
        val = body.get(key)
        if isinstance(val, list):
            return [e for e in val if isinstance(e, dict)]
    return []


def _entry_slug(entry: dict) -> Optional[str]:
    """The phase slug of one card entry, under any accepted key. Never raises."""
    if not isinstance(entry, dict):
        return None
    for key in _PHASE_SLUG_KEYS:
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _phase_states(board_id: str, cfg: dict) -> dict:
    """GET the run and return {phase_slug: status}. Empty dict on any board
    problem (unreachable, non-200, unparsable) — never raises."""
    url = f"{cfg['base_url']}{cfg['run_path']}/{board_id}"
    try:
        st, body = _request_with_retry("GET", url, None, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"state GET failed for {board_id} ({type(exc).__name__}: {exc}).")
        return {}
    if st != 200:
        _log(f"state GET non-OK for {board_id} (HTTP {st}).")
        return {}
    states: dict = {}
    for entry in _phase_entries(body):
        slug = _entry_slug(entry)
        status = entry.get("status")
        if slug and isinstance(status, str):
            states[slug] = status
    return states


# ---------------------------------------------------------------------------
# CREATE — POST {run_path} (idempotent on run_id, server-side)
# ---------------------------------------------------------------------------
def create_run(
    run_id: str,
    *,
    diagram_type: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    source_path: Optional[str] = None,
    quality: Optional[str] = None,
    owner: Optional[str] = None,
    department: Optional[str] = None,
    workspace: Optional[str] = None,
    agent_id: Optional[str] = None,
    env: Optional[dict] = None,
) -> Optional[str]:
    """Create (or idempotently re-fetch) the archify run grouping + one card per
    lifecycle phase. Returns the id the server echoed on success, else None
    (FAIL-SOFT — a None return never blocks the archify job)."""
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled (no-op); run continues unboarded.")
        return None
    if not (run_id or "").strip():
        _log("create skipped — run_id missing.")
        return None
    if not (diagram_type or "").strip():
        _log("create skipped — diagram_type missing.")
        return None
    if diagram_type.strip().lower() not in DIAGRAM_TYPES:
        _log(f"warning — diagram_type {diagram_type!r} is not one of "
             f"{list(DIAGRAM_TYPES)}; sending it anyway (the board is a view, "
             f"the server is the authority).")

    payload = build_run_payload(
        run_id, diagram_type=diagram_type, title=title, description=description,
        source_path=source_path, quality=quality, owner=owner,
        department=department, workspace=workspace, agent_id=agent_id,
    )
    url = f"{cfg['base_url']}{cfg['run_path']}"
    try:
        status, body = _request_with_retry("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"create POST failed ({type(exc).__name__}: {exc}); run continues unboarded.")
        return None

    if status in (200, 201):
        board_id = _extract_run_id(body)
        if board_id:
            _set_board_id(run_id, board_id)
            reused = isinstance(body, dict) and body.get("created") is False
            _log(f"run grouping {'reused' if reused else 'created'}: board_id={board_id} "
                 f"({len(_phase_entries(body))} cards, run_id={run_id}, "
                 f"diagram_type={payload['diagram_type']}).")
            return board_id
        _log(f"create POST OK (HTTP {status}) but the server echoed no run id: {body}; "
             f"run continues unboarded (fail-soft).")
        return None

    _log(f"create POST non-OK (HTTP {status}): {body}; run continues unboarded.")
    return None


# ---------------------------------------------------------------------------
# READ — GET {run_path}/{id}
# ---------------------------------------------------------------------------
def get_run(run_id: str, *, env: Optional[dict] = None) -> Optional[dict]:
    """Read one archify run grouping. Returns the parsed run object on HTTP 200,
    else None (board disabled, unreachable, non-200, unparsable). FAIL-SOFT:
    never raises."""
    cfg = board_config(env)
    if cfg is None:
        return None
    if not (run_id or "").strip():
        return None
    board_id = board_id_for(run_id, env=env)
    url = f"{cfg['base_url']}{cfg['run_path']}/{board_id}"
    try:
        st, body = _request_with_retry("GET", url, None, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"GET run {run_id} failed ({type(exc).__name__}: {exc}).")
        return None
    if st == 200 and isinstance(body, dict):
        return body
    _log(f"GET run {run_id} non-OK (HTTP {st}): {body}.")
    return None


def phase_status(run_id: str, phase: str, *, env: Optional[dict] = None) -> Optional[str]:
    """One phase card's current status, or None when the board is disabled,
    unreachable, or the card is absent. FAIL-SOFT: never raises."""
    cfg = board_config(env)
    if cfg is None:
        return None
    if not (run_id or "").strip() or not (phase or "").strip():
        return None
    return _phase_states(board_id_for(run_id, env=env), cfg).get(phase)


def current_phase(run_id: str, *, env: Optional[dict] = None) -> Optional[str]:
    """The run's current phase: the FIRST lifecycle phase not yet ``done``.
    Returns None when the board is disabled/unreachable, or when every phase is
    already done. FAIL-SOFT: never raises."""
    cfg = board_config(env)
    if cfg is None:
        return None
    if not (run_id or "").strip():
        return None
    states = _phase_states(board_id_for(run_id, env=env), cfg)
    if not states:
        return None
    for phase in PHASES:
        if states.get(phase) != "done":
            return phase
    return None


# ---------------------------------------------------------------------------
# MOVE — PATCH {run_path}/{id} (one transition)
# ---------------------------------------------------------------------------
def _move_once(
    board_id: str,
    phase: str,
    status: str,
    cfg: dict,
    *,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
    note: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    blocked_on_human: Optional[str] = None,
    ask: Optional[str] = None,
) -> bool:
    """PATCH ONE phase card to ONE status. FAIL-SOFT: returns False (never
    raises) on any board problem."""
    payload = build_move_payload(
        phase, status, reason=reason, actor=actor, note=note,
        blocked_reason=blocked_reason, blocked_on_human=blocked_on_human, ask=ask,
    )
    url = f"{cfg['base_url']}{cfg['run_path']}/{board_id}"
    try:
        st, body = _request_with_retry("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"move {phase}->{status} failed ({type(exc).__name__}: {exc}).")
        return False
    if st == 200:
        return True
    _log(f"move {phase}->{status} non-OK (HTTP {st}): {body}.")
    return False


def _legal_path(src: str, dst: str) -> Optional[list]:
    """Shortest legal status path src..dst (inclusive of dst, excluding src) over
    the CC LEGAL_TRANSITIONS map. None when unreachable. 'blocked' is reachable
    from any state in one hop. Walks e.g. backlog->in_progress->review->done
    rather than issuing an illegal direct jump."""
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


def set_phase_status(
    run_id: str,
    phase: str,
    target: str,
    *,
    reason: Optional[str] = None,
    actor: str = _DEFAULT_ACTOR,
    note: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    blocked_on_human: Optional[str] = None,
    ask: Optional[str] = None,
    env: Optional[dict] = None,
) -> bool:
    """Drive ONE phase card to ``target``, walking the minimal legal path from
    its current status (read via GET). FAIL-SOFT: returns False (never raises)
    on any board problem; the archify job is unaffected. For target='blocked',
    supply a blocked_reason in {decision,approval,credential,payment} and a
    non-empty ask (the endpoint rejects a blocked move without them)."""
    cfg = board_config(env)
    if cfg is None:
        return False
    if not (run_id or "").strip():
        _log("set_phase_status skipped — run_id missing.")
        return False
    if phase not in PHASES:
        _log(f"set_phase_status refused — unknown phase {phase!r} "
             f"(valid: {list(PHASES)}).")
        return False
    if target not in VALID_STATUSES:
        _log(f"set_phase_status refused — invalid target {target!r}.")
        return False
    if target == "blocked":
        if blocked_reason not in VALID_BLOCKED_REASONS or not (ask or "").strip():
            _log("set_phase_status(blocked) refused — needs blocked_reason "
                 "in {decision,approval,credential,payment} + non-empty ask.")
            return False

    board_id = board_id_for(run_id, env=env)
    current = phase_status(run_id, phase, env=env)
    if current is None:
        # Card status unknown (board unreachable / card missing): attempt a single
        # direct move and let the server reject an illegal jump (fail-soft).
        return _move_once(board_id, phase, target, cfg, reason=reason, actor=actor,
                          note=note, blocked_reason=blocked_reason,
                          blocked_on_human=blocked_on_human, ask=ask)
    path = _legal_path(current, target)
    if path is None:
        _log(f"no legal path {current}->{target} for phase {phase}; skipping.")
        return False
    ok = True
    for i, step in enumerate(path):
        last = i == len(path) - 1
        ok = _move_once(
            board_id, phase, step, cfg,
            reason=reason if last else f"auto-step toward {target}",
            actor=actor,
            note=note if last else None,
            blocked_reason=blocked_reason if step == "blocked" else None,
            blocked_on_human=blocked_on_human if step == "blocked" else None,
            ask=ask if step == "blocked" else None,
        )
        if not ok:
            break
    return ok


def advance_run(
    run_id: str,
    *,
    to_phase: Optional[str] = None,
    note: Optional[str] = None,
    actor: str = _DEFAULT_ACTOR,
    env: Optional[dict] = None,
) -> Optional[str]:
    """Advance a run PHASE BY PHASE. Returns the phase advanced to, else None
    (FAIL-SOFT — a None return never blocks the archify job).

    With ``to_phase`` given: every phase strictly before it is closed (``done``)
    and the target is opened (``in_progress``). Without ``to_phase``: the next
    phase after the run's current one is opened, and — when the current phase is
    the terminal ``deliver`` — ``deliver`` is closed instead (the run is done).
    ``deliver`` is therefore both "advanced to" and "closed" without ambiguity.
    """
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled (no-op); run continues unboarded.")
        return None
    if not (run_id or "").strip():
        _log("advance skipped — run_id missing.")
        return None

    target = (to_phase or "").strip() or None
    if target is not None and target not in PHASES:
        _log(f"advance refused — unknown target phase {target!r} "
             f"(valid: {list(PHASES)}).")
        return None

    states = _phase_states(board_id_for(run_id, env=env), cfg)

    if target is None:
        cur = None
        for phase in PHASES:
            if states.get(phase) != "done":
                cur = phase
                break
        if cur is None:
            if states:
                _log(f"advance no-op — every phase is already done for run {run_id}.")
            else:
                _log(f"advance no-op — no readable phase state for run {run_id} "
                     f"(board disabled, unreachable, or grouping missing).")
            return None
        nxt = next_phase(cur)
        if nxt is None:
            # Terminal phase: advancing the lifecycle means CLOSING it.
            if not set_phase_status(run_id, cur, "done", reason=note, actor=actor, env=env):
                _log(f"advance stopped — could not close terminal phase {cur!r}.")
                return None
            _log(f"run {run_id} complete — terminal phase {cur!r} closed.")
            return cur
        target = nxt

    # Close every phase strictly before the target, then open the target.
    for prior in PHASES[:PHASES.index(target)]:
        if states.get(prior) == "done":
            continue
        if not set_phase_status(run_id, prior, "done", actor=actor,
                                reason=f"auto-complete before phase {target}",
                                env=env):
            _log(f"advance stopped — could not close phase {prior!r}.")
            return None
    if states.get(target) == "in_progress":
        _log(f"advance no-op — phase {target!r} is already in_progress for run {run_id}.")
        return target
    if not set_phase_status(run_id, target, "in_progress", reason=note, actor=actor, env=env):
        _log(f"advance stopped — could not open phase {target!r}.")
        return None
    _log(f"run {run_id} advanced to phase {target!r}.")
    return target


# ---------------------------------------------------------------------------
# OFFLINE SELF-CHECK — no network, no credentials, no state written.
# ---------------------------------------------------------------------------
_ALLOWED_IMPORT_ROOTS = {
    "__future__", "argparse", "ast", "collections", "hashlib", "hmac", "json",
    "os", "pathlib", "sys", "typing", "urllib",
}


def _source_import_roots() -> Optional[set]:
    """Parse THIS file's AST and return the set of imported top-level module
    names — the stdlib-only proof. None when the source is unavailable (the
    check is then reported as skipped, never failed)."""
    import ast
    try:
        src = Path(__file__).read_text(encoding="utf-8")
    except (OSError, NameError, ValueError):
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def selftest() -> int:
    """The offline self-check: proves the phase list, the pure payload builders,
    the auth-parity signature, the legal-path walker and the fail-soft contract
    hold with NO network access and NO credentials. Returns 0 on pass, 1 on any
    contract violation."""
    errors: list = []

    def check(cond, msg) -> None:
        if not cond:
            errors.append(msg)

    # ---- 1. config: absent base URL => board disabled ------------------------
    check(board_config({}) is None,
          "board_config({}) must be None when MISSION_CONTROL_URL is unset.")
    check(board_config({"MISSION_CONTROL_URL": "   "}) is None,
          "board_config must treat a blank MISSION_CONTROL_URL as disabled.")
    cfg = board_config({"MISSION_CONTROL_URL": "https://cc.example.com/"})
    check(isinstance(cfg, dict), "board_config must return a dict when the URL is set.")
    if isinstance(cfg, dict):
        check(cfg.get("base_url") == "https://cc.example.com",
              f"base_url must be stripped of the trailing slash; got {cfg.get('base_url')!r}.")
        check(cfg.get("run_path") == "/api/archify-runs",
              f"run_path default must be /api/archify-runs; got {cfg.get('run_path')!r}.")
        check(cfg.get("timeout") == 8,
              f"CC_BOARD_TIMEOUT default must be 8; got {cfg.get('timeout')!r}.")
        check(cfg.get("token") == "" and cfg.get("secret") == "",
              "token/secret must default to empty strings, never None.")
    check(board_config({"MISSION_CONTROL_URL": "https://x.example.com",
                        "MC_ARCHIFY_PATH": "v2/archify-runs",
                        "CC_BOARD_TIMEOUT": "not-an-int"}).get("run_path")
          == "/v2/archify-runs",
          "MC_ARCHIFY_PATH must be normalized to a leading slash.")
    check(board_config({"MISSION_CONTROL_URL": "https://x.example.com",
                        "CC_BOARD_TIMEOUT": "not-an-int"}).get("timeout") == 8,
          "a non-numeric CC_BOARD_TIMEOUT must fall back to the default, not raise.")

    # ---- 2. the lifecycle phase list + diagram types -------------------------
    check(PHASES == ("received", "authoring", "validate", "render", "deliver"),
          f"PHASES must be the archify lifecycle in order; got {PHASES!r}.")
    check(len(set(PHASES)) == len(PHASES), "PHASES must not contain duplicates.")
    check(DIAGRAM_TYPES == ("architecture", "workflow", "sequence", "dataflow", "lifecycle"),
          f"DIAGRAM_TYPES must be the five archify types; got {DIAGRAM_TYPES!r}.")
    check(next_phase("received") == "authoring"
          and next_phase("authoring") == "validate"
          and next_phase("validate") == "render"
          and next_phase("render") == "deliver",
          "next_phase must walk the lifecycle in order.")
    check(next_phase("deliver") is None,
          "next_phase must return None at the terminal phase.")
    check(next_phase("nope") is None and phase_index("nope") is None,
          "unknown phases must return None, never raise.")
    check([phase_index(p) for p in PHASES] == [0, 1, 2, 3, 4],
          "phase_index must follow PHASES order.")

    # ---- 3. payload builders (pure, offline) --------------------------------
    phases = build_phases("archify architecture — run-1")
    check(isinstance(phases, list) and len(phases) == len(PHASES),
          "build_phases must emit exactly one card per lifecycle phase.")
    check([p.get("slug") for p in phases] == list(PHASES),
          f"build_phases must preserve lifecycle order; got {phases!r}.")
    check(all(isinstance(p.get("title"), str) and p["title"].strip() for p in phases),
          "every phase card must carry a non-empty title.")

    payload = build_run_payload("run-1", diagram_type="architectURE",
                                source_path="examples/web-app.architecture.json",
                                quality="showcase")
    check(payload.get("run_id") == "run-1",
          "the external run id must be sent on CREATE (idempotency/external id).")
    check(payload.get("idempotency_key") == "archify:run:run-1",
          f"the idempotency key must be derived from the run id; got {payload.get('idempotency_key')!r}.")
    check(payload.get("diagram_type") == "architecture",
          f"diagram_type must be normalized to lower case; got {payload.get('diagram_type')!r}.")
    check("architecture" in str(payload.get("description"))
          and payload["description"].startswith("archify run run-1"),
          "the diagram type must appear in the run description (card label).")
    check("received -> authoring -> validate -> render -> deliver"
          in str(payload.get("description")),
          "the description must name the lifecycle the cards walk.")
    check([p.get("slug") for p in payload.get("phases", [])] == list(PHASES),
          "the CREATE body must carry one card per phase, in lifecycle order.")
    check(payload.get("source_path") == "examples/web-app.architecture.json"
          and payload.get("quality") == "showcase",
          "supplied archify metadata must be carried on the payload.")
    lean = build_run_payload("run-2", diagram_type="sequence")
    check(not any(k in lean for k in ("owner", "department", "workspace", "agent_id",
                                      "source_path", "quality")),
          "optional fields must be OMITTED (never sent empty) when not supplied.")
    check(lean.get("title") and "run-2" in lean["title"],
          "a default title must still name the run.")

    move = build_move_payload("render", "done", reason="render ok", actor="skill69-archify")
    check(move == {"phase_slug": "render", "status": "done",
                   "reason": "render ok", "actor": "skill69-archify"},
          f"a plain move payload must be exactly "
          f"{{'phase_slug': 'render', 'status': 'done', 'reason': ..., 'actor': ...}}; "
          f"got {move!r}.")
    blocked = build_move_payload("validate", "blocked", blocked_reason="decision",
                                 blocked_on_human="operator", ask="fix the schema")
    check(blocked.get("blocked_reason") == "decision"
          and blocked.get("blocked_on_human") == "operator"
          and blocked.get("ask") == "fix the schema",
          f"a blocked move must carry the full CC triad; got {blocked!r}.")

    # ---- 4. auth parity ------------------------------------------------------
    check(_sign("", b"{}") is None, "_sign with no secret must be None.")
    sig = _sign("s3cret", b"{}")
    check(isinstance(sig, str) and len(sig) == 64,
          f"_sign must return a 64-char SHA-256 hex digest; got {sig!r}.")
    expected = hmac.new(b"s3cret", b"{}", hashlib.sha256).hexdigest()
    check(sig == expected,
          "x-webhook-signature must be HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex.")
    check(_sign("s3cret", b"{}") == sig, "_sign must be deterministic.")

    # ---- 5. LEGAL path: no illegal jumps ------------------------------------
    check(_legal_path("in_progress", "done") == ["review", "done"],
          "in_progress->done must walk through review.")
    check(_legal_path("backlog", "done") == ["in_progress", "review", "done"],
          "backlog->done must walk in_progress->review->done.")
    check(_legal_path("done", "done") == [], "done->done must be an empty path.")
    check(_legal_path("backlog", "blocked") == ["blocked"],
          "any state -> blocked must be one hop.")
    check(_legal_path("done", "in_progress") == ["backlog", "in_progress"],
          "done->in_progress must route back through backlog.")

    # ---- 6. FAIL-SOFT with no env, and NO network touched -------------------
    orig_request = _request
    net_calls: list = []

    def _no_network(*args, **kwargs):
        net_calls.append(args)
        raise AssertionError("selftest must not touch the network")

    globals()["_request"] = _no_network
    try:
        check(create_run("run-1", diagram_type="architecture", env={}) is None,
              "create_run with the board disabled must return None, not raise.")
        check(set_phase_status("run-1", "received", "in_progress", env={}) is False,
              "set_phase_status with the board disabled must return False, not raise.")
        check(advance_run("run-1", env={}) is None,
              "advance_run with the board disabled must return None, not raise.")
        check(get_run("run-1", env={}) is None,
              "get_run with the board disabled must return None, not raise.")
        check(phase_status("run-1", "received", env={}) is None,
              "phase_status with the board disabled must return None, not raise.")
        check(current_phase("run-1", env={}) is None,
              "current_phase with the board disabled must return None, not raise.")
        check(board_id_for("run-1", env={}) == "run-1",
              "board_id_for must fall back to the external run id, not raise.")
        # An invalid blocked move is refused BEFORE any request is issued.
        check(set_phase_status("run-1", "validate", "blocked",
                               env={"MISSION_CONTROL_URL": "https://cc.example.com"}) is False,
              "a blocked move without the triad must be refused, not raise.")
        check(set_phase_status("run-1", "not-a-phase", "done",
                               env={"MISSION_CONTROL_URL": "https://cc.example.com"}) is False,
              "an unknown phase must be refused, not raise.")
        check(set_phase_status("run-1", "render", "sideways",
                               env={"MISSION_CONTROL_URL": "https://cc.example.com"}) is False,
              "an invalid status must be refused, not raise.")
    finally:
        globals()["_request"] = orig_request
    check(not net_calls,
          f"no request may be issued while the board is disabled; saw {net_calls!r}.")

    # ---- 7. FAIL-SOFT when the board is configured but UNREACHABLE ----------
    def _unreachable(*args, **kwargs):
        raise urllib.error.URLError("selftest: simulated board outage")

    globals()["_request"] = _unreachable
    try:
        live_env = {"MISSION_CONTROL_URL": "https://cc.example.com"}
        check(create_run("run-1", diagram_type="architecture", env=live_env) is None,
              "an unreachable board must degrade create_run to None, not raise.")
        check(set_phase_status("run-1", "render", "done", env=live_env) is False,
              "an unreachable board must degrade set_phase_status to False, not raise.")
        check(advance_run("run-1", env=live_env) is None,
              "an unreachable board must degrade advance_run to None, not raise.")
        check(get_run("run-1", env=live_env) is None,
              "an unreachable board must degrade get_run to None, not raise.")
        check(current_phase("run-1", env=live_env) is None,
              "an unreachable board must degrade current_phase to None, not raise.")
    finally:
        globals()["_request"] = orig_request

    # ---- 8. STDLIB ONLY (AST proof of this file's own imports) --------------
    roots = _source_import_roots()
    if roots is None:
        print("[cc_board] selftest: stdlib-import check SKIPPED (source unavailable).",
              file=sys.stderr)
    else:
        third_party = sorted(roots - _ALLOWED_IMPORT_ROOTS)
        check(not third_party,
              f"only stdlib imports are allowed; found {third_party!r}.")

    if errors:
        print("=== cc_board selftest: FAILURES ===", file=sys.stderr)
        for err in errors:
            print(f"  FAIL: {err}", file=sys.stderr)
        return 1
    print("=== cc_board selftest: ALL BEHAVIORS HOLD "
          "(fail-soft no-op, phase lifecycle, pure payload builders, auth parity, "
          "legal-path walker, stdlib-only) — no network touched ===")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _usage_error(msg: str) -> int:
    """Print a usage error to stderr and return exit code 2 (a USAGE error is
    the only thing that may fail the CLI; a board problem never does)."""
    print(f"cc_board: {msg}", file=sys.stderr, flush=True)
    return 2


def _fail_soft(msg: str) -> int:
    """Log a degrade line and return exit 0 (a board failure never fails the
    run)."""
    _log(msg)
    return 0


def cmd_run_begin(args: argparse.Namespace) -> int:
    """Create the run grouping + one card per lifecycle phase."""
    if not (args.run_id or "").strip():
        return _usage_error("run-begin requires --run-id")
    diagram_type = (args.diagram_type or "").strip().lower()
    if not diagram_type:
        return _usage_error("run-begin requires --diagram-type")
    if diagram_type not in DIAGRAM_TYPES:
        return _usage_error(f"run-begin: invalid --diagram-type {args.diagram_type!r}; "
                            f"must be one of {list(DIAGRAM_TYPES)}")

    board_id = create_run(
        args.run_id,
        diagram_type=diagram_type,
        title=args.title,
        description=args.description,
        source_path=args.source,
        quality=args.quality,
        owner=args.owner,
        department=args.department,
        workspace=args.workspace,
        agent_id=args.agent_id,
    )
    if board_id:
        print(board_id)
        return 0
    return _fail_soft("run-begin: run grouping not created (board disabled or "
                      "unreachable); the archify run continues unboarded.")


def cmd_phase(args: argparse.Namespace) -> int:
    """Move ONE phase card to a status."""
    if not (args.run_id or "").strip():
        return _usage_error("phase requires --run-id")
    if args.phase not in PHASES:
        return _usage_error(f"phase: invalid --phase {args.phase!r}; "
                            f"must be one of {list(PHASES)}")
    if args.status not in ("in_progress", "review", "done", "blocked"):
        return _usage_error(f"phase: invalid --status {args.status!r}; "
                            f"must be one of ['blocked', 'done', 'in_progress', 'review']")
    if args.status == "blocked" and args.blocked_reason not in VALID_BLOCKED_REASONS:
        return _usage_error(f"phase: --blocked-reason must be one of "
                            f"{list(VALID_BLOCKED_REASONS)} for --status blocked")

    ok = set_phase_status(
        args.run_id, args.phase, args.status,
        reason=args.reason,
        note=args.note,
        blocked_reason=(args.blocked_reason or "approval") if args.status == "blocked" else None,
        blocked_on_human=(args.blocked_on_human or "operator") if args.status == "blocked" else None,
        ask=(args.ask or args.note
             or "archify run blocked — operator input needed") if args.status == "blocked" else None,
    )
    if ok:
        print(f"{args.phase}:{args.status}")
        return 0
    return _fail_soft(f"phase: {args.phase}->{args.status} not applied (board disabled, "
                      f"unreachable, or refused); the archify run continues.")


def cmd_advance(args: argparse.Namespace) -> int:
    """Advance the run one phase (or up to --to-phase)."""
    if not (args.run_id or "").strip():
        return _usage_error("advance requires --run-id")
    if args.to_phase and args.to_phase not in PHASES:
        return _usage_error(f"advance: invalid --to-phase {args.to_phase!r}; "
                            f"must be one of {list(PHASES)}")

    reached = advance_run(args.run_id, to_phase=args.to_phase, note=args.note)
    if reached:
        print(reached)
        return 0
    return _fail_soft("advance: no phase advanced (board disabled or unreachable, "
                      "run complete, or the move was refused); the archify run continues.")


def cmd_close(args: argparse.Namespace) -> int:
    """Terminal patch for the run (--phase defaults to the last lifecycle phase)."""
    if not (args.run_id or "").strip():
        return _usage_error("close requires --run-id")
    if args.status not in ("done", "blocked"):
        return _usage_error("close: --status must be 'done' or 'blocked'")
    phase = args.phase or PHASES[-1]
    if phase not in PHASES:
        return _usage_error(f"close: invalid --phase {phase!r}; must be one of {list(PHASES)}")

    if args.status == "blocked":
        reason = args.reason or "approval"
        if reason not in VALID_BLOCKED_REASONS:
            return _usage_error(f"close: --reason must be one of {list(VALID_BLOCKED_REASONS)}, "
                                f"got {reason!r}")
        ok = set_phase_status(
            args.run_id, phase, "blocked",
            reason=args.note,
            blocked_reason=reason,
            blocked_on_human=args.blocked_on_human or "operator",
            ask=args.ask or args.note or "archify run blocked — operator input needed",
        )
        if ok:
            print(f"{phase}:blocked")
            return 0
        return _fail_soft(f"close blocked: {phase} not blocked (board disabled, unreachable, "
                          f"or refused); the archify run continues.")

    ok = set_phase_status(args.run_id, phase, "done", reason=args.note)
    if ok:
        print(f"{phase}:done")
        return 0
    return _fail_soft(f"close done: {phase} not closed (board disabled, unreachable, "
                      f"or refused); the archify run continues.")


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Bare `selftest` is handled before argparse so both the literal subcommand
    # form and the `--selftest` flag form work.
    if argv and argv[0] == "selftest":
        return selftest()

    parser = argparse.ArgumentParser(
        prog="cc_board.py",
        description="Skill 69 (archify) producer-side Command Center board caller "
                    "(FAIL-SOFT). Boards one archify run grouping with one card "
                    "per lifecycle phase: received -> authoring -> validate -> "
                    "render -> deliver.",
    )
    parser.add_argument("--selftest", action="store_true",
                        help="Run the offline self-check (no network, no credentials) and exit.")
    sub = parser.add_subparsers(dest="command")

    p_begin = sub.add_parser("run-begin", help="Create the run grouping + one card per phase")
    p_begin.add_argument("--run-id", required=True,
                         help="External/idempotency run id (a retry cannot double-create)")
    p_begin.add_argument("--diagram-type", required=True,
                         help=f"One of {list(DIAGRAM_TYPES)}")
    p_begin.add_argument("--title", default=None, help="Run/card title (default: 'archify <type> — <run-id>')")
    p_begin.add_argument("--description", default=None, help="Run description override")
    p_begin.add_argument("--source", default=None, help="Path to the archify JSON-IR input")
    p_begin.add_argument("--quality", default=None, help="archify validate quality mode (e.g. showcase)")
    p_begin.add_argument("--owner", default=None, help="Board owner label")
    p_begin.add_argument("--department", default=None, help="CC department slug")
    p_begin.add_argument("--workspace", default=None, help="CC workspace slug")
    p_begin.add_argument("--agent-id", default=None, help="Provenance agent id (never assigned_agent_id)")
    p_begin.set_defaults(func=cmd_run_begin)

    p_phase = sub.add_parser("phase", help="Move one phase card to a status")
    p_phase.add_argument("--run-id", required=True, help="External run id")
    p_phase.add_argument("--phase", required=True, help=f"One of {list(PHASES)}")
    p_phase.add_argument("--status", required=True,
                         help="CC status (in_progress|review|done|blocked)")
    p_phase.add_argument("--note", default=None, help="Optional note for the move")
    p_phase.add_argument("--reason", default=None, help="Optional reason for the move")
    p_phase.add_argument("--blocked-reason", default=None, choices=list(VALID_BLOCKED_REASONS),
                         help="Required for --status blocked (default: approval)")
    p_phase.add_argument("--blocked-on-human", default=None, help="owner|operator (default: operator)")
    p_phase.add_argument("--ask", default=None, help="What the human must do (--status blocked)")
    p_phase.set_defaults(func=cmd_phase)

    p_advance = sub.add_parser("advance", help="Advance the run one phase (or up to --to-phase)")
    p_advance.add_argument("--run-id", required=True, help="External run id")
    p_advance.add_argument("--to-phase", default=None, help=f"Target phase, one of {list(PHASES)}")
    p_advance.add_argument("--note", default=None, help="Optional note recorded on the moves")
    p_advance.set_defaults(func=cmd_advance)

    p_close = sub.add_parser("close", help="Terminal patch for the run")
    p_close.add_argument("--run-id", required=True, help="External run id")
    p_close.add_argument("--status", required=True, choices=["done", "blocked"],
                         help="Terminal status")
    p_close.add_argument("--phase", default=None,
                         help=f"Phase to close (default: the last lifecycle phase, {PHASES[-1]!r})")
    p_close.add_argument("--note", default=None, help="Closing note (serves as the blocked 'ask')")
    p_close.add_argument("--reason", default=None, choices=list(VALID_BLOCKED_REASONS),
                         help="Blocked reason (default: approval)")
    p_close.add_argument("--blocked-on-human", default=None, choices=["owner", "operator"],
                         help="Who must act to unblock (default: operator)")
    p_close.add_argument("--ask", default=None, help="What the human must do (--status blocked)")
    p_close.set_defaults(func=cmd_close)

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
