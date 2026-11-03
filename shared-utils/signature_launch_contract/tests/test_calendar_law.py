"""One Black Friday calendar law: shared law, shared validator, Skill 83 and the Skill 44 reader.

S44-01: a calendar ordered teaser < countdown <= doors_open <= launch < cyber_monday
<= last_call < doors_close must pass every consumer.
S44-27: the black-friday.json fixture is the Skill 49 generator's output, not a hand copy.

Run: python3 -m pytest shared-utils/signature_launch_contract/tests/test_calendar_law.py -q
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
FIXTURE = CONTRACT / "fixtures" / "black-friday.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


law = _load("t_calendar_law", CONTRACT / "calendar_law.py")
validator = _load("t_validate_launch_plan", CONTRACT / "validate_launch_plan.py")
reader = _load("t_plan_reader",
               _skill("44-convert-and-flow-operator") / "automation-templates" / "launch-c" / "plan_reader.py")
sys.path.insert(0, str(_skill("83-black-friday-launcher")))
from launcher_core import launch_plan as skill83  # noqa: E402

sys.path.insert(0, str(_skill("49-signature-funnel") / "scripts"))
generator = _load("t_s49_launch_plan", _skill("49-signature-funnel") / "scripts" / "launch_plan.py")

SCHEMA = validator.load_json(validator.SCHEMA_PATH)
BASE = json.loads(FIXTURE.read_text(encoding="utf-8"))

# The Black Friday inputs the fixture is generated from (Skill 49 build_launch_plan).
BF_LAUNCH = {
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
BF_ANSWERS = {
    "launch.launch_at": "2026-11-27T00:00:00-05:00",
    "launch.doors_open_at": "2026-11-27T00:00:00-05:00",
    "launch.doors_close_at": "2026-12-01T00:00:00-05:00",
    "launch.timezone": "America/New_York",
    "launch.black_friday.teaser_at": "2026-11-20T09:00:00-05:00",
    "launch.black_friday.countdown_at": "2026-11-24T09:00:00-05:00",
    "launch.black_friday.cyber_monday_at": "2026-11-30T00:00:00-05:00",
    "launch.black_friday.last_call_at": "2026-11-30T20:00:00-05:00",
    "launch.channels": ["email", "text"],
    "launch.a2p_ready": False,
    "launch.conversation_ai": False,
    "launch.landing_url": "https://example.com/black-friday",
    "launch.sales_page_url": "https://example.com/black-friday/offer",
    "launch.checkout_url": "https://example.com/black-friday/order",
    "launch.thank_you_url": "https://example.com/black-friday/access",
}


def plan_with(**phases: str) -> dict:
    """The fixture with some calendar phases replaced (phase names from calendar_law)."""
    plan = copy.deepcopy(BASE)
    calendar = plan["launch_calendar"]
    for phase, value in phases.items():
        path = law.PHASE_FIELDS[phase]
        node = calendar
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = value
    return plan


D = "2026-11-{:02d}T{}:00:00-05:00"
# name -> overrides. Every row here is VALID under the law.
VALID = {
    "fixture": {},
    "launch_after_doors_open": {"launch": D.format(27, "09")},
    "doors_open_after_countdown": {"doors_open": D.format(27, "08"), "launch": D.format(27, "08")},
    "countdown_at_doors_open": {"countdown": D.format(27, "00")},
    "cyber_monday_at_last_call": {"last_call": D.format(30, "00")},
}
# Every row here is INVALID under the law; every consumer must refuse it.
INVALID = {
    "teaser_after_countdown": {"teaser": D.format(25, "09")},
    "countdown_after_doors_open": {"countdown": D.format(28, "09")},
    "launch_before_doors_open": {"launch": D.format(26, "09")},
    "launch_after_cyber_monday": {"launch": D.format(30, "12")},
    "cyber_monday_after_last_call": {"cyber_monday": D.format(30, "21")},
    "last_call_after_doors_close": {"last_call": "2026-12-01T09:00:00-05:00"},
}
# Strict pairs: equality is refused by the law and the validator (Skill 83 still accepts
# equality today; its unit adopts the shared law).
STRICT = {
    "teaser_equals_countdown": {"teaser": D.format(24, "09")},
    "launch_equals_cyber_monday": {"launch": D.format(30, "00")},
    "last_call_equals_doors_close": {"last_call": "2026-12-01T00:00:00-05:00"},
}


def skill83_refuses(plan: dict) -> bool:
    try:
        skill83.black_friday_calendar(plan)
    except skill83.LaunchPlanError:
        return True
    return False


def reader_refuses(plan: dict) -> bool:
    try:
        reader.read_launch_plan(plan)
    except reader.ReaderError:
        return True
    return False


@pytest.mark.parametrize("name", sorted(VALID))
def test_valid_calendar_passes_law_validator_and_skill83(name):
    plan = plan_with(**VALID[name])
    assert law.violations(plan["launch_calendar"]) == []
    assert validator.validate_plan(plan, SCHEMA) == []
    assert not skill83_refuses(plan)


@pytest.mark.parametrize("name", sorted(VALID))
def test_valid_calendar_passes_the_44_reader(name):
    assert not reader_refuses(plan_with(**VALID[name]))


def test_44_reader_cli_accepts_the_fixture(tmp_path):
    out = tmp_path / "automation-builds.json"
    rc = reader.main(["--launch-plan", str(FIXTURE), "--out", str(out)])
    assert rc == reader.EXIT_BLOCKED
    doc = json.loads(out.read_text())
    assert {n["phase"] for n in doc["builds"][0]["schedule"]["calendar_nodes"]} >= {
        "teaser", "countdown", "cyber_monday", "last_call"}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_invalid_calendar_is_refused_by_all_four(name):
    plan = plan_with(**INVALID[name])
    assert law.violations(plan["launch_calendar"])
    assert validator.validate_plan(plan, SCHEMA)
    assert skill83_refuses(plan)
    assert reader_refuses(plan)


@pytest.mark.parametrize("name", sorted(STRICT))
def test_strict_pairs_are_refused_by_law_and_validator(name):
    plan = plan_with(**STRICT[name])
    assert law.violations(plan["launch_calendar"])
    assert validator.validate_plan(plan, SCHEMA)


def test_black_friday_block_required_when_the_launch_is_black_friday():
    calendar = copy.deepcopy(BASE["launch_calendar"])
    del calendar["black_friday"]
    assert law.violations(calendar) == []
    assert any("black_friday" in v for v in law.violations(calendar, black_friday_required=True))


def test_zone_less_deadline_is_refused():
    plan = plan_with(teaser="2026-11-20T09:00:00")
    assert any("UTC offset" in e for e in validator.validate_plan(plan, SCHEMA))


def test_fixture_equals_the_49_generator_output():
    result = generator.build_launch_plan(copy.deepcopy(BF_LAUNCH), copy.deepcopy(BF_ANSWERS))
    assert result["state"] == "ready", result["missing"]
    assert result["plan"] == BASE


def test_fixture_has_no_orphan_email_sequence_or_missing_onboarding_review():
    waited = {w for key in ("pages", "email_sequences", "text_sets", "automations")
              for unit in BASE[key] for w in unit["waits_for"]}
    assert [e["id"] for e in BASE["email_sequences"] if e["id"] not in waited] == []
    assert "email_doors_closing" in waited
    assert "onboarding_review" in {a["family"] for a in BASE["automations"]}


def test_schema_carries_commerce_unit_kind_and_approved_plan_hash_binding():
    assert "approved_plan_hash" in SCHEMA["properties"]
    assert "approval_ref" in SCHEMA["properties"]
    assert "commerce_units" in SCHEMA["properties"]
    kinds = SCHEMA["definitions"]["commerce_unit"]["properties"]["kind"]["enum"]
    assert {"product", "price", "order_form", "order_bump"} <= set(kinds)

    plan = copy.deepcopy(BASE)
    plan["approved_plan_hash"] = "a" * 64
    plan["approval_ref"] = "cc-approval:demo"
    plan["commerce_units"] = [{"id": "commerce_main_price", "kind": "price",
                               "draft_only": True, "waits_for": ["page_sales"]}]
    assert validator.validate_plan(plan, SCHEMA) == []

    bad_hash = copy.deepcopy(plan)
    bad_hash["approved_plan_hash"] = "abc"
    assert validator.validate_plan(bad_hash, SCHEMA)

    bad_kind = copy.deepcopy(plan)
    bad_kind["commerce_units"][0]["kind"] = "gift"
    assert validator.validate_plan(bad_kind, SCHEMA)

    duplicate = copy.deepcopy(plan)
    duplicate["commerce_units"][0]["id"] = "page_sales"
    assert any("more than one unit" in e for e in validator.validate_plan(duplicate, SCHEMA))
