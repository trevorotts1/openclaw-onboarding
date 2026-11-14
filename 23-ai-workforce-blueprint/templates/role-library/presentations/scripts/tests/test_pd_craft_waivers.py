"""PD-309 — craft waivers are OWNER APPROVALS, and slide attribution is correct.

The defect (PASS6-LAST.md §1 PD-309, reproduced there):

  * `slide_craft._load_waivers` and `craft_judgement._load_craft_waivers` accepted
    any record carrying `af_code` + a non-empty `approved_by` + a non-empty
    `reason` + a slide list. No owner message, no oracle call, no date, no run id
    — so a file the running agent writes could waive fifteen render-time craft
    rules. `craft_judgement` also accepted `"ALL"` for all five of its codes.
  * `slide_craft._finding_slides` read the SECOND element of an offender tuple as
    a slide for EVERY rule. Only AF-DEN-1 (`check_den_ladder_gaps`) puts the next
    beat slide there; for AF-AUD-4 / AF-AUD-5 / AF-HOOK-5 that element is the
    copy-block index. A headline hit is copy[0], so the attributed slide set
    contained 0, and slide ordinals must be above zero — a real owner waiver for a
    headline could never apply.

Rows proven here (from the unit's acceptance list, A1):

  A1a  typed record with NO owner message id            -> NOT a waiver
  A1b  record whose owner_msg_id a stub oracle resolves -> the rule IS waived
  A1c  a headline AF-AUD-4 hit (copy[0]) is waived by a record naming that slide
  A1d  an UNDETERMINED oracle (cannot run) rejects the record
  A1e  craft_judgement's five codes use the SAME loader, and "ALL" is refused

The only stubbed seam is the owner oracle (`approvals._cc_board_oracle`): the
validator, the schema, the loaders, the checks, the attribution and
`run_all_checks` are the real code. No test makes a network call or spends a
token.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job import approvals as _approvals  # noqa: E402
import craft_judgement as cj  # noqa: E402
import slide_craft as sc  # noqa: E402

REAL_OWNER_MSG_ID = "msg-owner-309"
SLIDE_WITH_HIT = 5

# A shape-valid owner approval — the only thing missing in each negative case is
# the field that case names.
def _record(**overrides):
    rec = {
        "af_code": "AF-AUD-4",
        "slides": [SLIDE_WITH_HIT],
        "approved_by": "Trevor",
        "reason": "owner accepts this wording in the headline",
        "granted_at": "2026-11-13T09:30:00-04:00",
        "owner_msg_id": REAL_OWNER_MSG_ID,
    }
    rec.update(overrides)
    for key, value in list(rec.items()):
        if value is None:
            del rec[key]
    return rec


def _write_run(tmp_path, *, copy=None, waivers=None):
    """A minimal run dir: one slide whose HEADLINE (copy[0]) carries a meta token,
    and the waiver file under test. Every other craft input is ABSENT, so the
    other nine checks DEFER ("" = pass) and AF-AUD-4 is the only rule in play."""
    run = tmp_path / "run"
    (run / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    blocks = copy or ["webinar pricing reveal", "second copy block"]
    (run / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": SLIDE_WITH_HIT, "copy": blocks}]), encoding="utf-8")
    if waivers is not None:
        (run / "working" / "checkpoints" / "slide_craft_waivers.json").write_text(
            json.dumps(waivers), encoding="utf-8")
    return run


@pytest.fixture()
def oracle(monkeypatch):
    """Stub the owner oracle the way the live board answers: a set of message ids
    that really are owner-authored. `oracle.set(...)` swaps in another answer
    (None = UNDETERMINED, the board cannot be reached)."""
    state = {"ids": frozenset({REAL_OWNER_MSG_ID})}

    def _stub(run_dir=None):  # noqa: ANN001 — mirrors _cc_board_oracle's signature
        return state["ids"]

    monkeypatch.setattr(_approvals, "_cc_board_oracle", _stub)
    monkeypatch.delenv("OPENCLAW_GATEWAY_URL", raising=False)
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    state["set"] = lambda ids: state.__setitem__("ids", ids)
    return state


def _aud_blocking(run):
    all_pass, blocking = sc.run_all_checks(run)
    return all_pass, [r for r in blocking if r.startswith("AF-AUD-4")]


def test_a1a_typed_record_without_owner_msg_id_is_not_a_waiver(tmp_path, oracle):
    """A1: a record the agent can type — even with a real approver name, a real
    reason and a real timestamp — authorizes nothing without an owner message."""
    rec = _record(owner_msg_id=None)
    run = _write_run(tmp_path, waivers=[rec])

    assert sc._load_waivers(run) == {}, "a record with no owner_msg_id was honoured"
    all_pass, aud = _aud_blocking(run)
    assert not all_pass
    assert aud, "AF-AUD-4 must stay blocking when the waiver is unproven"


def test_a1b_stub_verified_id_waives_the_rule(tmp_path, oracle):
    """A1: the same record WITH an id the owner oracle resolves is a waiver."""
    run = _write_run(tmp_path, waivers=[_record()])

    waivers = sc._load_waivers(run)
    assert waivers.get("AF-AUD-4", {}).get("slides") == {SLIDE_WITH_HIT}
    all_pass, aud = _aud_blocking(run)
    assert aud == [], f"a verified owner approval did not waive the rule: {aud}"
    assert all_pass


def test_a1c_headline_hit_is_waived_by_the_record_naming_its_slide(tmp_path, oracle):
    """A1: a headline hit (copy[0]) is waived by a record naming that slide. This
    is the half the old attribution broke: it read the copy-block index (0) as a
    slide, so the attributed set was {slide, 0} and 0 can never be named."""
    # copy[0] is the headline: the offender tuple is (slide, 0, token).
    run = _write_run(
        tmp_path,
        copy=["webinar headline", "second copy block"],
        waivers=[_record(slides=[SLIDE_WITH_HIT])],
    )

    all_pass, aud = _aud_blocking(run)
    assert aud == [], f"a headline hit naming slide {SLIDE_WITH_HIT} was not waived: {aud}"
    assert all_pass


def test_a1c2_attribution_takes_the_second_element_as_a_slide_only_for_den1():
    """A1: the copy-block index is never a slide; only AF-DEN-1's next-beat slide is."""
    headline = {"offenders": [[SLIDE_WITH_HIT, 0, "webinar"]]}
    assert sc._finding_slides(headline, "check_aud_meta_tokens") == {SLIDE_WITH_HIT}
    # A rule whose record carries no name cannot widen it either (fail-closed).
    assert sc._finding_slides(headline) == {SLIDE_WITH_HIT}
    # AF-DEN-1 is the ONE rule whose second element is a slide and is kept.
    gap = {"offenders": [[8, 10, 2]]}
    assert sc._finding_slides(gap, "check_den_ladder_gaps") == {8, 10}
    assert sc._finding_slides(gap, "check_aud_meta_tokens") == {8}


def test_a1d_undetermined_oracle_rejects_the_record(tmp_path, oracle):
    """A1: an oracle that cannot answer never opens the gate."""
    oracle["set"](None)
    run = _write_run(tmp_path, waivers=[_record()])

    assert sc._load_waivers(run) == {}
    all_pass, aud = _aud_blocking(run)
    assert not all_pass and aud


def test_a1e_craft_judgement_uses_the_same_loader_and_refuses_all(tmp_path, oracle):
    """A1: the five FIX 18 codes are waived by the SAME verified owner approval,
    and "ALL" is not accepted for any of them (only AF-DEN-4 has it)."""
    hook2 = _record(af_code="AF-HOOK-2", slides=[4])
    run = _write_run(tmp_path, waivers=[hook2])
    assert cj._load_craft_waivers(run).get("AF-HOOK-2", {}).get("slides") == {4}

    # No owner message id -> no waiver.
    run = _write_run(tmp_path, waivers=[_record(af_code="AF-HOOK-2", slides=[4],
                                                owner_msg_id=None)])
    assert cj._load_craft_waivers(run) == {}

    # "ALL" is refused for AF-HOOK-2 even with a verified id.
    run = _write_run(tmp_path, waivers=[_record(af_code="AF-HOOK-2", slides=["ALL"])])
    assert cj._load_craft_waivers(run) == {}

    # ... and the same "ALL" refusal holds on slide_craft's own codes.
    run = _write_run(tmp_path, waivers=[_record(af_code="AF-OBI-1", slides=["ALL"])])
    assert sc._load_waivers(run) == {}


def test_a1f_self_grant_marker_is_rejected(tmp_path, oracle):
    """The producing agent can never approve its own skip — even with an id."""
    run = _write_run(tmp_path, waivers=[_record(approved_by="the running agent, via builder")])
    assert sc._load_waivers(run) == {}


def test_a1g_short_reason_and_midnight_timestamp_are_rejected(tmp_path, oracle):
    """The validator's other two forgery shapes still bite through the loader."""
    for bad in (_record(reason="x"),
                _record(granted_at="2026-11-13T00:00:00-04:00")):
        run = _write_run(tmp_path, waivers=[bad])
        assert sc._load_waivers(run) == {}, f"accepted a forged record: {bad}"


def test_a1h_malformed_file_still_fails_closed(tmp_path, oracle):
    """Non-list / unreadable waiver files authorize nothing (unchanged contract)."""
    run = _write_run(tmp_path)
    path = run / "working" / "checkpoints" / "slide_craft_waivers.json"
    for payload in ('{"af_code": "AF-AUD-4"}', "not json at all", "[]"):
        path.write_text(payload, encoding="utf-8")
        assert sc._load_waivers(run) == {}
    path.unlink()
    assert sc._load_waivers(run) == {}


def test_a1i_the_real_preflight_gate_sees_the_same_verdict(tmp_path, oracle):
    """The gate build_deck actually runs (PREFLIGHT_REQUIRED's `_chk_slide_craft`)
    agrees with the loader: unproven record -> AF-AUD-4 blocks; verified record
    naming the slide -> it does not."""
    import build_deck as bd  # local: heavy module, only this test needs it

    run = _write_run(tmp_path, waivers=[_record(owner_msg_id=None)])
    reason = bd._chk_slide_craft(run)
    assert "AF-AUD-4" in reason, f"the gate did not block on an unproven waiver: {reason!r}"

    run = _write_run(tmp_path / "verified", copy=["webinar headline", "body"],
                     waivers=[_record()])
    reason = bd._chk_slide_craft(run)
    assert "AF-AUD-4" not in reason, f"the gate did not honour a verified waiver: {reason!r}"
