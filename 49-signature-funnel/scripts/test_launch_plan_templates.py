"""S44-12: every template 49 _automations emits is a Skill 44 buildable key."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import launch_plan  # noqa: E402

assert launch_plan.BUILDABLE_MANIFEST.is_file()
BUILDABLE = launch_plan.buildable_keys()
LAUNCH = {
    "launch_id": "demo-2026-11", "journey_mode": "single_simple",
    "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": False},
    "offers": [
        {"slot": "main", "display_name": "Demo Offer",
         "prices": [{"amount_minor": 49700, "currency": "USD"}]},
        {"slot": "upsell_1", "display_name": "Demo Upgrade",
         "prices": [{"amount_minor": 9900, "currency": "USD"}]},
        {"slot": "downsell_1", "display_name": "Smaller Demo",
         "prices": [{"amount_minor": 4900, "currency": "USD"}]},
    ],
}
ANSWERS = {
    "launch.launch_at": "2026-11-03T12:00:00-05:00",
    "launch.doors_open_at": "2026-11-03T09:00:00-05:00",
    "launch.doors_close_at": "2026-11-10T23:59:00-05:00",
    "launch.timezone": "America/New_York",
    "launch.channels": ["email", "text"],
    "launch.conversation_ai": True, "launch.conversation_ai_mode": "faq",
    "offers.main.payment_plans": True,
    "launch.product_type": "webinar", "launch.event.starts_at": "2026-11-04T19:00:00-05:00",
    "launch.landing_url": "https://example.com/landing",
    "launch.sales_page_url": "https://example.com/sales",
    "launch.checkout_url": "https://example.com/order",
    "launch.thank_you_url": "https://example.com/thanks",
}


def _plan():
    result = launch_plan.build_launch_plan(LAUNCH, ANSWERS)
    assert result["state"] == "ready", result["missing"]
    return result["plan"]


def test_every_family_has_a_template_and_the_plan_emits_all_of_them():
    families = {a["family"] for a in _plan()["automations"]}
    assert families == set(launch_plan.TEMPLATE_BY_FAMILY)


def test_every_emitted_template_is_buildable():
    for unit in _plan()["automations"]:
        assert unit["template"] in BUILDABLE, (unit["id"], unit["template"])
    assert launch_plan.template_problems(_plan()) == []


def test_named_decisions():
    by_family = {a["family"]: a["template"] for a in _plan()["automations"]}
    assert by_family["pre_launch"] == "launch-a/launch-a-prelaunch-window"
    assert by_family["opt_in"] == "launch-a/launch-optin-register-login"
    assert by_family["abandoned_checkout"] == "launch-b/abandoned-checkout-recovery"
    assert by_family["page_retargeting"] == "launch-b/launch-b-retarget-visited-sales-no-checkout"
    assert by_family["onboarding_review"] == "launch-c/launch-c-onboarding-first-hour-day-week"


def test_gate_refuses_unbuildable_and_unapproved_new():
    ok = frozenset(launch_plan.TEMPLATE_BY_FAMILY.values())  # isolates the gate from the manifest
    bad = json.loads(json.dumps(_plan()))
    bad["automations"][0]["template"] = "cart-open-cart-close-launch-sequence"
    bad["automations"][1]["template"] = "new"
    assert len(launch_plan.template_problems(bad, ok)) == 2
    bad["automations"][1]["new_template"] = {
        "owner_approved_reason": "no buildable twin", "compile_spec": {"graph": "x"}}
    assert len(launch_plan.template_problems(bad, ok)) == 1
