"""PD-200 — the render's speech checks read the folder the speech is written to.

The P9-SPEECH step writes `working/deliverables/PRESENTERS-SPEECH.md`, but both
render-time speech checks (`_chk_speech_length` and `check_speech_qc_teeth`)
searched five older places and never that one. So a too-short speech was never
caught by the length rule, and a later render refused an honest speech-QC report
as "fabricated" because it could not find the speech the report graded.

PD-200 fixes it with one module list, `SPEECH_CANDIDATE_RELS`, with
`working/deliverables/PRESENTERS-SPEECH.md` first, used by both checks, and
moves the hook-count re-measure above the "no usable duration target" return so
it runs in both cases.

Acceptance rows (A1), the five probes from the finding:
  1. 50-word speech at working/deliverables/ -> AF-SPEECH-SHORT
  2. full speech there plus a report -> pass
  3. no speech plus a report -> the "MISSING" failure
  4. no speech and no report -> pass
  5. no talk length in the interview, speech present, hook missing -> the hook
     failure is returned

Everything here is files on disk. No network, no model call, no live service.
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

DELIVERABLES_SPEECH = "working/deliverables/PRESENTERS-SPEECH.md"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _speech_run(tmp_path, words=None, target_minutes=None, report=False,
                name="run"):
    """A run dir with the speech where P9-SPEECH writes it (when `words` is
    given), an intake target (when `target_minutes` is given), and the
    speech-QC report (when `report` is true)."""
    rd = tmp_path / name
    rd.mkdir(parents=True, exist_ok=True)
    if target_minutes is not None:
        intake = rd / "working" / "copy" / "intake.json"
        intake.parent.mkdir(parents=True, exist_ok=True)
        intake.write_text(json.dumps({"target_talk_minutes": target_minutes}))
    if words is not None:
        speech = rd / DELIVERABLES_SPEECH
        speech.parent.mkdir(parents=True, exist_ok=True)
        speech.write_text(" ".join(["word"] * words))
    if report:
        report_path = rd / "working" / "qc" / "speech_qc_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "gate": "Phase Speech-QC", "average": 9.0,
            "triggered_autofails": [], "pass": True,
            "qc_independence": {"graded_by": "qc-specialist-independent-reviewer",
                                "independent": True}}))
    return rd


class _HookFires:
    """Stand-in for pitch_engines_check whose hook-count engine fires."""

    def run(self, run_dir, phase="SPEECH-QC"):
        return [{"code": "AF-SPEECH-HOOK-COUNT",
                 "detail": "hook sung 1x, needs 5-20x"}]


# ---------------------------------------------------------------------------
# PD-200 A1 — the five probe cases
# ---------------------------------------------------------------------------

def test_candidate_list_looks_in_deliverables_first():
    """One list, deliverables first, then the five older names in their old
    order — both checks can only ever measure the same file."""
    assert bd.SPEECH_CANDIDATE_RELS[0] == DELIVERABLES_SPEECH
    assert tuple(bd.SPEECH_CANDIDATE_RELS[1:]) == (
        "working/presenter-speech/speech.md",
        "working/delivery/PRESENTERS-SPEECH.md",
        "working/presenter-speech/PRESENTERS-SPEECH.md",
        "working/delivery/PRESENTER-SPEECH.md",
        "working/presenter-speech/PRESENTER-SPEECH.md",
    )


def test_a1_short_speech_in_deliverables_fails_af_speech_short(tmp_path):
    """50 words for a 30-minute talk, written where P9-SPEECH writes it ->
    the length gate now finds it and fails AF-SPEECH-SHORT."""
    rd = _speech_run(tmp_path, words=50, target_minutes=30)
    reason = bd._chk_speech_length(rd)
    assert "AF-SPEECH-SHORT" in reason, reason
    assert "50 words" in reason, reason


def test_a2_full_speech_in_deliverables_with_report_passes(tmp_path):
    """A full-length speech (30 min x 120 wpm = 3,600 words) there plus a
    report -> both checks pass instead of calling the report fabricated."""
    rd = _speech_run(tmp_path, words=3600, target_minutes=30, report=True)
    assert bd._chk_speech_length(rd) == ""
    assert bd.check_speech_qc_teeth(rd) == ""


def test_a3_no_speech_with_report_is_the_missing_failure(tmp_path):
    """Report present, no speech anywhere -> the report grades a speech that is
    not on disk: the MISSING / FABRICATED failure."""
    rd = _speech_run(tmp_path, report=True)
    reason = bd.check_speech_qc_teeth(rd)
    assert "AF-SPEECH-QC" in reason, reason
    assert "MISSING" in reason, reason


def test_a4_no_speech_and_no_report_passes(tmp_path):
    """Genuine pre-speech state: nothing to grade -> both checks defer."""
    rd = _speech_run(tmp_path)
    assert bd._chk_speech_length(rd) == ""
    assert bd.check_speech_qc_teeth(rd) == ""


def test_a5_no_talk_length_speech_present_hook_missing_returns_hook(tmp_path, monkeypatch):
    """No target_talk_minutes in the interview would formerly return a pass
    before the hook check ran. The hook check now runs in both cases, so a
    missing hook is returned even with no duration target."""
    rd = _speech_run(tmp_path, words=3600)  # speech present, no intake target
    monkeypatch.setattr(bd, "_import_pitch_engines_check", lambda: _HookFires())
    reason = bd.check_speech_qc_teeth(rd)
    assert "AF-SPEECH-QC" in reason, reason
    assert "hook-count" in reason, reason
