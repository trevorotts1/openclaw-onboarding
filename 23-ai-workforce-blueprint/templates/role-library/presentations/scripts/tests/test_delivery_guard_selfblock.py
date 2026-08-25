"""Tests for the P9-DELIVER self-block bug in canonical_render_guard.py.

BUG: missing_attestations() swept EVERY manifest phase, including the phase
currently being dispatched. guard_pre_delivery() runs BEFORE P9-DELIVER can
possibly attest itself (attestation only happens once the guard has already
passed and delivery proceeds — see run_signature_deck.py's DELIVERY_PHASE_ID
branch), so P9-DELIVER always appeared in its own missing list and every real
delivery was refused, unconditionally, for every run, forever.

FIX: missing_attestations() now takes target_phase_id (default
DELIVERY_PHASE_ID = "P9-DELIVER") and excludes every phase whose `order` is
>= the target's own order before sweeping — mirroring check_phase_preconditions'
`order < target_order` exclusion (run_signature_deck.py:855-857 /
build_deck.check_phase_preconditions, called with prior_phase_ids only)
exactly. guard_pre_delivery() threads target_phase_id through unchanged.

Covered here:
  * the in-flight target phase is excluded from its own sweep (the fix);
  * a genuinely unattested EARLIER phase (P7-TELEPROMPTER) is still caught —
    the guard must not trade the false block for a hole;
  * the exact pre-fix failure mode is reproduced directly (target_phase_id=None)
    to prove the exclusion — not some other change — is what fixes it;
  * guard_pre_render() is confirmed NOT to share the defect (it has no
    `phases` parameter and never calls missing_attestations() at all).
"""

import json
import pathlib
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import canonical_render_guard as crg  # noqa: E402
import run_signature_deck as rsd  # noqa: E402


def _real_phases():
    """The actual production manifest phase list (id + order) — the same list
    run_signature_deck.py loads and passes to guard_pre_delivery()."""
    return rsd.load_manifest()["phases"]


def _make_run_dir(attested_ids):
    """A clean run dir whose process_manifest.json attests exactly
    `attested_ids` and nothing else. No hand-rolled scripts, no rendered PNGs,
    no image_qc_report.json — scan_run_dir()/run_fix2_checks()/
    qc_generator_guard all defer/pass cleanly on an empty run dir, so the only
    thing under test is the attestation sweep.

    F04: attestation rows must be COMPLETED + substance-verified
    (status=='done', substance_verified==True) to count — the same shape the
    runner's attest_phase() writes. Bare id-only rows are forged-shaped and
    satisfy nothing."""
    r = pathlib.Path(tempfile.mkdtemp())
    (r / "working" / "checkpoints").mkdir(parents=True)
    manifest = {
        "phase_attestations": [
            {
                "phase_id": pid,
                "role": "test",
                "method": "artifact_present",
                "status": "done",
                "substance_verified": True,
            }
            for pid in attested_ids
        ]
    }
    (r / "working" / "checkpoints" / "process_manifest.json").write_text(
        json.dumps(manifest))
    return r


def test_inflight_target_phase_excluded_from_its_own_sweep():
    """An otherwise-complete run — every phase attested EXCEPT P9-DELIVER
    itself, which cannot possibly be attested yet — must not name P9-DELIVER
    in its own missing list, and must have nothing missing at all."""
    phases = _real_phases()
    all_ids = [ph["id"] for ph in phases]
    assert crg.DELIVERY_PHASE_ID in all_ids, "fixture assumption: P9-DELIVER must be a real manifest phase"
    attested = [pid for pid in all_ids if pid != crg.DELIVERY_PHASE_ID]
    run_dir = _make_run_dir(attested)

    missing = crg.missing_attestations(run_dir, phases)

    assert crg.DELIVERY_PHASE_ID not in missing, (
        f"P9-DELIVER must never require its own attestation before it is "
        f"dispatched; got missing={missing!r}")
    assert missing == [], f"expected a fully-attested run to have nothing missing, got {missing!r}"


def test_genuinely_missing_earlier_phase_still_caught():
    """THE CRITICAL CHECK: a genuinely skipped earlier phase (P7-TELEPROMPTER,
    order 8.95 — immediately before P9-DELIVER at order 9) must STILL be
    refused. The fix must not trade a false block for a hole."""
    phases = _real_phases()
    all_ids = [ph["id"] for ph in phases]
    skip_phase = "P7-TELEPROMPTER"
    assert skip_phase in all_ids, "fixture assumption: P7-TELEPROMPTER must be a real manifest phase"
    attested = [pid for pid in all_ids
                if pid not in (crg.DELIVERY_PHASE_ID, skip_phase)]
    run_dir = _make_run_dir(attested)

    missing = crg.missing_attestations(run_dir, phases)

    assert skip_phase in missing, (
        f"a genuinely unattested earlier phase must still be reported missing; "
        f"got missing={missing!r}")
    assert crg.DELIVERY_PHASE_ID not in missing


def test_guard_pre_delivery_passes_full_run():
    """END-TO-END 'AFTER' REPRODUCTION: guard_pre_delivery() itself (not just
    missing_attestations()) must PASS when every phase except P9-DELIVER is
    attested and the run dir is otherwise clean. This is the exact scenario
    from the bug report — an otherwise-complete run reaching guard_pre_delivery()
    — and after the fix it must no longer be refused."""
    phases = _real_phases()
    all_ids = [ph["id"] for ph in phases]
    attested = [pid for pid in all_ids if pid != crg.DELIVERY_PHASE_ID]
    run_dir = _make_run_dir(attested)

    reason = crg.guard_pre_delivery(run_dir, phases)

    assert reason == "", f"expected PASS (empty string), got refusal:\n{reason}"


def test_guard_pre_delivery_still_refuses_incomplete_run():
    """guard_pre_delivery() must still REFUSE when a real earlier phase
    (P7-TELEPROMPTER) was never attested — the guard still bites, and the
    refusal must name the real gap, never the delivery phase itself."""
    phases = _real_phases()
    all_ids = [ph["id"] for ph in phases]
    skip_phase = "P7-TELEPROMPTER"
    attested = [pid for pid in all_ids
                if pid not in (crg.DELIVERY_PHASE_ID, skip_phase)]
    run_dir = _make_run_dir(attested)

    reason = crg.guard_pre_delivery(run_dir, phases)

    assert reason != "", "expected a refusal when an earlier phase is unattested, got PASS"
    assert "AF-PHASE-SKIPPED" in reason
    assert skip_phase in reason
    assert crg.DELIVERY_PHASE_ID not in reason, (
        "the delivery phase itself must never be named as a cause of refusal — "
        f"it cannot possibly be attested yet. Got:\n{reason}")


def test_without_target_exclusion_old_bug_reproduces():
    """Directly reproduces the PRE-FIX bug: sweeping with no target-phase
    exclusion (target_phase_id=None) puts P9-DELIVER in its own missing list
    even though every OTHER phase is attested — the exact 'otherwise-complete
    run refused, P9-DELIVER named in its own missing list' failure mode from
    the bug report. Proves the target_phase_id exclusion — not some other
    change — is what fixes it."""
    phases = _real_phases()
    all_ids = [ph["id"] for ph in phases]
    attested = [pid for pid in all_ids if pid != crg.DELIVERY_PHASE_ID]
    run_dir = _make_run_dir(attested)

    old_behavior_missing = crg.missing_attestations(run_dir, phases, target_phase_id=None)
    assert old_behavior_missing == [crg.DELIVERY_PHASE_ID], (
        "sweeping with no target exclusion must reproduce the original bug — "
        f"P9-DELIVER named in its own missing list; got {old_behavior_missing!r}")

    fixed_missing = crg.missing_attestations(run_dir, phases)
    assert fixed_missing == [], f"expected the fixed default to clear the run, got {fixed_missing!r}"


def test_guard_pre_render_does_not_share_the_defect():
    """guard_pre_render() takes NO `phases` argument and never calls
    missing_attestations() at all — it only scans for hand-rolled
    renderers/assemblers (scan_run_dir) and the QC-generator guard. Confirms
    P4-RENDER's own precondition check (a DIFFERENT function —
    run_signature_deck.check_phase_preconditions, called from _dispatch_render
    via the ordinary phase-precondition gate, not this guard) is not exposed to
    the same in-flight self-attestation bug through this guard."""
    import inspect
    src = inspect.getsource(crg.guard_pre_render)
    assert "missing_attestations" not in src, (
        "guard_pre_render must not call missing_attestations — if it does, it "
        "needs the SAME target_phase_id exclusion this test suite would then "
        "also need to cover for P4-RENDER")
    sig = inspect.signature(crg.guard_pre_render)
    assert "phases" not in sig.parameters
