"""U-checkout-commerce-03 (CHK-19): the order plan targets the funnel
order-form step, attaches the read-back product + price, places the bump, and
verifies the bump's product; render evidence must come from the capture
function. Offline: no network, no browser."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ghl_ecosystem as eco  # noqa: E402
import ghl_form_builder as fb  # noqa: E402
import ghl_method_decision as md  # noqa: E402
import ghl_order_elements as oe  # noqa: E402

SPEC = {
    "location_id": "LOC_TEST",
    "order_form": {"product": {"product_ref": "prod_main",
                               "price_ref": "price_main",
                               "source": "caller_supplied"}},
    "collect_payment": {"product": {"product_ref": "prod_cp",
                                    "source": "caller_supplied"}},
    "bump": {"product": {"product_ref": "prod_bump", "price_ref": "price_bump",
                         "source": "caller_supplied"}},
    "upsell": {"product": {"product_ref": "prod_up", "source": "s44_phase_a"}},
    "downsell": {"product": {"product_ref": "prod_down",
                             "source": "caller_supplied"}},
    "thank_you": True,
}

GOOD = {
    "order_tile_present": True, "payment_tile_present": True,
    "selected_product_ref": "prod_main", "selected_price_ref": "price_main",
    "collect_payment_selected_product_ref": "prod_cp",
    "bump_present": True, "bump_checked": False,
    "bump_selected_product_ref": "prod_bump",
    "bump_selected_price_ref": "price_bump",
    "upsell_selected_product_ref": "prod_up",
    "downsell_selected_product_ref": "prod_down",
    "thank_you_step_present": True,
}


@pytest.fixture
def plan():
    return oe.build_order_plan(SPEC)


def _capture(plan, obs=None, source="fixture"):
    return oe.capture_order_render(plan, lambda _p: dict(obs or GOOD),
                                   source=source)


def test_plan_targets_funnel_order_form_step_not_form_builder_tiles(plan):
    assert plan["surface"] == oe.SURFACE_FUNNEL_ORDER_STEP
    for el in plan["elements"]:
        assert el["placement"]["target"] == oe.SURFACE_FUNNEL_ORDER_STEP
        if "via" in el["placement"]:
            assert el["placement"]["via"].endswith(
                "not a form-builder Payments tile")
            assert "F5" not in el["placement"]["via"]


def test_plan_attaches_product_and_price_and_places_bump(plan):
    main = plan["elements"][0]
    assert main["binding"]["product_ref"] == "prod_main"
    assert main["binding"]["price_ref"] == "price_main"
    bump = next(e for e in plan["elements"] if e["kind"] == "order_bump")
    assert bump["placement"]["after"] == "order_form"
    actions = [s["action"] for s in plan["steps"]]
    assert actions.index("set_order_form_product") < actions.index("add_order_bump")
    assert actions[-1] == "capture_order_render"


def test_thank_you_step_and_accept_decline_links(plan):
    # A plan built without the approved route graph keeps its slot identity
    # but carries NO links: this module never invents a route. It is not
    # install-ready, and every extra element says so.
    assert plan["install_ready"] is False
    assert plan["blockers"]
    by_slot = {e["slot"]: e for e in plan["elements"] if e.get("slot")}
    assert "links" not in by_slot["upsell_1"]
    assert "links" not in by_slot["downsell_1"]
    assert by_slot["thank_you"]["binding"] is None

    graph_plan = oe.build_order_plan(dict(
        SPEC,
        checkout_family=oe.CHECKOUT_FAMILY_ORDER_UPSELL_V2_FUNNEL,
        route_graph=_TEST_GRAPH,
        # the install path binds the price its one-click action charges
        upsell=None,
        upsells=[
            {"slot": "upsell_1",
             "product": {"product_ref": "prod_up", "price_ref": "price_up",
                         "source": "s44_phase_a"}},
            {"slot": "upsell_2",
             "product": {"product_ref": "prod_up2", "price_ref": "price_up2",
                         "source": "caller_supplied"}},
        ],
        downsell={"product": {"product_ref": "prod_down",
                              "price_ref": "price_down",
                              "source": "caller_supplied"}}))
    assert graph_plan["install_ready"] is True and not graph_plan["blockers"]
    by_slot = {e["slot"]: e for e in graph_plan["elements"] if e.get("slot")}
    assert (by_slot["upsell_1"]["links"]["accept"],
            by_slot["upsell_1"]["links"]["decline"]) == ("G-U2", "G-D1")
    assert (by_slot["downsell_1"]["links"]["accept"],
            by_slot["downsell_1"]["links"]["decline"]) == ("G-U2", "G-TY")
    assert by_slot["upsell_2"]["links"]["accept"] == "G-TY"
    assert by_slot["upsell_1"]["links"]["on_payment_failed"]["is_decline"] is False


# TEST-SHAPED route graph for the link assertions above: the same node/edge
# shape Skill 49's compiler emits, with fixture page ids only.
_TEST_GRAPH = {
    "schema_version": "1.0", "tenant_id": "T", "location_id": "LOC_TEST",
    "launch_id": "G", "revision": 1, "test_only": True,
    "nodes": [{"page_id": "G-CHECKOUT", "role": "checkout"},
              {"page_id": "G-U1", "role": "upsell_1"},
              {"page_id": "G-D1", "role": "downsell_1"},
              {"page_id": "G-U2", "role": "upsell_2"},
              {"page_id": "G-TY", "role": "thank_you"}],
    "edges": [
        {"from": "G-CHECKOUT", "event": "payment_succeeded", "to": "G-U1",
         "guard": "verified_main_payment"},
        {"from": "G-U1", "event": "payment_succeeded", "to": "G-U2",
         "guard": "verified_u1_payment"},
        {"from": "G-U1", "event": "explicit_decline", "to": "G-D1",
         "guard": "no_charge_decline"},
        {"from": "G-D1", "event": "payment_succeeded", "to": "G-U2",
         "guard": "verified_d1_payment"},
        {"from": "G-D1", "event": "explicit_decline", "to": "G-TY",
         "guard": "no_charge_decline"},
        {"from": "G-U2", "event": "payment_succeeded", "to": "G-TY",
         "guard": "verified_u2_payment"},
        {"from": "G-U2", "event": "explicit_decline", "to": "G-TY",
         "guard": "no_charge_decline"},
    ],
    "pending_failed_payment_behavior":
        oe.PENDING_BEHAVIOR,
}


def test_per_element_bindings_reach_form_task_patch(plan):
    patch = oe.form_task_patch(plan, per_element=True)
    assert patch["order_element_bindings"]["Collect Payment"]["product_ref"] \
        == "prod_cp"
    assert patch["order_element_bindings"]["Sell Products"]["price_ref"] \
        == "price_main"
    task = {"location_id": "L", "form_name": "F",
            "form_fields": [{"element": "Sell Products", "label": "Sell"},
                            {"element": "Collect Payment", "label": "Pay"}],
            **patch}
    fields = {f["element"]: f for f in fb._resolve_fields(task)}
    assert fields["Collect Payment"]["order_product_ref"] == "prod_cp"
    assert fields["Sell Products"]["order_product_ref"] == "prod_main"
    assert fields["Sell Products"]["order_price_ref"] == "price_main"
    dep = fb.plan_dependencies(list(fields.values()), task)
    pf = fb._run_preflight(task, list(fields.values()), dep)
    assert next(c for c in pf["checks"]
                if c["check"] == "F-P10:order_binding")["pass"]


def test_bump_product_must_match_binding(plan):
    v = oe.verify_order_render(plan, dict(GOOD, bump_selected_product_ref="prod_X"))
    assert not v["ok"]
    assert any(c["check"] == "bump_selected_product_matches_binding"
               and not c["ok"] for c in v["checks"])
    assert oe.verify_order_render(plan, GOOD)["ok"]


def test_price_mismatch_fails(plan):
    assert not oe.verify_order_render(
        plan, dict(GOOD, selected_price_ref="price_other"))["ok"]
    assert not oe.verify_order_render(
        plan, dict(GOOD, bump_selected_price_ref=None))["ok"]


def test_captured_evidence_passes_and_is_marked_fixture(plan):
    v = oe.verify_order_render(plan, _capture(plan), require_capture=True)
    assert v["ok"] and v["attested"] and not v["live_capture"]
    live = oe.verify_order_render(plan, _capture(plan, source="live"),
                                  require_capture=True)
    assert live["live_capture"]


def test_hand_written_evidence_is_refused(plan):
    v = oe.verify_order_render(plan, dict(GOOD), require_capture=True)
    assert not v["ok"] and not v["attested"]
    assert v["checks"][0]["check"] == "evidence_provenance"


def test_tampered_or_foreign_evidence_is_refused(plan):
    ev = _capture(plan)
    edited = dict(ev, observations=dict(ev["observations"], bump_checked=True))
    assert not oe.verify_order_render(plan, edited, require_capture=True)["ok"]
    forged = dict(ev, provenance_hash="0" * 64)
    assert not oe.verify_order_render(plan, forged, require_capture=True)["ok"]
    other = oe.build_order_plan(dict(SPEC, location_id="OTHER"))
    assert not oe.verify_order_render(other, ev, require_capture=True)["ok"]


def test_captured_evidence_requires_bump_product_readback(plan):
    obs = {k: v for k, v in GOOD.items() if k != "bump_selected_product_ref"}
    assert not oe.verify_order_render(plan, _capture(plan, obs))["ok"]


def test_cli_verify_render_refuses_hand_written_file(plan, tmp_path):
    import json
    pp, ep = tmp_path / "plan.json", tmp_path / "ev.json"
    pp.write_text(json.dumps(plan))
    ep.write_text(json.dumps(GOOD))
    assert oe.main(["--verify-render", str(pp), str(ep)]) == 1
    oe.write_evidence(str(ep), _capture(plan))
    assert oe.main(["--verify-render", str(pp), str(ep)]) == 0


def test_capture_needs_a_reader_and_real_observations(plan):
    with pytest.raises(oe.OrderPlanError):
        oe.capture_order_render(plan, None)
    with pytest.raises(oe.OrderPlanError):
        oe.capture_order_render(plan, lambda _p: {})
    with pytest.raises(oe.OrderPlanError):
        oe.capture_order_render(plan, lambda _p: dict(GOOD), source="guess")


def test_blank_price_ref_refused():
    bad = dict(SPEC, order_form={"product": {"product_ref": "p", "price_ref": " ",
                                             "source": "caller_supplied"}})
    with pytest.raises(oe.OrderPlanError):
        oe.build_order_plan(bad)


def test_ecosystem_receipt_becomes_binding():
    rec = {"ok": True, "product_id": "P1", "price_id": "R1",
           "reread_http_status": 200}
    assert eco.order_binding_from_receipt(rec) == {
        "product_ref": "P1", "price_ref": "R1", "source": "s44_phase_a"}
    for bad in ({}, dict(rec, ok=False), dict(rec, price_id=""),
                dict(rec, reread_http_status=None)):
        with pytest.raises(ValueError):
            eco.order_binding_from_receipt(bad)


def test_order_plan_recorded_as_payment_configuration(plan, tmp_path):
    rec = md.record_order_plan(str(tmp_path), plan)
    entry = next(e for e in rec["operations"] if e["id"] == "order:order_bump")
    assert entry["operationClass"] == "payment_configuration"
    assert entry["chosenLane"] == oe.SURFACE_FUNNEL_ORDER_STEP
    assert "payment_configuration" not in md.UNEMITTED_OPERATION_CLASSES
