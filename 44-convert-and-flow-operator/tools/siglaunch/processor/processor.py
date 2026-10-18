"""S44-06/07 production purchase processor on the durable store.

The L1 PurchaseProcessor's semantics (work/events/events.py) with the
in-memory stand-ins replaced by the S44-05 durable store:

- short, wait-free spine: validate → inbox record-if-unseen → per-line
  grants → per-line fulfillment action → buyer registration → verified
  purchase tag action. Enrollment and long sequences are downstream
  actions, never steps here (A18: a long campaign can never block a
  later purchase);
- grants happen only from verified `succeeded` payment state;
- every effect is a claimed ledger action first, so concurrent or
  repeated processing never multiplies effects, and an executor whose
  outcome is unknown parks the action instead of completing it;
- fulfillment is its own claimed action per granted line, created from
  the verified event — it never depends on a thank-you page visit (A20);
- the verified-purchase tag application is a claimed action executed
  through the injected applier (the engine-side seam of DESIGN-S44-06
  section 1); with no applier configured the action stays claimed —
  visible outstanding work, never silently done;
- suppression (A21) is the store's authority check: active entitlement
  state, rechecked at dispatch time, never at enqueue time.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import jsonschema

# Staging note: the work-tree original imported validate_event from
# the L1 events module (work/events/events.py), which is staged
# separately and is not part of this package. Validation therefore
# lives here, against the schemas vendored beside the staged
# normalizer. Dual-version (schema v1.1 switch, CR-S44-001): every
# vendored candidate is registered under the version its own
# schema_version const declares — never the version its filename
# suggests — and validate_event dispatches on the event's stamped
# version, failing closed on any other, missing, or non-string
# version (the same registry/dispatch as the L1 events module).
# v1.2 acceptance (CR-S44-003, consumer side): the vendored copy is a
# byte-identical copy of shared-utils/signature_launch/events/
# purchase-event.v1.2.schema.json. Acceptance only — nothing here
# stamps 1.2, and parent_order_ref is never required, never identity,
# never used for grouping or dedupe.
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "normalizer"
_SCHEMA_CANDIDATES = [
    _SCHEMA_DIR / "purchase-event.schema.json",
    _SCHEMA_DIR / "purchase-event.v1.1.schema.json",
    _SCHEMA_DIR / "purchase-event.v1.2.schema.json",
]

_SCHEMAS: dict = {}
SCHEMA_SOURCES: dict = {}


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
        "purchase-event v1.0 schema not found beside the staged "
        "normalizer: "
        + ", ".join(str(p) for p in _SCHEMA_CANDIDATES))

# Back-compat surface: the single v1.0 schema this module originally
# loaded, and where it was loaded from.
_SCHEMA = _SCHEMAS["1.0"]
SCHEMA_PATH = Path(SCHEMA_SOURCES["1.0"])
SUPPORTED_SCHEMA_VERSIONS = tuple(sorted(_SCHEMAS))


def validate_event(event: dict) -> dict:
    """Validate a normalized envelope against its stamped schema
    version. Same contract as events.validate_event: v1.0 validates
    as before; v1.1 additionally allows the optional nullable
    contact_ref; v1.2 additionally allows the optional nullable
    parent_order_ref (acceptance only — parent_order_ref is never
    required and is not part of any identity, grouping, or dedupe
    key). An unknown, missing, or non-string schema_version fails
    closed, as does a non-object event. Raises on an invalid event,
    returns the event on success."""
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


def _action_key(event: dict, line: dict, action_type: str,
                version: str) -> tuple:
    txn = event.get("native_transaction_ref") or event["native_order_ref"]
    return (event["tenant_id"], txn, line["native_line_ref"],
            action_type, version)


class DurableProcessor:
    def __init__(self, store, tag_applier: Optional[Callable] = None,
                 purchase_tag: Optional[str] = None, version: str = "v1"):
        self.store = store
        self.tag_applier = tag_applier
        self.purchase_tag = purchase_tag  # verbatim Phase-A string
        self.version = version

    def process(self, event: dict,
                contact_ref: Optional[str] = None) -> dict:
        """Process one inbox-ACCEPTED event. Recording/dedup happens
        exactly once, upstream, in the normalizer's ingest (design
        section 1 ordering); this method must only ever be called with
        events ingest accepted, so a redelivery can never reach it."""
        validate_event(event)
        tenant = event["tenant_id"]
        if event["event_type"] == "refund_observed" or \
                event["payment_status"] in ("refunded",
                                             "partially_refunded"):
            for line in event["line_items"]:
                for ent in line["entitlement_ids"]:
                    self.store.revoke_entitlement(
                        tenant, line["native_line_ref"], ent)
            return {"result": "refund_applied", "actions_created": 0}
        if event["payment_status"] != "succeeded":
            return {"result": f"no_grant:{event['payment_status']}",
                    "actions_created": 0}
        created = 0
        for line in event["line_items"]:
            for ent in line["entitlement_ids"]:
                key = _action_key(event, line, "grant_access",
                                  self.version)
                if self.store.claim_action(
                        key, {"entitlement": ent}) is None:
                    self.store.grant_entitlement(
                        tenant, line["native_line_ref"], ent)
                    self.store.mark_action(key, "done",
                                           evidence_ref=event["evidence_ref"])
                    created += 1
            fkey = _action_key(event, line, "initiate_fulfillment",
                               self.version)
            if self.store.claim_action(
                    fkey, {"slot": line["slot"]}) is None:
                created += 1  # stays 'claimed' for the fulfillment worker
            if contact_ref:
                self.store.add_buyer(tenant, event["launch_id"],
                                     contact_ref, line["native_line_ref"])
        # verified-purchase tag: the handler workflow's entry seam
        if self.purchase_tag:
            tkey = (tenant, event.get("native_transaction_ref")
                    or event["native_order_ref"], "*",
                    "apply_verified_purchase_tag", self.version)
            if self.store.claim_action(
                    tkey, {"tag": self.purchase_tag}) is None:
                created += 1
                if self.tag_applier is not None and contact_ref:
                    try:
                        self.tag_applier(contact_ref, self.purchase_tag)
                        self.store.mark_action(
                            tkey, "done",
                            evidence_ref=event["evidence_ref"])
                    except Exception:
                        # outcome unknown: park, never claim success
                        self.store.mark_action(tkey, "unknown")
        return {"result": "processed", "actions_created": created}

    def fulfill(self, key: tuple, executor: Callable[[dict], None]) -> str:
        """Run one claimed fulfillment action. Executor success marks it
        done; an exception parks it as unknown (visible review), never a
        silent retry."""
        action = self.store.get_action(key)
        if action is None:
            return "not_found"
        if action["state"] == "done":
            return "already_done"
        if action["state"] == "unknown":
            return "parked_unknown"
        try:
            executor(action["payload"])
        except Exception:
            self.store.mark_action(key, "unknown")
            return "parked_unknown"
        self.store.mark_action(key, "done")
        return "done"

    def is_suppressed(self, tenant: str, launch: str,
                      contact_ref: str) -> bool:
        return self.store.is_suppressed(tenant, launch, contact_ref)


def dispatch_marketing(processor: DurableProcessor, queued: dict,
                       sender: Callable[[dict], str]) -> str:
    """A21: suppression rechecked immediately before the send."""
    if processor.is_suppressed(queued["tenant_id"], queued["launch_id"],
                               queued["contact_ref"]):
        return "suppressed"
    return sender(queued)
