"""PD-TEST-135 -- a verifier-parked BLOCKED phase must be re-admittable on resume.

THE DEFECT, measured on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.

`phases._phase_terminal_bad` treats {QUARANTINED, FAILED, BLOCKED, OBSOLETE} as
terminal -- it withholds every descendant -- but `_READMITTABLE_PHASE_STATUSES`
listed only FAILED and QUARANTINED. BLOCKED was therefore the ONE status that was
terminal-bad yet never re-admittable, so a phase parked by a substance check
could not be re-entered by ANY resume.

Consequence observed live: P4-COPY sat status="blocked" on
"substance check failed: AF-NO-VILLAIN ..." while the INSTALLED
`intelligence_engines_check.check_copy()` returned ZERO problems against the same
copy -- the defect had already been fixed by PD-TEST-125 (v25.1.22). A sanctioned
`--resume` logged 15+ "waits on P4-COPY (blocked) -- not admitted" lines and
re-parked the run without ever re-adjudicating it, so `out.pptx` and 33 other
phases stayed blocked behind one stale string. The only documented exit was an
owner skip_approval token -- marking the phase done WITHOUT re-running the check.

WHAT THESE TESTS PIN
  * a BLOCKED phase whose block records a CHECKER verdict is re-admitted;
  * an OPERATOR park (no checker verdict) is still honoured;
  * the pre-existing FAILED / QUARANTINED behaviour is unchanged;
  * re-admission preserves attempts, heal_events and the prior reason.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from presentation_job import phases  # noqa: E402

LIVE_REASON = (
    "substance check failed: AF-NO-VILLAIN: no VILLAIN/antagonist beat anywhere "
    "in the arc. 'No one cares about the hero until they meet the villain' ... "
    "An owner_skip_approval token for this phase is required to advance it to done."
)


def _phase(pid, status, **kw):
    d = {"id": pid, "status": status, "attempts": 3,
         "heal_events": kw.pop("heal_events", [])}
    d.update(kw)
    return d


def _state(tmp_path, *phases_):
    return {"run_dir": str(tmp_path), "phases": list(phases_)}


def test_verifier_parked_blocked_phase_is_readmitted(tmp_path):
    st = _state(tmp_path, _phase(
        "P4-COPY", "blocked", blocked_reason=LIVE_REASON,
        heal_events=[{"at": "2026-09-15T15:15:55-04:00",
                      "class": "verifier_substance",
                      "reason": "substance check failed"}]))
    recs = phases.readmit_retryable_phases(st)
    assert [r["phase"] for r in recs] == ["P4-COPY"]
    assert st["phases"][0]["status"] == "pending"


def test_blocked_reason_alone_is_NOT_enough(tmp_path):
    """INVERTED BY THE TWO REVIEWS. The first cut accepted the reason on its own;
    both reviewers showed that made the guard purely lexical, so any operator
    prose mentioning verification reopened a paid phase. The block must now be
    the SAME EPISODE as a recorded verifier heal -- a bare reason is not proof."""
    st = _state(tmp_path, _phase("P4-COPY", "blocked", blocked_reason=LIVE_REASON))
    assert phases.readmit_retryable_phases(st) == []
    assert st["phases"][0]["status"] == "blocked"


def test_operator_park_is_still_honoured(tmp_path):
    st = _state(tmp_path, _phase(
        "P-U-SALES-BUILD", "blocked",
        blocked_reason="operator parked: awaiting owner decision on the page split"))
    assert phases.readmit_retryable_phases(st) == []
    assert st["phases"][0]["status"] == "blocked"


def test_reasonless_block_is_still_honoured(tmp_path):
    st = _state(tmp_path, _phase("P-X", "blocked"))
    assert phases.readmit_retryable_phases(st) == []
    assert st["phases"][0]["status"] == "blocked"


def test_failed_and_quarantined_unchanged(tmp_path):
    st = _state(tmp_path,
                _phase("P-FAILED", "failed", failed_reason="rc=3"),
                _phase("P-QUAR", "quarantined", quarantined_reason="produced nothing"),
                _phase("P-DONE", "done"),
                _phase("P-PEND", "pending"))
    assert sorted(r["phase"] for r in phases.readmit_retryable_phases(st)) == \
        ["P-FAILED", "P-QUAR"]


def test_readmission_preserves_history_and_counter(tmp_path):
    st = _state(tmp_path, _phase(
        "P4-COPY", "blocked", blocked_reason=LIVE_REASON,
        heal_events=[{"class": "verifier_substance", "reason": LIVE_REASON}]))
    before = copy.deepcopy(st["phases"][0])
    recs = phases.readmit_retryable_phases(st)
    ps = st["phases"][0]
    assert ps["attempts"] == before["attempts"]
    assert ps["heal_events"] == before["heal_events"]
    assert recs[0]["prior_status"] == "blocked"
    assert recs[0]["prior_reason"] == LIVE_REASON
    assert ps["readmissions"][-1]["phase"] == "P4-COPY"
    assert st["resume_readmissions"][-1]["phase"] == "P4-COPY"

def test_terminal_bad_still_includes_blocked(tmp_path):
    """The withholding rule is unchanged -- BLOCKED is still terminal-bad while
    it stands; only its RE-ADMITTABILITY changed."""
    assert phases._phase_terminal_bad("blocked") is True
    assert phases._phase_terminal_bad("quarantined") is True
    assert phases._phase_terminal_bad("done") is False


# ---------------------------------------------------------------------------
# TWO independent reviews of the first cut (2026-09-16) both returned
# MERGE-WITH-CHANGES on the same finding: the operator-park protection was
# lexical, and 5/8 (one reviewer) and 12/12 (the other) crafted OPERATOR park
# reasons were silently REOPENED and would re-run a paid phase on the next
# --resume. Reviewer 2 also measured that the shipped test that claimed to cover
# the operator path passed only because its sample reason happened to contain no
# marker -- coverage narrower than the guarantee it advertised.
#
# The fix matches the SHAPE of the engine's substance park instead of heal's
# vocabulary: the reason must BEGIN with the checker's own verdict prefix AND the
# phase's MOST RECENT heal event must be a verifier_substance event whose reason
# the block quotes (the same episode).
# ---------------------------------------------------------------------------

OPERATOR_REASONS = [
    "operator parked: awaiting verifier review",
    "operator decision - do not auto-verify this phase",
    "parked by human after verify step",
    "operator stopped the run to verify spend",
    "HOLD - operator must verify brand compliance before re-run",
    "human halted run: awaiting operator verification of output quality",
    "parked by owner pending manual QA",
    "owner retracted approval; re-verify with client before continuing",
    "awaiting client sign-off on verifier wording",
    "gate declined: client asked us to verify the claim first",
    "waiver granted pending verify of invoice",
    "owner_skip_approval token required to verify",
    "budget review: verify spend before resuming",
    "client asked to verify the price ladder",
    "operator parked: awaiting owner decision on the page split",
]


@pytest.mark.parametrize("reason", OPERATOR_REASONS)
def test_operator_reasons_are_never_reopened(reason):
    """An operator park must survive even when its prose mentions verification.
    The first cut reopened every one of these; that is paid re-runs on resume."""
    assert not phases._block_is_verifier_sourced(
        {"blocked_reason": reason, "heal_events": []}), reason
    st = {"run_dir": "/nonexistent", "phases": [
        {"id": "OP", "status": "blocked", "attempts": 1,
         "heal_events": [], "blocked_reason": reason}]}
    assert phases.readmit_retryable_phases(st) == []
    assert st["phases"][0]["status"] == "blocked"


def test_stale_verifier_heal_cannot_reopen_a_budget_park():
    """A dispatcher budget park is not a substance park, even when the phase
    still carries an older verifier_substance heal event."""
    assert not phases._block_is_verifier_sourced({
        "blocked_reason": ("dispatcher paid retry budget: paid retry budget "
                           "exhausted after 3 provider attempts (DISPATCH_RETRY_CAP=3)."),
        "heal_events": [{"class": "verifier_substance",
                         "reason": "substance check failed: AF-OLD: stale"}]})


def test_verifier_heal_without_the_verdict_prefix_is_not_enough():
    """heal.classify_failure returns owner_decision for the live P4-COPY reason
    (its owner_skip_approval sentence is boilerplate the engine appends to every
    substance park), so heal cannot arbitrate this. The SHAPE can."""
    assert not phases._block_is_verifier_sourced({
        "blocked_reason": "operator_skip_approval token required to verify",
        "heal_events": [{"class": "verifier_substance",
                         "reason": "substance check failed: AF-NO-VILLAIN: x"}]})


def test_engine_substance_park_is_recognised():
    """The exact shape the engine writes: verdict prefix + matching latest heal."""
    verdict = ("substance check failed: AF-NO-VILLAIN: no VILLAIN/antagonist "
               "beat anywhere in the arc.")
    live = {"blocked_reason": verdict + " An owner_skip_approval token for this "
                                        "phase is required to advance it to done.",
            "heal_events": [{"class": "missing_input", "reason": "produced nothing"},
                            {"class": "verifier_substance", "reason": verdict}]}
    assert phases._block_is_verifier_sourced(live)


def test_prior_reason_records_the_block_being_cleared():
    """Both reviewers: the record preferred quarantined/failed reason, so the
    live P4-COPY audit trail named a missing artifact instead of the substance
    verdict actually being reopened."""
    verdict = "substance check failed: AF-NO-VILLAIN: x"
    st = {"run_dir": "/nonexistent", "phases": [{
        "id": "P4-COPY", "status": "blocked", "attempts": 7,
        "blocked_reason": verdict,
        "quarantined_reason": "agent-authored phase produced nothing within 60 minutes",
        "heal_events": [{"class": "verifier_substance", "reason": verdict}]}]}
    recs = phases.readmit_retryable_phases(st)
    assert recs[0]["prior_reason"] == verdict
