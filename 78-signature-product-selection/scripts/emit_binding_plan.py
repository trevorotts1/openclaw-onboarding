#!/usr/bin/env python3
"""emit_binding_plan.py - Skill 78 native checkout binding plan (S78-06).

Emits the explicit offer-to-native-checkout mapping that S79 consumes and
S06 installs (doc 08 section 7, doc 02 section 5). Two supported routes:

- platform_native_selection: the verified platform selection mechanism
  carries the choice; the plan records the single checkout binding.
- per_offer_targets: one native checkout target per approved product/price,
  all produced by Skill 79. Multiple instances of the same native mechanism,
  never a new skill and never a duplicate product catalog.

Targets are keyed by (offer_id, price_choice_id): an offer with several
approved billing schedules gets one target per price choice. The plan fails
closed when any selectable price choice lacks a target, when two entries
claim the same (offer, price choice) or the same target reference, when a
target's native IDs do not match the approved catalog, or, when the caller
supplies an allowlist, when a target reference is not on it. S78 emits this
plan; it never edits S79's checkout implementation.

Usage:
  emit_binding_plan.py <launch.json> <targets.json> --route per_offer_targets|platform_native_selection [--allowlist <json-list>]
  emit_binding_plan.py --self-test
Exit: 0 plan emitted, 2 violation, 3 fail-closed error.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selection_core import Violation, check_invocation, validate_catalog  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402

V_BINDING_INCOMPLETE = "S78-BINDING-INCOMPLETE"
V_BINDING_SHARED = "S78-BINDING-SHARED-TARGET"
V_BINDING_DUPLICATE = "S78-BINDING-DUPLICATE-TARGET"
V_BINDING_DRIFT = "S78-BINDING-TARGET-DRIFT"
V_BINDING_ALLOWLIST = "S78-BINDING-NOT-ALLOWLISTED"


def emit_plan(launch, targets, *, route, allowlist=None):
    if route not in ("per_offer_targets", "platform_native_selection"):
        raise Violation(V_BINDING_INCOMPLETE, f"Unknown handoff route {route!r}.")
    if check_invocation(launch) != "proceed":
        raise Violation(V_BINDING_INCOMPLETE, "Binding plan requires a multiple_options launch.")
    validate_catalog(launch)
    mains = [o for o in launch["offers"] if o.get("slot") == "main"]
    by_key = {}
    seen_targets = set()
    for t in targets:
        key = (t.get("offer_id"), t.get("price_choice_id"))
        if key in by_key:
            raise Violation(V_BINDING_DUPLICATE, f"Two checkout targets claim {key}; the mapping must be explicit and single.")
        target_ref = t.get("target_ref")
        if target_ref in seen_targets:
            raise Violation(V_BINDING_SHARED, f"Checkout target {target_ref!r} is shared by more than one price choice.")
        if allowlist is not None and target_ref not in allowlist:
            raise Violation(V_BINDING_ALLOWLIST, f"Checkout target {target_ref!r} is not on the supplied allowlist.")
        seen_targets.add(target_ref)
        by_key[key] = t
    mappings = []
    for offer in mains:
        for price in offer["prices"]:
            t = by_key.get((offer["offer_id"], price["price_choice_id"]))
            if t is None:
                raise Violation(
                    V_BINDING_INCOMPLETE,
                    f"Offer {offer['offer_id']!r} price choice {price['price_choice_id']!r} has no native checkout target.",
                )
            if t.get("native_product_id") != offer.get("native_product_id") or t.get("native_price_id") != price.get("native_price_id"):
                raise Violation(
                    V_BINDING_DRIFT,
                    f"Target for {offer['offer_id']!r} / {price['price_choice_id']!r} native IDs do not match the approved catalog mapping.",
                )
            mappings.append({
                "offer_id": offer["offer_id"],
                "price_choice_id": price["price_choice_id"],
                "native_product_id": t["native_product_id"],
                "native_price_id": t["native_price_id"],
                "checkout_target_ref": t["target_ref"],
                "currency": price["currency"],
                "amount_minor": price["amount_minor"],
            })
    return {
        "schema_version": "1.0",
        "kind": "selection_binding_plan",
        "tenant_id": launch["tenant_id"],
        "location_id": launch["location_id"],
        "launch_id": launch["launch_id"],
        "revision": launch["revision"],
        "route": route,
        "mappings": mappings,
        "consumers": ["S79", "S06"],
        "producer": "S78",
        "notes": (
            "Selection carries an opaque session reference only; the checkout "
            "revalidates this mapping at purchase time. Native quote and "
            "read-back are authoritative (acceptance A05)."
        ),
    }


SELF_TEST_TARGETS = [
    {"offer_id": "MAIN-A", "price_choice_id": "MAIN-A-USD", "native_product_id": "TEST-PROD-A",
     "native_price_id": "TEST-PRICE-A", "target_ref": "TEST-CHECKOUT-A"},
    {"offer_id": "MAIN-B", "price_choice_id": "MAIN-B-USD", "native_product_id": "TEST-PROD-B",
     "native_price_id": "TEST-PRICE-B", "target_ref": "TEST-CHECKOUT-B"},
]


def self_test():
    plan = emit_plan(SELF_TEST_LAUNCH, SELF_TEST_TARGETS, route="per_offer_targets")
    assert len(plan["mappings"]) == 2
    # Multi-price offer: one target per price choice works.
    import copy as _copy
    launch = _copy.deepcopy(SELF_TEST_LAUNCH)
    launch["offers"][0]["prices"].append(
        {"price_choice_id": "MAIN-A-USD-INST", "currency": "USD", "amount_minor": 9700,
         "billing_type": "installment", "native_price_id": "TEST-PRICE-A2",
         "schedule": [{"amount_minor": 4850, "due": "today"}, {"amount_minor": 4850, "due": "in 30 days"}],
         "terms_source": None, "approval_status": "approved"})
    multi_targets = SELF_TEST_TARGETS + [
        {"offer_id": "MAIN-A", "price_choice_id": "MAIN-A-USD-INST", "native_product_id": "TEST-PROD-A",
         "native_price_id": "TEST-PRICE-A2", "target_ref": "TEST-CHECKOUT-A2"}]
    multi = emit_plan(launch, multi_targets, route="per_offer_targets")
    assert len(multi["mappings"]) == 3, multi
    for targets, code, kw in [
        (SELF_TEST_TARGETS[:1], V_BINDING_INCOMPLETE, {}),
        ([dict(SELF_TEST_TARGETS[0]), dict(SELF_TEST_TARGETS[1], target_ref="TEST-CHECKOUT-A")], V_BINDING_SHARED, {}),
        ([dict(SELF_TEST_TARGETS[0]), dict(SELF_TEST_TARGETS[1], native_price_id="FORGED")], V_BINDING_DRIFT, {}),
        (SELF_TEST_TARGETS + [dict(SELF_TEST_TARGETS[0], target_ref="TEST-CHECKOUT-A-DUP")], V_BINDING_DUPLICATE, {}),
        (SELF_TEST_TARGETS, V_BINDING_ALLOWLIST, {"allowlist": {"TEST-CHECKOUT-A"}}),
    ]:
        try:
            emit_plan(SELF_TEST_LAUNCH, targets, route="per_offer_targets", **kw)
        except Violation as v:
            assert v.code == code, (v.code, code)
        else:
            raise AssertionError(f"targets were not rejected with {code}")
    print("emit_binding_plan --self-test: PASS (per-price-choice plan incl. multi-price offer; incomplete, shared, duplicate, drift, allowlist rejections)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2 or "--route" not in argv:
        print("usage: emit_binding_plan.py <launch.json> <targets.json> --route <route> [--allowlist <json-list>]", file=sys.stderr)
        return 3
    try:
        allowlist = None
        if "--allowlist" in argv:
            allowlist = set(json.loads(Path(argv[argv.index("--allowlist") + 1]).read_text()))
        plan = emit_plan(
            json.loads(Path(args[0]).read_text()),
            json.loads(Path(args[1]).read_text()),
            route=argv[argv.index("--route") + 1],
            allowlist=allowlist,
        )
    except Violation as v:
        print(f"VIOLATION [{v.code}]: {v.message}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
