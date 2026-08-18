#!/usr/bin/env python3
"""
test_fix2_qc_unskippable.py — FIX-2 (Error 2): QC phases structurally unskippable
+ real report floor.

FIX-2 gate (Gauntlet Loop per-task QC row):
    Write each of the 4 QC reports as 3-byte '{}' and attempt attest; write a
    skip record for P-PROMPT-QC; write one real 20-slide report.
    -> The placeholder attest FAILS (AF-QC-PLACEHOLDER); the QC-phase skip record
       is refused (phase stays required, AF-QC-SKIP); the real report passes.

The four QC phases (P1Q-COPY-QC / P-PROMPT-QC / P-TYPO-QC / P-SHIFT-QC) may NEVER
be waived by a phase-skip record, and their reports must clear a REAL-CONTENT
floor (> 256 bytes, valid JSON, >= 20 real per-slide verdicts) before the phase
may attest. A 3-byte '{}' placeholder (the exact Error-2 artifact) can never
satisfy a QC phase.

Covers:
  1. SKIP-RECORD REFUSAL — a well-formed owner-approved skip record naming a QC
     phase is refused by load_skip_approvals (AF-QC-SKIP), by
     build_deck.check_phase_preconditions, and by canonical_render_guard's
     missing_attestations (the QC phase stays a required precondition). A
     NON-QC phase skip is still honored (known-good control).
  2. PLACEHOLDER FAIL — attesting any of the four QC phases with a 3-byte '{}'
     report is refused (AF-QC-PLACEHOLDER, attest_phase exit 2).
  3. REAL REPORT PASS — a real 20-slide report (one per-slide verdict per slide)
     attests clean for all four QC phases.
  4. A verdict-less or sub-floor report is refused even when its JSON is large.

Every `test_*` function below is a thin pytest-visible wrapper around a
`_check_*` helper that does the actual work and returns a `fails` list. The
wrapper asserts the list empty so a broken guard FAILS under pytest, not just
under the `python3 <file>` script path — a check that can only fail when run
one specific way is not a check. `main()` calls the `_check_*` helpers
directly so script-mode aggregation/exit-code behavior is unchanged.

Run:  python3 test_fix2_qc_unskippable.py
      python3 -m pytest test_fix2_qc_unskippable.py -q
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_deck as bd  # noqa: E402
import run_signature_deck as rsd  # noqa: E402
import canonical_render_guard as guard  # noqa: E402

QC_PHASES = ("P1Q-COPY-QC", "P-PROMPT-QC", "P-TYPO-QC", "P-SHIFT-QC")
SLIDE_FLOOR = bd.QC_REPORT_SLIDE_FLOOR  # 20

NON_QC_PHASE = "P3-ARC"  # a real non-QC manifest phase for the control


def _run_dir(prefix: str, reports=None, n_slides=20) -> Path:
    """Build a run dir with working/qc/ populated from `reports` (dict of
    report-filename -> python object to JSON-dump)."""
    rd = Path(tempfile.mkdtemp(prefix=prefix))
    qc_dir = rd / "working" / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in (reports or {}).items():
        (qc_dir / name).write_text(json.dumps(obj))
    return rd


def _real_report(gate: str, builder: str, reviewer: str, n=SLIDE_FLOOR,
                 key="per_slide_scores") -> dict:
    """A REAL QC report: gate + average >= 8.5 + pass:true + independence block +
    one real per-slide verdict per slide (n slides)."""
    return {
        "gate": gate,
        "average": 9.1,
        "pass": True,
        "qc_independence": {"graded_by": reviewer, "independent": True,
                            "builder": builder, "self_graded": False},
        key: [{"slide": i, "average": 9.1, "pass": True,
               "scores": {"c1": 9}, "verdict": "pass"} for i in range(1, n + 1)],
    }


def _placeholder_report() -> dict:
    return {}  # json.dumps({}) == "{}" == 2 bytes (the 3-byte Error-2 artifact)


def _write_skip_approval(run_dir: Path, phase_ids, approved_by="Trevor BlackCEO",
                         owner_msg_id="real-owner-msg-001"):
    ckpt = run_dir / "working" / "checkpoints"
    ckpt.mkdir(parents=True, exist_ok=True)
    approvals = [{
        "phase_id": pid,
        "owner_approved": True,
        "approved_by": approved_by,
        "reason": "owner authorized this phase skip",
        "timestamp": "2026-08-06T14:30:00Z",
        "owner_msg_id": owner_msg_id,
        "owner_action": "approved_skip",
    } for pid in phase_ids]
    (ckpt / "phase_skip_approvals.json").write_text(json.dumps({"approvals": approvals}))


# ---------------------------------------------------------------------------
# 1. SKIP-RECORD REFUSAL (AF-QC-SKIP)
# ---------------------------------------------------------------------------
def _check_qc_phase_skip_record_refused_in_load_skip_approvals():
    fails = []
    rd = _run_dir("fix2_skip_load_")
    owner_msg_id = "real-owner-msg-001"
    _write_skip_approval(rd, [QC_PHASES[1], NON_QC_PHASE],
                         owner_msg_id=owner_msg_id)  # P-PROMPT-QC + P3-ARC
    # FIXTURE FIX: this run dir has no cc_task_id / reachable Command Center, so
    # the real owner-message oracle is legitimately UNDETERMINED — and production
    # correctly fails closed on that (AF-FORGED-APPROVAL, "undetermined never
    # opens the gate"). That refusal is CORRECT and must never be weakened. What
    # THIS test is actually proving is a different, later gate: that once an
    # owner_msg_id is authenticated, a QC-phase skip is STILL refused. So the
    # fixture stubs the oracle to resolve the exact id it wrote — i.e. it makes
    # the approval genuinely verifiable — isolating AF-QC-SKIP from the separate,
    # correctly-fail-closed AF-FORGED-APPROVAL path.
    with patch.object(rsd, "_resolve_owner_msg_ids",
                      return_value=frozenset({owner_msg_id})):
        approvals = rsd.load_skip_approvals(rd)
    if QC_PHASES[1] in approvals:
        fails.append(f"AF-QC-SKIP: QC phase {QC_PHASES[1]!r} must NOT be in "
                     f"load_skip_approvals, got {sorted(approvals)}")
    if NON_QC_PHASE not in approvals:
        fails.append(f"KNOWN-GOOD CONTROL: non-QC phase {NON_QC_PHASE!r} skip must "
                     "still be honored (control is broken if it is not)")
    print(f"FIX2-SKIP load_skip_approvals   -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_qc_phase_skip_record_refused_in_load_skip_approvals():
    fails = _check_qc_phase_skip_record_refused_in_load_skip_approvals()
    assert not fails, "\n".join(fails)


def _check_qc_phase_skip_record_refused_in_check_phase_preconditions():
    fails = []
    rd = _run_dir("fix2_skip_precond_")
    _write_skip_approval(rd, [QC_PHASES[1]])  # P-PROMPT-QC
    # P4-RENDER (order 4.9) requires P-PROMPT-QC (order 4.8) prior. The skip must
    # NOT satisfy it -> AF-PHASE-SKIPPED still fires naming P-PROMPT-QC.
    reason = bd.check_phase_preconditions(rd, "P4-RENDER", [QC_PHASES[1]])
    if not reason or "AF-PHASE-SKIPPED" not in reason or QC_PHASES[1] not in reason:
        fails.append(f"FIX2-SKIP: check_phase_preconditions must STILL fail with "
                     f"AF-PHASE-SKIPPED naming {QC_PHASES[1]!r} despite its skip "
                     f"record, got {reason!r}")
    # Control: a NON-QC phase skip IS honored (P3-ARC).
    rd2 = _run_dir("fix2_skip_precond_control_")
    _write_skip_approval(rd2, [NON_QC_PHASE])
    if bd.check_phase_preconditions(rd2, "P4-RENDER", [NON_QC_PHASE]):
        fails.append("KNOWN-GOOD CONTROL: a non-QC phase skip must satisfy the "
                     "precondition (control is broken if it does not)")
    print(f"FIX2-SKIP check_phase_preconds   -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_qc_phase_skip_record_refused_in_check_phase_preconditions():
    fails = _check_qc_phase_skip_record_refused_in_check_phase_preconditions()
    assert not fails, "\n".join(fails)


def _check_qc_phase_skip_record_refused_in_guard_missing_attestations():
    fails = []
    rd = _run_dir("fix2_skip_guard_")
    _write_skip_approval(rd, [QC_PHASES[1]])
    phases = [
        {"id": QC_PHASES[1], "order": 4.8},
        {"id": "P4-RENDER", "order": 4.9},
        {"id": "P9-DELIVER", "order": 9},
    ]
    # phase_skip_approvals passed from the runner's load_skip_approvals is ALREADY
    # filtered (QC phase absent), but the guard must ALSO refuse a directly-seeded
    # set containing the QC phase (belt and braces at pre-delivery).
    missing = guard.missing_attestations(
        rd, phases, phase_skip_approvals={QC_PHASES[1]}, target_phase_id="P4-RENDER")
    if QC_PHASES[1] not in missing:
        fails.append(f"FIX2-SKIP: guard.missing_attestations must still list "
                     f"{QC_PHASES[1]!r} as missing despite a skip set naming it, "
                     f"got {missing}")
    print(f"FIX2-SKIP guard.missing         -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_qc_phase_skip_record_refused_in_guard_missing_attestations():
    fails = _check_qc_phase_skip_record_refused_in_guard_missing_attestations()
    assert not fails, "\n".join(fails)


def _check_qc_phase_skip_never_satisfies_next_required_phase():
    fails = []
    phases = rsd.load_manifest()["phases"]
    # Attest every NON-QC phase so the ONLY phases remaining are the QC phases.
    # (They remain required — a skip record can never satisfy a QC phase.)
    all_attested = [{"phase_id": p["id"], "artifact_sha": "x"} for p in phases
                    if p["id"] not in bd.UNSKIPPABLE_QC_PHASES]
    rd = _run_dir("fix2_skip_next_")
    ckpt = rd / "working" / "checkpoints"
    ckpt.mkdir(parents=True, exist_ok=True)
    (ckpt / "process_manifest.json").write_text(
        json.dumps({"phase_attestations": all_attested}))
    # A skip record naming EVERY QC phase (all four).
    _write_skip_approval(rd, list(bd.UNSKIPPABLE_QC_PHASES))
    ph, _k, _n = rsd._next_required_phase(rd, phases)
    if ph is None or ph["id"] not in bd.UNSKIPPABLE_QC_PHASES:
        fails.append(f"FIX2-SKIP: --next must STILL serve a QC phase despite skip "
                     f"records naming all four QC phases (the skip must never satisfy "
                     f"a QC phase), got {ph and ph['id']!r}")
    # Control: a NON-QC phase skip IS honored -> --next advances past it.
    rd2 = _run_dir("fix2_skip_next_control_")
    ckpt2 = rd2 / "working" / "checkpoints"
    ckpt2.mkdir(parents=True, exist_ok=True)
    (ckpt2 / "process_manifest.json").write_text(
        json.dumps({"phase_attestations": all_attested}))
    _write_skip_approval(rd2, [NON_QC_PHASE])
    ph2, _k2, _n2 = rsd._next_required_phase(rd2, phases)
    if ph2 is not None and ph2["id"] == NON_QC_PHASE:
        fails.append(f"KNOWN-GOOD CONTROL: --next must treat a NON-QC skip as "
                     f"satisfied and NOT serve {NON_QC_PHASE!r}, but it did")
    print(f"FIX2-SKIP --next turn-gate     -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_qc_phase_skip_never_satisfies_next_required_phase():
    fails = _check_qc_phase_skip_never_satisfies_next_required_phase()
    assert not fails, "\n".join(fails)


# ---------------------------------------------------------------------------
# 2. PLACEHOLDER FAIL (AF-QC-PLACEHOLDER at attest)
# ---------------------------------------------------------------------------
def _check_placeholder_report_attest_refused_all_four_qc_phases():
    fails = []
    report_files = {
        "P1Q-COPY-QC": "copy_qc_report.json",
        "P-PROMPT-QC": "prompt_qc_report.json",
        "P-TYPO-QC": "typography_qc_report.json",
        "P-SHIFT-QC": "priority_shift_report.json",
    }
    for phase, fname in report_files.items():
        rd = _run_dir(f"fix2_placeholder_{phase}_", {fname: _placeholder_report()})
        try:
            rsd.attest_phase(rd, phase, "qc-specialist-presentations",
                             "qc_pass_measurer", "deadbeef")
            fails.append(f"AF-QC-PLACEHOLDER: {phase} attested a 3-byte '{{}}' "
                         "placeholder report — it MUST refuse")
        except SystemExit as e:
            if e.code != 2:
                fails.append(f"{phase}: placeholder attest should exit 2, got {e.code}")
    print(f"FIX2-PLACEHOLDER all-4-attest   -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_placeholder_report_attest_refused_all_four_qc_phases():
    fails = _check_placeholder_report_attest_refused_all_four_qc_phases()
    assert not fails, "\n".join(fails)


def _check_verdict_less_big_report_attest_refused():
    fails = []
    # A report LARGER than 256 bytes but with no per-slide verdicts (a fat rubber
    # stamp) must ALSO be refused — size alone is not real QC.
    rd = _run_dir("fix2_rubberstamp_", {"copy_qc_report.json": {
        "gate": "Phase 1Q", "average": 9.1, "pass": True,
        "qc_independence": {"graded_by": "qc-specialist-presentations",
                            "independent": True, "builder": "slide-copywriter",
                            "self_graded": False},
        "filler": "x" * 1000,  # fat but verdict-less
    }})
    try:
        rsd.attest_phase(rd, "P1Q-COPY-QC", "qc-specialist-presentations",
                         "qc_pass_measurer", "deadbeef")
        fails.append("AF-QC-PLACEHOLDER: a fat but verdict-less report must be "
                     "refused (size alone is not real QC)")
    except SystemExit as e:
        if e.code != 2:
            fails.append(f"verdict-less attest should exit 2, got {e.code}")
    print(f"FIX2-PLACEHOLDER verdict-less    -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_verdict_less_big_report_attest_refused():
    fails = _check_verdict_less_big_report_attest_refused()
    assert not fails, "\n".join(fails)


# ---------------------------------------------------------------------------
# 3. REAL REPORT PASS (the known-good control)
# ---------------------------------------------------------------------------
def _check_real_report_attests_for_all_four_qc_phases():
    fails = []
    specs = {
        "P1Q-COPY-QC": ("copy_qc_report.json", "Phase 1Q", "slide-copywriter",
                        "qc-specialist-presentations", "per_slide_scores"),
        "P-PROMPT-QC": ("prompt_qc_report.json", "Phase Prompt-QC",
                        "prompt-author-presentations", "qc-specialist-prompt-presentations",
                        "slides"),
        "P-TYPO-QC": ("typography_qc_report.json", "Phase Typography-QC",
                      "typography-architect", "qc-specialist-typography-presentations",
                      "slides"),
        "P-SHIFT-QC": ("priority_shift_report.json", "AF-PRIORITY-SHIFT",
                       "qc-specialist-presentations", "qc-specialist-presentations",
                       "slides"),
    }
    for phase, (fname, gate, builder, reviewer, key) in specs.items():
        rep = _real_report(gate, builder, reviewer, key=key)
        if phase == "P-SHIFT-QC":
            # shift report is a 14-item checklist + per-slide verdicts
            rep["items"] = [{"item": f"i{i}", "pass": True, "evidence": "x"}
                            for i in range(14)]
        rd = _run_dir(f"fix2_real_{phase}_", {fname: rep})
        try:
            rsd.attest_phase(rd, phase, "qc-specialist-presentations",
                             "qc_pass_measurer", "deadbeef")
        except SystemExit as e:
            fails.append(f"{phase}: real 20-slide report attestation should pass, "
                         f"got exit {e.code}")
        pm_path = rd / "working" / "checkpoints" / "process_manifest.json"
        if not pm_path.exists():
            fails.append(f"{phase}: real report attest wrote no process_manifest")
            continue
        pm = json.loads(pm_path.read_text())
        attested = [a.get("phase_id") for a in pm.get("phase_attestations", [])]
        if phase not in attested:
            fails.append(f"{phase}: real report attest did not record the phase")
    print(f"FIX2-REAL all-4-attest          -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_real_report_attests_for_all_four_qc_phases():
    fails = _check_real_report_attests_for_all_four_qc_phases()
    assert not fails, "\n".join(fails)


# ---------------------------------------------------------------------------
# 4. check_qc_reports_real aggregate floor (used by the pre-delivery guard)
# ---------------------------------------------------------------------------
def _check_aggregate_report_floor():
    fails = []
    # Placeholder copy report + REAL prompt/typography/shift reports -> the
    # aggregate floor must fail SPECIFICALLY on the placeholder copy report.
    rd = _run_dir("fix2_agg_placeholder_", {
        "copy_qc_report.json": _placeholder_report(),
        "prompt_qc_report.json": _real_report("Phase Prompt-QC",
                                              "prompt-author-presentations",
                                              "qc-specialist-prompt-presentations",
                                              key="slides"),
        "typography_qc_report.json": _real_report("Phase Typography-QC",
                                                  "typography-architect",
                                                  "qc-specialist-typography-presentations",
                                                  key="slides"),
        "priority_shift_report.json": _real_report("AF-PRIORITY-SHIFT",
                                                   "qc-specialist-presentations",
                                                   "qc-specialist-presentations",
                                                   key="slides"),
    })
    r = bd.check_qc_reports_real(rd)
    if not r or "AF-QC-PLACEHOLDER" not in r or "copy_qc_report.json" not in r:
        fails.append(f"aggregate floor must fail on a placeholder copy report, got {r!r}")
    # All four real reports -> aggregate floor passes.
    specs = {
        "copy_qc_report.json": _real_report("Phase 1Q", "slide-copywriter",
                                            "qc-specialist-presentations"),
        "prompt_qc_report.json": _real_report("Phase Prompt-QC",
                                              "prompt-author-presentations",
                                              "qc-specialist-prompt-presentations",
                                              key="slides"),
        "typography_qc_report.json": _real_report("Phase Typography-QC",
                                                  "typography-architect",
                                                  "qc-specialist-typography-presentations",
                                                  key="slides"),
        "priority_shift_report.json": _real_report("AF-PRIORITY-SHIFT",
                                                   "qc-specialist-presentations",
                                                   "qc-specialist-presentations",
                                                   key="slides"),
    }
    rd2 = _run_dir("fix2_agg_real_", specs)
    r2 = bd.check_qc_reports_real(rd2)
    if r2:
        fails.append(f"aggregate floor must PASS with four real 20-slide reports, "
                     f"got {r2!r}")
    print(f"FIX2-AGGREGATE floor            -> {'PASS' if not fails else 'FAIL'}")
    return fails


def test_aggregate_report_floor():
    fails = _check_aggregate_report_floor()
    assert not fails, "\n".join(fails)


def main():
    fails = []
    for fn in [_check_qc_phase_skip_record_refused_in_load_skip_approvals,
               _check_qc_phase_skip_record_refused_in_check_phase_preconditions,
               _check_qc_phase_skip_record_refused_in_guard_missing_attestations,
               _check_qc_phase_skip_never_satisfies_next_required_phase,
               _check_placeholder_report_attest_refused_all_four_qc_phases,
               _check_verdict_less_big_report_attest_refused,
               _check_real_report_attests_for_all_four_qc_phases,
               _check_aggregate_report_floor]:
        try:
            fails += fn()
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{fn.__name__} raised {exc!r}")
    print("=" * 60)
    if fails:
        print(f"FIX-2 QC TEST: FAIL ({len(fails)} failing assertion(s))")
        for f in fails:
            print("  - " + f)
        raise SystemExit(1)
    print("FIX-2 QC TEST: PASS — QC phases structurally unskippable + real report floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
