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
    p["billing"] = "monthly"  # the cadence word beside the price: 79's request requires the interval too
    d["answers"]["packages"]["value"][0]["native_product_id"] = "prod_1"
    record, _ = om.answers_to_record(d, **IDENT)
    plan = om.record_to_plan(record)
    premium = next(o for o in plan["offers_in_order"] if o["display_name"] == "Premium")
    assert premium["exclusions"] == ["No refunds after week 2"] and premium["prices"][0]["billing_type"] == "recurring"
    assert plan["comparison_matrix"]["exclusions"][0]["exclusion"] == "No refunds after week 2"
    assert next(o for o in plan["offers_in_order"] if o["display_name"] == "Starter")["native_product_id"] == "prod_1"
    req = om.record_to_checkout_request(record, "MAIN-2", checkout_mode="combined_single_offer", **CONTEXT)
    assert req["main_price"]["billing_type"] == "recurring"
    assert req["main_price"]["recurring_interval"] == "month"
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


def test_the_entrys_own_cadence_word_is_the_billing_fact():
    """the client states how each offer bills beside the offer's own answer."""
    d = doc("answers.elevation.json")
    d["answers"]["upsell_1"]["value"]["billing"] = "monthly"
    d["answers"]["downsell_1"]["value"]["billing"] = "quarterly"
    record, flagged = om.answers_to_record(d, **IDENT)
    said = {f["field"] for f in flagged}
    assert "billing:upsell_1" not in said and "billing:downsell_1" not in said
    u1 = next(o for o in record["offers"] if o["slot"] == "upsell_1")["prices"][0]
    d1 = next(o for o in record["offers"] if o["slot"] == "downsell_1")["prices"][0]
    assert (u1["billing_type"], u1["recurring_interval"]) == ("recurring", "month")
    assert (d1["billing_type"], d1["recurring_interval"]) == ("recurring", "quarter")
    assert vlp.validate_launch(record) == []


def test_the_recurring_record_reaches_the_79_request_with_its_interval():
    d = doc("answers.elevation.json")
    d["answers"]["upsell_1"]["value"]["billing"] = "monthly"
    record, _ = om.answers_to_record(d, **IDENT)
    u1 = next(o for o in record["offers"] if o["slot"] == "upsell_1")
    req = om.record_to_checkout_request(record, u1["offer_id"], checkout_mode="combined_single_offer", **CONTEXT)
    assert (req["main_price"]["billing_type"], req["main_price"]["recurring_interval"]) == ("recurring", "month")


def test_an_intervalless_recurring_price_cannot_reach_a_request():
    d = doc("answers.elevation.json")
    p = d["answers"]["packages"]["value"][0]["price"]
    p["billing_type"] = "recurring"  # stated with no cadence word or interval anywhere
    record, _ = om.answers_to_record(d, **IDENT)
    main_id = next(o["offer_id"] for o in record["offers"] if o["prices"][0]["billing_type"] == "recurring")
    with pytest.raises(om.MapperError) as e:
        om.record_to_checkout_request(record, main_id, checkout_mode="combined_single_offer",
                                      **dict(CONTEXT, approved_plan_hash="p" * 64))
    assert e.value.code == "AF-CHECKOUT-BILLING"
    assert "recurring_interval" in e.value.detail


def test_a_cadence_word_the_release_does_not_carry_is_refused_not_flattened():
    d = doc("answers.elevation.json")
    d["answers"]["upsell_1"]["value"]["billing"] = "every other month"
    with pytest.raises(om.MapperError) as e:
        om.answers_to_record(d, **IDENT)
    assert e.value.code == "AF-OFFER-BILLING"
    assert "not one this release carries" in e.value.detail


def test_a_stated_global_cadence_word_the_release_does_not_carry_is_refused_not_flattened():
    """Devil's Advocate WORST-1: the global billing answer is stated too — the same refusal,
    so Skill 83's resolve_offer (which drops to_confirm) can never silently charge one payment."""
    d = doc("answers.elevation.json")
    d["answers"]["billing"] = {"value": "every other month", "status": "provided", "source": "client"}
    for caller in (om.answers_to_offers, om.resolve_offer):
        with pytest.raises(om.MapperError) as e:
            if caller is om.answers_to_offers:
                caller(d, test_only=True)
            else:
                caller(d, "answers-file:packages[0]", slot="main", display_name="Essential",
                       amount_minor=4900, currency="USD", test_only=True)
        assert e.value.code == "AF-OFFER-BILLING"


def test_a_trial_price_cannot_reach_a_request():
    """Devil's Advocate WORST-2: trial is plan-time-refused by the family, so the request
    builder never dresses it up as trial_then_recurring for a consumer that skipped the plan."""
    d = doc("answers.elevation.json")
    p = d["answers"]["packages"]["value"][0]["price"]
    p["billing_type"] = "trial"
    p["recurring_interval"] = "month"
    record, _ = om.answers_to_record(d, **IDENT)
    main_id = next(o["offer_id"] for o in record["offers"] if o["slot"] == "main")
    with pytest.raises(om.MapperError) as e:
        om.record_to_checkout_request(record, main_id, checkout_mode="combined_single_offer", **CONTEXT)
    assert e.value.code == "AF-CHECKOUT-BILLING"
    assert "payment plans are not supported in this release" in e.value.detail


def test_recurrence_terms_never_ride_a_non_recurring_price():
    d = doc("answers.elevation.json")
    d["answers"]["packages"]["value"][0]["price"]["billing_type"] = "one_time"
    d["answers"]["packages"]["value"][0]["price"]["recurring_interval"] = "month"
    with pytest.raises(om.MapperError) as e:
        om.answers_to_record(d, **IDENT)
    assert e.value.code == "AF-OFFER-BILLING"


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


# ------------------------------------------------ recurring offers end to end: weekly, monthly, quarterly, yearly
CADENCES = [("weekly", "week"), ("monthly", "month"), ("quarterly", "quarter"), ("yearly", "year"),
            ("every year", "year"), ("every three months", "quarter")]


def _launch_context():
    return _load("s71_launch_context_for_recurring", _skill("71-blackceo-signature-page") / "scripts" / "launch_context.py")


@pytest.mark.parametrize("word,interval", CADENCES)
def test_each_cadence_reaches_the_record_the_schema_and_the_79_request(word, interval):
    d = doc("answers.elevation.json")
    d["answers"]["upsell_1"]["value"]["billing"] = word
    record, _ = om.answers_to_record(d, **IDENT)
    u1 = next(o for o in record["offers"] if o["slot"] == "upsell_1")
    assert (u1["prices"][0]["billing_type"], u1["prices"][0]["recurring_interval"]) == ("recurring", interval)
    assert vlp.validate_launch(record) == []
    lc = _launch_context()
    schema = json.loads((_skill("71-blackceo-signature-page") / "references" / "launch.schema.json").read_text())
    assert lc.validate(record, schema, label="launch") == []  # the record schema carries recurring_interval
    req = om.record_to_checkout_request(record, u1["offer_id"], checkout_mode="combined_single_offer", **CONTEXT)
    vco.validate_request(req)
    assert (req["main_price"]["billing_type"], req["main_price"]["recurring_interval"]) == ("recurring", interval)


def test_a_one_payment_offer_next_to_a_monthly_one_stays_one_payment():
    d = doc("answers.elevation.json")
    d["answers"]["upsell_1"]["value"]["billing"] = "monthly"
    d["answers"]["downsell_1"]["value"]["billing"] = "all at once"
    record, _ = om.answers_to_record(d, **IDENT)
    d1 = next(o for o in record["offers"] if o["slot"] == "downsell_1")["prices"][0]
    assert d1["billing_type"] == "one_time" and "recurring_interval" not in d1


def test_a_stored_interval_outside_the_four_is_refused():
    d = doc("answers.elevation.json")
    p = d["answers"]["upsell_1"]["value"]["price"]
    p.update(billing_type="recurring", recurring_interval="fortnight")
    with pytest.raises(om.MapperError) as e:
        om.answers_to_record(d, **IDENT)
    assert e.value.code == "AF-OFFER-BILLING" and "fortnight" in e.value.detail


def test_the_schema_refuses_an_interval_on_a_price_that_is_not_recurring_and_a_cadenceless_recurring_price():
    offer_schema = json.loads((REPO / "shared-utils" / "signature_launch" / "domain" / "offer.schema.json").read_text())
    jsonschema = pytest.importorskip("jsonschema")
    price_schema = offer_schema["properties"]["prices"]["items"]
    base = {"price_choice_id": "X-USD", "currency": "USD", "amount_minor": 4900, "native_price_id": None,
            "schedule": [], "approval_status": "provided"}
    ok = dict(base, billing_type="recurring", recurring_interval="month")
    jsonschema.validate(ok, price_schema)
    for bad in (dict(base, billing_type="recurring"),                                # no cadence at all
                dict(base, billing_type="one_time", recurring_interval="month"),    # recurrence on one payment
                dict(base, billing_type="recurring", recurring_interval="fortnight")):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, price_schema)


def test_the_four_schema_copies_stay_byte_identical():
    ref = (REPO / "49-signature-funnel" / "schema" / "launch.schema.json").read_bytes()
    for copy_ in ((REPO / "shared-utils" / "signature_launch" / "domain" / "launch.schema.json"),
                  (REPO / "71-blackceo-signature-page" / "references" / "launch.schema.json")):
        assert copy_.read_bytes() == ref


def test_a_record_that_turns_a_one_payment_answer_into_a_subscription_fails_provenance():
    d = doc("answers.elevation.json")
    record, _ = om.answers_to_record(d, **IDENT)
    om.verify_provenance(d, record["offers"])
    forged = copy.deepcopy(record)
    forged["offers"][0]["prices"][0].update(billing_type="recurring", recurring_interval="month")
    with pytest.raises(om.MapperError) as e:
        om.verify_provenance(d, forged["offers"])
    assert e.value.code == "AF-OFFER-PROVENANCE"
