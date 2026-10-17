#!/usr/bin/env python3
"""build_selection_plan.py - Skill 78 plan builder (S78-04).

Builds the selection page plan from an approved launch catalog: invocation
verdict, normalized comparison matrix, recommendation (published only when
approved), per-offer presentation fields (including intended buyer and
primary outcome when the catalog carries them), page-level FAQ and trust
items when the launch carries them, and the asset list INTEGRATION
packages. Fails closed on any catalog violation.

Usage:
  build_selection_plan.py <launch.json> [--recommendation <rec.json>] [--production]
  build_selection_plan.py --self-test
Exit: 0 plan built (or clean single-offer decline), 2 violation, 3 fail-closed error.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selection_core import (  # noqa: E402
    Violation, build_recommendation, check_invocation, normalize_matrix, validate_assets, validate_catalog,
)


def build_plan(launch, recommendation=None, production=False):
    verdict = check_invocation(launch)
    if verdict == "decline_single_offer":
        return {
            "schema_version": "1.0",
            "kind": "selection_plan",
            "outcome": "declined_single_offer",
            "directive": "Use Skill 79 combined explanation/checkout mode. Do not render a selection page.",
            "tenant_id": launch.get("tenant_id"),
            "location_id": launch.get("location_id"),
            "launch_id": launch.get("launch_id"),
            "revision": launch.get("revision"),
        }
    validate_catalog(launch, production=production)
    matrix = normalize_matrix(launch)
    rec = build_recommendation(launch, recommendation)
    offers = []
    for offer in launch["offers"]:
        if offer.get("slot") != "main":
            continue
        offers.append({
            "offer_id": offer["offer_id"],
            "display_name": offer["display_name"],
            "intended_buyer": offer.get("intended_buyer"),
            "primary_outcome": offer.get("primary_outcome"),
            "deliverables": offer.get("deliverables", []),
            "limited_deliverables": offer.get("limited_deliverables", []),
            "conditional_deliverables": offer.get("conditional_deliverables", []),
            "exclusions": offer.get("exclusions", []),
            "prices": offer.get("prices", []),
            "native_product_id": offer.get("native_product_id"),
            "cta": f"Choose {offer['display_name']}",
        })
    return {
        "schema_version": "1.0",
        "kind": "selection_plan",
        "outcome": "plan",
        "tenant_id": launch["tenant_id"],
        "location_id": launch["location_id"],
        "launch_id": launch["launch_id"],
        "revision": launch["revision"],
        "offers_in_order": offers,
        "comparison_matrix": matrix,
        "recommendation": rec,
        "faq": launch.get("selection_faq") or [],
        "trust_items": launch.get("trust_items") or [],
        "asset_list": validate_assets(launch),
        "ui_model": {
            "control": "radio_group",
            "default_selected": None,
            "single_selected_state": True,
            "error_when_none_selected": "Choose a package to continue.",
            "mobile": "stacked offers; comparison in a disclosure that never hides material exclusions",
            "collects_payment": False,
        },
    }


SELF_TEST_LAUNCH = {
    "tenant_id": "TEST-TENANT", "location_id": "TEST-LOCATION", "launch_id": "TEST-LAUNCH",
    "revision": 1, "journey_mode": "multiple_options",
    "offers": [
        {"offer_id": "MAIN-A", "slot": "main", "display_name": "TEST ONLY A",
         "deliverables": ["base-a"], "exclusions": ["No private reviews"],
         "entitlement_ids": ["base-a"], "requires": [], "excludes": [],
         "native_product_id": "TEST-PROD-A",
         "prices": [{"price_choice_id": "MAIN-A-USD", "currency": "USD", "amount_minor": 9700,
                     "billing_type": "one_time", "native_price_id": "TEST-PRICE-A",
                     "schedule": [], "terms_source": None, "approval_status": "approved"}],
         "source_kind": "test_fixture", "source_ref": "self-test", "test_only": True},
        {"offer_id": "MAIN-B", "slot": "main", "display_name": "TEST ONLY B",
         "deliverables": ["base-a", "Two private review sessions"], "exclusions": [],
         "entitlement_ids": ["base-a", "reviews"], "requires": [], "excludes": [],
         "native_product_id": "TEST-PROD-B",
         "prices": [{"price_choice_id": "MAIN-B-USD", "currency": "USD", "amount_minor": 19700,
                     "billing_type": "one_time", "native_price_id": "TEST-PRICE-B",
                     "schedule": [], "terms_source": None, "approval_status": "approved"}],
         "source_kind": "test_fixture", "source_ref": "self-test", "test_only": True},
    ],
}


def self_test():
    plan = build_plan(SELF_TEST_LAUNCH, {"offer_id": "MAIN-B", "reason": "Recommended for founders who need individual feedback", "approved": True})
    assert plan["outcome"] == "plan", plan
    rows = {r["dimension_item"]: r["cells"] for r in plan["comparison_matrix"]["rows"]}
    assert rows["Two private review sessions"] == {"MAIN-A": "not_included", "MAIN-B": "included"}, rows
    assert plan["comparison_matrix"]["exclusions"][0]["visibility"] == "material"
    assert plan["recommendation"]["placement"] == "published"
    assert plan["ui_model"]["default_selected"] is None
    assert plan["asset_list"] == []
    single = dict(SELF_TEST_LAUNCH, journey_mode="single_simple", offers=SELF_TEST_LAUNCH["offers"][:1])
    assert build_plan(single)["outcome"] == "declined_single_offer"
    bad = json.loads(json.dumps(SELF_TEST_LAUNCH))
    bad["offers"][0]["prices"][0]["amount_minor"] = None
    bad["offers"][0]["prices"][0]["approval_status"] = "unknown"
    try:
        build_plan(bad)
    except Violation as v:
        assert v.code == "S78-UNKNOWN-PRICE", v.code
    else:
        raise AssertionError("unknown price was not rejected")
    print("build_selection_plan --self-test: PASS (plan, matrix states, single-offer decline, unknown-price rejection)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: build_selection_plan.py <launch.json> [--recommendation <rec.json>] [--production]", file=sys.stderr)
        return 3
    try:
        launch = json.loads(Path(args[0]).read_text())
        rec = None
        if "--recommendation" in argv:
            rec = json.loads(Path(argv[argv.index("--recommendation") + 1]).read_text())
        plan = build_plan(launch, rec, production="--production" in argv)
    except Violation as v:
        print(f"VIOLATION [{v.code}]: {v.message}", file=sys.stderr)
        return 2
    except Exception as e:  # fail closed
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
