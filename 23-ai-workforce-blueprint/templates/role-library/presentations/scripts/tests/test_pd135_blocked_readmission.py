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


def test_blocked_reason_alone_is_enough(tmp_path):
    """The heal_events class is corroboration, not a requirement: the reason the
    engine actually wrote is the primary signal."""
    st = _state(tmp_path, _phase("P4-COPY", "blocked", blocked_reason=LIVE_REASON))
    assert [r["phase"] for r in phases.readmit_retryable_phases(st)] == ["P4-COPY"]


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
        heal_events=[{"class": "verifier_substance", "reason": "kept"}]))
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
