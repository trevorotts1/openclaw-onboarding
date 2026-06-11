"""Convert and Flow CLI — single-chokepoint safety gate.

Every write (POST/PUT/DELETE) in ghl_client.py and ghl_internal_client.py
calls check_write() before sending.

Environment variables (all set by the 'caf'/'convertandflow'/'ghl' wrappers):
    CAF_ALLOWED_LOCATION_IDS  Comma-separated whitelist.  Empty = REFUSE ALL writes.
    CAF_DRAFT_ONLY            "true" (default) = triggers created as inactive (active:false).
    CAF_DRY_RUN               "true" = print payload only, never send.
    CAF_APPROVAL_TOKEN        Non-empty = explicit write approval token.
                              ZHC-/ZHC_ prefixed names are standing-approved per Section 5.

All safety values are read at call time so that env vars set after import
(e.g. by --dry-run flag callbacks) are always honoured.
"""
from __future__ import annotations

import os
import sys
import json
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


# ── Approval check ────────────────────────────────────────────────────────────

def _is_approved(name: str = "") -> bool:
    """Return True if the write is standing-approved (ZHC prefix) or explicit token present."""
    if os.environ.get("CAF_APPROVAL_TOKEN", "").strip():
        return True
    if name and (name.startswith("ZHC-") or name.startswith("ZHC_")):
        return True
    return False


# ── Public API ────────────────────────────────────────────────────────────────

class SafetyRefused(RuntimeError):
    """Raised when a write is blocked by a safety gate rule."""


def check_write(
    method: str,
    url: str,
    payload: Any = None,
    location_id: Optional[str] = None,
    workflow_name: str = "",
) -> None:
    """Assert all safety rules are satisfied before sending a write request.

    Call this at the top of post(), put(), delete() in both clients.

    Args:
        method:        HTTP verb (POST/PUT/DELETE).
        url:           Full request URL.
        payload:       Request body (for dry-run printing).
        location_id:   The GHL location/sub-account ID being targeted.
                       If None the gate skips the whitelist check (GET-only callers).
        workflow_name: Workflow/folder name for ZHC standing-approval check.

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
    if location_id is not None:
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

    # Rule 3 — APPROVAL GATE: internal-API writes require approval.
    if not _is_approved(workflow_name):
        raise SafetyRefused(
            "WRITE REFUSED: no approval token present.\n"
            "Set CAF_APPROVAL_TOKEN=<token> to approve this write, OR\n"
            "prefix the workflow/folder name with 'ZHC-' or 'ZHC_' for standing approval."
        )


def draft_only_active_flag() -> bool:
    """Return the correct 'active' value for trigger bodies.

    When CAF_DRAFT_ONLY=true (the default), triggers must be created INACTIVE
    so the workflow fires only when the operator explicitly activates it.
    Returns False when draft_only, True only when operator explicitly opts out.
    """
    return not _env_bool("CAF_DRAFT_ONLY", default=True)  # active=False when draft_only, active=True when opted out


# ── Internal helpers ──────────────────────────────────────────────────────────

def _print_dry_run(method: str, url: str, payload: Any) -> None:
    print(f"[DRY RUN] Would send: {method} {url}")
    if payload:
        try:
            print(json.dumps(payload, indent=2, default=str))
        except Exception:
            print(repr(payload))
