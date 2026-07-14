#!/usr/bin/env python3
"""
cc_board.py — Skill 06 PRODUCER-SIDE Command Center board caller (FAIL-SOFT).

This is the producer half of the board hookup for Skill-6 (funnel / website
builds). It posts ONE card to ``POST /api/tasks/ingest`` in
trevorotts1/blackceo-command-center (>= v4.52.0) and returns the task_id so
the build workflow can reference it. If the board is unreachable, unconfigured,
or returns an error the build CONTINUES — boarding is a convenience, never a
gate.

NON-NEGOTIABLE DESIGN RULES (mirrors 48-facebook-ad-generator/scripts/cc_board.py)
  * FAIL-SOFT. Any failure (missing URL, HTTP error, timeout, bad JSON) is
    caught, logged to stderr, and the skill job continues. This function returns
    a value (task_id string or None) and NEVER raises.

  * AUTH PARITY with the endpoint (verbatim from the ingest route handler):
      - ``Authorization: Bearer <MC_API_TOKEN>``  — global middleware layer.
        No-op when MC_API_TOKEN is absent or the board is same-origin.
      - ``x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` hex —
        per-route layer. The endpoint skips the check when WEBHOOK_SECRET is
        unset (dev mode). We sign the EXACT bytes we send so a configured secret
        matches byte-for-byte.

  * STDLIB ONLY (urllib) — zero third-party deps.

  * CREDENTIALS FROM ENV, never hardcoded; absent MISSION_CONTROL_URL => board
    disabled (clean no-op; the build is unaffected).
      MISSION_CONTROL_URL   base URL of the Command Center (e.g.
                            https://<client>.zerohumanworkforce.com). Absent =>
                            board disabled.
      MC_API_TOKEN          long-lived bearer (middleware layer). Optional.
      WEBHOOK_SECRET        HMAC secret (per-route layer). Optional.
      CC_BOARD_TIMEOUT      per-request timeout seconds (default 8).

REQUEST CONTRACT (matched to POST /api/tasks/ingest live endpoint):
  POST {base}/api/tasks/ingest
    headers: Authorization: Bearer <MC_API_TOKEN> (if set),
             x-webhook-signature: <hmac> (if WEBHOOK_SECRET set),
             Content-Type: application/json
    body:    {title, description?, priority?,
              source:'funnel'|'web-development',
              department_slug:'web-development'|'funnels',
              idempotency_key?}
    return:  201 (created) / 200 (deduped) ->
             {ok, task_id, workspace_id, resolved_by, status}

  department_slug routing:
    'funnels'          — sales funnel / opt-in funnel / multi-step funnel
    'web-development'  — single page, website, landing page, standalone page

  Fields intentionally OMITTED (the ingest route ignores them and the CC
  TaskStatus enum does NOT include them):
    task_type, stage, parent_task_id, depends_on, waiting_on_dependency.
  Only the 10-value TaskStatus enum values are valid status values on the server:
    backlog | in_progress | review | blocked | done (and assigned, which the
    Workforce-Engine v4.52.0 patch added). We do not set status in the POST —
    the route always creates at 'backlog' and then routeTask() re-assigns.

SELF-TEST (no board required, no network):
  python3 06-ghl-install-pages/tools/cc_board.py --selftest
  exits 0 on success, non-zero on failure.

LIVE DEMO:
  MISSION_CONTROL_URL=https://<cc-url> MC_API_TOKEN=<tok> \\
    python3 06-ghl-install-pages/tools/cc_board.py --demo
  Prints the returned task_id and workspace routing evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
import urllib.error
import urllib.request
from typing import Optional

_DEFAULT_TIMEOUT = 8

# Valid CC TaskStatus enum values (full 10-value enum from src/lib/types.ts:5 and
# migration 076). move_task() and update_status() both refuse anything outside
# this set so a typo can never be POSTed to the board.
_CC_STATUS_VALUES = (
    "backlog", "inbox", "planning", "pending_dispatch",
    "assigned", "in_progress", "review", "testing",
    "blocked", "done",
)

# Valid activity_type values (src/lib/validation.ts:31-37).
_CC_ACTIVITY_TYPES = ("spawned", "updated", "completed", "file_created", "status_changed")

# U9 §7.3 — Failure taxonomy. A build that lands on 'blocked' (or 'backlog' with a
# known cause) tags the transition note with ONE of these machine-parsable prefixes
# so the board is queryable for fleet-wide failure PATTERNS (an individual failure
# becomes fleet learning). Kept in lockstep with the spec's taxonomy set; a reason
# outside this tuple is logged and the note is posted un-prefixed (fail-soft, never
# a fabricated category).
_CC_BLOCK_REASONS = (
    "AUTH-STOP",       # revoked/expired token, sign-in/2FA screen appeared (F15)
    "SELECTOR-MISS",   # a locked anchor was not found in the live DOM (F3)
    "RATE-LIMIT",      # 429 / daily-quota floor hit (F8)
    "TOKEN-CONTEXT",   # 403 classified as a token-context mismatch (F9)
    "PARKED",          # circuit breaker opened → box PARK marker (browser_manager)
    "VERIFY-FAIL",     # sealed verifier / render_check did not PASS (F6)
)

# Dispatcher state -> CC board status (Area-6 board status updater). The
# v2_dispatcher state machine (backlog -> dispatched -> building -> verified |
# FAILED) maps onto the Kanban columns so a running build no longer sits at
# 'backlog'. 'verified' lands at 'review' (operator/QC signs off to 'done').
DISPATCH_STATE_TO_CC = {
    "dispatched": "in_progress",
    "building": "in_progress",
    "verified": "review",
    "FAILED": "blocked",
}


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
    return {
        "base_url": base,
        "token": (env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    """Single, greppable degrade line. Board failures are logged, not silent,
    and never fatal."""
    print(f"[cc_board:skill6] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex —
    byte-for-byte parity with verifyWebhookSignature() in the route handlers.
    Returns None when no secret (the endpoint also no-ops in that case)."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _post_json(url: str, payload: dict, cfg: dict, method: str = "POST"):
    """One signed JSON request (``method`` defaults to POST so existing callers
    are unchanged). Returns (status_code, parsed_json_or_None).
    Raises only urllib/OS errors — the public caller catches (fail-soft)."""
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
# PUBLIC API — ingest_task is the one call Skill-6 makes.
# ---------------------------------------------------------------------------
def ingest_task(
    title: str,
    description: str = "",
    *,
    job_type: str = "funnel",
    priority: str = "high",
    idempotency_key: Optional[str] = None,
    department_slug: Optional[str] = None,
    source: Optional[str] = None,
    env: Optional[dict] = None,
) -> Optional[str]:
    """POST one funnel/website job to /api/tasks/ingest.

    Returns the task_id string on success (HTTP 200 or 201), else None.
    FAIL-SOFT: never raises; a None return never blocks the Skill-6 build.

    Args:
        title:            Short card title visible on the Kanban board.
        description:      Job brief / customer request text (markdown OK).
        job_type:         'funnel' (sales funnel / opt-in / multi-step),
                          'website' (single page / landing page / full site), or
                          'survey'|'form'|'quiz' (survey / intake / quiz builds).
                          Controls department_slug routing:
                            'funnel'                  → department_slug='funnels'
                            'survey'|'form'|'quiz'    → department_slug='web-development', source='survey'
                            'website' / everything else → department_slug='web-development'
        priority:         CC TaskPriority: 'low'|'medium'|'high'|'critical'.
                          Default 'high' for customer-facing build jobs.
        idempotency_key:  Dedupe key; omit to let the caller generate one
                          automatically (uuid4). Supply a deterministic key
                          (e.g. sha256 of the job brief) for retry safety.
        department_slug:  OPTIONAL explicit department routing override. When
                          given, it wins over the job_type-derived slug — used by
                          the FIX-COPY-01 copy-dependency card to route a P2-COPY
                          job to ``'marketing'`` (the Conversion Copywriter's
                          department, per SOP-07 Step 3) rather than the builder's
                          own web-development / funnels column. NOTE: like
                          ``'funnels'``, a ``'marketing'`` slug that the Command
                          Center's departments.config.ts has not yet registered
                          resolves to the CEO catch-all column server-side —
                          visible, never lost; the LOCAL waiting_on_dependency
                          receipt is the binding gate, the card is visibility only.
        source:           OPTIONAL explicit source-tag override (defaults to the
                          job_type-derived source, or to ``department_slug`` when
                          only the slug is overridden).
        env:              Override os.environ (for testing).

    Returns:
        task_id (str) on success — the CC UUID for this board card.
        None on any failure (board unreachable / unconfigured / error).
    """
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled (no-op); build continues.")
        return None

    if not title or not title.strip():
        _log("ingest_task skipped — title is empty.")
        return None

    # Capture explicit routing overrides BEFORE the job_type mapping below
    # reassigns the local names (the parameters share the names department_slug /
    # source that the mapping writes to).
    _department_slug_override = (department_slug or "").strip()
    _source_override = (source or "").strip()

    # Map job_type -> department_slug.
    job_type_norm = (job_type or "funnel").lower().strip()
    if job_type_norm in ("funnel", "sales-funnel", "optin", "opt-in", "multistep"):
        # NOTE: department_slug='funnels' currently mis-resolves to the CEO catch-all
        # in the Command Center (departments.config.ts has no 'funnels' dept; only
        # 'web-development' resolves at :457). Option 2 (fast-follow) will add a
        # dedicated 'funnels'/'surveys' dept + workspace-seed migration. Until then
        # funnels land in the catch-all column — visible, not lost.
        department_slug = "funnels"
        source = "funnel"
    elif job_type_norm in ("survey", "form", "quiz"):
        # Option 1 (zero-migration, PRD §6.3 / §6.2): map survey/form/quiz to
        # 'web-development' which resolves today (departments.config.ts:457).
        # source='survey' tags the card so the activity feed identifies it as a
        # survey build even though the department column is web-development.
        # Option 2 (fast-follow): add a dedicated 'surveys' dept in departments.config.ts.
        department_slug = "web-development"
        source = "survey"
    else:
        # website, landing-page, single-page, web-development, etc.
        department_slug = "web-development"
        source = "web-development"

    # Explicit routing override (FIX-COPY-01): the caller may pin the card to a
    # specific department (e.g. 'marketing' for a P2-COPY dependency card) and/or
    # source tag, overriding the job_type-derived values above. Passing only a
    # department_slug defaults the source tag to that same slug.
    if _department_slug_override:
        department_slug = _department_slug_override
        source = (_source_override or _department_slug_override)
    elif _source_override:
        source = _source_override

    # Idempotency key — deterministic per job brief so retries don't duplicate.
    key = (idempotency_key or "").strip() or str(uuid.uuid4())

    payload: dict = {
        "title": title.strip(),
        "source": source,
        "department_slug": department_slug,
        "idempotency_key": key,
    }
    if description and description.strip():
        payload["description"] = description.strip()
    if priority and priority.strip():
        payload["priority"] = priority.strip()

    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _post_json(url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"POST {url} failed ({type(exc).__name__}: {exc}); build continues unregistered.")
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        resolved_by = body.get("resolved_by", "unknown")
        _log(
            f"task {'deduped' if deduped else 'created'}: task_id={task_id} "
            f"department={department_slug} resolved_by={resolved_by} "
            f"status={body.get('status', '?')} http={status}"
        )
        return task_id

    _log(f"POST /api/tasks/ingest non-OK (HTTP {status}): {body}; build continues unregistered.")
    return None


# ---------------------------------------------------------------------------
# PUBLIC API — update_status moves a card across the Kanban (Area-6 fix).
# ---------------------------------------------------------------------------
def update_status(
    task_id: str,
    status: str,
    *,
    note: str = "",
    env: Optional[dict] = None,
) -> bool:
    """Transition a board card to ``status`` so a running build no longer sits
    stuck at 'backlog' (Area-6: backlog/assigned/in_progress/review/blocked/done).

    PRODUCER HALF ONLY.

    *** CROSS-REPO CONTRACT — CONFIRM/ADD THE CONSUMER ROUTE. ***
    The exact status-transition endpoint lives in the SEPARATE command-center
    repo (``trevorotts1/blackceo-command-center``). ``ingest_task`` targets the
    CONFIRMED ``POST /api/tasks/ingest`` route; the per-task status route is NOT
    yet confirmed there. This caller therefore defaults to
    ``POST /api/tasks/{id}/status`` — inside the documented ``/api/tasks/<id>/...``
    route family (cf. ``POST /api/tasks/<id>/dispatch`` in
    v2-autonomous-build-sop.md) — and lets the operator override BOTH the method
    and the path template via env WITHOUT a code change, so it can be pointed at
    the real route the moment it is confirmed:
        CC_STATUS_METHOD         HTTP method (default 'POST'; e.g. 'PATCH').
        CC_STATUS_PATH_TEMPLATE  path containing a literal '{id}' (default
                                 '/api/tasks/{id}/status'; e.g. '/api/tasks/{id}'
                                 for a PATCH-the-resource style API).
    Until the CC route is confirmed/added, a 404 is caught and FAIL-SOFTS (the
    card simply does not move; the build is unaffected).

    Returns True on a 2xx transition, else False. FAIL-SOFT: never raises; a
    board outage NEVER blocks the build (mirrors ingest_task).

    Args:
        task_id:  CC task UUID returned by ingest_task (e.g. read from
                  routing/intake-receipt.json). Empty => no-op (returns False).
        status:   One of the CC TaskStatus enum values (see _CC_STATUS_VALUES).
        note:     Optional human-readable transition note (markdown OK).
        env:      Override os.environ (for testing).
    """
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled (no-op); status not pushed.")
        return False

    tid = (task_id or "").strip()
    if not tid:
        _log("update_status skipped — empty task_id.")
        return False

    status_norm = (status or "").strip().lower()
    if status_norm not in _CC_STATUS_VALUES:
        _log(
            f"update_status skipped — invalid status {status!r} "
            f"(allowed: {', '.join(_CC_STATUS_VALUES)})."
        )
        return False

    # DoD5 parity guard (v16.2.15): update_status must never post 'done' directly,
    # closing the legacy bypass hole that move_task's guard did not cover.  Any code
    # path that calls update_status('done') is a bug — the only valid transition to
    # 'done' is the QC gate (runQCOnReview, qc-scorer.ts:2988, PASS ≥ 8.5) promoting
    # a card from 'review'.  This guard is intentionally identical to move_task()'s
    # hard-block so no caller can reach 'done' via either public API.
    if status_norm == "done":
        _log(
            "update_status BLOCKED — the producer must never post 'done' directly. "
            "The only valid path to done is review → done via the QC gate "
            "(runQCOnReview, qc-scorer.ts:2988, PASS ≥ 8.5). "
            "Call update_status('review') and let the QC sweep promote the card."
        )
        return False

    env_map = env if env is not None else os.environ
    method = (env_map.get("CC_STATUS_METHOD") or "POST").strip().upper() or "POST"
    path_tmpl = (env_map.get("CC_STATUS_PATH_TEMPLATE") or "/api/tasks/{id}/status").strip()
    if "{id}" not in path_tmpl:
        _log(f"update_status skipped — CC_STATUS_PATH_TEMPLATE missing '{{id}}': {path_tmpl!r}.")
        return False

    payload: dict = {"status": status_norm}
    if note and note.strip():
        payload["note"] = note.strip()

    url = f"{cfg['base_url']}{path_tmpl.format(id=tid)}"
    try:
        http_status, body = _post_json(url, payload, cfg, method=method)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"{method} {url} failed ({type(exc).__name__}: {exc}); card not moved; build continues.")
        return False

    if 200 <= http_status < 300:
        _log(f"task {tid} -> {status_norm} (HTTP {http_status}, {method}).")
        return True

    _log(
        f"{method} status non-2xx (HTTP {http_status}) for task {tid} -> {status_norm}: "
        f"{body}; card not moved; build continues. "
        "If 404, CONFIRM the status route in blackceo-command-center."
    )
    return False


def update_status_for_state(
    task_id: str,
    dispatch_state: str,
    *,
    note: str = "",
    env: Optional[dict] = None,
) -> bool:
    """Convenience wrapper for v2_dispatcher: map a dispatcher state name
    (dispatched/building/verified/FAILED) onto its CC status and push it.

    Returns False (no-op, never raises) for unmapped states (e.g. the initial
    'backlog', which the ingest route already created the card at)."""
    cc_status = DISPATCH_STATE_TO_CC.get(dispatch_state)
    if not cc_status:
        return False
    return update_status(task_id, cc_status, note=note, env=env)


# ---------------------------------------------------------------------------
# PUBLIC API — post_activity posts a granular progress entry to the activity feed.
# ---------------------------------------------------------------------------
def post_activity(
    task_id: str,
    activity_type: str,
    message: str,
    metadata: Optional[dict] = None,
    *,
    env: Optional[dict] = None,
) -> bool:
    """POST one activity entry to ``/api/tasks/{id}/activities``.

    Auth: **Bearer only** — the middleware layer handles authentication for this
    endpoint; no HMAC is sent (contrast with move_task/ingest which are also
    HMAC-signed per the in-route verifier on /status).

    activity_type must be one of: spawned | updated | completed |
    file_created | status_changed (src/lib/validation.ts:31-37).

    FAIL-SOFT: never raises; a False return never blocks the build.

    Args:
        task_id:       CC task UUID returned by ingest_task.
        activity_type: One of _CC_ACTIVITY_TYPES.
        message:       Human-readable progress line (markdown OK).
        metadata:      Optional dict payload attached to the activity record.
        env:           Override os.environ (for testing).

    Returns:
        True on 2xx, False on any failure.
    """
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled; activity not posted.")
        return False

    tid = (task_id or "").strip()
    if not tid:
        _log("post_activity skipped — empty task_id.")
        return False

    atype = (activity_type or "").strip().lower()
    if atype not in _CC_ACTIVITY_TYPES:
        _log(
            f"post_activity skipped — invalid activity_type {activity_type!r} "
            f"(allowed: {', '.join(_CC_ACTIVITY_TYPES)})."
        )
        return False

    if not message or not message.strip():
        _log("post_activity skipped — empty message.")
        return False

    payload: dict = {
        "activity_type": atype,
        "message": message.strip(),
    }
    if metadata and isinstance(metadata, dict):
        payload["metadata"] = metadata

    # Bearer-only: pass a cfg copy with an empty secret so _post_json skips HMAC.
    cfg_bearer_only = dict(cfg, secret="")
    url = f"{cfg['base_url']}/api/tasks/{tid}/activities"
    try:
        status, body = _post_json(url, payload, cfg_bearer_only)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"POST {url} failed ({type(exc).__name__}: {exc}); activity not posted; build continues.")
        return False

    if 200 <= status < 300:
        _log(f"task {tid} activity posted: type={atype} http={status}.")
        return True

    _log(f"POST /activities non-2xx (HTTP {status}) for task {tid}: {body}; build continues.")
    return False


# ---------------------------------------------------------------------------
# B-U1 / U15 — persona-bundle READ. Rung 2 of the persona-bundle-acquisition
# ladder (persona_bundle_ladder.py): a read-only fetch against the Command
# Center's task_persona_bundle row so a CC-dispatched build gets the SAME
# blend bundle the Command Center already resolved, instead of re-selecting a
# second time or (today) never consuming a blend at all.
# ---------------------------------------------------------------------------
def fetch_persona_bundle(task_id: str, *, env: Optional[dict] = None) -> Optional[dict]:
    """GET ``/api/tasks/<id>/persona-bundle`` — a read-only endpoint mirroring
    the ``task_persona_bundle`` row (migration 090) for the given task.

    Auth: **Bearer only** (same class as ``post_activity`` — a read endpoint,
    no HMAC per-route layer).

    FAIL-SOFT: returns None on ANY failure — board unconfigured, network error,
    a non-2xx status, or a malformed body — including a 404 from an endpoint
    that has not shipped yet on the target Command Center. The caller (the
    bundle-acquisition ladder) falls through to the local ``--blend`` rung on
    any None. Never raises.

    Returns the bundle dict on success. Accepts either ``{"bundle": {...}}`` or
    a bare bundle object at the top level (endpoint-shape-tolerant since the
    CC-side route is not yet pinned by a shipped contract).
    """
    cfg = board_config(env)
    if cfg is None:
        return None
    tid = (task_id or "").strip()
    if not tid:
        return None

    url = f"{cfg['base_url']}/api/tasks/{tid}/persona-bundle"
    headers = {"Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        _log(f"GET {url} -> HTTP {exc.code}; persona bundle not fetched (falls through to local).")
        return None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"GET {url} failed ({type(exc).__name__}: {exc}); persona bundle not fetched.")
        return None

    if not (200 <= status < 300):
        _log(f"GET /persona-bundle non-2xx (HTTP {status}) for task {tid}; falls through to local.")
        return None
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    bundle = parsed.get("bundle") if "bundle" in parsed else parsed
    return bundle if isinstance(bundle, dict) and bundle else None


# ---------------------------------------------------------------------------
# U9 §7.2 — QC score emission. The per-build QC gate (qc-built-*.sh) emits its
# PASS/FAIL + numeric score INTO the card so the CC QC sweep reads ONE source (no
# re-scoring drift): the score rides in the activity metadata AND is human-visible
# in the message. This is the "emit QC scores into CC payloads" tightening.
# ---------------------------------------------------------------------------
def _normalize_qc_score(score) -> Optional[float]:
    """Coerce a score to a float clamped to [0, 10]. Returns None when the input is
    absent or non-numeric (a score-less QC emission is valid — passed-only)."""
    if score is None or (isinstance(score, str) and not score.strip()):
        return None
    try:
        val = float(score)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN
        return None
    return max(0.0, min(10.0, val))


def post_qc_score(
    task_id: str,
    score,
    gate: str,
    *,
    passed: Optional[bool] = None,
    scorecard_path: Optional[str] = None,
    note: str = "",
    env: Optional[dict] = None,
) -> bool:
    """Emit a QC verdict onto the card as a ``completed`` activity.

    Message:  ``QC: <score>/10 — <gate>[ [PASS|FAIL]]`` (score omitted when None).
    Metadata: ``{qc_score, qc_gate, qc_passed, scorecard_path}`` — the machine-
    parsable record the CC QC sweep reads to promote review → done from the SAME
    scorecard the gate scored (single source, no drift).

    FAIL-SOFT: never raises; a False return never blocks the build.

    Args:
        task_id:        CC task UUID returned by ingest_task.
        score:          0–10 numeric (int/float/str); clamped. None => passed-only.
        gate:           Gate label, e.g. 'qc-built-form' / 'qc-built-funnel'.
        passed:         Explicit PASS/FAIL. Defaults from score >= 8.5 when a score
                        is given and passed is not supplied.
        scorecard_path: Path to the scorecard the gate wrote (attached, not read).
        note:           Optional extra human-readable text appended to the message.
        env:            Override os.environ (for testing).

    Returns:
        True on 2xx, False on any failure.
    """
    tid = (task_id or "").strip()
    if not tid:
        _log("post_qc_score skipped — empty task_id.")
        return False

    gate_label = (gate or "").strip() or "qc"
    val = _normalize_qc_score(score)

    # Default the pass verdict from the score when not stated (8.5 is the standing
    # fleet threshold; runQCOnReview PASS >= 8.5).
    verdict = passed
    if verdict is None and val is not None:
        verdict = val >= 8.5

    if val is not None:
        message = f"QC: {val:.1f}/10 — {gate_label}"
    else:
        message = f"QC: {gate_label}"
    if verdict is not None:
        message += f" [{'PASS' if verdict else 'FAIL'}]"
    if note and note.strip():
        message += f" — {note.strip()}"

    metadata: dict = {"qc_gate": gate_label}
    if val is not None:
        metadata["qc_score"] = val
    if verdict is not None:
        metadata["qc_passed"] = bool(verdict)
    sc = (scorecard_path or "").strip()
    if sc:
        metadata["scorecard_path"] = sc

    return post_activity(tid, "completed", message, metadata=metadata, env=env)


# ---------------------------------------------------------------------------
# B-U6 / U20 — Producer reports USED personas back to the card
# (declared-vs-used, never silent).
#
# "A bundle-carrying task can never have its blend silently ignored — QC
# verifies the blend landed (B-U5), the card shows declared-vs-used (B-U6)."
# The Command Center side (blackceo-command-center src/lib/persona-mismatch.ts)
# compares this report's voice_persona_id against the card's DECLARED
# voice_persona_id (the resolved VOICE decision mirror column, migration 090)
# and renders a `persona_mismatch` chip + writes ONE `persona_mismatch`
# operator event on divergence. Agreement renders nothing.
# ---------------------------------------------------------------------------
def report_persona_used(
    task_id: str,
    *,
    page: Optional[str] = None,
    voice_persona_id: Optional[str] = None,
    topic_persona_id: Optional[str] = None,
    task_persona_id: Optional[str] = None,
    blend_directive_sha: Optional[str] = None,
    goal: Optional[str] = None,
    note: str = "",
    env: Optional[dict] = None,
) -> bool:
    """Report the personas the copy step ACTUALLY wrote with, onto the card.

    Posts ONE ``updated`` activity whose metadata is exactly::

        {kind: 'persona_used', page, voice_persona_id, topic_persona_id,
         task_persona_id, blend_directive_sha, goal}

    ``kind: 'persona_used'`` is an explicit discriminator the Command Center
    comparator keys on (never sniffs an arbitrary metadata shape). Call once
    per page — a multi-page funnel reports each page's used voice as its copy
    lands, independent of any deliverable()/artifact()/review() terminal call.

    Args:
        task_id:              CC task UUID returned by ingest_task.
        page:                 Page name/slug this report is for (e.g. 'main',
                              'upsell'). Omitted keys are never sent — a
                              caller reporting only the voice still produces a
                              valid, comparator-usable report.
        voice_persona_id:     REQUIRED — the VOICE persona the copy was
                              actually written in. Nothing is posted without it
                              (there would be nothing for the comparator to
                              compare).
        topic_persona_id:     The topic/craft hint persona actually used.
        task_persona_id:      The primary task-slot persona actually used.
        blend_directive_sha:  sha of the {{BLEND_DIRECTIVE}} text actually
                              rendered into the prompt (audit trail parity with
                              persona-selection-log.md's blend_directive_sha
                              line, B-U3/U17).
        goal:                 The page's conversion goal, for the human-facing
                              chip tooltip.
        note:                 Optional extra human-readable text.
        env:                  Override os.environ (for testing).

    Returns:
        True on 2xx, False on any failure (fail-soft — never blocks the build).
    """
    tid = (task_id or "").strip()
    if not tid:
        _log("report_persona_used skipped — empty task_id.")
        return False

    vpid = (voice_persona_id or "").strip()
    if not vpid:
        _log("report_persona_used skipped — empty voice_persona_id (nothing to compare).")
        return False

    page_label = (page or "").strip()
    message = f"Persona used: {page_label or 'page'} -> {vpid}"
    if note and note.strip():
        message += f" — {note.strip()}"

    metadata: dict = {"kind": "persona_used", "voice_persona_id": vpid}
    if page_label:
        metadata["page"] = page_label
    tpid = (topic_persona_id or "").strip()
    if tpid:
        metadata["topic_persona_id"] = tpid
    tkpid = (task_persona_id or "").strip()
    if tkpid:
        metadata["task_persona_id"] = tkpid
    sha = (blend_directive_sha or "").strip()
    if sha:
        metadata["blend_directive_sha"] = sha
    goal_text = (goal or "").strip()
    if goal_text:
        metadata["goal"] = goal_text

    return post_activity(tid, "updated", message, metadata=metadata, env=env)


# ---------------------------------------------------------------------------
# U9 §7.4 — Queue visibility. When the box-wide browser lock is held by another
# run, the waiting build parks its card at 'pending_dispatch' with the HOLDER's
# session name, so a wait is visible on the board, not mysterious.
# ---------------------------------------------------------------------------
def post_queue_wait(
    task_id: str,
    holder_session: str,
    *,
    note: str = "",
    env: Optional[dict] = None,
) -> bool:
    """Park the card at ``pending_dispatch`` naming the lock holder.

    Moves the card to ``pending_dispatch`` (a valid CC status) and posts a
    ``status_changed`` activity whose metadata carries ``holder_session`` so the
    board shows WHO holds the singleton browser lock.

    FAIL-SOFT: never raises; a False return never blocks the build.

    Args:
        task_id:        CC task UUID returned by ingest_task.
        holder_session: Canonical browser session name currently holding the lock
                        (e.g. 'ghl-skill6-<loc>'). Empty => generic wait note.
        note:           Optional extra human-readable text.
        env:            Override os.environ (for testing).

    Returns:
        True when either the status move or the activity post succeeds, else False.
    """
    tid = (task_id or "").strip()
    if not tid:
        _log("post_queue_wait skipped — empty task_id.")
        return False

    holder = (holder_session or "").strip()
    detail = f"queued — browser lock held by {holder}" if holder else "queued — waiting for browser lock"
    if note and note.strip():
        detail += f"; {note.strip()}"

    ok_move = move_task(tid, "pending_dispatch", note=detail, env=env)
    ok_act = post_activity(
        tid, "status_changed", detail,
        metadata={"holder_session": holder} if holder else None,
        env=env,
    )
    return ok_move or ok_act


# ---------------------------------------------------------------------------
# PUBLIC API — move_task transitions the Kanban card (HMAC-signed like ingest).
# ---------------------------------------------------------------------------
def move_task(
    task_id: str,
    status: str,
    note: Optional[str] = None,
    *,
    env: Optional[dict] = None,
) -> bool:
    """Transition a board card to ``status`` via ``POST /api/tasks/{id}/status``.

    Auth: **both headers** — ``Authorization: Bearer <MC_API_TOKEN>`` and
    ``x-webhook-signature: hex HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` over the
    compact JSON body — identical to the ingest signing contract.

    status in {backlog, inbox, planning, pending_dispatch, assigned, in_progress,
               review, testing, blocked, done}.

    PRODUCER RULE — "terminate at REVIEW, never at done":
    Any attempt to call ``move_task(task_id, 'done')`` is blocked by this
    function with a log warning and a False return. The only path to 'done' is
    the Command Center QC gate (``runQCOnReview`` in qc-scorer.ts:2988), which
    promotes the card from 'review' on PASS ≥ 8.5. Builders must call
    ``move_task('review')`` when an artifact is ready and let the sweep do the
    rest.

    FAIL-SOFT: never raises; a False return never blocks the build.

    Args:
        task_id: CC task UUID returned by ingest_task.
        status:  One of _CC_STATUS_VALUES (see above). 'done' is hard-blocked.
        note:    Optional human-readable transition note (markdown OK).
        env:     Override os.environ (for testing).

    Returns:
        True on 2xx, False on any failure or guard rejection.
    """
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled; task not moved.")
        return False

    tid = (task_id or "").strip()
    if not tid:
        _log("move_task skipped — empty task_id.")
        return False

    status_norm = (status or "").strip().lower()
    if status_norm not in _CC_STATUS_VALUES:
        _log(
            f"move_task skipped — invalid status {status!r} "
            f"(allowed: {', '.join(_CC_STATUS_VALUES)})."
        )
        return False

    # Enforce "terminate at REVIEW, never at done."
    # The QC gate (runQCOnReview) is the sole promoter from review → done.
    # Blocking it here makes the phase-driver structurally incapable of
    # self-certifying a build as complete.
    if status_norm == "done":
        _log(
            "move_task BLOCKED — the producer must never post 'done' directly. "
            "The only valid path to done is review → done via the QC gate "
            "(runQCOnReview, qc-scorer.ts:2988, PASS ≥ 8.5). "
            "Call move_task('review') and let the QC sweep promote the card."
        )
        return False

    payload: dict = {"status": status_norm}
    if note and note.strip():
        payload["note"] = note.strip()

    url = f"{cfg['base_url']}/api/tasks/{tid}/status"
    try:
        http_status, body = _post_json(url, payload, cfg)  # full dual headers
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"POST {url} failed ({type(exc).__name__}: {exc}); card not moved; build continues.")
        return False

    if 200 <= http_status < 300:
        _log(f"task {tid} → {status_norm} (HTTP {http_status}).")
        return True

    _log(
        f"POST /status non-2xx (HTTP {http_status}) for task {tid} → {status_norm}: "
        f"{body}; card not moved; build continues. "
        "If 404, CONFIRM the /status route in blackceo-command-center."
    )
    return False


# ---------------------------------------------------------------------------
# PUBLIC API — register_deliverable attaches the built artifact URL to the card.
# ---------------------------------------------------------------------------
def register_deliverable(
    task_id: str,
    url: str,
    meta: Optional[dict] = None,
    *,
    env: Optional[dict] = None,
) -> bool:
    """Register a built artifact via ``POST /api/tasks/{id}/deliverables``.

    Auth: both headers (Bearer + HMAC) per §6.2 "both headers on every request."
    If the /deliverables endpoint is absent (404) the call fail-softs and the
    build continues unregistered.

    FAIL-SOFT: never raises; a False return never blocks the build.

    Args:
        task_id: CC task UUID returned by ingest_task.
        url:     The built artifact URL (e.g. the live survey link captured from
                 Integrate → share in survey-builder-v2).
        meta:    Optional metadata dict (e.g. {"type": "survey_url",
                 "survey_id": "<id>", "slug": "<name>"}).
        env:     Override os.environ (for testing).

    Returns:
        True on 2xx, False on any failure (including 404 if endpoint absent).
    """
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled; deliverable not registered.")
        return False

    tid = (task_id or "").strip()
    if not tid:
        _log("register_deliverable skipped — empty task_id.")
        return False

    artifact_url = (url or "").strip()
    if not artifact_url:
        _log("register_deliverable skipped — empty url.")
        return False

    # The CC server's POST /api/tasks/{id}/deliverables validates against a Zod
    # schema requiring deliverable_type (enum: file|url|artifact|image) + a
    # non-empty title, with optional path/description — it does NOT accept a
    # bare `url` or `meta` key, so the old {"url": ..., "meta": ...} shape 400s.
    title = "Artifact URL"
    if meta and isinstance(meta, dict):
        for _key in ("title", "slug", "type"):
            _val = meta.get(_key)
            if _val:
                title = str(_val)
                break

    payload: dict = {
        "deliverable_type": "url",
        "title": title,
        "path": artifact_url,
    }
    if meta and isinstance(meta, dict):
        # Fold the metadata into `description` (JSON) so nothing is lost — the
        # schema has no `meta` field to carry it.
        payload["description"] = json.dumps(meta, separators=(",", ":"))

    endpoint = f"{cfg['base_url']}/api/tasks/{tid}/deliverables"
    try:
        http_status, body = _post_json(endpoint, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(
            f"POST {endpoint} failed ({type(exc).__name__}: {exc}); "
            "deliverable not registered; build continues."
        )
        return False

    if 200 <= http_status < 300:
        _log(f"task {tid} deliverable registered: url={artifact_url!r} http={http_status}.")
        return True

    _log(
        f"POST /deliverables non-2xx (HTTP {http_status}) for task {tid}: {body}; "
        "build continues. If 404, confirm /deliverables endpoint in blackceo-command-center."
    )
    return False


# ---------------------------------------------------------------------------
# PUBLIC API — BuildPhaseDriver: sequences all board moves for a single build.
# ---------------------------------------------------------------------------
class BuildPhaseDriver:
    """Phase-driver that sequences board moves across a Skill-6 build run.

    The driver enforces the end-to-end Kanban flow from PRD §6.2 / WIRING-MAP §4,
    with the U9 §7 tightenings folded in:

        on queue  → queued(holder_session)      → 'pending_dispatch' (lock wait; §7.4)
        on start  → move_task('in_progress') + post_activity('status_changed')
        per step  → post_activity('updated', 'Step k/N: ...')
        per artifact → deliverable(url, meta)    register each, card stays put (§7.1)
        on finish → review()                     → 'review' + post_activity('completed')
        on QC     → qc(score, gate)              → 'completed' QC activity w/ score (§7.2)
        on fail   → fail(reason=...)             'backlog'|'blocked' w/ taxonomy prefix (§7.3)

    artifact(url) remains a one-shot convenience = deliverable(url) + review() for
    single-deliverable builds (backward-compatible with existing callers).

    "Terminate at REVIEW, never at done":
        move_task('done') is hard-blocked inside move_task() — this class also
        never calls it, giving two independent layers of enforcement.  The only
        path to 'done' is the Command Center QC gate (runQCOnReview, PASS ≥ 8.5).

    All methods are FAIL-SOFT (never raise, never block the build).

    Usage::

        driver = BuildPhaseDriver(task_id)
        driver.start("GHL survey build started")
        for k, step_name in enumerate(build_steps, 1):
            execute_step(step_name)
            driver.step(k, len(build_steps), f"Step {k}/{len(build_steps)}: {step_name}")
        if survey_url:
            driver.artifact(survey_url, meta={"type": "survey_url"})
        else:
            driver.fail(human_required=False)   # retryable → backlog
    """

    def __init__(
        self,
        task_id: str,
        *,
        env: Optional[dict] = None,
    ) -> None:
        self._task_id = (task_id or "").strip()
        self._env = env   # None → use os.environ inside each helper
        self._started = False
        self._finished = False
        self._deliverables = 0   # U9: count registered deliverables (multi-artifact builds)

    # ------------------------------------------------------------------
    def start(self, note: str = "Build started") -> bool:
        """Signal build start: move_task('in_progress') + post_activity('status_changed').

        Idempotent — subsequent calls before finish() are no-ops (returns False).
        """
        if not self._task_id or self._finished or self._started:
            return False
        self._started = True
        ok1 = move_task(self._task_id, "in_progress", note=note, env=self._env)
        ok2 = post_activity(
            self._task_id, "status_changed",
            (note or "Build started — in progress"),
            env=self._env,
        )
        return ok1 or ok2

    # ------------------------------------------------------------------
    def step(self, k: int, total: int, message: str) -> bool:
        """Emit one 'updated' activity for material build step k-of-total.

        Auto-calls start() with a default note if the driver has not been
        started yet (e.g. caller skipped the explicit start() call).
        No-ops after finish() or fail().
        """
        if not self._task_id:
            return False
        if not self._started:
            self.start()
        if self._finished:
            return False
        msg = (message or "").strip() or f"Step {k}/{total}"
        return post_activity(self._task_id, "updated", msg, env=self._env)

    # ------------------------------------------------------------------
    def artifact(
        self,
        url: str,
        meta: Optional[dict] = None,
        note: str = "Artifact ready — moved to review for QC",
    ) -> bool:
        """Signal artifact ready — three ordered actions:

        1. register_deliverable(url, meta)  — attach the built URL to the card.
        2. move_task('review')              — NEVER 'done'; QC gate promotes.
        3. post_activity('completed', note) — surface the handoff to QC.

        Marks the phase finished so subsequent calls are no-ops.
        """
        if not self._task_id:
            return False
        if not self._started:
            self.start()
        if self._finished:
            return False
        self._finished = True

        ok1 = register_deliverable(self._task_id, url, meta=meta, env=self._env)
        # INVARIANT: never pass 'done' here — move_task also blocks it, giving
        # two independent layers of the "terminate at REVIEW" enforcement.
        ok2 = move_task(self._task_id, "review", note=note, env=self._env)
        ok3 = post_activity(self._task_id, "completed", note, env=self._env)
        return ok1 or ok2 or ok3

    # ------------------------------------------------------------------
    def deliverable(
        self,
        url: str,
        meta: Optional[dict] = None,
        note: str = "",
    ) -> bool:
        """Register ONE built artifact WITHOUT moving the card (U9 §7.1).

        A single build often produces several deliverables (preview URL, embed
        snippet path, survey/community URL). Call deliverable() once per artifact,
        then review() ONCE to move the card to review. Non-terminal, repeatable.

        Auto-starts the driver; no-ops after finish().
        """
        if not self._task_id:
            return False
        if not self._started:
            self.start()
        if self._finished:
            return False
        ok = register_deliverable(self._task_id, url, meta=meta, env=self._env)
        if ok:
            self._deliverables += 1
        if note and note.strip():
            post_activity(self._task_id, "file_created", note.strip(), env=self._env)
        return ok

    # ------------------------------------------------------------------
    def review(self, note: str = "Artifact(s) ready — moved to review for QC") -> bool:
        """Terminal move to 'review' after one or more deliverable() calls (U9 §7.1).

        NEVER 'done' — the CC QC gate is the sole promoter from review → done.
        Marks the phase finished so subsequent calls are no-ops.
        """
        if not self._task_id:
            return False
        if not self._started:
            self.start()
        if self._finished:
            return False
        self._finished = True
        ok1 = move_task(self._task_id, "review", note=note, env=self._env)
        ok2 = post_activity(self._task_id, "completed", note, env=self._env)
        return ok1 or ok2

    # ------------------------------------------------------------------
    def qc(
        self,
        score,
        gate: str,
        *,
        passed: Optional[bool] = None,
        scorecard_path: Optional[str] = None,
        note: str = "",
    ) -> bool:
        """Emit the per-build QC verdict onto the card (U9 §7.2).

        Deliberately NOT gated on _finished: QC runs while the card sits at
        'review', i.e. after artifact()/review(). Delegates to post_qc_score().
        """
        if not self._task_id:
            return False
        return post_qc_score(
            self._task_id, score, gate,
            passed=passed, scorecard_path=scorecard_path, note=note, env=self._env,
        )

    # ------------------------------------------------------------------
    def persona_used(
        self,
        *,
        page: Optional[str] = None,
        voice_persona_id: Optional[str] = None,
        topic_persona_id: Optional[str] = None,
        task_persona_id: Optional[str] = None,
        blend_directive_sha: Optional[str] = None,
        goal: Optional[str] = None,
        note: str = "",
    ) -> bool:
        """Report the personas ACTUALLY used at the copy step (B-U6 / U20).

        Declared-vs-used, never silent: delegates to report_persona_used().
        Call once per page as its copy lands. Deliberately NOT gated on
        _finished — persona-used reports are independent of the terminal
        artifact()/review() calls and may continue after the card has moved
        to review (e.g. a derived-pages pass that lands after the main page).
        """
        if not self._task_id:
            return False
        if not self._started:
            self.start()
        return report_persona_used(
            self._task_id,
            page=page,
            voice_persona_id=voice_persona_id,
            topic_persona_id=topic_persona_id,
            task_persona_id=task_persona_id,
            blend_directive_sha=blend_directive_sha,
            goal=goal,
            note=note,
            env=self._env,
        )

    # ------------------------------------------------------------------
    def queued(self, holder_session: str, note: str = "") -> bool:
        """Park the card at 'pending_dispatch' naming the lock holder (U9 §7.4).

        Called BEFORE start() while waiting on the box-wide browser lock, so a
        wait is visible on the board. Not gated on _started/_finished.
        """
        if not self._task_id:
            return False
        return post_queue_wait(self._task_id, holder_session, note=note, env=self._env)

    # ------------------------------------------------------------------
    def fail(self, *, human_required: bool = False, reason: Optional[str] = None) -> bool:
        """Signal build failure.

        human_required=False → move_task('backlog')   retryable by QC sweep.
        human_required=True  → move_task('blocked')   human sign-off required.

        reason (U9 §7.3): one of _CC_BLOCK_REASONS
        (AUTH-STOP|SELECTOR-MISS|RATE-LIMIT|TOKEN-CONTEXT|PARKED|VERIFY-FAIL).
        When given, the transition note is PREFIXED with '<REASON>: ' so the board
        is queryable for fleet-wide failure patterns. A reason outside the taxonomy
        is logged and the note is posted un-prefixed (never a fabricated category).

        Marks the phase finished so subsequent calls are no-ops.
        """
        if not self._task_id:
            return False
        self._finished = True
        target = "blocked" if human_required else "backlog"
        base_note = (
            "Build failed — human sign-off required; moved to blocked."
            if human_required
            else "Build failed — retryable; moved back to backlog."
        )
        prefix = ""
        if reason:
            r = str(reason).strip().upper()
            if r in _CC_BLOCK_REASONS:
                prefix = f"{r}: "
            else:
                _log(
                    f"fail() reason {reason!r} not in taxonomy "
                    f"({', '.join(_CC_BLOCK_REASONS)}); note posted un-prefixed."
                )
        note = f"{prefix}{base_note}"
        meta = {"block_reason": prefix[:-2]} if prefix else None
        ok1 = move_task(self._task_id, target, note=note, env=self._env)
        ok2 = post_activity(
            self._task_id, "status_changed", note, metadata=meta, env=self._env
        )
        return ok1 or ok2


# ---------------------------------------------------------------------------
# CLI — selftest + live demo
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """Unit-level self-test — no network required. Returns 0 on pass."""
    errors: list[str] = []

    # 1. board_config with no URL → None (board disabled).
    cfg = board_config({})
    if cfg is not None:
        errors.append("board_config({}) should return None when MISSION_CONTROL_URL absent")

    # 2. board_config with URL → dict with expected keys.
    cfg = board_config({"MISSION_CONTROL_URL": "https://example.zerohumanworkforce.com"})
    if cfg is None:
        errors.append("board_config should return dict when MISSION_CONTROL_URL is set")
    else:
        for k in ("base_url", "token", "secret", "timeout"):
            if k not in cfg:
                errors.append(f"board_config missing key: {k}")
        if cfg.get("base_url") != "https://example.zerohumanworkforce.com":
            errors.append(f"base_url unexpected: {cfg.get('base_url')!r}")

    # 3. _sign with no secret → None.
    sig = _sign("", b"hello")
    if sig is not None:
        errors.append("_sign with empty secret should return None")

    # 4. _sign with secret → hex string of correct length (SHA-256 = 64 hex chars).
    sig = _sign("mysecret", b"hello")
    if sig is None or len(sig) != 64:
        errors.append(f"_sign with secret should return 64-char hex, got {sig!r}")

    # 5. ingest_task with no URL → None (fail-soft, no exception).
    try:
        result = ingest_task("Test funnel job", env={})
        if result is not None:
            errors.append("ingest_task with no URL should return None")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ingest_task raised unexpectedly: {exc}")

    # 6. ingest_task with empty title → None.
    try:
        result = ingest_task("", env={"MISSION_CONTROL_URL": "https://x.example.com"})
        if result is not None:
            errors.append("ingest_task with empty title should return None")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ingest_task(empty title) raised unexpectedly: {exc}")

    # 7. department_slug mapping — including survey/form/quiz (Option 1, PRD §6.3).
    for jt, expected_slug, expected_source in [
        ("funnel", "funnels", "funnel"),
        ("sales-funnel", "funnels", "funnel"),
        ("opt-in", "funnels", "funnel"),
        ("survey", "web-development", "survey"),
        ("form", "web-development", "survey"),
        ("quiz", "web-development", "survey"),
        ("website", "web-development", "web-development"),
        ("landing-page", "web-development", "web-development"),
        ("single-page", "web-development", "web-development"),
    ]:
        # Mirror the mapping logic from ingest_task().
        norm = jt.lower().strip()
        if norm in ("funnel", "sales-funnel", "optin", "opt-in", "multistep"):
            slug = "funnels"
            src = "funnel"
        elif norm in ("survey", "form", "quiz"):
            slug = "web-development"
            src = "survey"
        else:
            slug = "web-development"
            src = "web-development"
        if slug != expected_slug:
            errors.append(f"job_type {jt!r} → department_slug {slug!r}, expected {expected_slug!r}")
        if src != expected_source:
            errors.append(f"job_type {jt!r} → source {src!r}, expected {expected_source!r}")

    # 7b. department_slug/source OVERRIDE (FIX-COPY-01 P2-COPY marketing routing).
    #     Mirror the override precedence: an explicit department_slug wins over the
    #     job_type-derived slug and defaults source to the same slug when unset.
    for dept_ov, src_ov, exp_slug, exp_src in [
        ("marketing", None, "marketing", "marketing"),
        ("marketing", "copy", "marketing", "copy"),
        (None, "copy", "web-development", "copy"),   # source-only override keeps derived slug
    ]:
        # start from the 'website' derivation (else-branch): slug=web-development, source=web-development
        slug, src = "web-development", "web-development"
        dep_ov = (dept_ov or "").strip()
        so_ov = (src_ov or "").strip()
        if dep_ov:
            slug = dep_ov
            src = (so_ov or dep_ov)
        elif so_ov:
            src = so_ov
        if slug != exp_slug:
            errors.append(f"override(dept={dept_ov!r},src={src_ov!r}) → slug {slug!r}, expected {exp_slug!r}")
        if src != exp_src:
            errors.append(f"override(dept={dept_ov!r},src={src_ov!r}) → source {src!r}, expected {exp_src!r}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1

    print("[selftest] PASS — all checks passed (no network required)")
    return 0


def _status_selftest() -> int:
    """update_status / update_status_for_state self-test — no network. Returns 0
    on pass. Satisfies the Area-6 DoD: card move backlog -> in_progress -> review
    (-> blocked) is exercised via the state mapping, and every guard fail-softs."""
    errors: list[str] = []

    # 1. No MISSION_CONTROL_URL => False, no raise (board disabled).
    try:
        if update_status("abc", "in_progress", env={}) is not False:
            errors.append("update_status with no MISSION_CONTROL_URL should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"update_status(no url) raised unexpectedly: {exc}")

    base_env = {"MISSION_CONTROL_URL": "https://x.example.com"}

    # 2. Empty task_id => False.
    try:
        if update_status("", "review", env=base_env) is not False:
            errors.append("update_status with empty task_id should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"update_status(empty id) raised unexpectedly: {exc}")

    # 3. Invalid status => False (never sends a bad enum value).
    try:
        if update_status("t1", "not-a-status", env=base_env) is not False:
            errors.append("update_status with invalid status should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"update_status(bad status) raised unexpectedly: {exc}")

    # 4. Path template missing '{id}' => False (guard).
    bad_tmpl_env = dict(base_env, CC_STATUS_PATH_TEMPLATE="/api/tasks/status")
    try:
        if update_status("t1", "blocked", env=bad_tmpl_env) is not False:
            errors.append("update_status with no '{id}' in CC_STATUS_PATH_TEMPLATE should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"update_status(bad template) raised unexpectedly: {exc}")

    # 5. Dispatcher-state mapping is the documented Area-6 table.
    expected = {"dispatched": "in_progress", "building": "in_progress",
                "verified": "review", "FAILED": "blocked"}
    if DISPATCH_STATE_TO_CC != expected:
        errors.append(f"DISPATCH_STATE_TO_CC drifted from Area-6 spec: {DISPATCH_STATE_TO_CC}")

    # 6. Every mapped CC status is a valid server enum value.
    for st in DISPATCH_STATE_TO_CC.values():
        if st not in _CC_STATUS_VALUES:
            errors.append(f"mapped status {st!r} not in _CC_STATUS_VALUES")

    # 7. update_status_for_state: a backlog/unknown state is a no-op (False, no
    #    raise); a known state with no board configured is also a fail-soft False.
    try:
        if update_status_for_state("t1", "backlog", env=base_env) is not False:
            errors.append("update_status_for_state('backlog') should be a no-op (False)")
        if update_status_for_state("t1", "verified", env={}) is not False:
            errors.append("update_status_for_state('verified') with no board should be False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"update_status_for_state raised unexpectedly: {exc}")

    # 8. DoD5 parity guard (v16.2.15): update_status('done') must be HARD-BLOCKED,
    #    mirroring the identical guard in move_task().  No caller can bypass the QC
    #    gate via update_status.
    try:
        if update_status("t1", "done", env=base_env) is not False:
            errors.append(
                "update_status('done') must be blocked (False) — "
                "terminate-at-REVIEW rule (DoD5 parity with move_task)"
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"update_status('done') raised unexpectedly: {exc}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[status-selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[status-selftest] PASS — all checks passed (no network required)")
    return 0


def _activity_selftest() -> int:
    """post_activity / move_task / register_deliverable self-test — no network. Returns 0 on pass."""
    errors: list[str] = []
    base_env = {"MISSION_CONTROL_URL": "https://x.example.com"}

    # 1. post_activity — no board → False, no raise.
    try:
        if post_activity("t1", "updated", "step 1", env={}) is not False:
            errors.append("post_activity(no board) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"post_activity(no board) raised: {exc}")

    # 2. post_activity — empty task_id → False.
    try:
        if post_activity("", "updated", "step 1", env=base_env) is not False:
            errors.append("post_activity(empty task_id) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"post_activity(empty task_id) raised: {exc}")

    # 3. post_activity — invalid activity_type → False.
    try:
        if post_activity("t1", "deleted", "oops", env=base_env) is not False:
            errors.append("post_activity(bad activity_type) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"post_activity(bad type) raised: {exc}")

    # 4. post_activity — empty message → False.
    try:
        if post_activity("t1", "updated", "", env=base_env) is not False:
            errors.append("post_activity(empty message) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"post_activity(empty msg) raised: {exc}")

    # 5. move_task — no board → False, no raise.
    try:
        if move_task("t1", "in_progress", env={}) is not False:
            errors.append("move_task(no board) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"move_task(no board) raised: {exc}")

    # 6. move_task — empty task_id → False.
    try:
        if move_task("", "review", env=base_env) is not False:
            errors.append("move_task(empty task_id) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"move_task(empty id) raised: {exc}")

    # 7. move_task — invalid status → False.
    try:
        if move_task("t1", "not-a-status", env=base_env) is not False:
            errors.append("move_task(bad status) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"move_task(bad status) raised: {exc}")

    # 8. move_task — 'done' is HARD-BLOCKED; the producer must never post done.
    try:
        if move_task("t1", "done", env=base_env) is not False:
            errors.append("move_task('done') must be blocked (False) — terminate-at-REVIEW rule")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"move_task('done') raised: {exc}")

    # 9. move_task — all valid statuses except 'done' are accepted (no board so
    #    they return False at the network call, not at the guard).
    for st in _CC_STATUS_VALUES:
        if st == "done":
            continue  # already tested above
        try:
            # With a real board URL the call would attempt HTTP; here it fails at
            # the network level (urlopen) and the guard-level tests have already
            # passed. We just verify no exception is raised.
            move_task("t1", st, env={"MISSION_CONTROL_URL": "http://127.0.0.1:0"})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"move_task({st!r}) raised unexpectedly: {exc}")

    # 10. register_deliverable — no board → False.
    try:
        if register_deliverable("t1", "https://example.com/survey", env={}) is not False:
            errors.append("register_deliverable(no board) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"register_deliverable(no board) raised: {exc}")

    # 11. register_deliverable — empty task_id → False.
    try:
        if register_deliverable("", "https://example.com/s", env=base_env) is not False:
            errors.append("register_deliverable(empty task_id) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"register_deliverable(empty id) raised: {exc}")

    # 12. register_deliverable — empty url → False.
    try:
        if register_deliverable("t1", "", env=base_env) is not False:
            errors.append("register_deliverable(empty url) should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"register_deliverable(empty url) raised: {exc}")

    # 13. register_deliverable — payload shape matches the CC Zod schema
    #     (deliverable_type + title + path; NEVER a bare top-level url/meta —
    #     that shape 400s against the real POST /api/tasks/{id}/deliverables).
    _captured_payload: dict = {}
    _orig_post_json = globals()["_post_json"]

    def _fake_post_json(url, payload, cfg, method="POST"):  # noqa: ANN001
        _captured_payload.clear()
        _captured_payload.update(payload)
        return 201, {"ok": True}

    globals()["_post_json"] = _fake_post_json
    try:
        register_deliverable(
            "t1",
            "https://example.com/survey",
            meta={"type": "survey_url", "slug": "intake-survey"},
            env=base_env,
        )
        if "deliverable_type" not in _captured_payload:
            errors.append("register_deliverable payload missing 'deliverable_type'")
        if "title" not in _captured_payload:
            errors.append("register_deliverable payload missing 'title'")
        if _captured_payload.get("path") != "https://example.com/survey":
            errors.append(
                "register_deliverable payload 'path' should equal the url, got "
                f"{_captured_payload.get('path')!r}"
            )
        if "url" in _captured_payload:
            errors.append("register_deliverable payload must NOT contain a bare top-level 'url' key")
        if "meta" in _captured_payload:
            errors.append("register_deliverable payload must NOT contain a bare top-level 'meta' key")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"register_deliverable(payload-shape) raised: {exc}")
    finally:
        globals()["_post_json"] = _orig_post_json

    # 14. Verify all valid activity_type values are in _CC_ACTIVITY_TYPES.
    for at in ("spawned", "updated", "completed", "file_created", "status_changed"):
        if at not in _CC_ACTIVITY_TYPES:
            errors.append(f"_CC_ACTIVITY_TYPES missing expected value: {at!r}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[activity-selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[activity-selftest] PASS — all checks passed (no network required)")
    return 0


def _phase_driver_selftest() -> int:
    """BuildPhaseDriver self-test — no network. Returns 0 on pass."""
    errors: list[str] = []

    # 1. Empty task_id → all methods are no-ops (False), no raises.
    try:
        d = BuildPhaseDriver("")
        if d.start() is not False:
            errors.append("driver.start() with empty task_id should return False")
        if d.step(1, 3, "step msg") is not False:
            errors.append("driver.step() with empty task_id should return False")
        if d.artifact("https://x.com/s") is not False:
            errors.append("driver.artifact() with empty task_id should return False")
        if d.fail() is not False:
            errors.append("driver.fail() with empty task_id should return False")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"BuildPhaseDriver('') raised: {exc}")

    # 2. start() is idempotent — second call returns False (already started).
    try:
        d = BuildPhaseDriver("task-abc", env={})
        d.start("first call")
        if d.start("second call") is not False:
            errors.append("driver.start() second call should be a no-op (False)")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"driver.start() idempotency raised: {exc}")

    # 3. finish() via artifact() blocks further calls.
    try:
        d = BuildPhaseDriver("task-xyz", env={})
        d.artifact("https://x.com/s")         # no board → fails at network, but sets _finished
        if d.artifact("https://x.com/s2") is not False:
            errors.append("driver.artifact() after finish should be a no-op (False)")
        if d.step(1, 1, "late step") is not False:
            errors.append("driver.step() after finish should be a no-op (False)")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"driver.artifact() finish-guard raised: {exc}")

    # 4. fail() blocks further calls.
    try:
        d = BuildPhaseDriver("task-fail", env={})
        d.fail(human_required=True)
        if d.fail(human_required=False) is not False:
            errors.append("driver.fail() after finish should be a no-op (False)")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"driver.fail() finish-guard raised: {exc}")

    # 5. step() auto-starts the driver if start() was not called.
    try:
        d = BuildPhaseDriver("task-auto", env={})
        if d._started:
            errors.append("driver._started should be False before any call")
        d.step(1, 2, "auto-start step")
        if not d._started:
            errors.append("driver.step() should auto-call start() if not yet started")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"driver.step() auto-start raised: {exc}")

    # 6. CRITICAL — 'done' must never be posted by the driver. Confirm that
    #    move_task blocks it independently (belt-and-suspenders test).
    try:
        env_no_board = {}
        # Even if somehow the driver called move_task('done'), the inner guard blocks it.
        if move_task("t1", "done", env=env_no_board) is not False:
            errors.append("move_task('done') must return False — terminate-at-REVIEW invariant")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"move_task('done') raised in phase-driver test: {exc}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[phase-driver-selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[phase-driver-selftest] PASS — all checks passed (no network required)")
    return 0


def _u9_selftest() -> int:
    """U9 §7 tightenings self-test — no network. Returns 0 on pass.

    Covers: QC-score normalization + emission payload, failure taxonomy prefix,
    queue-visibility pending_dispatch move, and multi-deliverable driver flow."""
    errors: list[str] = []
    base_env = {"MISSION_CONTROL_URL": "https://x.example.com"}

    # 1. Score normalization: clamp, coerce, reject non-numeric/None/NaN.
    cases = [
        (8.5, 8.5), (10, 10.0), ("9.2", 9.2), (0, 0.0),
        (11, 10.0), (-3, 0.0), ("", None), (None, None), ("abc", None),
        (float("nan"), None),
    ]
    for raw, want in cases:
        got = _normalize_qc_score(raw)
        if want is None:
            if got is not None:
                errors.append(f"_normalize_qc_score({raw!r}) should be None, got {got!r}")
        elif got != want:
            errors.append(f"_normalize_qc_score({raw!r}) => {got!r}, expected {want!r}")

    # 2. post_qc_score builds the right activity payload (capture via post_activity).
    captured = {}

    def _fake_activity(task_id, activity_type, message, metadata=None, *, env=None):
        captured["task_id"] = task_id
        captured["type"] = activity_type
        captured["message"] = message
        captured["metadata"] = metadata or {}
        return True

    orig_activity = globals()["post_activity"]
    globals()["post_activity"] = _fake_activity
    try:
        # a) explicit score + gate → derives PASS at >= 8.5, score in metadata.
        post_qc_score("t1", 8.5, "qc-built-form", scorecard_path="/e/sc.json", env=base_env)
        if captured.get("type") != "completed":
            errors.append("post_qc_score must post a 'completed' activity")
        if "QC: 8.5/10 — qc-built-form" not in captured.get("message", ""):
            errors.append(f"QC message shape wrong: {captured.get('message')!r}")
        if "[PASS]" not in captured.get("message", ""):
            errors.append("score 8.5 should derive [PASS] (>= 8.5 threshold)")
        md = captured.get("metadata", {})
        if md.get("qc_score") != 8.5 or md.get("qc_gate") != "qc-built-form":
            errors.append(f"QC metadata missing score/gate: {md!r}")
        if md.get("qc_passed") is not True:
            errors.append("QC metadata qc_passed should be True at 8.5")
        if md.get("scorecard_path") != "/e/sc.json":
            errors.append("QC metadata must attach scorecard_path")

        # b) sub-threshold score derives FAIL.
        post_qc_score("t1", 7.0, "qc-built-funnel", env=base_env)
        if "[FAIL]" not in captured.get("message", ""):
            errors.append("score 7.0 should derive [FAIL] (< 8.5)")

        # c) score-less, explicit passed=True → passed-only message, no qc_score key.
        post_qc_score("t1", None, "render-gate", passed=True, env=base_env)
        if "QC: render-gate [PASS]" not in captured.get("message", ""):
            errors.append(f"score-less QC message wrong: {captured.get('message')!r}")
        if "qc_score" in captured.get("metadata", {}):
            errors.append("score-less QC must omit qc_score from metadata")

        # d) empty task_id → False, no post.
        if post_qc_score("", 9.0, "g", env=base_env) is not False:
            errors.append("post_qc_score(empty task_id) should return False")
    finally:
        globals()["post_activity"] = orig_activity

    # 3. Failure taxonomy: valid reason prefixes the note; invalid is dropped.
    moves = []
    acts = []

    def _fake_move(task_id, status, note=None, *, env=None):
        moves.append({"status": status, "note": note})
        return True

    def _fake_act2(task_id, activity_type, message, metadata=None, *, env=None):
        acts.append({"type": activity_type, "message": message, "metadata": metadata})
        return True

    orig_move = globals()["move_task"]
    orig_act = globals()["post_activity"]
    globals()["move_task"] = _fake_move
    globals()["post_activity"] = _fake_act2
    try:
        d = BuildPhaseDriver("tk", env=base_env)
        d.fail(human_required=True, reason="selector-miss")  # case-insensitive
        if not moves or moves[-1]["status"] != "blocked":
            errors.append("fail(human_required=True) must move to 'blocked'")
        if not moves or not str(moves[-1]["note"]).startswith("SELECTOR-MISS: "):
            errors.append(f"fail reason must prefix note: {moves[-1]['note']!r}")
        if not acts or (acts[-1]["metadata"] or {}).get("block_reason") != "SELECTOR-MISS":
            errors.append("fail must attach block_reason metadata")

        moves.clear(); acts.clear()
        d2 = BuildPhaseDriver("tk2", env=base_env)
        d2.fail(reason="not-a-real-reason")  # invalid → un-prefixed, still fail-soft
        if not moves or moves[-1]["status"] != "backlog":
            errors.append("fail() default target must be 'backlog'")
        if moves and str(moves[-1]["note"]).split(":")[0] in _CC_BLOCK_REASONS:
            errors.append("an invalid reason must NOT produce a taxonomy prefix")

        # 4. Queue visibility → pending_dispatch naming the holder.
        moves.clear(); acts.clear()
        post_queue_wait("tk3", "ghl-skill6-LOC123", env=base_env)
        if not moves or moves[-1]["status"] != "pending_dispatch":
            errors.append("post_queue_wait must move to 'pending_dispatch'")
        if not moves or "ghl-skill6-LOC123" not in str(moves[-1]["note"]):
            errors.append("post_queue_wait note must name the lock holder")
        if not acts or (acts[-1]["metadata"] or {}).get("holder_session") != "ghl-skill6-LOC123":
            errors.append("post_queue_wait must carry holder_session metadata")

        # 5. Multi-deliverable flow: deliverable() is non-terminal, review() terminates.
        moves.clear(); acts.clear()
        reg_calls = []
        orig_reg = globals()["register_deliverable"]
        globals()["register_deliverable"] = (
            lambda tid, url, meta=None, *, env=None: (reg_calls.append(url) or True)
        )
        try:
            dm = BuildPhaseDriver("tk4", env=base_env)
            dm.deliverable("https://x/preview", meta={"type": "preview_url"})
            dm.deliverable("https://x/embed", meta={"type": "embed_snippet"})
            if len(reg_calls) != 2:
                errors.append(f"two deliverable() calls should register 2, got {len(reg_calls)}")
            if dm._finished:
                errors.append("deliverable() must NOT finish the phase")
            rc_review = dm.review()
            if not rc_review or not dm._finished:
                errors.append("review() must move to 'review' and finish the phase")
            if not moves or moves[-1]["status"] != "review":
                errors.append("review() must post 'review' status")
            if dm.deliverable("https://x/late") is not False:
                errors.append("deliverable() after review() must be a no-op (False)")
        finally:
            globals()["register_deliverable"] = orig_reg
    finally:
        globals()["move_task"] = orig_move
        globals()["post_activity"] = orig_act

    # 6. Taxonomy tuple is exactly the spec set (guards drift).
    if set(_CC_BLOCK_REASONS) != {
        "AUTH-STOP", "SELECTOR-MISS", "RATE-LIMIT", "TOKEN-CONTEXT", "PARKED", "VERIFY-FAIL"
    }:
        errors.append(f"_CC_BLOCK_REASONS drifted from spec taxonomy: {_CC_BLOCK_REASONS}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[u9-selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[u9-selftest] PASS — all checks passed (no network required)")
    return 0


def _persona_used_selftest() -> int:
    """B-U6 / U20 report_persona_used / BuildPhaseDriver.persona_used self-test —
    no network. Returns 0 on pass."""
    errors: list[str] = []
    base_env = {"MISSION_CONTROL_URL": "https://x.example.com"}

    captured: list[dict] = []

    def _fake_activity(task_id, activity_type, message, metadata=None, *, env=None):
        captured.append(
            {"task_id": task_id, "type": activity_type, "message": message, "metadata": metadata or {}}
        )
        return True

    orig_activity = globals()["post_activity"]
    globals()["post_activity"] = _fake_activity
    try:
        # 1. empty task_id → False, nothing posted.
        captured.clear()
        if report_persona_used("", voice_persona_id="hormozi-100m-offers", env=base_env) is not False:
            errors.append("report_persona_used(empty task_id) should return False")
        if captured:
            errors.append("report_persona_used(empty task_id) must not post anything")

        # 2. empty voice_persona_id → False, nothing posted (nothing to compare).
        captured.clear()
        if report_persona_used("t1", voice_persona_id="", env=base_env) is not False:
            errors.append("report_persona_used(empty voice_persona_id) should return False")
        if captured:
            errors.append("report_persona_used(empty voice_persona_id) must not post anything")

        # 3. full payload — every field lands in metadata with the 'kind' discriminator.
        captured.clear()
        ok = report_persona_used(
            "t1",
            page="main",
            voice_persona_id="hormozi-100m-offers",
            topic_persona_id="miller-building-storybrand",
            task_persona_id="hormozi-100m-offers",
            blend_directive_sha="abc123def456",
            goal="book-a-call",
            env=base_env,
        )
        if not ok:
            errors.append("report_persona_used(full payload) should return True")
        if len(captured) != 1:
            errors.append(f"report_persona_used should post exactly one activity, got {len(captured)}")
        else:
            act = captured[0]
            if act["type"] != "updated":
                errors.append(f"report_persona_used must post activity_type='updated', got {act['type']!r}")
            md = act["metadata"]
            if md.get("kind") != "persona_used":
                errors.append(f"metadata must carry kind='persona_used', got {md.get('kind')!r}")
            for k, v in (
                ("page", "main"),
                ("voice_persona_id", "hormozi-100m-offers"),
                ("topic_persona_id", "miller-building-storybrand"),
                ("task_persona_id", "hormozi-100m-offers"),
                ("blend_directive_sha", "abc123def456"),
                ("goal", "book-a-call"),
            ):
                if md.get(k) != v:
                    errors.append(f"metadata[{k!r}] = {md.get(k)!r}, expected {v!r}")

        # 4. partial payload (only page + voice) omits every unset optional key —
        #    never a fabricated empty-string field.
        captured.clear()
        report_persona_used("t1", page="upsell", voice_persona_id="wiebe-copy-hackers", env=base_env)
        md = captured[0]["metadata"] if captured else {}
        for k in ("topic_persona_id", "task_persona_id", "blend_directive_sha", "goal"):
            if k in md:
                errors.append(f"partial-payload metadata must OMIT unset key {k!r}, got {md.get(k)!r}")
        if md.get("page") != "upsell" or md.get("voice_persona_id") != "wiebe-copy-hackers":
            errors.append(f"partial-payload metadata missing required fields: {md!r}")

        # 5. BuildPhaseDriver.persona_used() delegates + auto-starts the driver.
        captured.clear()
        d = BuildPhaseDriver("t-driver", env=base_env)
        if d._started:
            errors.append("driver._started should be False before persona_used()")
        rc = d.persona_used(page="main", voice_persona_id="hormozi-100m-offers")
        if not rc:
            errors.append("driver.persona_used() should return True (fake post_activity always True)")
        if not d._started:
            errors.append("driver.persona_used() must auto-start the driver")
        persona_used_calls = [c for c in captured if (c["metadata"] or {}).get("kind") == "persona_used"]
        if len(persona_used_calls) != 1:
            errors.append(
                f"driver.persona_used() should post exactly one persona_used activity, "
                f"got {len(persona_used_calls)}"
            )

        # 6. driver.persona_used() with empty task_id → False, no post.
        captured.clear()
        d_empty = BuildPhaseDriver("", env=base_env)
        if d_empty.persona_used(voice_persona_id="hormozi-100m-offers") is not False:
            errors.append("driver.persona_used() with empty task_id should return False")
        if captured:
            errors.append("driver.persona_used() with empty task_id must not post anything")

        # 7. persona_used() is callable AFTER the phase finished (review()) — a
        #    derived-pages pass may report used personas after the main page
        #    already moved the card to review.
        captured.clear()
        d_late = BuildPhaseDriver("t-late", env=base_env)
        d_late.review()
        if not d_late._finished:
            errors.append("review() should finish the phase (precondition for check 7)")
        rc_late = d_late.persona_used(page="thank-you", voice_persona_id="hormozi-100m-offers")
        if not rc_late:
            errors.append("driver.persona_used() must still post after the phase finished (not gated on _finished)")
    finally:
        globals()["post_activity"] = orig_activity

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[persona-used-selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[persona-used-selftest] PASS — all checks passed (no network required)")
    return 0


def _demo(env: Optional[dict] = None) -> int:
    """Live demo — POST a test task to the board and print the result."""
    cfg = board_config(env)
    if cfg is None:
        print(
            "ERROR: MISSION_CONTROL_URL not set. Export it and retry:\n"
            "  MISSION_CONTROL_URL=https://... MC_API_TOKEN=... python3 cc_board.py --demo",
            file=sys.stderr,
        )
        return 1

    ikey = f"skill6-demo-{uuid.uuid4()}"
    task_id = ingest_task(
        title="[DEMO] Sales Funnel Build — Skill 06 board producer test",
        description=(
            "Automated demo card created by 06-ghl-install-pages/tools/cc_board.py --demo.\n"
            "This card verifies that a Skill-6 funnel/website request routes to the "
            "Funnels or Web Development department on the Command Center Kanban board."
        ),
        job_type="funnel",
        priority="high",
        idempotency_key=ikey,
        env=env,
    )
    if task_id:
        print(json.dumps({"ok": True, "task_id": task_id, "idempotency_key": ikey}, indent=2))
        return 0
    print(json.dumps({"ok": False, "task_id": None, "idempotency_key": ikey}, indent=2))
    return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Skill-6 Command Center board producer")
    parser.add_argument("--selftest", action="store_true", help="Run ALL unit tests — ingest + status + U9 (no network)")
    parser.add_argument("--status-selftest", action="store_true", help="Run update_status unit tests only (no network)")
    parser.add_argument("--u9-selftest", action="store_true", help="Run U9 §7 tightenings unit tests only (no network)")
    parser.add_argument("--demo", action="store_true", help="POST a live demo card to the board")
    parser.add_argument("--title", default="", help="Task title for --demo override")
    parser.add_argument(
        "--job-type",
        default="funnel",
        choices=["funnel", "website"],
        help="Job type for --demo",
    )
    # U9 §7.2 — QC-score emission entry point used by qc-built-*.sh gates (fail-soft).
    parser.add_argument("--emit-qc", action="store_true",
                        help="Emit a QC verdict onto a card (post_qc_score). Requires --task-id + --gate.")
    parser.add_argument("--task-id", default="", help="CC task UUID (with --emit-qc)")
    parser.add_argument("--gate", default="", help="QC gate label, e.g. qc-built-form (with --emit-qc)")
    parser.add_argument("--score", default="", help="0-10 numeric QC score (with --emit-qc); omit for passed-only")
    parser.add_argument("--passed", default="", help="'1'/'0'/'true'/'false' explicit PASS/FAIL (with --emit-qc)")
    parser.add_argument("--scorecard", default="", help="Path to the scorecard JSON (with --emit-qc). If --score is "
                                                        "omitted, a numeric 'score' key is read from this file.")
    args = parser.parse_args()

    if args.selftest:
        rc_ingest = _selftest()
        rc_status = _status_selftest()
        rc_activity = _activity_selftest()
        rc_phase = _phase_driver_selftest()
        rc_u9 = _u9_selftest()
        rc_persona_used = _persona_used_selftest()
        sys.exit(0 if (rc_ingest == 0 and rc_status == 0 and rc_activity == 0
                       and rc_phase == 0 and rc_u9 == 0 and rc_persona_used == 0) else 1)
    elif args.status_selftest:
        sys.exit(_status_selftest())
    elif args.u9_selftest:
        sys.exit(_u9_selftest())
    elif args.emit_qc:
        # Fail-soft QC emission for the shell gates. Never a build-blocker: any
        # problem prints to stderr and exits 0 so a QC gate's own exit code (the
        # real verdict) is what the build reads.
        _tid = args.task_id.strip()
        _gate = args.gate.strip()
        if not _tid or not _gate:
            _log("--emit-qc requires --task-id and --gate; skipped (no-op).")
            sys.exit(0)
        _score = args.score.strip() or None
        # When no explicit --score, try to read a numeric 'score' from the scorecard.
        if _score is None and args.scorecard.strip():
            try:
                with open(args.scorecard.strip()) as _fh:
                    _sc = json.load(_fh)
                if isinstance(_sc, dict):
                    for _k in ("score", "score_10", "overall_score", "weighted_score", "final_score"):
                        if _k in _sc and _normalize_qc_score(_sc[_k]) is not None:
                            _score = _sc[_k]
                            break
            except (OSError, ValueError) as _exc:
                _log(f"--emit-qc could not read score from {args.scorecard!r} ({_exc}); passed-only.")
        _passed = None
        _pv = args.passed.strip().lower()
        if _pv in ("1", "true", "yes", "pass"):
            _passed = True
        elif _pv in ("0", "false", "no", "fail"):
            _passed = False
        ok = post_qc_score(_tid, _score, _gate, passed=_passed,
                           scorecard_path=(args.scorecard.strip() or None))
        _log(f"--emit-qc {'posted' if ok else 'not posted (fail-soft)'} "
             f"task={_tid} gate={_gate} score={_score}.")
        sys.exit(0)
    elif args.demo:
        sys.exit(_demo())
    else:
        parser.print_help()
        sys.exit(1)
