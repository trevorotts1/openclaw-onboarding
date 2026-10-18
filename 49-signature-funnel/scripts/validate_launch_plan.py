#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_launch_plan.py — fail-closed validator for a Signature Launch record
(spec 06 S49-02/S49-06; contracts doc 02 §2–§4).

JSON Schema (schema/launch.schema.json, mirrored in
shared-utils/signature_launch/domain/) states the SHAPE. This validator states
the DOMAIN law a shape cannot express:

  * extras implication: U1 disabled requires D1 and U2 disabled;
  * enabled slots are DEFINED and disabled slots are not smuggled in: an
    upsell_1 offer exists iff extras.upsell_1, a bump offer exists iff
    bump_enabled, etc. An approved plan must be internally consistent because
    approval binds to its hash — inconsistency discovered later is a re-plan,
    never a silent edit;
  * journey consistency: single_simple has exactly one main offer;
    multiple_options has at least two; free_entry has at least one;
  * U1 and D1 are mutually exclusive — when both are defined, each must list
    the other in `excludes`;
  * requires/excludes reference real offers, never self, and requires is
    acyclic;
  * the bump never duplicates the selected package: if the bump's
    entitlement_ids are a subset of a main offer's, that main+bump pair is
    rejected (the runtime suppression rule lives in S79; an exact duplicate
    in an approved plan is a plan defect, caught here);
  * money discipline: amount_minor is an integer minor-unit count or null —
    never a float, never a bool, and UNKNOWN IS NEVER ZERO: a null amount is
    only honest with approval_status "unknown"; an amount present with status
    "unknown" is a contradiction;
  * approval discipline: while status is approved/building,
    plan_approval_ref must be present and NO price may be unknown (an
    unknowable price can never be approved). A price with a stated amount
    keeps its provenance state (e.g. recommended_unapproved): approving the
    plan approves every stated price inside it, because the plan approval
    binds the whole plan document hash (doc 03 §9) — the ledger state then
    becomes approved_recommendation;
  * provenance: every offer carries source_kind + source_ref; test_only is
    uniform across the record (a live plan never mixes fixture offers in).

Deterministic, stdlib only. Exit 0 = valid, 2 = violation, 3 = usage.

Q12 REVISION (launch schema 1.1, S49): validate_launch accepts record
schema_version "1.0" and "1.1" (dual-version acceptance, all other checks
retained). A 1.1 record may carry prompt_policy_id, the governing prompt
policy's registry-minted name, top level beside brand_ref/brand_hash. When
the key is present its value must be a non-empty string: null or blank is
refused, and absence is the only encoding of "no policy" (absent, null,
and a value are three different plan hashes). The field is OPTIONAL and
stays out of REQUIRED_LAUNCH_FIELDS; plan_document_hash is unchanged and
binds the field automatically, since it excludes only status and
plan_approval_ref.

DELIVERY-BINDING REVISION (launch schema 1.2, S49; S82-DEC-DELIVERYURL-01):
validate_launch also accepts record schema_version "1.2". A 1.2 record may
carry delivery_bindings, an OPTIONAL top-level object keyed by
entitlement_id whose entries state delivery_kind (access / download /
schedule_included_service) and delivery_url (an https destination or null),
read by Skill 44's fulfillment-map producer (CR-S82-003) for granted
entitlements. The schema layer enforces the entry shape, the kind enum, and
the https pattern; this validator enforces what the schema cannot see: a
whitespace-only URL is refused, an empty bindings object is refused
(absence is the only encoding of "no bindings"), and a binding naming an
entitlement no offer grants fails, naming the id (R-DB-1). The field stays
out of REQUIRED_LAUNCH_FIELDS; plan_document_hash is unchanged and binds
the field automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

SLOTS = ("main", "bump", "upsell_1", "downsell_1", "upsell_2")
SOURCE_KINDS = ("owner", "existing_verified_catalog", "recommendation", "test_fixture")
PRICE_STATUSES = ("provided", "recommended_unapproved", "approved", "unknown")
BILLING_TYPES = ("one_time", "recurring", "installment", "trial")
JOURNEY_MODES = ("single_simple", "multiple_options", "free_entry")
LAUNCH_STATUSES = ("collecting", "awaiting_plan_approval", "approved", "building",
                   "blocked")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

REQUIRED_LAUNCH_FIELDS = (
    "schema_version", "tenant_id", "location_id", "launch_id", "revision",
    "journey_mode", "status", "brand_ref", "brand_hash", "route_graph_ref",
    "route_graph_hash", "plan_approval_ref", "offers", "extras",
    "bump_enabled", "image_provider", "source_refs", "test_only",
)
REQUIRED_OFFER_FIELDS = (
    "offer_id", "slot", "display_name", "deliverables", "exclusions",
    "entitlement_ids", "requires", "excludes", "native_product_id", "prices",
    "source_kind", "source_ref", "test_only",
)
REQUIRED_PRICE_FIELDS = (
    "price_choice_id", "currency", "amount_minor", "billing_type",
    "native_price_id", "schedule", "approval_status",
)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_launch(launch: Any) -> List[str]:
    fails: List[str] = []

    def fail(msg: str) -> None:
        fails.append(msg)

    if not isinstance(launch, dict):
        return ["launch record is not a JSON object"]
    for f in REQUIRED_LAUNCH_FIELDS:
        if f not in launch:
            fail(f"launch record is missing required field {f!r}")
    if fails:
        return fails
    if launch["schema_version"] not in ("1.0", "1.1", "1.2"):
        fail(f"schema_version is {launch['schema_version']!r}, expected "
             "'1.0', '1.1' or '1.2'")
    if "prompt_policy_id" in launch:
        pid = launch["prompt_policy_id"]
        if not isinstance(pid, str) or not pid.strip():
            fail("prompt_policy_id, when present, must be a non-empty "
                 "string — null or blank is refused; omit the key entirely "
                 "when no policy governs (absence is the only encoding of "
                 "'no policy')")
    if "delivery_bindings" in launch:
        bindings = launch["delivery_bindings"]
        if not isinstance(bindings, dict):
            fail("delivery_bindings, when present, must be an object "
                 "keyed by entitlement_id")
        elif not bindings:
            fail("delivery_bindings is an empty object — absence is the "
                 "only encoding of 'no bindings'; omit the key entirely "
                 "when no entitlement is bound")
        else:
            for eid, entry in bindings.items():
                if not isinstance(eid, str) or not eid.strip():
                    fail("delivery_bindings keys must be non-empty "
                         "entitlement ids")
                    continue
                if not isinstance(entry, dict):
                    fail(f"delivery binding for entitlement {eid!r} is "
                         "not an object")
                    continue
                url = entry.get("delivery_url")
                if isinstance(url, str) and not url.strip():
                    fail(f"delivery binding for entitlement {eid!r}: "
                         "delivery_url is blank — a whitespace-only URL "
                         "is refused (minLength cannot see it); state the "
                         "https destination or null")
    for f in ("tenant_id", "location_id", "launch_id", "brand_ref", "brand_hash",
              "route_graph_ref", "route_graph_hash"):
        if not isinstance(launch[f], str) or not launch[f].strip():
            fail(f"field {f!r} must be a non-empty string")
    if not _is_int(launch["revision"]) or launch["revision"] < 1:
        fail(f"revision must be an integer >= 1, got {launch['revision']!r}")
    if launch["journey_mode"] not in JOURNEY_MODES:
        fail(f"journey_mode {launch['journey_mode']!r} is not a launch mode")
    if launch["status"] not in LAUNCH_STATUSES:
        fail(f"status {launch['status']!r} is not a launch status")
    if launch["image_provider"] not in ("kie", "agnes", "other_explicit"):
        fail(f"image_provider {launch['image_provider']!r} is not a known provider")
    if type(launch["bump_enabled"]) is not bool:
        fail("bump_enabled must be a boolean")
    if type(launch["test_only"]) is not bool:
        fail("test_only must be a boolean")

    extras = launch["extras"]
    if not isinstance(extras, dict):
        return fails + ["extras is not an object"]
    for k in ("upsell_1", "downsell_1", "upsell_2"):
        if type(extras.get(k)) is not bool:
            fail(f"extras.{k} must be a boolean, got {extras.get(k)!r}")
    if fails:
        return fails
    if not extras["upsell_1"] and (extras["downsell_1"] or extras["upsell_2"]):
        fail("U1 disabled requires D1 and U2 disabled")

    offers = launch["offers"]
    if not isinstance(offers, list) or not offers:
        return fails + ["offers must be a non-empty array"]
    by_id: Dict[str, Dict[str, Any]] = {}
    by_slot: Dict[str, List[Dict[str, Any]]] = {s: [] for s in SLOTS}
    for o in offers:
        if not isinstance(o, dict):
            fail(f"an offer entry is not an object: {o!r}")
            continue
        oid = o.get("offer_id")
        for f in REQUIRED_OFFER_FIELDS:
            if f not in o:
                fail(f"offer {oid!r} is missing required field {f!r}")
        if not isinstance(oid, str) or not oid.strip():
            fail(f"an offer has no usable offer_id: {o!r}")
            continue
        if oid in by_id:
            fail(f"duplicate offer_id {oid!r}")
        by_id[oid] = o
        if o.get("slot") not in SLOTS:
            fail(f"offer {oid!r} has unknown slot {o.get('slot')!r}")
        else:
            by_slot[o["slot"]].append(o)
        if o.get("source_kind") not in SOURCE_KINDS:
            fail(f"offer {oid!r} source_kind {o.get('source_kind')!r} is not a "
                 "provenance kind (owner / existing_verified_catalog / "
                 "recommendation / test_fixture)")
        if not isinstance(o.get("source_ref"), str) or not o["source_ref"].strip():
            fail(f"offer {oid!r} carries no source_ref — provenance is required "
                 "for every offered fact")
        if type(o.get("test_only")) is bool and o["test_only"] != launch["test_only"]:
            fail(f"offer {oid!r} test_only={o['test_only']} contradicts the "
                 f"record's test_only={launch['test_only']} — a live plan never "
                 "mixes fixture offers in")
        # Prices.
        prices = o.get("prices")
        if not isinstance(prices, list) or not prices:
            fail(f"offer {oid!r} carries no prices (at least one price choice "
                 "is required; an unknown price is stated as unknown, never "
                 "omitted and never zero-filled)")
        else:
            for p in prices:
                if not isinstance(p, dict):
                    fail(f"offer {oid!r} has a non-object price entry")
                    continue
                for f in REQUIRED_PRICE_FIELDS:
                    if f not in p:
                        fail(f"offer {oid!r} price is missing field {f!r}")
                amt = p.get("amount_minor")
                status = p.get("approval_status")
                if amt is not None and not _is_int(amt):
                    fail(f"offer {oid!r} price {p.get('price_choice_id')!r}: "
                         f"amount_minor {amt!r} is not an integer minor-unit "
                         "count (float dollars are forbidden)")
                if _is_int(amt) and amt < 0:
                    fail(f"offer {oid!r} price amount_minor is negative")
                if status not in PRICE_STATUSES:
                    fail(f"offer {oid!r} price approval_status {status!r} is "
                         "not a provenance state")
                if amt is None and status != "unknown":
                    fail(f"offer {oid!r} price has amount_minor null but status "
                         f"{status!r} — an unknown amount must be stated as "
                         "unknown (unknown is never silently zero or approved)")
                if amt is not None and status == "unknown":
                    fail(f"offer {oid!r} price states an amount AND status "
                         "unknown — a contradiction")
                cur = p.get("currency")
                if not isinstance(cur, str) or not _CURRENCY_RE.match(cur):
                    fail(f"offer {oid!r} price currency {cur!r} is not an "
                         "ISO 4217 code")
                if p.get("billing_type") not in BILLING_TYPES:
                    fail(f"offer {oid!r} price billing_type "
                         f"{p.get('billing_type')!r} is unknown")

    # Delivery bindings: a binding may only name an entitlement some
    # offer grants (R-DB-1). An orphan binding is a record error, most
    # likely a mistyped id; it fails here, naming the id, rather than
    # surfacing at fulfillment time as a missing buyer link.
    if isinstance(launch.get("delivery_bindings"), dict):
        granted_ids = set()
        for o in by_id.values():
            ents = o.get("entitlement_ids")
            if isinstance(ents, list):
                granted_ids.update(e for e in ents if isinstance(e, str))
        for eid in launch["delivery_bindings"]:
            if eid not in granted_ids:
                fail(f"delivery_bindings names entitlement {eid!r}, "
                     "which no offer grants — an orphan binding fails "
                     "validation (R-DB-1)")

    # Slot/extras agreement.
    for slot, flag in (("upsell_1", extras["upsell_1"]),
                       ("downsell_1", extras["downsell_1"]),
                       ("upsell_2", extras["upsell_2"]),
                       ("bump", launch["bump_enabled"])):
        defined = len(by_slot[slot]) > 0
        if flag and not defined:
            fail(f"slot {slot!r} is ENABLED but no offer defines it")
        if defined and not flag:
            fail(f"slot {slot!r} has offer(s) defined but is DISABLED — an "
                 "approved plan may not carry smuggled offers")

    # Journey consistency.
    mains = by_slot["main"]
    if not mains:
        fail("no main offer is defined")
    if launch["journey_mode"] == "single_simple" and len(mains) != 1:
        fail(f"single_simple requires exactly one main offer, found {len(mains)}")
    if launch["journey_mode"] == "multiple_options" and len(mains) < 2:
        fail(f"multiple_options requires at least two main offers, "
             f"found {len(mains)}")

    # U1/D1 mutual exclusion must be DECLARED when both exist.
    for a, b in (("upsell_1", "downsell_1"), ("downsell_1", "upsell_1")):
        for o in by_slot[a]:
            for other in by_slot[b]:
                if other["offer_id"] not in (o.get("excludes") or []):
                    fail(f"offer {o['offer_id']!r} ({a}) must declare "
                         f"{other['offer_id']!r} ({b}) in excludes — U1 and D1 "
                         "are mutually exclusive")

    # requires/excludes reference discipline + requires acyclicity.
    graph: Dict[str, List[str]] = {}
    for oid, o in by_id.items():
        for field in ("requires", "excludes"):
            for ref in o.get(field) or []:
                if ref == oid:
                    fail(f"offer {oid!r} {field} itself")
                elif ref not in by_id:
                    fail(f"offer {oid!r} {field} unknown offer {ref!r}")
        graph[oid] = [r for r in (o.get("requires") or []) if r in by_id]
    visiting: List[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            fail(f"requires cycle: {' -> '.join(visiting + [node])}")
            return
        visiting.append(node)
        for nxt in graph.get(node, []):
            visit(nxt)
        visiting.pop()

    for oid in graph:
        visit(oid)

    # Bump must not duplicate a main package's entitlements.
    for bump in by_slot["bump"]:
        bent = set(bump.get("entitlement_ids") or [])
        if not bent:
            fail(f"bump offer {bump['offer_id']!r} grants no entitlements")
        for m in mains:
            if bent and bent <= set(m.get("entitlement_ids") or []):
                fail(f"bump offer {bump['offer_id']!r} entitlements are a "
                     f"subset of main offer {m['offer_id']!r} — the bump "
                     "would sell the buyer what they already selected")

    # Approval discipline. The full binding (hash, identity, revocation) is
    # the approval GATE's job (assert_plan_build_approved below); this shape
    # rule only insists an approved/building record carries its approval
    # reference and no unknown money. A recommended_unapproved price inside
    # an approved record is covered by the plan approval itself, which binds
    # the whole plan hash — the recommendation was approved AS PART of the
    # plan, and its ledger state becomes approved_recommendation.
    if launch["status"] in ("approved", "building"):
        if not isinstance(launch["plan_approval_ref"], str) \
                or not launch["plan_approval_ref"].strip():
            fail(f"status is {launch['status']} but plan_approval_ref is "
                 "empty — no build without a recorded plan approval")
        for oid, o in by_id.items():
            for p in o.get("prices") or []:
                if p.get("approval_status") == "unknown":
                    fail(f"status is {launch['status']} but offer {oid!r} "
                         f"price {p.get('price_choice_id')!r} is still "
                         "unknown — approval cannot cover an unknowable price")
                if p.get("amount_minor") is None:
                    fail(f"status is {launch['status']} but offer {oid!r} "
                         "price amount is unknown")
    return fails


# ---------------------------------------------------------------------------
# Plan-approval gate (doc 03 §9). The hash binds the plan's CONTENT — offers,
# prices, route, revision, mode — never its lifecycle fields: `status` flips
# to approved BECAUSE the gate passed, and plan_approval_ref is written by
# the approval itself. Excluding both keeps one approval verifiable before
# and after the flip.
# ---------------------------------------------------------------------------
class ApprovalError(ValueError):
    pass


def plan_document_hash(launch: Dict[str, Any]) -> str:
    bindable = {k: v for k, v in launch.items()
                if k not in ("status", "plan_approval_ref")}
    return hashlib.sha256(json.dumps(bindable, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


APPROVAL_TYPES = ("launch_plan_build", "paid_asset_budget", "test_location_use",
                  "live_payment_test", "customer_send_activation",
                  "page_publication", "batch_merge", "release_publication",
                  "fleet_rollout")
VERIFICATION_CLASSES = ("authenticated_platform_record",
                        "recorded_consent_not_cryptographically_sealed")


def _check_approval_record(approval: Any, *, expected_type: str,
                           expected_subject_hash: str,
                           client_identity_ref: str,
                           worker_identity_ref: str,
                           max_age_hours: Optional[float],
                           now: Optional[datetime]) -> Dict[str, Any]:
    """The single approval-record discipline (doc 03 §9), shared by the plan
    gate and by every scoped side-effect approval. Checks, in order: record
    shape; the type matches what is being authorized (approval types are
    separate — a budget approval never authorizes a build, a build approval
    never authorizes a publication); the SCOPE actually contains that type
    (a narrowed or emptied scope authorizes nothing, doc 03 §9); not
    revoked; verification class recognized; subject hash == the current
    plan's document hash; the approver IS the launch's client identity; the
    approver is NOT the worker operating the run; the record carries the
    stable platform reference of the client's own response; the record is
    not expired and not from the future."""
    if not isinstance(approval, dict):
        raise ApprovalError("approval record is not an object")
    for f in ("schema_version", "approval_id", "subject_type", "subject_hash",
              "owner_identity_ref", "source_message_ref", "recorded_at",
              "scope", "revoked", "verification_class"):
        if f not in approval:
            raise ApprovalError(f"approval record is missing field {f!r}")
    if approval["schema_version"] != "1.0":
        raise ApprovalError("approval schema_version is not 1.0")
    if approval["subject_type"] != expected_type:
        raise ApprovalError(
            f"approval type {approval['subject_type']!r} does not authorize "
            f"{expected_type!r} (types are separate, doc 03 §9)")
    scope = approval["scope"]
    if not isinstance(scope, list) or not scope or \
            not all(isinstance(s, str) and s.strip() for s in scope) or \
            expected_type not in scope:
        raise ApprovalError(
            f"approval scope {scope!r} does not cover {expected_type!r} — a "
            "narrowed, emptied, or foreign scope authorizes nothing "
            "(doc 03 §9: the gate checks type, identity, hash, SCOPE, and "
            "revocation)")
    if approval["revoked"] is not False:
        raise ApprovalError("approval has been revoked")
    if approval["verification_class"] not in VERIFICATION_CLASSES:
        raise ApprovalError("approval verification_class is not recognized")
    if approval["subject_hash"] != expected_subject_hash:
        raise ApprovalError(
            "approval subject_hash does not match the current plan — the plan "
            "changed after approval (or this approval belongs to another plan)")
    owner = approval["owner_identity_ref"]
    if not isinstance(owner, str) or not owner.strip():
        raise ApprovalError("approval names no owner identity")
    if owner != client_identity_ref:
        raise ApprovalError(
            "the approver is not this launch's client identity — an unrelated "
            "identity cannot approve another launch")
    if owner == worker_identity_ref:
        raise ApprovalError(
            "the worker operating the run cannot approve its own work "
            "(self-approval is refused)")
    if not isinstance(approval["source_message_ref"], str) \
            or not approval["source_message_ref"].strip():
        raise ApprovalError(
            "approval carries no platform reference to the client's own "
            "response — recorded consent requires the owner's actual message")
    try:
        recorded = datetime.fromisoformat(
            str(approval["recorded_at"]).replace("Z", "+00:00"))
    except ValueError:
        raise ApprovalError("approval recorded_at is not a valid timestamp")
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if recorded > now:
        raise ApprovalError("approval recorded_at is in the future")
    if max_age_hours is not None and \
            (now - recorded).total_seconds() > max_age_hours * 3600:
        raise ApprovalError(
            f"approval is expired (older than {max_age_hours} hours) — "
            "re-confirm before acting")
    return {"ok": True, "approval_id": approval["approval_id"],
            "subject_hash": expected_subject_hash,
            "verification_class": approval["verification_class"]}


def assert_plan_build_approved(launch: Dict[str, Any], approval: Any, *,
                               client_identity_ref: str,
                               worker_identity_ref: str,
                               max_age_hours: Optional[float] = 72.0,
                               now: Optional[datetime] = None) -> Dict[str, Any]:
    """Assert that THIS launch plan may be built, under doc 03 §9.

    Raises ApprovalError on any failure; returns an assertion dict on
    success. The plan gate: type launch_plan_build AND that type inside the
    record's scope, subject hash == the current plan's document hash (any
    commercial change — a price, an offer, the route, the revision —
    invalidates it), approver is the client and not the worker, provenance
    reference present, not revoked, not expired. Without an external
    signing key the honest verification class is recorded consent, and the
    assertion says so — it is never dressed up as cryptographic proof."""
    return _check_approval_record(
        approval, expected_type="launch_plan_build",
        expected_subject_hash=plan_document_hash(launch),
        client_identity_ref=client_identity_ref,
        worker_identity_ref=worker_identity_ref,
        max_age_hours=max_age_hours, now=now)


def assert_scoped_approval(launch: Dict[str, Any], approval: Any,
                           approval_type: str, *,
                           client_identity_ref: str,
                           worker_identity_ref: str,
                           max_age_hours: Optional[float] = 72.0,
                           now: Optional[datetime] = None) -> Dict[str, Any]:
    """Assert a SCOPED side-effect approval (doc 02 §9, doc 03 §9): test
    location use, page publication, live payment test, customer send. The
    record gets exactly the plan gate's discipline — separate type, scope
    containing the type, plan-hash binding, client identity, no worker
    self-approval, provenance reference, revocation, expiry. The plan-build
    approval itself is NOT a scoped approval: it is checked by
    assert_plan_build_approved and never substitutes for one of these."""
    if approval_type == "launch_plan_build":
        raise ApprovalError(
            "launch_plan_build is the plan gate, not a scoped approval — use "
            "assert_plan_build_approved")
    if approval_type not in APPROVAL_TYPES:
        raise ApprovalError(f"unknown approval type {approval_type!r}")
    return _check_approval_record(
        approval, expected_type=approval_type,
        expected_subject_hash=plan_document_hash(launch),
        client_identity_ref=client_identity_ref,
        worker_identity_ref=worker_identity_ref,
        max_age_hours=max_age_hours, now=now)


def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> int:
    ok = True

    def say(good: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    def offer(oid: str, slot: str, amt: Optional[int] = 1000,
              status: str = "approved", ents=None, excludes=None) -> Dict[str, Any]:
        return {"offer_id": oid, "slot": slot, "display_name": oid,
                "deliverables": ["x"], "exclusions": [],
                "entitlement_ids": ents or [oid.lower()],
                "requires": [], "excludes": excludes or [],
                "native_product_id": None,
                "prices": [{"price_choice_id": f"{oid}-USD", "currency": "USD",
                            "amount_minor": amt, "billing_type": "one_time",
                            "native_price_id": None, "schedule": [],
                            "terms_source": None, "approval_status": status}],
                "source_kind": "owner", "source_ref": "self-test",
                "test_only": True}

    def plan_launch(offers, extras=None, mode="single_simple", status="approved",
               bump=False) -> Dict[str, Any]:
        return {"schema_version": "1.0", "tenant_id": "T", "location_id": "L",
                "launch_id": "X", "revision": 1, "journey_mode": mode,
                "status": status, "brand_ref": "B", "brand_hash": "H",
                "route_graph_ref": "r", "route_graph_hash": "h",
                "plan_approval_ref": "APPR-1" if status in ("approved", "building") else None,
                "offers": offers,
                "extras": extras or {"upsell_1": False, "downsell_1": False,
                                     "upsell_2": False},
                "bump_enabled": bump, "image_provider": "agnes",
                "source_refs": [], "test_only": True}

    good = plan_launch([offer("M", "main")])
    say(validate_launch(good) == [], "minimal approved single_simple plan validates")

    bad = plan_launch([offer("M", "main", amt=None, status="approved")])
    say(validate_launch(bad) != [], "null amount with status approved is refused")
    bad = plan_launch([offer("M", "main", amt=0, status="unknown")])
    say(validate_launch(bad) != [], "amount present with status unknown is refused")
    bad = plan_launch([offer("M", "main", amt=10.5)])
    say(validate_launch(bad) != [], "float amount_minor is refused (no float dollars)")
    bad = plan_launch([offer("M", "main", amt=None, status="unknown")])
    say(validate_launch(bad) != [], "approved launch with an unknown price is refused")
    covered = plan_launch([offer("M", "main", status="recommended_unapproved")])
    say(validate_launch(covered) == [],
        "a recommended price inside an approved record is covered by the plan "
        "approval that binds the whole plan hash")
    bad = plan_launch([offer("M", "main")],
                 extras={"upsell_1": True, "downsell_1": False, "upsell_2": False})
    say(validate_launch(bad) != [], "enabled U1 with no U1 offer is refused")
    bad = plan_launch([offer("M", "main"), offer("U1", "upsell_1")])
    say(validate_launch(bad) != [], "U1 offer defined while U1 disabled is refused")
    bad = plan_launch([offer("M", "main"),
                  offer("U1", "upsell_1"), offer("D1", "downsell_1")],
                 extras={"upsell_1": True, "downsell_1": True, "upsell_2": False})
    say(validate_launch(bad) != [], "U1/D1 without declared mutual exclusion is refused")
    good2 = plan_launch([offer("M", "main"),
                    offer("U1", "upsell_1", excludes=["D1"]),
                    offer("D1", "downsell_1", excludes=["U1"])],
                   extras={"upsell_1": True, "downsell_1": True, "upsell_2": False})
    say(validate_launch(good2) == [], "U1/D1 with declared exclusion validates")
    bad = plan_launch([offer("M", "main", ents=["a", "b"]),
                  offer("B", "bump", ents=["a"])], bump=True)
    say(validate_launch(bad) != [], "bump duplicating main entitlements is refused")
    pre = plan_launch([offer("M", "main", status="recommended_unapproved")],
                 status="awaiting_plan_approval")
    say(validate_launch(pre) == [],
        "pre-approval record with recommended_unapproved prices validates")

    # Approval gate: scope contents are checked (doc 03 §9, review D1) and
    # scoped approvals get the same discipline (review D6).
    from datetime import datetime as _dt, timezone as _tz

    def approval(scope, atype="launch_plan_build", owner="client:acme",
                 **over):
        rec = {"schema_version": "1.0", "approval_id": "A-1",
               "subject_type": atype,
               "subject_hash": plan_document_hash(good),
               "owner_identity_ref": owner,
               "source_message_ref": "msg-1",
               "recorded_at": _dt.now(_tz.utc).isoformat(),
               "scope": scope, "revoked": False,
               "verification_class":
                   "recorded_consent_not_cryptographically_sealed"}
        rec.update(over)
        return rec

    gate_kw = dict(client_identity_ref="client:acme",
                   worker_identity_ref="worker:s49")
    try:
        assert_plan_build_approved(good, approval(["launch_plan_build"]),
                                   **gate_kw)
        say(True, "gate accepts a valid approval whose scope covers the build")
    except ApprovalError:
        say(False, "gate accepts a valid approval whose scope covers the build")
    for bad_scope, label in (([], "empty scope"),
                             (["paid_asset_budget"], "foreign-only scope"),
                             (["something_else"], "unrelated scope")):
        try:
            assert_plan_build_approved(good, approval(bad_scope), **gate_kw)
            say(False, f"gate refuses an approval with {label} (D1)")
        except ApprovalError:
            say(True, f"gate refuses an approval with {label} (D1)")
    try:
        assert_scoped_approval(
            good, approval(["test_location_use"], atype="test_location_use"),
            "test_location_use", **gate_kw)
        say(True, "scoped approval passes the full gate discipline")
    except ApprovalError:
        say(False, "scoped approval passes the full gate discipline")
    try:
        assert_scoped_approval(
            good, approval(["test_location_use"], atype="test_location_use",
                           owner="worker:s49", source_message_ref=""),
            "test_location_use", **gate_kw)
        say(False, "scoped approval fabricated by the worker is refused (D6)")
    except ApprovalError:
        say(True, "scoped approval fabricated by the worker is refused (D6)")
    try:
        assert_scoped_approval(
            good, approval(["test_location_use"], atype="test_location_use",
                           recorded_at="2020-01-01T00:00:00+00:00"),
            "test_location_use", **gate_kw)
        say(False, "stale scoped approval is refused as expired (D6)")
    except ApprovalError:
        say(True, "stale scoped approval is refused as expired (D6)")
    try:
        assert_scoped_approval(
            good, approval(["launch_plan_build"]), "launch_plan_build",
            **gate_kw)
        say(False, "plan-build approval cannot pose as a scoped approval")
    except ApprovalError:
        say(True, "plan-build approval cannot pose as a scoped approval")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed Signature Launch plan validator. Exit 0 valid, "
                    "2 violation, 3 usage.")
    ap.add_argument("--launch", help="path to the launch record JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.launch:
        print("USAGE ERROR: pass --launch <launch.json> (or --self-test).")
        return EXIT_FAILCLOSED
    try:
        launch = _load_json(args.launch)
    except (OSError, ValueError) as exc:
        print(f"USAGE/IO ERROR: cannot load launch record: {exc}")
        return EXIT_FAILCLOSED
    fails = validate_launch(launch)
    if fails:
        print(f"FAIL: {len(fails)} plan violation(s):")
        for f in fails:
            print(f"  - {f}")
        return EXIT_VIOLATION
    print("PASS: launch plan is internally consistent (slots, provenance, "
          "money, exclusion, approval discipline).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
