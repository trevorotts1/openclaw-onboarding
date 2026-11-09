"""CON-16 and PRD-30: the Council step is labelled for what it is; downsell_2 is named.

Run: python3 -m pytest 83-black-friday-launcher/tests/test_council_label.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import council, intake  # noqa: E402
from launcher_core.constants import UNSUPPORTED_OFFER_ROLES  # noqa: E402

LAUNCH = {"launch_id": "bf-2026"}


def package_ready(_launch):
    return {"status": "ready_no_advice", "ready": True, "advice": None,
            "advice_state": "pending_live_session"}


def advice(_launch):
    return {"status": "advice_returned", "ready": True,
            "advice": {"recommendation": "stub"}, "advice_state": "returned"}


def test_default_step_says_no_advice_was_obtained():
    # The real runner (doctor.mjs): whatever its verdict, no session was held.
    record = council.planning_step(LAUNCH)
    assert record["council_session_held"] is False
    assert record["advice"] is None
    assert "No Council advice was obtained" in record["client_summary"]
    assert "not a Council review" in record["client_summary"]
    assert record["blocks_build"] is False and record["is_permission"] is False


def test_package_ready_is_not_advice():
    record = council.planning_step(LAUNCH, runner=package_ready)
    assert record["status"] == "ready_no_advice"
    assert record["council_session_held"] is False
    assert "No Council advice was obtained" in record["client_summary"]


def test_a_returned_session_is_labelled_as_advice():
    record = council.planning_step(LAUNCH, runner=advice)
    assert record["council_session_held"] is True
    assert "No Council advice" not in record["client_summary"]


def test_a_status_claiming_advice_with_none_is_not_a_session():
    claim = lambda _l: {"status": "advice_returned", "ready": True, "advice": None,
                        "advice_state": "returned"}
    assert council.planning_step(LAUNCH, runner=claim)["council_session_held"] is False


@pytest.mark.parametrize("runner", [package_ready, lambda _l: 1 / 0, lambda _l: "nope"])
def test_council_required_refuses_without_a_session(runner):
    with pytest.raises(council.CouncilRequiredError) as err:
        council.planning_step(LAUNCH, runner=runner, council_required=True)
    assert err.value.code == "AF-LAUNCH-COUNCIL-REQUIRED"
    assert "No Council advice was obtained" in err.value.detail


def test_council_required_passes_with_a_session():
    record = council.planning_step(LAUNCH, runner=advice, council_required=True)
    assert record["council_session_held"] is True


def test_a_doctor_pass_is_scoped_to_the_package_in_the_detail():
    record = council.planning_step(LAUNCH)
    if record["status"] == "ready_no_advice":  # doctor ran and passed
        assert record["detail"].startswith("package check only, no Council session:")


def test_downsell_2_has_a_named_refusal_reason():
    assert UNSUPPORTED_OFFER_ROLES["downsell_2"] == (
        "a second downsell is not supported in this release")


def test_an_intake_with_a_downsell_2_offer_is_refused_not_dropped():
    from test_decided_requirements import base_intake, with_checkout_facts  # same fixture the decided tests use

    payload = base_intake()
    payload["offers"] += [
        {"offer_id": "up-1", "name": "Up", "role": "upsell_1",
         "price": {"amount_minor": 9700, "currency": "USD"}},
        {"offer_id": "down-1", "name": "Down", "role": "downsell_1",
         "price": {"amount_minor": 4700, "currency": "USD"}},
        {"offer_id": "down-2", "name": "Down Two", "role": "downsell_2",
         "price": {"amount_minor": 2700, "currency": "USD"}},
    ]
    del payload["answers_file"]  # the helper writes the client's answers for every inline offer, downsell_2 included
    with_checkout_facts(payload)  # delivery, level and price source_ref on each: the named refusal is the role
    with pytest.raises(intake.IntakeError) as err:
        intake.validate(payload)
    assert err.value.field == "offers[3].role"
