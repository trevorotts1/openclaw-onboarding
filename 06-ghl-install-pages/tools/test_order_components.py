"""CHK-22 / S06-13 / UPS-28 proofs for the W8 commerce stack.

    python3 -m pytest 06-ghl-install-pages/tools/test_order_components.py -q
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))

import order_components as oc  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


BINDING = REPO / "80-signature-upsell" / "components" / "binding"
SHIMS = {
    "06-ghl-delivery": ("skills/06-ghl-delivery/order_components.py", "PriceRef"),
    "79-checkout": ("skills/79-checkout/order_bumps.py", "PriceRef"),
    "80-upsell": ("skills/80-upsell/native_upsell.py", "UpsellContractError"),
}

# --- CHK-22: card-data guard -------------------------------------------------


def test_company_name_is_allowed():
    oc.assert_no_card_data({"company_name": "Acme", "japan": "x", "span": 1})


@pytest.mark.parametrize("payload", [
    {"items": [{"cardnumber": "x"}]},
    {"cardNumber": "x"},
    {"billing": {"card_number": "x"}},
    {"pan": "x"},
    {"cvv": "123"},
    {"note": "my card 4111 1111 1111 1111"},
    {"items": ["4111-1111-1111-1111"]},
    {"a": [[{"memo": "4111111111111111"}]]},
])
def test_card_data_refused(payload):
    with pytest.raises(oc.CardDataRefused):
        oc.assert_no_card_data(payload)


def test_non_luhn_digit_run_allowed():
    oc.assert_no_card_data({"note": "order 4111111111111112"})


# --- S06-13: modules live under numbered skills, old paths re-export ---------


@pytest.mark.parametrize("old", sorted(SHIMS))
def test_old_path_is_thin_reexport(old):
    rel, name = SHIMS[old]
    path = REPO / rel
    assert path.is_file(), "old path must still exist (no file deleted)"
    assert len(path.read_text().splitlines()) < 40
    shim = _load("shim_" + old.replace("-", "_"), path)
    assert hasattr(shim, name)
    done = subprocess.run([sys.executable, "-I", str(path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_shim_is_the_real_guard():
    shim = _load("shim_order_components", REPO / SHIMS["06-ghl-delivery"][0])
    shim.assert_no_card_data({"company_name": "Acme"})
    with pytest.raises(shim.CardDataRefused):
        shim.assert_no_card_data({"items": [{"cardnumber": "x"}]})


def test_fresh_install_tree_runs_every_module(tmp_path):
    aliases = _load("discovery_aliases", REPO / "shared-utils" / "skills" / "discovery_aliases.py")
    skip = shutil.ignore_patterns("__pycache__", "tests", "fixtures", "*.pyc")
    shutil.copy(TOOLS / "browser_manager.sh", tmp_path / "bm.sh")  # existence only
    for sid, rel in [("06-ghl-install-pages", "tools"), ("79-signature-order-form", "scripts"),
                     ("80-signature-upsell", "components")]:
        shutil.copytree(REPO / sid / rel, tmp_path / sid / rel, ignore=skip)
    for mod in aliases.COMMERCE_MODULES:
        path = aliases.commerce_module_path(mod, tmp_path)
        assert path is not None, mod + " missing from the install tree"
        done = subprocess.run([sys.executable, "-I", str(path)], capture_output=True, text=True)
        assert done.returncode == 0, mod + ": " + done.stdout + done.stderr


# --- S06-13: the driver against a recorded browser_manager.sh transcript -----

RECORDED_FLOW = json.loads('''[
 [{"frame_id": "frame_1", "op": "list_components", "tab_id": "tab_1"}, {"ok": true, "result": [{"component_id": "chk_real_1", "kind": "checkout"}, {"component_id": "form_real_9", "kind": "order_form"}]}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "set_state", "patch": {"main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}}, "tab_id": "tab_1"}, {"ok": true, "result": null}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 4900}}}],
 [{"frame_id": "frame_1", "op": "list_components", "tab_id": "tab_1"}, {"ok": true, "result": [{"component_id": "chk_real_1", "kind": "checkout"}, {"component_id": "form_real_9", "kind": "order_form"}]}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 4900}}}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 4900}}}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "set_state", "patch": {"bumps": [{"benefit_explanation": "Because reasons", "disclosure_text": null, "headline": "Headline", "offer_id": "offer_a", "price": {"amount_minor": 900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_2", "native_product_id": "prod_2", "recurring_interval": null, "trial_days": null}, "selected": false}]}, "tab_id": "tab_1"}, {"ok": true, "result": null}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [{"benefit_explanation": "Because reasons", "disclosure_text": null, "headline": "Headline", "offer_id": "offer_a", "price": {"amount_minor": 900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_2", "native_product_id": "prod_2", "recurring_interval": null, "trial_days": null}, "selected": false}], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 4900}}}],
 [{"frame_id": "frame_1", "op": "list_components", "tab_id": "tab_1"}, {"ok": true, "result": [{"component_id": "chk_real_1", "kind": "checkout"}, {"component_id": "form_real_9", "kind": "order_form"}]}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [{"benefit_explanation": "Because reasons", "disclosure_text": null, "headline": "Headline", "offer_id": "offer_a", "price": {"amount_minor": 900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_2", "native_product_id": "prod_2", "recurring_interval": null, "trial_days": null}, "selected": false}], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 4900}}}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "set_state", "patch": {"bumps": [{"benefit_explanation": "Because reasons", "disclosure_text": null, "headline": "Headline", "offer_id": "offer_a", "price": {"amount_minor": 900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_2", "native_product_id": "prod_2", "recurring_interval": null, "trial_days": null}, "selected": true}]}, "tab_id": "tab_1"}, {"ok": true, "result": null}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [{"benefit_explanation": "Because reasons", "disclosure_text": null, "headline": "Headline", "offer_id": "offer_a", "price": {"amount_minor": 900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_2", "native_product_id": "prod_2", "recurring_interval": null, "trial_days": null}, "selected": true}], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 5800}}}],
 [{"frame_id": "frame_1", "op": "list_components", "tab_id": "tab_1"}, {"ok": true, "result": [{"component_id": "chk_real_1", "kind": "checkout"}, {"component_id": "form_real_9", "kind": "order_form"}]}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [{"benefit_explanation": "Because reasons", "disclosure_text": null, "headline": "Headline", "offer_id": "offer_a", "price": {"amount_minor": 900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_2", "native_product_id": "prod_2", "recurring_interval": null, "trial_days": null}, "selected": true}], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 5800}}}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [{"benefit_explanation": "Because reasons", "disclosure_text": null, "headline": "Headline", "offer_id": "offer_a", "price": {"amount_minor": 900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_2", "native_product_id": "prod_2", "recurring_interval": null, "trial_days": null}, "selected": true}], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 5800}}}]
]''')


def test_driver_replays_recorded_flow():
    replay = oc._ReplayRunner(RECORDED_FLOW)
    ex = oc.OrderComponentExecutor(
        oc.BrowserManagerDriver(replay), oc.FrameScope("tab_1", "frame_1"),
        oc.ComponentFamily("checkout_v2", 2, False))
    assert ex.bind_main_price("chk_real_1", oc._price()).state == "bound-verified"
    bump = oc.BumpAttach("offer_a", "Headline", "Because reasons", oc._price("prod_2", "price_2", 900))
    assert ex.attach_bump("chk_real_1", bump).state == "bound-verified"
    assert ex.set_bump_selected("chk_real_1", "offer_a", True).state == "bound-verified"
    assert ex.read_native_totals("chk_real_1")["total_minor"] == 5800
    assert replay.calls == len(RECORDED_FLOW)
    assert all(op.readback == "verified" for op in ex.ops)


def test_driver_departure_from_recording_fails():
    ex = oc.OrderComponentExecutor(
        oc.BrowserManagerDriver(oc._ReplayRunner(RECORDED_FLOW)), oc.FrameScope("tab_9", "frame_1"),
        oc.ComponentFamily("checkout_v2", 2, False))
    with pytest.raises(AssertionError):
        ex.resolve_component("chk_real_1")


def _manager(tmp_path, body):
    script = tmp_path / "browser_manager.sh"
    script.write_text("#!/usr/bin/env bash\n" + body)
    return script


def test_default_runner_goes_through_browser_manager_eval(tmp_path):
    reply = json.dumps(json.dumps({"ok": True, "result": []}))  # agent-browser quotes it
    script = _manager(tmp_path, '[ "$1" = eval ] && [ "$2" = -- ] || exit 64\n'
                                "printf '%s\\n' '" + reply + "'\n")
    drv = oc.BrowserManagerDriver(oc._manager_runner(script))
    assert drv.list_components(oc.FrameScope("t", "f")) == ()


def test_manager_failure_is_raised_without_leaking_stderr(tmp_path):
    script = _manager(tmp_path, "echo SECRET-DETAIL >&2\nexit 75\n")
    drv = oc.BrowserManagerDriver(oc._manager_runner(script))
    with pytest.raises(oc.OrderComponentError) as err:
        drv.list_components(oc.FrameScope("t", "f"))
    assert "75" in str(err.value) and "SECRET-DETAIL" not in str(err.value)


# --- UPS-28: one extra-offer vocabulary across both libraries ----------------


@pytest.fixture(scope="module")
def libs():
    sys.path.insert(0, str(BINDING.parent / "adapters"))
    sys.path.insert(0, str(BINDING))
    import adapter_common
    import extra_offer_binding
    nu = _load("native_upsell_under_test", BINDING / "native_upsell.py")
    return adapter_common, extra_offer_binding, nu


def test_both_libraries_expose_the_same_sets(libs):
    ac, eob, nu = libs
    schema = json.loads(Path(ac.REQUEST_SCHEMA_PATH).read_text())
    enum = frozenset(schema["properties"]["disclosure"]["properties"]["billing_type"]["enum"])
    assert enum == {"one_time", "recurring", "installment", "trial"}
    assert eob.BILLING_TYPES == nu.BILLING_TYPES == enum
    assert eob.ENTRY_CONTEXTS == nu.ENTRY_CONTEXTS
    assert eob.PURCHASE_STATES == nu.PURCHASE_STATES
    assert eob.TRANSITIONS == nu.TRANSITIONS
    assert eob.VERIFIED_SOURCES == nu.VERIFIED_PURCHASE_SOURCES == ac.ADAPTER_VERIFICATION_SOURCES
    assert eob.FALLBACK_STANDARD_CHECKOUT == nu.FALLBACK_STANDARD_CHECKOUT


_TERMS = {"interval": "month", "interval_count": 1, "cycles": 3}
_BINDING_KW = dict(
    tenant_ref="tenant:T", location_ref="location:L", launch_ref="launch:T/r1",
    launch_revision="rev:T-R1", parent_order_ref="native:P",
    parent_verification_source="native_purchase_ledger", offer_id="O1",
    native_product_ref="native:PRD", native_price_ref="native:PRC",
    capability_evidence_ref="native:CAP", amount_minor=6700, currency="USD",
    success_route_ref="route:s", decline_route_ref="route:d", error_route_ref="route:e",
    disclosure_terms_ref="catalog:D", copy_refs=("request:R/copy",))
_UPSELL_KW = {k: v for k, v in _BINDING_KW.items() if k not in ("error_route_ref", "copy_refs")}
_UPSELL_KW.update(role="upsell_1", failure_route_ref="route:f", confirmation_route_ref="route:c",
                  checkout_family="v2_funnel", processor_ref="processor-1",
                  payment_mode="saved_card_one_click", domain_ref="buy.example.com")


@pytest.mark.parametrize("billing", ["installment", "trial", "recurring"])
def test_installment_and_trial_pass_both_and_need_terms(libs, billing):
    _, eob, nu = libs
    eob.BindingContext(**_BINDING_KW, billing_type=billing, recurring_terms=_TERMS)
    nu.PurchaseContext(**_UPSELL_KW, billing_type=billing, recurring_terms=_TERMS)
    with pytest.raises(eob.BindingError):
        eob.BindingContext(**_BINDING_KW, billing_type=billing)
    with pytest.raises(nu.UpsellContractError):
        nu.PurchaseContext(**_UPSELL_KW, billing_type=billing)


def test_unknown_billing_refused_by_both(libs):
    _, eob, nu = libs
    with pytest.raises(eob.BindingError):
        eob.BindingContext(**_BINDING_KW, billing_type="weekly")
    with pytest.raises(nu.UpsellContractError):
        nu.PurchaseContext(**_UPSELL_KW, billing_type="weekly")
