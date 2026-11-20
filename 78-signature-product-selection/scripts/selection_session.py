"""Selection session store for Skill 78 (S78-05).

Pure stdlib model of the selection-state contract in doc 08 section 6 and
doc 02 section 5. The production bridge is a server-side session keyed by an
opaque reference; this module is the deterministic core that bridge calls:

- create: store a validated selection intent under an opaque ref with a TTL
- resume: return the stored intent only after revalidation against the
  current approved catalog; a changed price or mapping returns
  'reconfirm_required' with the material diff, never a silent switch
- expiry: an expired or unknown ref returns 'expired' with a helpful
  restart/confirm message, never a defaulted package
- every expired / reconfirm_required result also carries client_explanation:
  the four-part plain message (what happened, why, the fix, the buyer's
  choices) from scripts/explain_stop.py, beside the existing message
- submit idempotence: confirming the same session and selection twice
  returns the same draft reference; a second draft order is never created

Tenant isolation: a ref resolves only inside its own tenant/launch.
No contact identity, card data, or price authority is stored from a URL.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from explain_stop import explain_stop
from selection_core import Violation, format_money, validate_binding

DEFAULT_TTL_SECONDS = 1800


def to_iso(epoch_seconds: int) -> str:
    """The store's epoch-second clock as the timezone-aware ISO-8601 UTC string Skill 79 parses as an instant
    (CHK-07, issue 77). Epoch stays the store's own TTL arithmetic; every time handed to Skill 79 is this."""
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

EXPIRED_MESSAGE = (
    "Your selection session has expired, so nothing was chosen for you. "
    "Review the packages and choose again to continue to checkout."
)
RECONFIRM_CODES = ("S78-SELECTION-PRICE-DRIFT", "S78-SELECTION-STALE-REVISION", "S78-UNAPPROVED-PRICE")

def _expired() -> Dict[str, Any]:
    return {"state": "expired", "message": EXPIRED_MESSAGE, "client_explanation": explain_stop("S78-SESSION-EXPIRED")}

def _reconfirm(v: Violation, selection: Mapping[str, Any], launch: Mapping[str, Any]) -> Dict[str, Any]:
    """The reconfirm_required result: the stored choice is shown, never swapped, never charged silently."""
    current = next((o for o in launch["offers"] if o["offer_id"] == selection.get("offer_id")), None)
    price = next((p for p in (current or {}).get("prices") or []
                  if p.get("price_choice_id") == selection.get("price_choice_id")), None)
    old, new = selection.get("amount_minor_snapshot"), (price or {}).get("amount_minor")
    change = None
    if isinstance(old, int) and isinstance(new, int) and old != new:
        change = (f"It was {format_money(old, selection.get('currency'))}, "
                  f"now it is {format_money(new, price.get('currency'))}.")
    return {
        "state": "reconfirm_required",
        "reason_code": v.code,
        "message": (
            "The terms for your selected package changed since you chose it. "
            "Review the current terms and confirm before continuing; "
            "you will never be charged a changed amount without confirming."
        ),
        "selected_offer_id": selection.get("offer_id"),
        "previous_amount_minor": selection.get("amount_minor_snapshot"),
        "current_offer": current,
        "client_explanation": explain_stop(
            "S78-SESSION-RECONFIRM", {"offer": (current or {}).get("display_name"), "change": change}),
    }


class SessionStore:
    """In-memory reference store. Record and draft access routes through
    the four small storage hooks below (_put_record, _get_record,
    _put_draft, _get_draft) so a durable backend can replace ONLY the
    storage layer while inheriting the resume/confirm semantics above
    verbatim. See selection_session_store.DurableSessionStore."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.ttl = ttl_seconds
        self._records: Dict[str, Dict[str, Any]] = {}
        self._drafts: Dict[str, str] = {}

    # Storage hooks (in-memory implementation).
    def _put_record(self, ref: str, rec: Dict[str, Any]) -> None:
        self._records[ref] = rec

    def _get_record(self, ref: str) -> Optional[Dict[str, Any]]:
        return self._records.get(ref)

    def _put_draft(self, ref: str, draft_ref: str) -> None:
        self._drafts[ref] = draft_ref

    def _get_draft(self, ref: str) -> Optional[str]:
        return self._drafts.get(ref)

    def create(self, selection: Mapping[str, Any], *, now: int) -> str:
        ref = "sel_" + secrets.token_urlsafe(24)
        self._put_record(ref, {
            "selection": dict(selection),
            "tenant_id": selection["tenant_id"],
            "launch_id": selection["launch_id"],
            "created_at": now,
            "expires_at": now + self.ttl,
        })
        return ref

    def _lookup(self, ref: str, *, tenant_id: str, launch_id: str, now: int) -> Optional[Dict[str, Any]]:
        rec = self._get_record(ref)
        if rec is None:
            return None
        if rec["tenant_id"] != tenant_id or rec["launch_id"] != launch_id:
            return None  # cross-tenant/session mappings are rejected silently to the caller as expired
        if now > rec["expires_at"]:
            return None
        return rec

    def resume(self, ref: str, *, tenant_id: str, launch_id: str, launch: Mapping[str, Any], now: int) -> Dict[str, Any]:
        rec = self._lookup(ref, tenant_id=tenant_id, launch_id=launch_id, now=now)
        if rec is None:
            return _expired()
        selection = rec["selection"]
        try:
            validate_binding(selection, launch, expected_revision=int(launch["revision"]))
        except Violation as v:
            if v.code in RECONFIRM_CODES:
                return _reconfirm(v, selection, launch)
            return _expired()
        return {"state": "resumed", "selection": selection, "expires_at": to_iso(rec["expires_at"])}

    def confirm(self, ref: str, *, tenant_id: str, launch_id: str, launch: Mapping[str, Any], now: int) -> Dict[str, Any]:
        """Idempotent confirm, fail-closed on current terms. The current
        approved launch is a required argument: confirm revalidates the
        stored selection exactly as resume does before any draft reference
        is issued, so a price or mapping change between selection and
        confirm produces reconfirm_required, never a confirmed draft for
        stale terms. The same session then confirms to the same draft
        reference no matter how many times the CTA is clicked."""
        rec = self._lookup(ref, tenant_id=tenant_id, launch_id=launch_id, now=now)
        if rec is None:
            return _expired()
        selection = rec["selection"]
        try:
            validate_binding(selection, launch, expected_revision=int(launch["revision"]))
        except Violation as v:
            if v.code in RECONFIRM_CODES:
                return _reconfirm(v, selection, launch)
            return _expired()
        existing = self._get_draft(ref)
        if existing is not None:
            return {"state": "confirmed", "draft_ref": existing, "duplicate": True}
        digest = hashlib.sha256(
            json.dumps(rec["selection"], sort_keys=True).encode()
        ).hexdigest()[:24]
        draft_ref = f"draft_{digest}"
        self._put_draft(ref, draft_ref)
        return {"state": "confirmed", "draft_ref": draft_ref, "duplicate": False}
