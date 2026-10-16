"""S06-06 - native builder/order-element integration (fixture/offline only).

Covers the four S06-06 build surfaces:

  * SEO cap reconciliation (prep step 1, Q1 disposition): 155 is the
    operative SAVE-TIME description cap on BOTH splice paths
    (ghl_builder.build_seo_meta and ghl_rest_canvas.build_seo_meta); 160
    survives only as ghl_rest_canvas's DISPLAY-truncation constant and
    never authorizes a longer description. The 156-160 band is pinned on
    each side.
  * Step-type SEO/privacy policy (prep step 6, gap 5): marketing steps keep
    the full SEO gates; purchase/thank-you steps get a privacy meta with an
    explicit noindex directive and are scored against the privacy policy,
    never the marketing gates.
  * Order-element plan layer (prep steps 4-5, gaps 1-4): ghl_order_elements
    plans native Payments tiles + bump/upsell/downsell with caller-supplied
    product bindings, fails closed without them, refuses a pre-checked
    bump, and verifies rendered evidence (selected-product match, bump
    UNCHECKED).
  * ID-handoff record (prep step 3, gap 6): ghl_id_handoff assembles the
    five ID-surfacing mechanisms into one per-run record with provenance,
    carries the pipeline as an honest name binding (id None), and derives
    IDs from the F6 receipts store only.
  * Form-builder Payments carve-out (gap 3): _resolve_fields stamps
    Payments tiles as order elements, preflight F-P10 fails closed without
    task["order_binding"], and the F5 placement guard refuses to drag an
    unbound Payments tile.

No network, no browser, no live GHL - pure fixture tests with generic fake
values only.
"""
from __future__ import annotations

import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_builder as gb
import ghl_form_builder as fb
import ghl_id_handoff as ih
import ghl_order_elements as oe
import ghl_receipts as receipts
import ghl_rest_canvas as rc

FOUNDER = "Jordan Rivera"
CANON = "https://funnel.example.com/optin"
CANON_HOSTS = ("funnel.example.com",)
GCS_IMG = "https://storage.googleapis.com/msgsndr/loc123/media/hero.png"
KEYWORDS = ["alpha keyword", "beta keyword", "gamma keyword"]


def _canvas_meta(description: str) -> dict:
    return rc.build_seo_meta(
        title="A Perfectly Fine Title", description=description,
        keywords=KEYWORDS, founder_name=FOUNDER, canonical_url=CANON,
        og_image=GCS_IMG)


def _builder_meta(description: str) -> dict:
    return gb.build_seo_meta(
        title="A Perfectly Fine Title", description=description,
        keywords=KEYWORDS, founder_name=FOUNDER, canonical_url=CANON,
        og_image=GCS_IMG)


# ── SEO cap reconciliation: the 156-160 band, pinned on BOTH paths ──────────

class TestSeoCapReconciliation:
    def test_the_two_numbers_and_their_roles(self):
        # 155 is the save-time cap on both modules; 160 is display-only.
        assert gb.SEO_DESC_MAX == 155
        assert rc.SEO_DESCRIPTION_SAVE_MAX == 155
        assert rc.SEO_DESCRIPTION_SAVE_MAX == gb.SEO_DESC_MAX
        assert rc.SEO_DESCRIPTION_MAX == 160  # display-truncation ONLY

    def test_canvas_accepts_155(self):
        meta = _canvas_meta("d" * 155)
        assert len(meta["description"]) == 155

    @pytest.mark.parametrize("n", [156, 158, 160, 161])
    def test_canvas_refuses_the_band_and_beyond(self, n):
        with pytest.raises(ValueError, match="description"):
            _canvas_meta("d" * n)

    def test_builder_accepts_155(self):
        meta = _builder_meta("d" * 155)
        assert len(meta["description"]) == 155

    @pytest.mark.parametrize("n", [156, 158, 160, 161])
    def test_builder_refuses_the_band_and_beyond(self, n):
        with pytest.raises(gb.SeoValidationError):
            _builder_meta("d" * n)

    def test_canvas_validate_seo_meta_enforces_save_cap(self):
        meta = _canvas_meta("d" * 155)
        meta["description"] = "d" * 157  # drifted past the save cap
        with pytest.raises(ValueError, match="description"):
            rc.validate_seo_meta(meta, founder_name=FOUNDER,
                                 canonical_hosts=CANON_HOSTS)

    def test_autosave_verify_string_names_the_save_cap(self):
        blob = {"sections": [{"elements": []}], "settings": {}}
        step = rc.page_seo_autosave(
            "PAGEID0000000000fake", blob, _canvas_meta("d" * 120),
            funnel_id="FUNNELID000000000fake", page_version=1,
            founder_name=FOUNDER, canonical_hosts=CANON_HOSTS)
        assert "description<=155" in step["expect"]["verify_seo"]
        assert "description<=160" not in step["expect"]["verify_seo"]


# ── Step-type SEO/privacy policy ─────────────────────────────────────────────

class TestStepTypePolicy:
    @pytest.mark.parametrize("step,expected", [
        ("Signature Sales Page", "marketing"),
        ("webinar registration", "marketing"),
        ("checkout", "purchase"),
        ("Order Form", "purchase"),
        ("upsell", "purchase"),
        ("downsell", "purchase"),
        ("thank-you", "thank_you"),
        ("Order Confirmation", "thank_you"),
        ("receipt page", "thank_you"),
    ])
    def test_classification_from_names(self, step, expected):
        assert gb.classify_step_type(step)["step_type"] == expected

    def test_declared_type_wins_over_name(self):
        out = gb.classify_step_type({"step_type": "purchase", "name": "Sales"})
        assert out == {"step_type": "purchase", "basis": "explicit"}

    def test_unrecognized_step_defaults_to_marketing(self):
        out = gb.classify_step_type("some custom step")
        assert out == {"step_type": "marketing", "basis": "default"}

    def test_marketing_step_keeps_full_gates(self):
        meta = gb.build_step_seo_meta(
            "sales page", title="T", description="d" * 100,
            keywords=KEYWORDS, founder_name=FOUNDER, canonical_url=CANON,
            og_image=GCS_IMG)
        assert meta["author"] == FOUNDER
        assert "robots" not in meta
        # The marketing gates still HALT: no founder, no meta.
        with pytest.raises(gb.SeoValidationError):
            gb.build_step_seo_meta(
                "sales page", title="T", description="d" * 100,
                keywords=KEYWORDS, founder_name="", canonical_url=CANON,
                og_image=GCS_IMG)

    def test_purchase_step_gets_privacy_meta_without_marketing_inputs(self):
        meta = gb.build_step_seo_meta("checkout", title="Secure Checkout")
        assert meta["robots"] == gb.NOINDEX_ROBOTS
        assert meta["keywords"] == [] and meta["author"] == ""
        assert meta["canonicalUrl"] == "" and meta["ogImage"] == ""

    def test_private_step_description_still_save_capped(self):
        with pytest.raises(gb.SeoValidationError):
            gb.build_step_seo_meta("thank_you", title="Thank You",
                                   description="d" * 156)
        meta = gb.build_step_seo_meta("thank_you", title="Thank You",
                                      description="d" * 155)
        assert len(meta["description"]) == 155

    def test_assert_step_gate_scores_private_steps_on_privacy(self):
        meta = gb.build_private_step_seo_meta(title="Secure Checkout")
        assert gb.assert_step_seo_populated(meta, "checkout")["ok"]
        no_robots = dict(meta)
        del no_robots["robots"]
        verdict = gb.assert_step_seo_populated(no_robots, "checkout")
        assert not verdict["ok"]
        assert any("noindex" in r for r in verdict["reasons"])

    def test_assert_step_gate_scores_marketing_steps_on_full_seo(self):
        verdict = gb.assert_step_seo_populated({}, "sales page")
        assert not verdict["ok"] and verdict["step_type"] == "marketing"
        meta = gb.build_step_seo_meta(
            "sales page", title="T", description="d" * 100,
            keywords=KEYWORDS, founder_name=FOUNDER, canonical_url=CANON,
            og_image=GCS_IMG)
        assert gb.assert_step_seo_populated(meta, "sales page")["ok"]

    def test_unknown_policy_type_refused(self):
        with pytest.raises(gb.SeoValidationError):
            gb.seo_policy_for_step("mystery")
        assert gb.seo_policy_for_step("purchase")["seo_required"] is False
        assert gb.seo_policy_for_step("marketing")["seo_required"] is True


# ── Order-element plan layer ─────────────────────────────────────────────────

FULL_SPEC = {
    "location_id": "LOC_TEST",
    "form_name": "Signature Order Form",
    "order_form": {"product": {"product_ref": "prod_main_offer",
                               "source": "caller_supplied"}},
    "collect_payment": True,
    "bump": {"product": {"product_ref": "prod_bump_offer",
                         "source": "caller_supplied"}},
    "upsell": {"product": {"native_product_ref": "prod_upsell",
                           "source": "s44_phase_a"}},
    "downsell": {"product": {"product_ref": "prod_downsell",
                             "source": "caller_supplied"}},
}

GOOD_RENDER = {
    "order_tile_present": True, "payment_tile_present": True,
    "selected_product_ref": "prod_main_offer",
    "bump_present": True, "bump_checked": False,
    "upsell_selected_product_ref": "prod_upsell",
    "downsell_selected_product_ref": "prod_downsell",
}


class TestOrderPlan:
    def test_full_plan_shape(self):
        plan = oe.build_order_plan(FULL_SPEC)
        assert plan["schema"] == "skill6-order-plan/1"
        kinds = [e["kind"] for e in plan["elements"]]
        assert kinds == ["order_form", "collect_payment", "order_bump",
                         "upsell", "downsell"]
        tiles = {e["kind"]: e.get("tile") for e in plan["elements"]}
        assert tiles["order_form"] == "Sell Products"
        assert tiles["collect_payment"] == "Collect Payment"
        assert oe.PAYMENTS_TILES == ("Sell Products", "Collect Payment")
        assert oe.is_payments_tile("Sell Products")
        assert not oe.is_payments_tile("First Name")

    def test_bump_default_is_unchecked(self):
        plan = oe.build_order_plan(FULL_SPEC)
        bump = next(e for e in plan["elements"] if e["kind"] == "order_bump")
        assert bump["default_checked"] is False
        assert oe.BUMP_DEFAULT_CHECKED is False

    def test_native_product_ref_key_carried_verbatim(self):
        plan = oe.build_order_plan(FULL_SPEC)
        upsell = next(e for e in plan["elements"] if e["kind"] == "upsell")
        assert upsell["binding"] == {"product_ref": "prod_upsell",
                                     "binding_source": "s44_phase_a"}

    def test_plan_carries_no_price(self):
        plan = oe.build_order_plan(FULL_SPEC)
        for element in plan["elements"]:
            assert "price" not in element["binding"]

    def test_form_task_patch(self):
        plan = oe.build_order_plan(FULL_SPEC)
        assert oe.form_task_patch(plan) == {
            "order_binding": {"product_ref": "prod_main_offer",
                              "source": "caller_supplied"}}

    @pytest.mark.parametrize("spec", [
        {},                                                     # no location
        {"location_id": "L"},                                   # no order_form
        {"location_id": "L", "order_form": {}},                 # unbound
        {"location_id": "L", "order_form": {"product": {"source": "caller_supplied"}}},
        {"location_id": "L", "order_form": {"product": {"product_ref": "p",
                                                        "source": "guessed"}}},
        {"location_id": "L",
         "order_form": {"product": {"product_ref": "p", "source": "caller_supplied"}},
         "bump": {"product": {"product_ref": "b", "source": "caller_supplied"},
                  "default_checked": True}},                   # pre-checked bump
        {"location_id": "L",
         "order_form": {"product": {"product_ref": "p", "source": "caller_supplied"}},
         "upsell": {"product": {"product_ref": "u", "source": "caller_supplied"},
                    "one_click": False}},
        {"location_id": "L",
         "order_form": {"product": {"product_ref": "p", "source": "caller_supplied"}},
         "bump": {}},                                           # bumpless binding
    ])
    def test_fail_closed_specs(self, spec):
        with pytest.raises(oe.OrderPlanError):
            oe.build_order_plan(spec)

    def test_module_selftest(self):
        assert oe._selftest() == 0


class TestOrderRenderVerification:
    def test_good_render_passes(self):
        verdict = oe.verify_order_render(oe.build_order_plan(FULL_SPEC),
                                         GOOD_RENDER)
        assert verdict["ok"], verdict["reasons"]

    @pytest.mark.parametrize("patch", [
        {"selected_product_ref": "prod_OTHER"},   # wrong product bound
        {"selected_product_ref": None},           # no product read back
        {"bump_checked": True},                   # bump pre-checked
        {"bump_checked": None},                   # bump state unobserved
        {"bump_present": False},                  # bump missing
        {"order_tile_present": False},            # order tile missing
        {"payment_tile_present": False},          # payment tile missing
        {"upsell_selected_product_ref": "prod_X"},
        {"downsell_selected_product_ref": "prod_X"},
    ])
    def test_bad_renders_fail(self, patch):
        rendered = dict(GOOD_RENDER)
        rendered.update(patch)
        verdict = oe.verify_order_render(oe.build_order_plan(FULL_SPEC),
                                         rendered)
        assert not verdict["ok"]


# ── ID-handoff record ────────────────────────────────────────────────────────

class TestIdHandoff:
    def test_schema_is_distinct_from_the_routing_record(self):
        assert ih.SCHEMA_ID == "skill6-id-handoff/1"
        assert ih.SCHEMA_ID != "skill6-method-decision/1"
        assert ih.handoff_path("/run/x").endswith(
            os.path.join("routing", "id-handoff.json"))

    def test_record_all_mechanisms(self):
        h = ih.new_handoff(run_id="r1", location_ref="LOC")
        ih.record_funnel(h, "FUNNEL123")
        ih.record_page(h, "optin", "PAGE123")
        ih.record_form(h, "cuPqQhLbk0GKeguEbGYW")
        ih.record_workflow(
            h, "https://app.gohighlevel.com/v2/location/L/workflows/WF9x8y7z")
        objs = h["objects"]
        assert objs["funnel"]["source"] == "funnel_create_response"
        assert objs["pages"][0]["source"] == "create_step_response"
        assert objs["form"]["source"] == "form_builder_iframe_src"
        assert objs["workflow"]["id"] == "WF9x8y7z"
        assert "workflow" not in h["missing"]

    def test_pipeline_is_an_honest_name_binding(self):
        h = ih.new_handoff()
        ih.record_pipeline_by_name(h, "ZHC Sales Pipeline")
        entry = h["objects"]["pipeline"]
        assert entry["id"] is None and entry["bound_by"] == "name"

    @pytest.mark.parametrize("fn", [
        lambda h: ih.record_funnel(h, ""),
        lambda h: ih.record_form(h, "not a form id!!"),
        lambda h: ih.record_workflow(h, "https://x.example/nope"),
        lambda h: ih.record_product(h, "p1", "invented_source"),
        lambda h: ih.record_order_element(h, "Sell Products", "",
                                          "caller_supplied"),
    ])
    def test_fail_closed_recording(self, fn):
        with pytest.raises(ih.HandoffError):
            fn(ih.new_handoff())

    def test_write_load_round_trip(self, tmp_path):
        h = ih.new_handoff(run_id="rt", location_ref="LOC")
        ih.record_funnel(h, "FUNNEL123")
        path = ih.write_handoff(str(tmp_path), h)
        assert os.path.isfile(path)
        loaded = ih.load_handoff(str(tmp_path))
        assert loaded["objects"]["funnel"]["id"] == "FUNNEL123"
        assert loaded["schema"] == "skill6-id-handoff/1"

    def test_assembly_from_receipts_only_proves_what_receipts_prove(
            self, tmp_path):
        root = str(tmp_path)
        receipts.write_receipt(root, receipts.make_receipt(
            "funnel", "main", "created", response_id="FUNNEL999",
            verify={"ok": True}))
        receipts.write_receipt(root, receipts.make_receipt(
            "workflow", "followup", "failed",
            response_id="WF_must_not_appear", error="boom"))
        receipts.write_receipt(root, receipts.make_receipt(
            "page", "optin", "created", response_id=None))
        h = ih.assemble_from_receipts(root, run_id="r1")
        assert h["objects"]["funnel"]["id"] == "FUNNEL999"
        assert "workflow" in h["missing"] and "pages" in h["missing"]
        assert ih.verify_against_receipts(h, root)["ok"]
        h["objects"]["funnel"]["id"] = "FUNNEL_fabricated"
        assert not ih.verify_against_receipts(h, root)["ok"]

    def test_module_selftest(self):
        assert ih._selftest() == 0


# ── Form-builder Payments carve-out ──────────────────────────────────────────

def _order_task(**extra):
    task = {"location_id": "LOC1", "form_name": "ZHC Order Form",
            "form_fields": [{"element": "First Name", "label": "First Name"},
                            {"element": "Sell Products",
                             "label": "Sell Products"}]}
    task.update(extra)
    return task


class TestFormBuilderOrderCarveOut:
    def test_payments_tile_is_stamped_as_order_element(self):
        fields = fb._resolve_fields(_order_task())
        tile = next(f for f in fields if f["element"] == "Sell Products")
        assert tile["order_element"] is True
        assert tile["order_product_ref"] is None
        plain = next(f for f in fields if f["element"] == "First Name")
        assert "order_element" not in plain

    def test_preflight_fails_closed_without_binding(self):
        task = _order_task()
        fields = fb._resolve_fields(task)
        dep = fb.plan_dependencies(fields, task)
        pf = fb._run_preflight(task, fields, dep)
        assert pf["pass"] is False
        assert "F-P10" in (pf.get("stop_reason") or "")

    def test_preflight_passes_with_binding(self):
        task = _order_task(order_binding={"product_ref": "prod_main",
                                          "source": "caller_supplied"})
        fields = fb._resolve_fields(task)
        tile = next(f for f in fields if f["element"] == "Sell Products")
        assert tile["order_product_ref"] == "prod_main"
        assert tile["order_binding_source"] == "caller_supplied"
        dep = fb.plan_dependencies(fields, task)
        pf = fb._run_preflight(task, fields, dep)
        f10 = next(c for c in pf["checks"] if c["check"] == "F-P10:order_binding")
        assert f10["pass"] is True

    def test_forms_without_payments_tiles_unaffected(self):
        task = {"location_id": "LOC1", "form_name": "ZHC Plain Form",
                "form_fields": [{"element": "City", "label": "City"}]}
        fields = fb._resolve_fields(task)
        dep = fb.plan_dependencies(fields, task)
        pf = fb._run_preflight(task, fields, dep)
        f10 = next(c for c in pf["checks"] if c["check"] == "F-P10:order_binding")
        assert f10["pass"] is True

    def test_f5_placement_guard_refuses_unbound_payments_tile(self):
        with pytest.raises(fb.StopAndReport) as excinfo:
            fb._place_quick_add_field(
                "s", {"element": "Collect Payment",
                      "label": "Collect Payment"},
                "/tmp", [0], [], [])
        assert excinfo.value.step == "F5.order-binding"
