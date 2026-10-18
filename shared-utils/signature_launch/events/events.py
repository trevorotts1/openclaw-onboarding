"""S44 L1 reference implementation — Signature Launch purchase events.

LANE-B READINESS BUILD (schema v1.1 switch, CR-S44-001 follow-up).
This is a lane copy of work/events/events.py with dual-version
validation added. It is NOT landed anywhere: the originals in the work
layout and in the packaged tree are untouched. Placement instructions
are in this lane's REPORT.md.

TEST-ONLY / L1 (deterministic, in-memory). This module implements the
semantics required by packet doc 14 sections 4-6 and doc 02 section 8:

- normalize native order events into the purchase-event envelope
  (validated against the domain purchase-event schemas, v1.0 AND v1.1);
- deduplicate by verified provider event identity within tenant — never
  by contact alone, never by order alone (one order can gain later extras);
- action ledger keyed by tenant + verified transaction/order-line identity
  + action type + entitlement/campaign version;
- grant entitlements only from validated successful payment state;
- buyer suppression is RECHECKED at dispatch time (A21), not at enqueue;
- unknown external outcomes are reconciled, never blindly replayed.

Schema versioning (CR-S44-001, S49 ruling, landed on main
7c3d4a2b4bbe7d79b56eea8448f3fa9d266106d4 in
shared-utils/signature_launch/domain/):
- v1.0 events validate exactly as before (no contact_ref allowed);
- v1.1 events validate against the v1.1 schema: contact_ref is OPTIONAL
  and nullable, an opaque native contact ID only, never PII; when
  present it must be a string or null (the schema also rejects an
  empty string via minLength);
- v1.2 events validate against the v1.2 schema (CR-S44-003, S49
  ruling; landed by PR #2190 in train #2235, main 9ccd6536):
  parent_order_ref is OPTIONAL and nullable — the opaque provider
  order identity of the initial order, populated only from a real
  provider read-back, never synthesized, never derived, and never
  load-bearing for dedupe, grants, or revocations. ACCEPTANCE ONLY
  in this step: normalize_order_event does not stamp "1.2" and does
  not carry parent_order_ref through; producer stamping is a later,
  separate step in the CR-S44-003 sequence;
- any other schema_version — or a missing one — FAILS CLOSED.

It does NOT call GHL, does NOT prove any live behavior, and must never be
labeled live proof. Production adapters replace the in-memory stores with
the durable tenant-scoped inbox/outbox described in doc 14 section 5.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

import jsonschema

# --- Schema loading (dual version) -------------------------------------------
# Loading keeps the packaged module's spirit: a vendored schema beside
# the module wins; a sibling domain/ directory (the repo layout, where
# S49 landed v1.1) is next; the packet path (room development layout)
# is the last fallback. Every candidate file is registered under the
# version its own schema_version const declares, never under the
# version its filename suggests — in domain/, the un-suffixed
# purchase-event.schema.json IS the current version (v1.2 since the
# PR #2190 landing; v1.1 before it) with the preserved versions
# beside it under versioned names, while the vendored copy beside
# the packaged events module is v1.0.
_HERE = Path(__file__).resolve().parent
_SCHEMA_CANDIDATES = [
    _HERE / "purchase-event.schema.json",
    _HERE / "purchase-event.v1.0.schema.json",
    _HERE / "purchase-event.v1.1.schema.json",
    _HERE / "purchase-event.v1.2.schema.json",
    _HERE.parent / "domain" / "purchase-event.schema.json",
    _HERE.parent / "domain" / "purchase-event.v1.0.schema.json",
    _HERE.parent / "domain" / "purchase-event.v1.1.schema.json",
    _HERE.parent / "domain" / "purchase-event.v1.2.schema.json",
]
# Packet fallback (room development layout) only when this file sits
# deep enough for the packet tree to be an ancestor. Guarded: an
# unguarded parents[4] raised IndexError at import whenever the module
# was copied to a shallow path (e.g. a temp dir directly under /tmp),
# which crashed import instead of merely missing the fallback. Found
# by the S44 watchdog's L1 re-run, 2026-10-16; pinned by
# ShallowPathImportTests in test_events_dual.py.
_PARENTS = Path(__file__).resolve().parents
if len(_PARENTS) > 4:
    _SCHEMA_CANDIDATES.append(
        _PARENTS[4] / "packet" / "reference" / "schemas"
        / "purchase-event.schema.json")

_SCHEMAS: Dict[str, dict] = {}
SCHEMA_SOURCES: Dict[str, str] = {}


def _register_schema(path: Path) -> None:
    try:
        schema = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    const = (schema.get("properties", {}).get("schema_version", {})
             .get("const"))
    if isinstance(const, str) and const not in _SCHEMAS:
        _SCHEMAS[const] = schema
        SCHEMA_SOURCES[const] = str(path)


for _candidate in _SCHEMA_CANDIDATES:
    if _candidate.exists():
        _register_schema(_candidate)

if "1.0" not in _SCHEMAS:
    raise FileNotFoundError(
        "purchase-event v1.0 schema not found in any known location: "
        + ", ".join(str(p) for p in _SCHEMA_CANDIDATES))

# Back-compat surface: the single-schema name the original module
# exposed. With dual acceptance this is the v1.0 schema; SCHEMA_PATH
# names where it was loaded from.
_SCHEMA = _SCHEMAS["1.0"]
SCHEMA_PATH = Path(SCHEMA_SOURCES["1.0"])
SUPPORTED_SCHEMA_VERSIONS = tuple(sorted(_SCHEMAS))


def validate_event(event: dict) -> dict:
    """Validate a normalized envelope against its stamped schema version.

    v1.0 validates as before; v1.1 additionally allows the optional
    nullable contact_ref; v1.2 additionally allows the optional
    nullable parent_order_ref (acceptance only — nothing in this
    module stamps "1.2" yet). An unknown, missing, or non-string
    schema_version fails closed, as does an event whose version's
    schema is not installed alongside this module.
    """
    if not isinstance(event, dict):
        raise jsonschema.ValidationError(
            f"purchase event must be an object, got {type(event).__name__}")
    version = event.get("schema_version")
    if not isinstance(version, str) or version not in _SCHEMAS:
        raise jsonschema.ValidationError(
            f"unsupported schema_version {version!r}: fail closed "
            f"(installed schemas: {sorted(_SCHEMAS)})")
    jsonschema.validate(event, _SCHEMAS[version])
    return event


# --- Native event mapping (doc 14 section 4) ---------------------------------
# The native submission type may say 'Upsell' for U1, D1 and U2 alike; the
# internal slot is resolved ONLY through verified product/page/price
# bindings supplied by the launch record, never from the submission label.
SLOT_BY_BINDING_KEY = "verified_binding"  # binding: native_product_ref -> slot


def normalize_order_event(raw: dict, bindings: Dict[str, str]) -> dict:
    """Map a native order read-back into the internal envelope.

    `raw` is the adapter's read-back shape (test fixture here); `bindings`
    maps native product refs to internal slots using verified IDs.
    Raises ValueError on unmapped product (quarantine, never guess a slot)
    or on a missing verified event identity.

    Version stamping: if the read-back carries a contact_ref key (the
    opaque native contact ID, or null), the envelope stamps "1.1" and
    carries the value through; otherwise it stamps "1.0" exactly as
    before. The value is never derived from a name or email.

    v1.2 note: a read-back carrying parent_order_ref is NOT stamped
    "1.2" and the field is not carried through by this function.
    Producer stamping is the later CR-S44-003 step; this build is
    acceptance-only (validate_event accepts the "1.2" stamp).
    """
    if not raw.get("provider_event_id"):
        raise ValueError("quarantine: no verified provider event identity")
    lines: List[dict] = []
    for item in raw["line_items"]:
        slot = bindings.get(item["native_product_ref"])
        if slot is None:
            raise ValueError(
                f"quarantine: unmapped native product {item['native_product_ref']}")
        lines.append({
            "native_line_ref": item["native_line_ref"],
            "offer_id": item["offer_id"],
            "slot": slot,
            "currency": item["currency"],
            "amount_minor": int(item["amount_minor"]),
            "entitlement_ids": list(item["entitlement_ids"]),
        })
    event = {
        "schema_version": "1.0",
        "tenant_id": raw["tenant_id"],
        "location_id": raw["location_id"],
        "launch_id": raw["launch_id"],
        "provider": raw["provider"],
        "event_id": raw["provider_event_id"],
        "event_type": raw.get("event_type", "purchase_observed"),
        "native_order_ref": raw["native_order_ref"],
        "native_transaction_ref": raw.get("native_transaction_ref"),
        "occurred_at": raw["occurred_at"],
        "received_at": raw["received_at"],
        "payment_status": raw["payment_status"],
        "line_items": lines,
        "evidence_ref": raw["evidence_ref"],
        "test_only": bool(raw.get("test_only", True)),
    }
    if "contact_ref" in raw:
        event["contact_ref"] = raw["contact_ref"]
        event["schema_version"] = "1.1"
    return validate_event(event)


# --- Durable-semantics stores (in-memory L1 stand-ins) ------------------------

class Inbox:
    """Unique key: (tenant, provider, verified event identity)."""

    def __init__(self) -> None:
        self._seen: set = set()
        self._lock = threading.Lock()

    def record_if_unseen(self, event: dict) -> bool:
        key = (event["tenant_id"], event["provider"], event["event_id"])
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True


class ActionLedger:
    """Action key: tenant + transaction/order-line identity + action type
    + entitlement/campaign version. Atomic claim prevents two workers
    dispatching the same action concurrently (doc 14 section 5)."""

    def __init__(self) -> None:
        self._actions: Dict[tuple, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(event: dict, line: dict, action_type: str, version: str) -> tuple:
        txn = event.get("native_transaction_ref") or event["native_order_ref"]
        return (event["tenant_id"], txn, line["native_line_ref"],
                action_type, version)

    def claim(self, key: tuple, payload: dict) -> Optional[dict]:
        """Atomically claim an action. Returns existing entry if present."""
        with self._lock:
            if key in self._actions:
                return self._actions[key]
            entry = {"key": key, "payload": payload, "state": "claimed"}
            self._actions[key] = entry
            return None

    def mark(self, key: tuple, state: str) -> None:
        with self._lock:
            self._actions[key]["state"] = state

    def get(self, key: tuple) -> Optional[dict]:
        with self._lock:
            return self._actions.get(key)

    def entries(self) -> List[dict]:
        with self._lock:
            return list(self._actions.values())


class EntitlementBook:
    """Authoritative per-line entitlement state (doc 02 section 8).
    Refunds change state; history is never deleted."""

    def __init__(self) -> None:
        self._grants: Dict[tuple, dict] = {}
        self._lock = threading.Lock()

    def grant(self, tenant: str, line_ref: str, entitlement: str) -> bool:
        k = (tenant, line_ref, entitlement)
        with self._lock:
            if k in self._grants and self._grants[k]["state"] == "active":
                return False
            self._grants[k] = {"state": "active"}
            return True

    def revoke(self, tenant: str, line_ref: str, entitlement: str) -> None:
        k = (tenant, line_ref, entitlement)
        with self._lock:
            if k in self._grants:
                self._grants[k]["state"] = "revoked"

    def active(self, tenant: str) -> List[str]:
        """Entitlements active for the tenant: an entitlement is active while
        at least one of its line grants is active. Line-level state is kept
        in _grants so a refund revokes only its own line (a second line
        granting the same entitlement, e.g. a renewal period, keeps it
        active)."""
        with self._lock:
            return sorted({e for (t, _l, e), v in self._grants.items()
                           if t == tenant and v["state"] == "active"})


class PurchaseProcessor:
    """Short, wait-free purchase handler (doc 14 section 6). Longer
    sequences are separate downstream enrollments, never steps here."""

    def __init__(self, version: str = "v1") -> None:
        self.inbox = Inbox()
        self.ledger = ActionLedger()
        self.book = EntitlementBook()
        self.version = version
        # buyer suppression registry: (tenant, launch, contact_ref) -> True
        self.buyers: set = set()

    def process(self, event: dict, contact_ref: Optional[str] = None) -> dict:
        validate_event(event)
        if not self.inbox.record_if_unseen(event):
            return {"result": "duplicate_event", "actions_created": 0}
        created = 0
        if event["event_type"] == "refund_observed" or \
                event["payment_status"] in ("refunded", "partially_refunded"):
            for line in event["line_items"]:
                for ent in line["entitlement_ids"]:
                    self.book.revoke(event["tenant_id"],
                                     line["native_line_ref"], ent)
            return {"result": "refund_applied", "actions_created": 0}
        if event["payment_status"] != "succeeded":
            # pending/failed/requires-action/unknown never grant (doc 02 s8)
            return {"result": f"no_grant:{event['payment_status']}",
                    "actions_created": 0}
        for line in event["line_items"]:
            for ent in line["entitlement_ids"]:
                if self.book.grant(event["tenant_id"],
                                   line["native_line_ref"], ent):
                    key = self.ledger.key(event, line, "grant_access",
                                          self.version)
                    if self.ledger.claim(key, {"entitlement": ent}) is None:
                        self.ledger.mark(key, "done")
                        created += 1
            # fulfillment initiation is its own idempotent action per line
            fkey = self.ledger.key(event, line, "initiate_fulfillment",
                                   self.version)
            if self.ledger.claim(fkey, {"slot": line["slot"]}) is None:
                self.ledger.mark(fkey, "done")
                created += 1
        # Buyer registration: an explicit processing-context contact_ref
        # wins; otherwise a v1.1 envelope's own contact_ref is the
        # auditable binding (CR-S44-001) and registers the buyer.
        effective_contact_ref = contact_ref or event.get("contact_ref")
        if effective_contact_ref:
            self.buyers.add((event["tenant_id"], event["launch_id"],
                             effective_contact_ref))
        return {"result": "processed", "actions_created": created}

    def is_suppressed(self, tenant: str, launch: str,
                      contact_ref: str) -> bool:
        return (tenant, launch, contact_ref) in self.buyers


def dispatch_marketing(processor: PurchaseProcessor, queued: dict,
                       sender: Callable[[dict], str]) -> str:
    """A21: suppression is rechecked immediately before the send, not when
    the message was queued. Returns 'sent', 'suppressed', or raises."""
    if processor.is_suppressed(queued["tenant_id"], queued["launch_id"],
                               queued["contact_ref"]):
        return "suppressed"
    return sender(queued)
