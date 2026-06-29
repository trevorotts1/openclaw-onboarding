#!/usr/bin/env python3
"""
cc_board.py — Presentations PRODUCER-SIDE Command Center caller (FAIL-SOFT) (FIX G).

The producer half of the board hookup whose server half is ``POST /api/tasks/ingest``
(+ ``PATCH /api/tasks/[id]``) in trevorotts1/blackceo-command-center. It lands a
governed deck run on the board as ONE task at job-start and moves it through the
lifecycle at phase boundaries, so a flagship deck is never invisible on the board
again. Mirrors the VERIFIED Skill-48 cc_board.py pattern (48-facebook-ad-generator).

NON-NEGOTIABLE DESIGN RULES (identical to the Skill-48 contract)
  * FAIL-SOFT. A board outage, missing token, unreachable URL, HTTP error, timeout,
    or any other failure is CAUGHT, LOGGED to stderr, and the deck run CONTINUES.
    Boarding the run is a convenience, never a gate on the deck itself. Every public
    function returns a value and NEVER raises. The ONLY thing that fails a deck for
    "not on the board" is the OFFLINE chk_cc_registered() closeout check
    (AF-CC-UNREGISTERED), which is fail-CLOSED on never-attempted and fail-SOFT on
    transport: it reads task_id out of process_manifest.json, so it passes whether
    or not the live POST reached a degraded board (degrade-to-ungrouped is logged).
  * AUTH PARITY with the endpoint:
      - ``Authorization: Bearer <MC_API_TOKEN>`` (global middleware layer).
      - ``x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)`` hex (per-route
        layer, copied verbatim from /api/tasks/ingest). We sign the EXACT bytes sent.
  * STDLIB ONLY (urllib) — zero third-party deps.
  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => clean no-op.
      MISSION_CONTROL_URL  base URL (e.g. https://<box>.zerohumanworkforce.com).
                           Absent => board disabled (clean no-op; run unaffected).
      MC_API_TOKEN         long-lived bearer (optional).
      WEBHOOK_SECRET       HMAC secret (optional; CC_WEBHOOK_SECRET also accepted).
      CC_BOARD_TIMEOUT     per-request timeout seconds (default 8).
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

# CC TaskStatus + legal transitions (server is the final authority; this only walks
# a minimal legal path client-side).
VALID_STATUSES = ("backlog", "in_progress", "review", "blocked", "done")
VALID_BLOCKED_REASONS = ("decision", "approval", "credential", "payment")
_DEFAULT_TIMEOUT = 8
DEPARTMENT_SLUG = "presentations"


def _log(msg: str) -> None:
    print(f"[cc_board:presentations] {msg}", file=sys.stderr, flush=True)


def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment; None (clean no-op) when
    MISSION_CONTROL_URL is unset. Never raises."""
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


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: Optional[dict], cfg: dict):
    """One signed JSON request -> (status_code, parsed_json_or_None). Raises only
    urllib/OS errors, which the public callers catch (fail-soft)."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else b""
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
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# JOB-START — POST /api/tasks/ingest (idempotent on idempotency_key, server-side)
# ---------------------------------------------------------------------------
def ingest_job(
    deck_slug: str,
    title: str,
    *,
    description: str = "",
    owner: Optional[str] = None,
    run_dir: Optional[Path] = None,
    env: Optional[dict] = None,
) -> Optional[str]:
    """Open (or idempotently re-fetch) the deck task on the board. Returns the task_id
    on success, else None (FAIL-SOFT). Stamps task_id into process_manifest.json so the
    offline AF-CC-UNREGISTERED check passes whether or not the live POST succeeded."""
    cfg = board_config(env)
    if cfg is None:
        _log("MISSION_CONTROL_URL unset — board disabled (no-op); deck run continues ungrouped.")
        return None
    if not deck_slug or not title:
        _log("ingest skipped — deck_slug/title missing.")
        return None
    payload = {
        "title": title,
        "description": description or f"Signature deck build: {deck_slug}",
        "department_slug": DEPARTMENT_SLUG,
        "idempotency_key": f"deck:{deck_slug}",
        "source": "presentations-pipeline",
    }
    if owner:
        payload["owner"] = owner
    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"ingest POST failed ({type(exc).__name__}: {exc}); deck run continues ungrouped.")
        if run_dir is not None:
            stamp_task_id(run_dir, f"deck:{deck_slug}", attempted=True, registered=False)
        return None
    task_id = None
    if isinstance(body, dict):
        task_id = body.get("task_id") or body.get("id") or (body.get("task") or {}).get("id")
    if status in (200, 201) and task_id:
        _log(f"deck task on board: task_id={task_id} (department={DEPARTMENT_SLUG}).")
        if run_dir is not None:
            stamp_task_id(run_dir, str(task_id), attempted=True, registered=True)
        return str(task_id)
    _log(f"ingest POST non-OK (HTTP {status}): {body}; deck run continues ungrouped.")
    if run_dir is not None:
        stamp_task_id(run_dir, f"deck:{deck_slug}", attempted=True, registered=False)
    return None


# ---------------------------------------------------------------------------
# PHASE BOUNDARY — PATCH /api/tasks/{id} (one status transition; report-gated)
# ---------------------------------------------------------------------------
def patch_phase(
    task_id: str,
    status: str,
    *,
    reason: Optional[str] = None,
    actor: str = "presentations-producer",
    blocked_reason: Optional[str] = None,
    ask: Optional[str] = None,
    env: Optional[dict] = None,
) -> bool:
    """Move the deck task to `status` at a phase boundary. FAIL-SOFT (returns False,
    never raises). Tied to the FIX E report gate by the caller (the runner PATCHes
    only after a phase's client done-report is recorded)."""
    cfg = board_config(env)
    if cfg is None or not task_id:
        return False
    if status not in VALID_STATUSES:
        _log(f"patch refused — invalid status {status!r}.")
        return False
    payload: dict = {"status": status}
    if reason:
        payload["reason"] = reason
    if actor:
        payload["actor"] = actor
    if status == "blocked":
        if blocked_reason not in VALID_BLOCKED_REASONS or not (ask or "").strip():
            _log("patch(blocked) refused — needs blocked_reason in "
                 "{decision,approval,credential,payment} + non-empty ask.")
            return False
        payload["blocked_reason"] = blocked_reason
        payload["ask"] = ask
    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"patch ->{status} failed ({type(exc).__name__}: {exc}).")
        return False
    if st == 200:
        return True
    _log(f"patch ->{status} non-OK (HTTP {st}): {body}.")
    return False


# ---------------------------------------------------------------------------
# Receipt stamping + offline closeout check (AF-CC-UNREGISTERED)
# ---------------------------------------------------------------------------
def _proc_manifest_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / "checkpoints" / "process_manifest.json"


def stamp_task_id(run_dir: Path, task_id: str, *, attempted: bool, registered: bool) -> bool:
    """Merge the CC registration receipt into process_manifest.json without disturbing
    other fields. Atomic. Never raises."""
    p = _proc_manifest_path(run_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        obj = {}
        if p.exists():
            try:
                obj = json.loads(p.read_text())
                if not isinstance(obj, dict):
                    obj = {}
            except (json.JSONDecodeError, OSError):
                obj = {}
        obj["cc_registration"] = {
            "task_id": task_id,
            "attempted": bool(attempted),
            "registered": bool(registered),
            "department_slug": DEPARTMENT_SLUG,
        }
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, indent=2))
        os.replace(tmp, p)
        return True
    except OSError as exc:
        _log(f"stamp_task_id failed ({exc}).")
        return False


def chk_cc_registered(run_dir) -> str:
    """OFFLINE closeout check for AF-CC-UNREGISTERED. Returns '' on pass, a non-empty
    AF message on fail. FAIL-CLOSED on never-attempted (the pipeline must at minimum
    ATTEMPT to board the deck); FAIL-SOFT on transport (an attempted-but-degraded
    board still passes — degrade-to-ungrouped is logged, not a deck failure)."""
    p = _proc_manifest_path(Path(run_dir))
    if not p.exists():
        return ('{"code": "AF-CC-UNREGISTERED"} process_manifest.json absent — the '
                "Command Center registration was never attempted (fail-closed).")
    try:
        obj = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return ('{"code": "AF-CC-UNREGISTERED"} process_manifest.json unreadable — cannot '
                "prove the deck was boarded (fail-closed).")
    reg = obj.get("cc_registration") if isinstance(obj, dict) else None
    if not isinstance(reg, dict) or reg.get("attempted") is not True or not reg.get("task_id"):
        return ('{"code": "AF-CC-UNREGISTERED"} no cc_registration receipt — the pipeline '
                "never attempted to register the deck on the Command Center (fail-closed). "
                "The board ingest is a deterministic postflight step, not an agent choice.")
    return ""  # attempted (registered or transport-degraded) => pass (fail-soft on transport)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Presentations CC board producer (FIX G).")
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--run-dir")
    chk = sub.add_parser("check")
    chk.add_argument("--run-dir", required=True)
    args, _ = ap.parse_known_args()
    if args.cmd == "check":
        msg = chk_cc_registered(args.run_dir)
        print(json.dumps({"af": msg or None, "ok": not msg}, indent=2))
        sys.exit(1 if msg else 0)
    ap.print_help()
