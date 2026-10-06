"""FIX 97 — Speech QC pacing arithmetic (the QC.md proof, both directions).

QC.md FIX 97: "A 60-minute fixture speech at 130 wpm passes P-SPEECH-QC when
TARGET_WPM=130, and one at 140 passes when TARGET_WPM=140; each fails at the
other target."

Proven here at three layers:

  1. THE PURE ARITHMETIC (the exact function the critic extracted and ran):
     _speech_pacing_deviation(words, target_minutes, target_wpm) vs
     SPEECH_PACING_BAND — PASS iff |words/TARGET_WPM - target_minutes| <= band.
     A 60-minute speech sized for 130 wpm (7,800 words) passes at TARGET_WPM=130
     and FAILS at 140 (7.14% > 7%); one sized for 140 (8,400 words) passes at 140
     and fails at 130 (7.69% > 7%). (A 10% band cannot discriminate 130 vs 140 —
     they are only ~7.7% apart — which is why the band is 0.07.)

  2. THE GATE (_chk_speech_length, the AF-SPEECH-SHORT / AF-SPEECH-PACING
     duration gate): the run's OWN target rate comes from intake.json
     (`target_wpm`, the key deck-intake-driver.py writes, matched
     case-insensitively because the intake schema's storeOn spelling is
     `TARGET_WPM`); SPEECH_TARGET_WPM is only the default when intake states
     none. The critic's finding — calls passing (words, target) only, so a
     130-wpm run behaved identically to a 140-wpm run — is closed.

  3. P-SPEECH-QC (check_speech_qc_teeth, the deterministic re-measure behind the
     phase gate): a genuine shape-valid pass:true report over a speech outside
     the band is REJECTED (AF-SPEECH-QC naming AF-SPEECH-PACING); the same
     speech at the correct target passes.

No network, no credentials. Stdlib + pytest/tmp_path only.
"""

import importlib.util
import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location("build_deck", SCRIPTS / "build_deck.py")
bd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bd)


# ---------------------------------------------------------------------------
# 1. The pure arithmetic — the exact fixtures the critic ran, both targets
# ---------------------------------------------------------------------------

def test_band_is_fix97_seven_pct():
    """The band that makes the proof satisfiable: 130 vs 140 wpm differ by
    ~7.1-7.7%, so the PASS-iff-|dev|<=band band must be <= 7% to discriminate."""
    assert bd.SPEECH_PACING_BAND == 0.07


def test_pure_arithmetic_60min_130wpm_passes_at_130_fails_at_140():
    """7,800 words = 60 min at 130 wpm. PASS iff |dev| <= band: 0% at 130
    (within), 7.14% at 140 (outside)."""
    dev_at_130 = bd._speech_pacing_deviation(7800, 60.0, 130)
    dev_at_140 = bd._speech_pacing_deviation(7800, 60.0, 140)
    assert dev_at_130 is not None and dev_at_130 <= bd.SPEECH_PACING_BAND
    assert dev_at_140 is not None and dev_at_140 > bd.SPEECH_PACING_BAND


def test_pure_arithmetic_60min_140wpm_passes_at_140_fails_at_130():
    """8,400 words = 60 min at 140 wpm. 0% at 140 (within), 7.69% at 130
    (outside)."""
    dev_at_140 = bd._speech_pacing_deviation(8400, 60.0, 140)
    dev_at_130 = bd._speech_pacing_deviation(8400, 60.0, 130)
    assert dev_at_140 is not None and dev_at_140 <= bd.SPEECH_PACING_BAND
    assert dev_at_130 is not None and dev_at_130 > bd.SPEECH_PACING_BAND


def test_pure_arithmetic_degenerate_inputs_return_none():
    """target<=0 or wpm<=0 cannot be divided -> None (no verdict, not a pass)."""
    assert bd._speech_pacing_deviation(100, 0, 130) is None
    assert bd._speech_pacing_deviation(100, -5, 130) is None
    assert bd._speech_pacing_deviation(100, 60.0, 0) is None
    assert bd._speech_pacing_deviation(100, 60.0, -1) is None


# ---------------------------------------------------------------------------
# 2. The gate — _chk_speech_length reads the run's OWN TARGET_WPM from intake
# ---------------------------------------------------------------------------

def _speech_run(tmp_path, words, intake, name="run"):
    """A run dir with intake.json (verbatim dict — the test controls the key
    spelling) and a PRESENTERS-SPEECH.md of `words` words."""
    rd = tmp_path / name
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "delivery").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
    (rd / "working" / "delivery" / "PRESENTERS-SPEECH.md").write_text(
        " ".join(["word"] * words))
    return rd


def test_gate_60min_130wpm_passes_when_target_130(tmp_path):
    """The QC.md proof, leg 1: 7,800 words passes P-SPEECH-QC-class gating when
    TARGET_WPM=130 (intake lowercase key, the driver's spelling)."""
    rd = _speech_run(tmp_path, 7800,
                     {"target_talk_minutes": 60, "target_wpm": 130})
    assert bd._chk_speech_length(rd) == ""


def test_gate_60min_130wpm_speech_fails_when_target_140(tmp_path):
    """The QC.md proof, leg 2: the SAME 7,800-word speech FAILS at
    TARGET_WPM=140 — 130 wpm effective is 7.14% off, outside the 7% band."""
    rd = _speech_run(tmp_path, 7800,
                     {"target_talk_minutes": 60, "target_wpm": 140})
    reason = bd._chk_speech_length(rd)
    assert reason, "7800w at TARGET_WPM=140 must FAIL (7.14% > 7%)"
    assert "AF-SPEECH-PACING" in reason, reason


def test_gate_60min_140wpm_passes_when_target_140(tmp_path):
    rd = _speech_run(tmp_path, 8400,
                     {"target_talk_minutes": 60, "target_wpm": 140})
    assert bd._chk_speech_length(rd) == ""


def test_gate_60min_140wpm_speech_fails_when_target_130(tmp_path):
    rd = _speech_run(tmp_path, 8400,
                     {"target_talk_minutes": 60, "target_wpm": 130})
    reason = bd._chk_speech_length(rd)
    assert reason, "8400w at TARGET_WPM=130 must FAIL (7.69% > 7%)"
    assert "AF-SPEECH-PACING" in reason, reason


def test_gate_reads_uppercase_target_wpm_key(tmp_path):
    """The intake question schema's storeOn spelling is TARGET_WPM; the driver
    writes lowercase. BOTH must resolve — a gate that only reads one spelling
    is the exact defect the critic proved."""
    rd = _speech_run(tmp_path, 7800,
                     {"target_talk_minutes": 60, "TARGET_WPM": 130})
    assert bd._chk_speech_length(rd) == ""
    rd2 = _speech_run(tmp_path, 7800,
                      {"target_talk_minutes": 60, "TARGET_WPM": 140}, name="run2")
    assert "AF-SPEECH-PACING" in bd._chk_speech_length(rd2)


def test_gate_defaults_to_speech_target_wpm_when_intake_omits_it(tmp_path):
    """No target_wpm in intake -> SPEECH_TARGET_WPM (140) is the default, so the
    7,800-word speech (130 wpm effective) is 7.14% off and fails."""
    rd = _speech_run(tmp_path, 7800, {"target_talk_minutes": 60})
    reason = bd._chk_speech_length(rd)
    assert reason and "AF-SPEECH-PACING" in reason, reason


def test_gate_short_speech_still_fails_af_speech_short_first(tmp_path):
    """Leg 1 unchanged: below the 120-wpm hard floor the failure is
    AF-SPEECH-SHORT (not the pacing code)."""
    rd = _speech_run(tmp_path, 3400, {"target_talk_minutes": 60, "target_wpm": 130})
    reason = bd._chk_speech_length(rd)
    assert "AF-SPEECH-SHORT" in reason, reason


def test_gate_out_of_band_but_above_floor_names_resize_target(tmp_path):
    """The failure message tells the writer exactly what to hit: 60 min x 140
    wpm = 8,400 words."""
    rd = _speech_run(tmp_path, 7800, {"target_talk_minutes": 60, "target_wpm": 140})
    reason = bd._chk_speech_length(rd)
    assert "8400 words" in reason, reason


# ---------------------------------------------------------------------------
# 3. P-SPEECH-QC — check_speech_qc_teeth re-measures the same band
# ---------------------------------------------------------------------------

def _genuine_report():
    return {"gate": "Phase Speech-QC", "average": 9.0,
            "triggered_autofails": [], "pass": True,
            "qc_independence": {"graded_by": "qc-specialist-independent-reviewer",
                                "independent": True}}


def _speech_run_with_report(tmp_path, words, intake, report):
    rd = _speech_run(tmp_path, words, intake, name="teeth")
    (rd / "working" / "qc").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "qc" / "speech_qc_report.json").write_text(json.dumps(report))
    return rd


def test_pspeech_qc_rejects_genuine_report_over_wrong_pace_speech(tmp_path):
    """A shape-valid pass:true report over a 7,800-word speech on a TARGET_WPM=140
    run is a fabricated pass — the speech is 7.14% off the band. The teeth
    REJECT it (AF-SPEECH-QC naming AF-SPEECH-PACING), mirroring
    _chk_speech_length's leg 2."""
    rd = _speech_run_with_report(
        tmp_path, 7800, {"target_talk_minutes": 60, "target_wpm": 140},
        _genuine_report())
    reason = bd.check_speech_qc_teeth(rd)
    assert reason, "genuine report over an out-of-band speech must FAIL"
    assert "AF-SPEECH-QC" in reason, reason
    assert "AF-SPEECH-PACING" in reason, reason


def test_pspeech_qc_passes_genuine_report_over_in_band_speech(tmp_path):
    """The same report over the same speech measured at the run's correct
    TARGET_WPM=130 (0% deviation) PASSES."""
    rd = _speech_run_with_report(
        tmp_path, 7800, {"target_talk_minutes": 60, "target_wpm": 130},
        _genuine_report())
    assert bd.check_speech_qc_teeth(rd) == ""


def test_pspeech_qc_teeth_match_gate_at_both_targets(tmp_path):
    """Lockstep: for BOTH fixtures the teeth and the gate return the same
    verdict — the report layer can never disagree with the duration gate."""
    for words, wpm, expect_pass in ((7800, 130, True), (7800, 140, False),
                                    (8400, 140, True), (8400, 130, False)):
        rd = _speech_run_with_report(
            tmp_path, words, {"target_talk_minutes": 60, "target_wpm": wpm},
            _genuine_report())
        gate = bd._chk_speech_length(rd)
        teeth = bd.check_speech_qc_teeth(rd)
        if expect_pass:
            assert gate == "", (words, wpm, gate)
            assert teeth == "", (words, wpm, teeth)
        else:
            assert "AF-SPEECH-PACING" in gate, (words, wpm, gate)
            assert "AF-SPEECH-PACING" in teeth, (words, wpm, teeth)
