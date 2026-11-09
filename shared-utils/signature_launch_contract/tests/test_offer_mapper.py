"""Contract test for the canonical offer mapper (PRD-18, PRD-03).

One round trip: answers file -> launch record 1.2 -> Skill 78 plan -> Skill 79 checkout request must keep
every offer's name, billing, deliverables, exclusions and price, for both answers fixtures. The expected
values are read straight from the answers file, never from the mapper.

Run: python3 -m pytest shared-utils/signature_launch_contract/tests/test_offer_mapper.py -q
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
CONTRACT = HERE.parents[1]
REPO = HERE.parents[3]

def _skill(name):  # onboarding: 49-signature-funnel; 999: .claude/skills/signature-funnel
    p = REPO / name
    return p if p.is_dir() else REPO / ".claude/skills" / name.split("-", 1)[1]

FIXTURES = REPO / "shared-utils" / "client_intake" / "fixtures"
sys.path.insert(0, str(CONTRACT))
import offer_mapper as om  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vlp = _load("sf49_validate_launch_plan", _skill("49-signature-funnel") / "scripts" / "validate_launch_plan.py")
vco = _load("s79_validate_checkout", _skill("79-signature-order-form") / "scripts" / "validate_checkout.py")

IDENT = dict(tenant_id="t1", location_id="loc1", launch_id="L1", revision=1, brand_ref="brand:1", brand_hash="h" * 64,
             route_graph_ref="route-graph:L1:rev1", route_graph_hash="g" * 64, plan_approval_ref="approval:1")
CONTEXT = dict(approved_plan_hash="p" * 64, brand_revision="b1", terms_ref="terms:1", native_capability_evidence_ref="cap:1",
               successful_payment_next_route="/thanks", fulfillment_mapping_ref="fulfil:1", consent_ref="consent:1",
               failed_pending_requirements={"failed_state_copy_ref": "c:f", "pending_state_copy_ref": "c:p",
                                            "retry_policy": "reconcile_native_records_first"})
ANSWER_FILES = ["answers.7fig.json", "answers.elevation.json"]


def doc(name):
    return json.loads((FIXTURES / name).read_text())


def expected_offers(d):
    """What the client said, offer by offer, read from the answers file itself."""
    v = {k: e["value"] for k, e in d["answers"].items()}
    rows = [(p["display_name"], p["deliverables"], p.get("exclusions", []), p["price"], p["price"].get("billing_type", "one_time"))
            for p in v["packages"]]
    for slot in ("bump", "upsell_1", "downsell_1", "upsell_2"):
        if isinstance(v.get(slot), dict):
            p = v[slot]
            rows.append((p["display_name"], p["deliverables"], p.get("exclusions", []), p["price"], p["price"].get("billing_type", "one_time")))
    return rows


def facts(offer, price):
    return (offer["display_name"], offer["deliverables"], offer["exclusions"],
            {"amount_minor": price["amount_minor"], "currency": price["currency"]}, price["billing_type"])


def want(row):
    name, deliv, excl, price, billing = row
    return (name, deliv, excl, {"amount_minor": price["amount_minor"], "currency": price["currency"]}, billing)


def round_trip(d):
    record, _ = om.answers_to_record(d, **IDENT)
    assert vlp.validate_launch(record) == []
    rows = expected_offers(d)
    assert [facts(o, o["prices"][0]) for o in record["offers"]] == [want(r) for r in rows]

    plan_record = record
    if record["journey_mode"] == "folded_levels":
        # Skill 78 declines folded_levels (the levels sit on the sales page, there is no selection page), so the
        # same offers are planned through a journey 78 supports, the way the checkout instances are built.
        with pytest.raises(Exception) as declined:
            om.record_to_plan(record)
        assert getattr(declined.value, "code", None) == "S78-JOURNEY-MODE-DECLINE"
        plan_record = {**record, "journey_mode": "multiple_options"}
    plan = om.record_to_plan(plan_record)
    assert plan["outcome"] == "plan"
    mains = [want(r) for r, o in zip(rows, record["offers"]) if o["slot"] == "main"]
    assert [facts(o, o["prices"][0]) for o in plan["offers_in_order"]] == mains
    assert [o["offer_id"] for o in plan["offers_in_order"]] == [o["offer_id"] for o in record["offers"] if o["slot"] == "main"]

    for o, row in zip(record["offers"], rows):  # every offer reaches checkout with its id, billing and price
        req = om.record_to_checkout_request(record, o["offer_id"], checkout_mode="combined_single_offer", **CONTEXT)
        vco.validate_request(req)
        mp = req["main_price"]
        assert req["main_offer_id"] == o["offer_id"]
        assert (mp["amount_minor"], mp["currency"], mp["billing_type"]) == (row[3]["amount_minor"], row[3]["currency"], row[4])
        assert mp["approval_status"] == "approved" and req["main_entitlement_ids"] == o["entitlement_ids"]
        assert facts(o, o["prices"][0]) == want(row)  # name, deliverables, exclusions ride with the offer_id, in the record


@pytest.mark.parametrize("name", ANSWER_FILES)
def test_round_trip_preserves_every_offer_fact(name):
    round_trip(doc(name))


def test_round_trip_keeps_exclusions_billing_and_native_ids_the_fixtures_do_not_carry():
    d = doc("answers.elevation.json")
    p = d["answers"]["packages"]["value"][1]
    p["exclusions"] = ["No refunds after week 2"]
    p["price"]["billing_type"] = "recurring"
    p["price"]["schedule"] = [{"amount_minor": 49700, "due": "monthly"}]  # 78 refuses recurring with no interval
    d["answers"]["packages"]["value"][0]["native_product_id"] = "prod_1"
    record, _ = om.answers_to_record(d, **IDENT)
    plan = om.record_to_plan(record)
    premium = next(o for o in plan["offers_in_order"] if o["display_name"] == "Premium")
    assert premium["exclusions"] == ["No refunds after week 2"] and premium["prices"][0]["billing_type"] == "recurring"
    assert plan["comparison_matrix"]["exclusions"][0]["exclusion"] == "No refunds after week 2"
    assert next(o for o in plan["offers_in_order"] if o["display_name"] == "Starter")["native_product_id"] == "prod_1"
    req = om.record_to_checkout_request(record, "MAIN-2", checkout_mode="combined_single_offer", **CONTEXT)
    assert req["main_price"]["billing_type"] == "recurring"
    assert req["main_price"]["schedule"] == [{"sequence": 1, "amount_minor": 49700, "due": "monthly"}]
    vco.validate_request(req)


def test_provided_prices_are_provided_owner_with_a_resolving_source_ref():
    d = doc("answers.elevation.json")
    record, _ = om.answers_to_record(d, **IDENT)
    om.verify_provenance(d, record["offers"])
    for o in record["offers"]:
        assert o["prices"][0]["approval_status"] == "provided" and o["source_kind"] == "owner"
        assert om.REF.match(o["source_ref"])
    assert record["offers"][0]["source_ref"] == "answers-file:packages[0]"


def test_recommended_price_shows_recommended_unapproved_in_launch_json_and_78_refuses_it():
    d = doc("answers.elevation.json")
    d["answers"]["packages"]["status"] = "default_to_confirm"
    # 78 refuses a recommended price until the client's plan approval covers it (U-products-07): this record
    # is built before that approval, so it is awaiting_plan_approval with no plan_approval_ref.
    record, _ = om.answers_to_record(d, **{**IDENT, "plan_approval_ref": None})
    assert record["status"] == "awaiting_plan_approval"
    launch = json.loads(json.dumps(record))  # what is written to launch.json
    mains = [o for o in launch["offers"] if o["slot"] == "main"]
    assert {o["prices"][0]["approval_status"] for o in mains} == {"recommended_unapproved"}
    assert {o["source_kind"] for o in mains} == {"recommendation"}
    assert launch["offers"][-1]["prices"][0]["approval_status"] == "provided"  # the upsell was still provided
    with pytest.raises(Exception) as e:
        om.record_to_plan(record)
    assert getattr(e.value, "code", None) == "S78-UNAPPROVED-PRICE"
    approved, _ = om.answers_to_record(d, **IDENT)  # the same prices once the plan approval carries a ref
    assert om.record_to_plan(approved)["outcome"] == "plan"


def test_billing_comes_from_the_answers_never_a_constant():
    d = doc("answers.elevation.json")
    _, flagged = om.answers_to_record(d, **IDENT)
    assert [f["field"] for f in flagged] == ["billing:packages[0]", "billing:packages[1]", "billing:upsell_1", "billing:downsell_1"]
    d["answers"]["billing"] = {"value": "monthly", "status": "provided", "source": "client"}
    record, flagged = om.answers_to_record(d, **IDENT)
    assert flagged == [] and {o["prices"][0]["billing_type"] for o in record["offers"]} == {"recurring"}


def test_offer_without_a_resolving_source_ref_is_refused_at_intake():
    d = doc("answers.elevation.json")
    record, _ = om.answers_to_record(d, **IDENT)
    forged = copy.deepcopy(record["offers"][0])
    forged["source_ref"] = "answers-file:made_up_price"
    with pytest.raises(om.MapperError) as e:
        om.verify_provenance(d, [forged])
    assert e.value.code == "AF-OFFER-SOURCE-REF"
    forged["source_ref"] = "launcher-intake:L1:r1"  # the old self-assigned ref
    with pytest.raises(om.MapperError):
        om.verify_provenance(d, [forged])


def test_a_made_up_price_or_self_assigned_approval_is_refused_even_with_a_real_ref():
    d = doc("answers.elevation.json")
    d["answers"]["packages"]["status"] = "suggested"
    record, _ = om.answers_to_record(d, **IDENT)
    liar = copy.deepcopy(record["offers"][0])
    liar["prices"][0]["approval_status"], liar["source_kind"] = "approved", "owner"
    with pytest.raises(om.MapperError) as e:
        om.verify_provenance(d, [liar])
    assert e.value.code == "AF-OFFER-PROVENANCE"
    cheaper = copy.deepcopy(record["offers"][0])
    cheaper["prices"][0]["amount_minor"] = 1
    with pytest.raises(om.MapperError):
        om.verify_provenance(d, [cheaper])


def test_unknown_or_amountless_prices_and_unapproved_plans_fail_closed():
    d = doc("answers.elevation.json")
    d["answers"]["packages"]["status"] = "unknown"
    with pytest.raises(om.MapperError) as e:
        om.answers_to_record(d, **IDENT)
    assert e.value.code == "AF-OFFER-PRICE-UNKNOWN"
    d = doc("answers.elevation.json")
    del d["answers"]["packages"]["value"][0]["price"]["amount_minor"]
    with pytest.raises(om.MapperError):
        om.answers_to_record(d, **IDENT)
    record, _ = om.answers_to_record(doc("answers.elevation.json"), **{**IDENT, "plan_approval_ref": None})
    assert record["status"] == "awaiting_plan_approval"
    with pytest.raises(om.MapperError) as e:
        om.record_to_checkout_request(record, "MAIN-1", checkout_mode="combined_single_offer", **CONTEXT)
    assert e.value.code == "AF-CHECKOUT-UNAPPROVED"
    approved, _ = om.answers_to_record(doc("answers.elevation.json"), **IDENT)
    approved["offers"][0]["prices"][0]["billing_type"] = "installment"
    with pytest.raises(om.MapperError) as e:
        om.record_to_checkout_request(approved, "MAIN-1", checkout_mode="combined_single_offer", **CONTEXT)
    assert e.value.code == "AF-CHECKOUT-BILLING"


# ---------------------------------------------------------------- Skill 83 intake: resolve_offer (PRD-03)
FIXTURES_83 = _skill("83-black-friday-launcher") / "fixtures"


def _ref(role, mains_seen):
    return f"answers-file:packages[{mains_seen}]" if role == "main" else f"answers-file:{role}"


@pytest.mark.parametrize("fx", ["elevation", "seven-figure-preneur"])
def test_every_83_fixture_offer_resolves_in_its_answers_file(fx):
    d = json.loads((FIXTURES_83 / fx / "answers.json").read_text())
    intake = json.loads((FIXTURES_83 / fx / "intake.json").read_text())
    n = 0
    for o in intake["offers"]:
        got = om.resolve_offer(d, _ref(o["role"], n), slot=o["role"], display_name=o["name"],
                               amount_minor=o["price"]["amount_minor"], currency=o["price"]["currency"])
        n += o["role"] == "main"
        assert got["offer_id"] == o["offer_id"]
        assert (got["prices"][0]["approval_status"], got["source_kind"], got["prices"][0]["billing_type"]) == (
            "provided", "owner", "one_time")


def test_resolve_offer_refuses_an_unresolved_ref_and_a_made_up_price():
    d = json.loads((FIXTURES_83 / "elevation" / "answers.json").read_text())
    kw = dict(slot="main", display_name="TEST ONLY Essential", amount_minor=9700, currency="USD")
    for bad in (None, "", "answers-file:made_up_price", "launcher-intake:L1:r1", "answers-file:packages[9]"):
        with pytest.raises(om.MapperError) as e:
            om.resolve_offer(d, bad, **kw)
        assert e.value.code == "AF-OFFER-SOURCE-REF"
    for field, value in (("amount_minor", 1), ("display_name", "Made Up"), ("slot", "bump"), ("currency", "EUR")):
        with pytest.raises(om.MapperError) as e:
            om.resolve_offer(d, "answers-file:packages[0]", **{**kw, field: value})
        assert e.value.code == "AF-OFFER-PROVENANCE"


def test_resolve_offer_carries_a_recommended_price_as_recommended_unapproved():
    d = json.loads((FIXTURES_83 / "elevation" / "answers.json").read_text())
    d["answers"]["packages"]["status"] = "suggested"
    got = om.resolve_offer(d, "answers-file:packages[0]", slot="main", display_name="TEST ONLY Essential",
                           amount_minor=9700, currency="USD")
    assert (got["prices"][0]["approval_status"], got["source_kind"]) == ("recommended_unapproved", "recommendation")
