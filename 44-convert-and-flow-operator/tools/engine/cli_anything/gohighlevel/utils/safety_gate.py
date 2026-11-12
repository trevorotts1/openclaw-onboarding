"""Convert and Flow CLI — single-chokepoint safety gate.

Every write (POST/PUT/DELETE) in ghl_client.py and ghl_internal_client.py
calls check_write() before sending.

Environment variables (all set by the 'caf'/'convertandflow'/'ghl' wrappers):
    CAF_ALLOWED_LOCATION_IDS  Comma-separated whitelist.  Empty = REFUSE ALL writes.
    CAF_DRAFT_ONLY            "true" (default) = triggers created as inactive (active:false).
    CAF_DRY_RUN               "true" = print payload only, never send.
    CAF_APPROVAL_ID           Id of the owner approval record (fetched live from Command
                              Center; the id alone approves nothing). Writes need an
                              'automation_write' record, draft-off a 'publish' record, each
                              bound to {location_id, action, object_key, plan_sha256,
                              approver, expires_at}. CAF_WRITE_ACTION / CAF_PLAN_SHA256 /
                              CAF_OBJECT_KEY name the current action, plan and object.
                              An env token or a ZHC- name is NOT approval (S44-16).

All safety values are read at call time so that env vars set after import
(e.g. by --dry-run flag callbacks) are always honoured.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional


# ── Env helpers (always read live from os.environ) ────────────────────────────

def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_set(name: str) -> frozenset[str]:
    """Read a comma-separated env var into a frozenset of stripped, non-empty strings."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return frozenset()
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


# ── Approval check (S44-16) ───────────────────────────────────────────────────
# The owner's yes is a record minted by Command Center from the client's own reply;
# the AI session cannot write that service, so an env var, a ZHC- name or a file the
# session wrote is never approval. Same endpoint approval_record.py (shared-utils) reads.

_APPROVAL_PATH = "/api/launch-approvals/{approval_id}"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_LOOPBACK = ("localhost", "127.0.0.1", "::1")
_NEEDED = ("kind", "location_id", "action", "object_key", "plan_sha256", "approver",
           "expires_at", "revoked", "verification_class")


def _fetch_record(approval_id: str) -> dict:
    """GET the approval record from Command Center. Any failure raises SafetyRefused."""
    base = os.environ.get("MISSION_CONTROL_URL", "").strip().rstrip("/")
    token = os.environ.get("MC_API_TOKEN", "").strip()
    if not _ID_RE.match(approval_id or ""):
        raise SafetyRefused("WRITE REFUSED: CAF_APPROVAL_ID is missing or malformed.")
    parts = urllib.parse.urlsplit(base)
    if not (base and token and parts.hostname and (
            parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOOPBACK))):
        raise SafetyRefused("WRITE REFUSED: Command Center is not configured "
                            "(MISSION_CONTROL_URL / MC_API_TOKEN); cannot verify approval.")
    req = urllib.request.Request(
        base + _APPROVAL_PATH.format(approval_id=urllib.parse.quote(approval_id, safe="")),
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
    try:
        timeout = int(os.environ.get("CC_BOARD_TIMEOUT") or 8)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rec = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SafetyRefused("WRITE REFUSED: approval record could not be fetched from "
                            f"Command Center ({type(exc).__name__}); fail-closed.")
    return rec["approval"] if isinstance(rec, dict) and isinstance(rec.get("approval"), dict) else rec


_HEX64 = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")


def _canon_hash(value) -> str:
    """Bare lowercase 64-hex from '<hex>' or 'sha256:<hex>'; '' when it is neither."""
    m = _HEX64.match(value.strip()) if isinstance(value, str) else None
    return m.group(1).lower() if m else ""


def _with_bound_fields(rec) -> dict:
    """Fill location_id/action/object_key/plan_sha256/approver/verification_class from the
    Command Center launch_approvals shape when the record does not carry them natively.

    Command Center stores scope as a JSON string {"location_id","action","object_key"}, the
    plan as plan_hash ('sha256:<hex>') and the verified owner as client_identity_ref. Native
    fields always win. A scope that is not that JSON object (a chat-minted free-text scope)
    yields nothing, so the missing fields keep the record 'malformed' and the write is refused.
    The record was fetched from Command Center with the bearer token, which is what
    authenticated_platform_record means, so that class is filled only for such a fetch.
    """
    if not isinstance(rec, dict):
        return rec
    out = dict(rec)
    scope = out.get("scope")
    if isinstance(scope, str):
        try:
            scope = json.loads(scope)
        except ValueError:
            scope = None
    if isinstance(scope, dict):
        for k in ("location_id", "action", "object_key"):
            if k not in out and isinstance(scope.get(k), str):
                out[k] = scope[k]
    if "plan_sha256" not in out and "plan_hash" in out:
        out["plan_sha256"] = out["plan_hash"]
    if "approver" not in out and "client_identity_ref" in out:
        out["approver"] = out["client_identity_ref"]
    if "verification_class" not in out and isinstance(scope, dict) and "location_id" in out:
        out["verification_class"] = "authenticated_platform_record"
    return out


def _require_approval(kind: str, location_id: str, action: str, object_key: str,
                      plan_sha256: str) -> dict:
    """Return the verified record or raise SafetyRefused naming the mismatched field."""
    if not (action and plan_sha256):
        raise SafetyRefused("WRITE REFUSED: the current action and plan sha256 are unknown "
                            "(set CAF_WRITE_ACTION and CAF_PLAN_SHA256); nothing to approve against.")
    rec = _with_bound_fields(_fetch_record(os.environ.get("CAF_APPROVAL_ID", "").strip()))
    if not isinstance(rec, dict) or any(k not in rec for k in _NEEDED):
        raise SafetyRefused("WRITE REFUSED: approval record is malformed.")
    bad = [name for name, ok in (
        ("kind", rec["kind"] == kind),
        ("location_id", rec["location_id"] == location_id),
        ("action", rec["action"] == action),
        ("object_key", rec["object_key"] == object_key),
        ("plan_sha256", bool(_canon_hash(rec["plan_sha256"])) and bool(_canon_hash(plan_sha256))
         and hmac.compare_digest(_canon_hash(rec["plan_sha256"]), _canon_hash(plan_sha256))),
        ("approver", isinstance(rec["approver"], str) and bool(rec["approver"].strip())),
        ("revoked", rec["revoked"] is False),
        ("verification_class", rec["verification_class"] == "authenticated_platform_record"),
    ) if not ok]
    try:
        exp = datetime.fromisoformat(str(rec["expires_at"]).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            bad.append("expires_at")
    except ValueError:
        bad.append("expires_at")
    if bad:
        raise SafetyRefused("WRITE REFUSED: approval record does not match this write "
                            f"(kind {kind!r}); mismatched: {', '.join(bad)}.")
    return rec


def _current(action: str, object_key: str, plan_sha256: str) -> tuple:
    return (action or os.environ.get("CAF_WRITE_ACTION", "").strip(),
            object_key or os.environ.get("CAF_OBJECT_KEY", "").strip(),
            plan_sha256 or os.environ.get("CAF_PLAN_SHA256", "").strip())


# ── Public API ────────────────────────────────────────────────────────────────

class SafetyRefused(RuntimeError):
    """Raised when a write is blocked by a safety gate rule."""


def check_write(
    method: str,
    url: str,
    payload: Any = None,
    location_id: Optional[str] = None,
    workflow_name: str = "",
    action: str = "",
    object_key: str = "",
    plan_sha256: str = "",
) -> None:
    """Assert all safety rules are satisfied before sending a write request.

    Call this at the top of post(), put(), delete() in both clients.

    Args:
        method:        HTTP verb (POST/PUT/DELETE).
        url:           Full request URL.
        payload:       Request body (for dry-run printing).
        location_id:   The GHL location/sub-account ID being targeted.
                       For a WRITE this MUST resolve to a real, whitelisted id — None
                       (unresolved target) is refused fail-closed. GET callers return
                       before the whitelist check, so None is only meaningful on writes.
        workflow_name: Workflow/folder name; the default object_key.
        action / object_key / plan_sha256: what the owner approved; default to the
                       CAF_WRITE_ACTION / CAF_OBJECT_KEY (else workflow_name) / CAF_PLAN_SHA256 env.

    Raises:
        SafetyRefused: if any rule blocks the write.
        SystemExit(0): in dry-run mode (after printing what would be sent).
    """
    verb = method.upper()
    is_write = verb in ("POST", "PUT", "DELETE", "PATCH")
    if not is_write:
        return  # GETs always pass

    # Rule 1 — DRY RUN: print and stop before any network call.
    if _env_bool("CAF_DRY_RUN"):
        _print_dry_run(verb, url, payload)
        sys.exit(0)

    # Rule 2 — LOCATION WHITELIST: fail-closed (empty list = refuse all).
    # A WRITE with an UNKNOWN target (location_id is None) can NOT be whitelist-checked.
    # GET callers already returned above, so reaching here with None means a mutating
    # request whose sub-account is unresolved — refuse it (never skip the whitelist).
    if location_id is None:
        raise SafetyRefused(
            "WRITE REFUSED: the target location_id is unknown/unresolved for this write.\n"
            "A mutating request must target an explicit, whitelisted GHL sub-account.\n"
            "Set GOHIGHLEVEL_LOCATION_ID (and GOHIGHLEVEL_ALLOWED_LOCATION_IDS) so the\n"
            "safety gate can verify the location before any write (fail-closed)."
        )
    allowed = _env_set("CAF_ALLOWED_LOCATION_IDS")
    if not allowed:
        raise SafetyRefused(
            "WRITE REFUSED: CAF_ALLOWED_LOCATION_IDS is empty or unset.\n"
            "Set it in ~/.openclaw/secrets/.env:\n"
            "  GOHIGHLEVEL_ALLOWED_LOCATION_IDS=YOUR_LOCATION_ID\n"
            "Leaving it empty intentionally blocks all writes (fail-closed)."
        )
    if location_id not in allowed:
        raise SafetyRefused(
            f"WRITE REFUSED: location '{location_id}' is not in the approved whitelist.\n"
            f"Approved: {sorted(allowed)}\n"
            "Add it to GOHIGHLEVEL_ALLOWED_LOCATION_IDS if this is your sub-account."
        )

    # Rule 3 — APPROVAL GATE: a verified automation_write record bound to this
    # location, action, object and plan (S44-16). No env token or name opens it.
    # ponytail: one Command Center GET per write; cache per process if a build is too slow.
    act, obj, plan = _current(action, object_key, plan_sha256)
    _require_approval("automation_write", location_id, act, obj or workflow_name, plan)


def draft_only_active_flag(location_id: Optional[str] = None, object_key: str = "",
                           plan_sha256: str = "") -> bool:
    """Return the correct 'active' value for trigger bodies.

    Triggers are created INACTIVE (False) unless CAF_DRAFT_ONLY is off AND a verified
    'publish' approval record (action 'publish') binds this location, object and plan.
    The env toggle alone never goes live (S44-16); a missing/bad record stays draft.
    """
    if _env_bool("CAF_DRAFT_ONLY", default=True):
        return False
    _, obj, plan = _current("", object_key, plan_sha256)
    loc = location_id or os.environ.get("GHL_LOCATION_ID", "").strip()
    try:
        _require_approval("publish", loc, "publish", obj, plan)
    except SafetyRefused as exc:
        print(f"[caf] draft-off ignored, staying inactive: {exc}", file=sys.stderr)
        return False
    return True


# ── Internal helpers ──────────────────────────────────────────────────────────

def _print_dry_run(method: str, url: str, payload: Any) -> None:
    print(f"[DRY RUN] Would send: {method} {url}")
    if payload:
        try:
            print(json.dumps(payload, indent=2, default=str))
        except Exception:
            print(repr(payload))
