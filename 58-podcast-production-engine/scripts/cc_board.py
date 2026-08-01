#!/usr/bin/env python3
"""
cc_board.py -- Podcast department PRODUCER-SIDE Command Center board caller
(FAIL-SOFT). Lands an episode run on the CC Kanban board in the 'podcast'
workspace and advances cards through the production lifecycle.

WHY THIS EXISTS (onb-20)
  The CC kanban has a fully-seeded Podcast department (workspace 'podcast',
  4 agents, 6 lanes) but nothing cards episode runs onto it -- the lane is
  permanently empty. This is the producer half that fixes that: it creates one
  card per episode run and moves it through the production phases as the run
  progresses. The board is a CONVENIENCE, never a gate.

NON-NEGOTIABLE DESIGN RULES (identical contract to the fleet cc_board.py
callers in Skill 47 / Skill 48)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and
    the episode run CONTINUES. Every command returns exit 0 on board errors.
    Only a usage error (missing required args) exits non-zero.
  * STDLIB ONLY (urllib) -- zero third-party deps, mirrors the rest of the
    deterministic podcast spine.
  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => clean no-op.
      CC_BASE_URL     base URL of the Command Center (e.g.
                      http://localhost:4000). Absent => board disabled
                      (clean no-op; the run is unaffected).
      MC_API_TOKEN    long-lived bearer (middleware layer). Optional.
      WEBHOOK_SECRET  HMAC secret (per-route layer). Optional.
      CC_BOARD_TIMEOUT per-request timeout seconds (default 5).
  * BOUNDED TIMEOUT (5s), ONE retry on network error only (not on 4xx/5xx).
  * IDEMPOTENT: run-begin with an already-mapped job-id re-emits the existing
    task-id (no duplicate cards).

REQUEST CONTRACT
  CREATE   POST {base}/api/tasks/ingest
    headers: Authorization: Bearer <MC_API_TOKEN> (if set),
             x-webhook-signature: <hmac> (if WEBHOOK_SECRET set),
             Content-Type: application/json
    body:    {title, department_slug, source, source_ref, idempotency_key}
    return:  201 (created) / 200 (deduped) -> {ok, task_id, workspace_id, status}

  UPDATE   PATCH {base}/api/tasks/{task_id}
    headers: same as CREATE
    body:    {status, phase_id?, note?}
    return:  200 -> task object
    status vocabulary (CC TaskStatus): backlog | in_progress | review | blocked | done

  READ     GET {base}/api/tasks/{task_id}
    headers: same as CREATE
    return:  200 -> task object (carries the current `status`)

STATE MACHINE (rem-2)
  The CC PATCH route enforces a state machine (task-lifecycle.ts):
  `done` is reachable ONLY from `review` (or `testing`). Any other
  source status PATCHed to `done` is rejected (403 / illegal-edge).
  `blocked` is accepted from any non-done source (the route's blocked
  gate at lines 349-396 runs unconditionally on status='blocked').
  This caller is TRANSITION-AWARE: before a `done` PATCH it reads the
  card's current status (GET /api/tasks/{id}) and, when that status is
  not `review` or `testing`, PATCHes `status:'review'` FIRST so the
  subsequent `done` PATCH lands on a legal edge. The deliverable
  registration (onb-21) stays BEFORE the done patch. The fail-soft
  contract is unchanged: a refused transition is logged, not fatal.

CLI SUBCOMMANDS
  run-begin   --job-id --client-label --episode-title [--department podcast]
              Create the episode card on the CC board. Card title convention:
              "Episode: <title> (<client>)".
  patch-phase --job-id --phase <slug> --status <in_progress|review|done|blocked>
              [--permalink <url>]
              Update the card's phase annotation and CC-native status.
              When --status done, use --permalink to register a deliverable
              (Podbean episode URL) before the done patch so the CC
              completion-evidence gate (T0-01) passes.
  close       --job-id --status done|blocked [--note <text>]
              [--reason <decision|approval|credential|payment>]
              [--blocked-on-human <owner|operator>] [--permalink <url>]
              Terminal patch for the episode card.
              Blocked (--status blocked):
                Sends the full blocked triad: blocked_reason (from --reason,
                default approval), blocked_on_human (from --blocked-on-human,
                default operator), and ask (from --note, default sensible
                string). Required by the CC blocked-column gate
                (route.ts lines 349-377).
              Done (--status done):
                When --permalink is provided, registers it as a task
                deliverable (POST /api/tasks/{id}/deliverables) before
                the done patch so the completion-evidence gate (T0-01)
                passes. Without --permalink, warns on stderr and still
                attempts (fail-soft absorbs the gate refusal).
                TRANSITION-AWARE (rem-2): before the done PATCH the
                caller reads the card's current status via GET; when it
                is not 'review' (or 'testing') it PATCHes
                status:'review' FIRST so the done PATCH lands on a legal
                state-machine edge. Blocked close sends the triad and
                works from any non-done state (the route's blocked gate
                is source-agnostic).

STATE PERSISTENCE
  Job-id -> task-id mapping is persisted in
  ~/.openclaw/podcast-engine/board-map.json (0600) so patch/close can find
  the card after a restart.
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

_DEFAULT_TIMEOUT = 5
_STATE_DIR = Path.home() / ".openclaw" / "podcast-engine"
_STATE_FILE = _STATE_DIR / "board-map.json"


# ---------------------------------------------------------------------------
# Config -- read from the environment; absent base URL => board disabled.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled,
    a clean no-op) when CC_BASE_URL is not set. Never raises."""
    env = env if env is not None else os.environ
    base = (env.get("CC_BASE_URL") or "").strip().rstrip("/")
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
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex -- byte-for-
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
    except urllib.error.HTTPError as exc:  # 4xx/5xx -- read the body for context
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


def _request_with_retry(method: str, url: str, payload: Optional[dict], cfg: dict):
    """One signed JSON request with ONE retry on network error only.
    Returns (status_code, parsed_json_or_None)."""
    try:
        return _request(method, url, payload, cfg)
    except (urllib.error.URLError, OSError) as exc:
        _log(f"{method} {url} network error ({type(exc).__name__}: {exc}); retrying once.")
        try:
            return _request(method, url, payload, cfg)
        except (urllib.error.URLError, OSError, ValueError) as exc2:
            raise exc2


# ---------------------------------------------------------------------------
# State persistence -- job-id <-> task-id mapping
# ---------------------------------------------------------------------------
def _load_map() -> dict:
    """Load the board-map.json state file. Returns empty dict on any error.
    Never raises."""
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text())
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError) as exc:
        _log(f"board-map load failed ({exc}); starting with empty map.")
    return {}


def _save_map(data: dict) -> None:
    """Atomically write the board-map.json state file with 0600 permissions.
    Never raises."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.parent.chmod(0o700)  # ensure dir is private
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.chmod(0o600)
        os.replace(tmp, _STATE_FILE)
    except OSError as exc:
        _log(f"board-map save failed ({exc}).")


def _get_task_id(job_id: str) -> Optional[str]:
    """Look up the CC task_id for a given podcast job_id. Returns None if not
    mapped. Never raises."""
    return _load_map().get(job_id)


def _set_task_id(job_id: str, task_id: str) -> None:
    """Persist the job_id -> task_id mapping. Never raises."""
    data = _load_map()
    data[job_id] = task_id
    _save_map(data)


# ---------------------------------------------------------------------------
# READ -- GET /api/tasks/{task_id} (transition-aware done path, rem-2)
# ---------------------------------------------------------------------------
# Statuses from which a `done` PATCH is a LEGAL state-machine edge. The CC
# PATCH route (route.ts) + task-lifecycle.ts allow `done` only from `review`
# or `testing`; any other source is refused (403 / illegal-edge). Keeping this
# set local to the caller (not imported from the TS route) is deliberate: the
# caller is the side that must sequence the transition, and a TS schema change
# does not silently widen what this Python caller does.
_DONE_SOURCE_STATUSES = {"review", "testing"}


def get_card_status(task_id: str, *, env: Optional[dict] = None) -> Optional[str]:
    """Read the current CC status of a card via GET /api/tasks/{task_id}.

    Returns the status string ('backlog'|'in_progress'|'review'|'blocked'|
    'done'|'testing'|...) on success, or None on any board problem (board
    disabled, card missing, HTTP error, network error). FAIL-SOFT: never
    raises."""
    cfg = board_config(env)
    if cfg is None:
        return None

    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request_with_retry("GET", url, None, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"GET {task_id} failed ({type(exc).__name__}: {exc}).")
        return None

    if st == 200 and isinstance(body, dict) and body.get("status"):
        return str(body["status"])

    _log(f"GET {task_id} non-OK (HTTP {st}): {body}.")
    return None


# ---------------------------------------------------------------------------
# CREATE -- POST /api/tasks/ingest (idempotent via job-id map)
# ---------------------------------------------------------------------------
def create_board_card(
    job_id: str,
    client_label: str,
    episode_title: str,
    *,
    department: str = "podcast",
    env: Optional[dict] = None,
) -> Optional[str]:
    """Create (or idempotently re-fetch) the episode card on the CC board.
    Returns the echoed task_id on success, else None (FAIL-SOFT)."""
    cfg = board_config(env)
    if cfg is None:
        _log("CC_BASE_URL unset -- board disabled (no-op); run continues.")
        return None
    if not job_id or not episode_title:
        _log("create skipped -- job_id/episode_title missing.")
        return None

    # Idempotency: if already mapped, return the existing task_id.
    existing = _get_task_id(job_id)
    if existing:
        _log(f"board card already exists for job_id={job_id} (task_id={existing}); re-using.")
        return existing

    title = f"Episode: {episode_title} ({client_label})" if client_label else f"Episode: {episode_title}"
    payload: dict = {
        "title": title,
        "department_slug": department,
        "source": "podcast-engine",
        "source_ref": f"podcast:{job_id}",
        "idempotency_key": f"podcast:episode:{job_id}",
    }

    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request_with_retry("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"ingest POST failed ({type(exc).__name__}: {exc}); run continues unboarded.")
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        _set_task_id(job_id, task_id)
        _log(f"board card {'created' if body.get('deduped') is not True else 'deduped'}: "
             f"task_id={task_id} (job_id={job_id}).")
        return task_id

    _log(f"ingest POST non-OK (HTTP {status}): {body}; run continues unboarded.")
    return None


# ---------------------------------------------------------------------------
# UPDATE -- PATCH /api/tasks/{task_id}
# ---------------------------------------------------------------------------
def patch_board_card(
    job_id: str,
    *,
    phase: Optional[str] = None,
    status: Optional[str] = None,
    note: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    blocked_on_human: Optional[str] = None,
    ask: Optional[str] = None,
    env: Optional[dict] = None,
) -> bool:
    """PATCH the episode card's phase annotation and/or CC-native status.
    FAIL-SOFT: returns False (never raises) on any board problem."""
    cfg = board_config(env)
    if cfg is None:
        return False

    task_id = _get_task_id(job_id)
    if not task_id:
        _log(f"patch skipped -- no task_id mapped for job_id={job_id}.")
        return False

    if not phase and not status:
        _log("patch skipped -- nothing to update.")
        return False

    # ── TRANSITION-AWARE done path (rem-2) ────────────────────────────────
    # The CC PATCH route enforces a state machine (task-lifecycle.ts): `done`
    # is reachable ONLY from `review` (or `testing`). A `done` PATCH from any
    # other source status is refused (403 / illegal-edge). So before the
    # `done` PATCH we READ the card's current status (GET /api/tasks/{id})
    # and, when it is not already a legal `done` source, we PATCH
    # `status:'review'` FIRST so the subsequent `done` PATCH lands on a legal
    # edge. The deliverable registration (onb-21) is done by the CALLER
    # (cmd_close / cmd_patch_phase) before this function is reached, so the
    # completion-evidence gate is already satisfied by the time `done` PATCHes.
    # `blocked` is source-agnostic (the route's blocked gate runs on any
    # non-done status), so no pre-transition is needed there.
    # FAIL-SOFT: every step is absorbed -- a refused review transition or a
    # read failure is logged and the done PATCH is still attempted (the route
    # may yet accept it, e.g. the card was already in review); a failure of
    # the done PATCH itself returns False (never raises).
    pre_patched_review = False
    if status == "done":
        cur = get_card_status(task_id, env=env)
        if cur is not None and cur not in _DONE_SOURCE_STATUSES:
            _log(f"transition-aware done: card {task_id} in '{cur}' -- "
                 f"PATCHing status:'review' before done.")
            review_payload: dict = {"status": "review"}
            review_url = f"{cfg['base_url']}/api/tasks/{task_id}"
            try:
                rst, rbody = _request_with_retry("PATCH", review_url, review_payload, cfg)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                _log(f"review pre-PATCH {task_id} failed ({type(exc).__name__}: {exc}); "
                     f"attempting done anyway.")
                rst = None
            if rst == 200:
                pre_patched_review = True
            elif rst is not None:
                _log(f"review pre-PATCH {task_id} non-OK (HTTP {rst}): {rbody}; "
                     f"attempting done anyway.")
        elif cur is None:
            _log(f"transition-aware done: could not read status for {task_id}; "
                 f"attempting done PATCH directly (fail-soft).")

    payload: dict = {}
    if phase:
        payload["phase_id"] = phase
    if status:
        payload["status"] = status
    if note:
        payload["note"] = note
    if status == "blocked":
        payload["blocked_reason"] = blocked_reason or "approval"
        payload["blocked_on_human"] = blocked_on_human or "operator"
        payload["ask"] = ask or "Podcast episode run blocked - operator input needed"

    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request_with_retry("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"PATCH {task_id} failed ({type(exc).__name__}: {exc}).")
        return False

    if st == 200:
        _log(f"board card patched: task_id={task_id} phase={phase} status={status}"
             f"{' (pre-transitioned review)' if pre_patched_review else ''}.")
        return True

    _log(f"PATCH {task_id} non-OK (HTTP {st}): {body}.")
    return False


# ---------------------------------------------------------------------------
# DELIVERABLE REGISTRATION -- POST /api/tasks/{task_id}/deliverables
# ---------------------------------------------------------------------------
def register_deliverable(
    job_id: str,
    *,
    permalink: str,
    deliverable_type: str = "url",
    title: str = "Podbean episode permalink",
    env: Optional[dict] = None,
) -> bool:
    """Register a task deliverable (the Podbean episode permalink) with the CC
    board so the completion-evidence gate passes. FAIL-SOFT: returns False
    (never raises) on any board problem."""
    cfg = board_config(env)
    if cfg is None:
        return False

    task_id = _get_task_id(job_id)
    if not task_id:
        _log(f"deliverable skipped -- no task_id mapped for job_id={job_id}.")
        return False

    payload: dict = {
        "deliverable_type": deliverable_type,
        "title": title,
        "path": permalink,
    }

    url = f"{cfg['base_url']}/api/tasks/{task_id}/deliverables"
    try:
        st, body = _request_with_retry("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"deliverable POST {task_id} failed ({type(exc).__name__}: {exc}).")
        return False

    if st == 201:
        _log(f"deliverable registered: task_id={task_id} permalink={permalink}.")
        return True

    _log(f"deliverable POST {task_id} non-OK (HTTP {st}): {body}.")
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fail_usage(msg: str) -> None:
    """Print usage error to stderr and exit 2."""
    print(f"cc_board: {msg}", file=sys.stderr)
    sys.exit(2)


def _fail_soft_and_exit(msg: str) -> None:
    """Log a degrade line and exit 0 (board failure never fails the run)."""
    _log(msg)
    sys.exit(0)


def cmd_run_begin(args: argparse.Namespace) -> None:
    """Create the episode card on the CC board."""
    if not args.job_id:
        _fail_usage("run-begin requires --job-id")
    if not args.episode_title:
        _fail_usage("run-begin requires --episode-title")

    task_id = create_board_card(
        job_id=args.job_id,
        client_label=args.client_label or "",
        episode_title=args.episode_title,
        department=args.department or "podcast",
    )
    if task_id:
        print(task_id)
    else:
        _fail_soft_and_exit("board card not created (board unreachable or disabled); run continues.")


def cmd_patch_phase(args: argparse.Namespace) -> None:
    """Patch the episode card's phase and status."""
    if not args.job_id:
        _fail_usage("patch-phase requires --job-id")
    if not args.phase:
        _fail_usage("patch-phase requires --phase")
    if not args.status:
        _fail_usage("patch-phase requires --status")

    valid_phases = {
        "received", "researching", "writing", "in_qc",
        "generating_art", "producing_audio", "publishing", "enrolling", "complete",
    }
    if args.phase not in valid_phases:
        _fail_usage(f"patch-phase: invalid phase {args.phase!r}; must be one of {sorted(valid_phases)}")

    valid_statuses = {"in_progress", "review", "done", "blocked"}
    if args.status not in valid_statuses:
        _fail_usage(f"patch-phase: invalid status {args.status!r}; must be one of {sorted(valid_statuses)}")

    if args.status == "done":
        if args.permalink:
            register_deliverable(
                job_id=args.job_id,
                permalink=args.permalink,
                deliverable_type="url",
                title="Podbean episode permalink",
            )
        else:
            print("cc_board: warning: no permalink - done transition may be refused by the completion-evidence gate",
                  file=sys.stderr, flush=True)

    ok = patch_board_card(
        job_id=args.job_id,
        phase=args.phase,
        status=args.status,
    )
    if not ok:
        _fail_soft_and_exit("patch-phase failed (board unreachable or card not found); run continues.")


def cmd_close(args: argparse.Namespace) -> None:
    """Terminal patch for the episode card."""
    if not args.job_id:
        _fail_usage("close requires --job-id")
    if args.status not in ("done", "blocked"):
        _fail_usage("close: --status must be 'done' or 'blocked'")

    if args.status == "blocked":
        reason = args.reason or "approval"
        if reason not in ("decision", "approval", "credential", "payment"):
            _fail_usage(f"close: --reason must be one of decision|approval|credential|payment, got {reason!r}")
        ask = args.note or "Podcast episode run blocked - operator input needed"
        ok = patch_board_card(
            job_id=args.job_id,
            status="blocked",
            blocked_reason=reason,
            blocked_on_human=args.blocked_on_human or "operator",
            ask=ask,
        )
        if not ok:
            _fail_soft_and_exit("close blocked failed (board unreachable or card not found); run continues.")
        return

    # --status done
    if args.permalink:
        register_deliverable(
            job_id=args.job_id,
            permalink=args.permalink,
            deliverable_type="url",
            title="Podbean episode permalink",
        )
    else:
        print("cc_board: warning: no permalink - done transition may be refused by the completion-evidence gate",
              file=sys.stderr, flush=True)

    ok = patch_board_card(
        job_id=args.job_id,
        status="done",
        note=args.note,
    )
    if not ok:
        _fail_soft_and_exit("close done failed (board unreachable or card not found); run continues.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cc_board.py",
        description="Podcast department producer-side Command Center board caller (FAIL-SOFT).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run-begin
    p_begin = sub.add_parser("run-begin", help="Create the episode card on the CC board")
    p_begin.add_argument("--job-id", required=True, help="Podcast job identifier")
    p_begin.add_argument("--client-label", default="", help="Client name label")
    p_begin.add_argument("--episode-title", required=True, help="Episode title")
    p_begin.add_argument("--department", default="podcast", help="CC workspace slug (default: podcast)")
    p_begin.set_defaults(func=cmd_run_begin)

    # patch-phase
    p_phase = sub.add_parser("patch-phase", help="Update the card's phase and CC-native status")
    p_phase.add_argument("--job-id", required=True, help="Podcast job identifier")
    p_phase.add_argument("--phase", required=True, help="Phase slug (received|researching|writing|in_qc|generating_art|producing_audio|publishing|enrolling|complete)")
    p_phase.add_argument("--status", required=True, help="CC status (in_progress|review|done|blocked)")
    p_phase.add_argument("--permalink", default=None, help="Podbean episode permalink URL (required for done transitions to pass the completion-evidence gate)")
    p_phase.set_defaults(func=cmd_patch_phase)

    # close
    p_close = sub.add_parser("close", help="Terminal patch for the episode card")
    p_close.add_argument("--job-id", required=True, help="Podcast job identifier")
    p_close.add_argument("--status", required=True, choices=["done", "blocked"], help="Terminal status")
    p_close.add_argument("--note", default=None, help="Optional closing note (serves as the 'ask' for blocked status)")
    p_close.add_argument("--reason", default=None, choices=["decision", "approval", "credential", "payment"],
                         help="Blocked reason (required for --status blocked; default: approval)")
    p_close.add_argument("--blocked-on-human", default=None, choices=["owner", "operator"],
                         help="Who must act to unblock (default: operator)")
    p_close.add_argument("--permalink", default=None, help="Podbean episode permalink URL (required for done transitions to pass the completion-evidence gate)")
    p_close.set_defaults(func=cmd_close)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
