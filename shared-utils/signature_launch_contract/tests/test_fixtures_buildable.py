"""Issues 58 and 73: a contract-valid launch plan is a buildable plan with Skill 50's counts.

* The shared validator refuses an automation template Skill 44 cannot build (the same
  LAUNCH-PLAN-TEMPLATE-UNBUILDABLE rule Skill 49's planner and Skill 44's reader apply).
* The four shared fixtures name only buildable templates, carry the email counts Skill 50's
  family registry fixes, and are taken by Skill 44's reader without a template refusal.
* Skill 49's planner is the producer of both facts: its TEMPLATE_BY_FAMILY and its
  registry-read email_counts() are what the fixtures carry.

Run: python3 -m pytest shared-utils/signature_launch_contract/tests/test_fixtures_buildable.py -q
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _skill(name):  # onboarding: 49-signature-funnel; 999: .claude/skills/signature-funnel
    p = ROOT / name
    return p if p.is_dir() else ROOT / ".claude/skills" / name.split("-", 1)[1]


CONTRACT = ROOT / "shared-utils" / "signature_launch_contract"
FIXTURES = CONTRACT / "fixtures"
NAMES = sorted(p.stem for p in FIXTURES.glob("*.json"))
REGISTRY = _skill("50-email-engine") / "profiles" / "launch-email-families.json"
MANIFEST = (_skill("44-convert-and-flow-operator") / "automation-templates"
            / "_matcher" / "buildable-templates.json")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load("t_fx_validate_launch_plan", CONTRACT / "validate_launch_plan.py")
reader = _load("t_fx_plan_reader", _skill("44-convert-and-flow-operator")
               / "automation-templates" / "launch-c" / "plan_reader.py")
sys.path.insert(0, str(_skill("49-signature-funnel") / "scripts"))
generator = _load("t_fx_s49_launch_plan", _skill("49-signature-funnel") / "scripts" / "launch_plan.py")

SCHEMA = validator.load_json(validator.SCHEMA_PATH)
BUILDABLE = {t["key"] for t in json.loads(MANIFEST.read_text(encoding="utf-8"))["templates"]}
REGISTRY_COUNTS = {f["kind"]: f["email_count"]
                   for f in json.loads(REGISTRY.read_text(encoding="utf-8"))["families"]}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_the_four_fixtures_are_present():
    assert NAMES == ["7figurepreneur", "black-friday", "elevation", "multi-option"]


@pytest.mark.parametrize("name", NAMES)
def test_fixture_is_contract_valid_and_buildable(name):
    assert validator.validate_plan(fixture(name), SCHEMA) == []


@pytest.mark.parametrize("name", NAMES)
def test_fixture_templates_are_buildable_and_the_planners_own(name):
    for unit in fixture(name)["automations"]:
        assert unit["template"] in BUILDABLE, (name, unit["id"], unit["template"])
        assert unit["template"] == generator.TEMPLATE_BY_FAMILY[unit["family"]], (name, unit["id"])


@pytest.mark.parametrize("name", NAMES)
def test_fixture_email_counts_equal_skill_50_registry(name):
    plan = fixture(name)
    assert plan["email_sequences"], name
    for unit in plan["email_sequences"]:
        assert unit["email_count"] == REGISTRY_COUNTS[unit["kind"]], (name, unit["id"], unit["kind"])
        assert unit["email_count"] == generator.email_counts()[unit["kind"]], (name, unit["id"])


@pytest.mark.parametrize("name", NAMES)
def test_44_reader_takes_the_fixture_through_template_validation(name, tmp_path):
    out = tmp_path / "automation-builds.json"
    # EXIT_BLOCKED: parsed and compiled, blocked only for want of Skill 50 build plans.
    assert reader.main(["--launch-plan", str(FIXTURES / f"{name}.json"), "--out", str(out)]) \
        == reader.EXIT_BLOCKED, name


def test_black_friday_fixture_agrees_with_the_real_producer_on_counts_and_templates():
    launch = {
        "launch_id": "black-friday-2026", "journey_mode": "single_simple",
        "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": False},
        "offers": [
            {"slot": "main", "display_name": "Black Friday Power Bundle",
             "prices": [{"amount_minor": 19700, "currency": "USD"}]},
            {"slot": "upsell_1", "display_name": "Fast Start Upgrade",
             "prices": [{"amount_minor": 9700, "currency": "USD"}]},
            {"slot": "downsell_1", "display_name": "Small Start",
             "prices": [{"amount_minor": 4700, "currency": "USD"}]},
        ],
    }
    answers = {
        "launch.launch_at": "2026-11-27T00:00:00-05:00",
        "launch.doors_open_at": "2026-11-27T00:00:00-05:00",
        "launch.doors_close_at": "2026-12-01T00:00:00-05:00",
        "launch.timezone": "America/New_York",
        "launch.black_friday.teaser_at": "2026-11-20T09:00:00-05:00",
        "launch.black_friday.countdown_at": "2026-11-24T09:00:00-05:00",
        "launch.black_friday.cyber_monday_at": "2026-11-30T00:00:00-05:00",
        "launch.black_friday.last_call_at": "2026-11-30T20:00:00-05:00",
        "launch.channels": ["email", "text"], "launch.a2p_ready": False,
        "launch.conversation_ai": False,
        "launch.landing_url": "https://example.com/black-friday",
        "launch.sales_page_url": "https://example.com/black-friday/offer",
        "launch.checkout_url": "https://example.com/black-friday/order",
        "launch.thank_you_url": "https://example.com/black-friday/access",
    }
    result = generator.build_launch_plan(launch, answers)
    assert result["state"] == "ready", result["missing"]
    produced, committed = result["plan"], fixture("black-friday")
    assert [(e["id"], e["kind"], e["email_count"]) for e in produced["email_sequences"]] \
        == [(e["id"], e["kind"], e["email_count"]) for e in committed["email_sequences"]]
    assert [(a["id"], a["template"]) for a in produced["automations"]] \
        == [(a["id"], a["template"]) for a in committed["automations"]]


# --- the validator's own refusal, on synthetic plans (not the fixtures) -------------------------

def plan_with(template, **extra):
    plan = fixture("elevation")
    plan["automations"][0]["template"] = template
    plan["automations"][0].update(extra)
    return plan


def template_errors(plan):
    return [e for e in validator.validate_plan(plan, SCHEMA) if validator.TEMPLATE_UNBUILDABLE in e]


def test_validator_refuses_a_template_outside_the_manifest():
    errors = template_errors(plan_with("cart-open-cart-close-launch-sequence"))
    assert len(errors) == 1 and "cart-open-cart-close-launch-sequence" in errors[0]


@pytest.mark.parametrize("extra", [
    {},
    {"new_template": {"owner_approved_reason": "  ", "compile_spec": {"a": 1}}},
    {"new_template": {"owner_approved_reason": "owner said so"}},
])
def test_validator_refuses_new_without_an_approved_new_template(extra):
    assert len(template_errors(plan_with("new", **extra))) == 1


def test_validator_accepts_new_with_reason_and_compile_spec():
    plan = plan_with("new", new_template={"owner_approved_reason": "owner approved a small custom step",
                                          "compile_spec": {"build_graph": []}})
    assert template_errors(plan) == []


def test_validator_accepts_every_manifest_key():
    for key in sorted(BUILDABLE):
        assert template_errors(plan_with(key)) == [], key


def test_validator_with_no_manifest_refuses_every_plan(monkeypatch):
    monkeypatch.setattr(validator, "_SKILL44_DIRS", ("no-such-skill-44-dir",))
    assert validator.buildable_manifest() is None
    errors = template_errors(copy.deepcopy(fixture("elevation")))
    assert len(errors) == 1 and "cannot confirm" in errors[0]
