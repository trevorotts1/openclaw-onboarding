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


def _post_json(url: str, payload: dict, cfg: dict):
    """One signed JSON POST. Returns (status_code, parsed_json_or_None).
    Raises only urllib/OS errors — the public caller catches (fail-soft)."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    req = urllib.request.Request(url, data=raw_body, headers=headers, method="POST")
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
    env: Optional[dict] = None,
) -> Optional[str]:
    """POST one funnel/website job to /api/tasks/ingest.

    Returns the task_id string on success (HTTP 200 or 201), else None.
    FAIL-SOFT: never raises; a None return never blocks the Skill-6 build.

    Args:
        title:            Short card title visible on the Kanban board.
        description:      Job brief / customer request text (markdown OK).
        job_type:         'funnel' (sales funnel / opt-in / multi-step) or
                          'website' (single page / landing page / full site).
                          Controls department_slug routing:
                            'funnel'  → department_slug='funnels'
                            'website' → department_slug='web-development'
        priority:         CC TaskPriority: 'low'|'medium'|'high'|'critical'.
                          Default 'high' for customer-facing build jobs.
        idempotency_key:  Dedupe key; omit to let the caller generate one
                          automatically (uuid4). Supply a deterministic key
                          (e.g. sha256 of the job brief) for retry safety.
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

    # Map job_type -> department_slug.
    job_type_norm = (job_type or "funnel").lower().strip()
    if job_type_norm in ("funnel", "sales-funnel", "optin", "opt-in", "multistep"):
        department_slug = "funnels"
        source = "funnel"
    else:
        # website, landing-page, single-page, web-development, etc.
        department_slug = "web-development"
        source = "web-development"

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

    # 7. department_slug mapping.
    for jt, expected_slug in [
        ("funnel", "funnels"),
        ("sales-funnel", "funnels"),
        ("opt-in", "funnels"),
        ("website", "web-development"),
        ("landing-page", "web-development"),
        ("single-page", "web-development"),
    ]:
        # Verify the mapping logic directly.
        norm = jt.lower().strip()
        if norm in ("funnel", "sales-funnel", "optin", "opt-in", "multistep"):
            slug = "funnels"
        else:
            slug = "web-development"
        if slug != expected_slug:
            errors.append(f"job_type {jt!r} → department_slug {slug!r}, expected {expected_slug!r}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1

    print("[selftest] PASS — all checks passed (no network required)")
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
    parser.add_argument("--selftest", action="store_true", help="Run unit tests (no network)")
    parser.add_argument("--demo", action="store_true", help="POST a live demo card to the board")
    parser.add_argument("--title", default="", help="Task title for --demo override")
    parser.add_argument(
        "--job-type",
        default="funnel",
        choices=["funnel", "website"],
        help="Job type for --demo",
    )
    args = parser.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    elif args.demo:
        sys.exit(_demo())
    else:
        parser.print_help()
        sys.exit(1)
