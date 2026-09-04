"""Tests for the T1 QC-gate TEETH — the deterministic re-measure behind the three
report-only QC gates (_chk_copy_qc / _chk_typography_qc / _chk_speech_qc).

The legacy gates validated only the report's SHAPE (gate string, average >= 8.5, no
triggered autofails, pass:true, independent-reviewer provenance) and NEVER opened the
artifact they graded — so an agent could type 8.9/pass:true over a deck whose real copy
violates the AF-COPY-BAND character bands, or a design system whose declared tokens are
below the AF-FONT-FLOOR floors, or a speech that does not fill the requested duration,
and it sailed through. The teeth close exactly that gap by RE-MEASURING the on-disk
artifacts (check_prompt_qc_teeth / check_image_qc_vision pattern):

  * _chk_copy_qc          -> check_copy_qc_teeth: re-derives truth from the ACTUAL
                             rendered slides.json copy[] (bands + per-slide coverage);
  * _chk_typography_qc    -> check_typography_qc_teeth: re-measures the
                             working/typography/type_layout_system.md tokens
                             (min_body_pt / type_scale_steps / min_contrast_ratio)
                             against the AF-FONT-FLOOR floors;
  * _chk_speech_qc        -> check_speech_qc_teeth: re-parses the REAL speech file
                             (duration floor vs target_talk_minutes x 120 wpm +
                             AF-SPEECH-HOOK-COUNT engine).

Per gate, BOTH directions are proven:
  * a FABRICATED PASS report (shape-valid, pass:true, independent reviewer) over a
    CONTRADICTING real artifact must FAIL naming the EXACT discrepancy;
  * a GENUINE report matching a COMPLIANT real artifact must PASS;
plus the D10 defer controls (missing input that is legitimately not yet produced
defers; present-but-broken fails; a report grading a nonexistent speech is a
fabricated pass and FAILS).

No network, no credentials. Stdlib + pytest/tmp_path only — the gates must run
identically on a deployed client box.
"""

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402


def _indep(reviewer="qc-specialist-presentations", builder="slide-copywriter"):
    """The independent-reviewer provenance block every passing QC report must carry
    (AF-QC-INDEPENDENCE)."""
    return {"graded_by": reviewer, "independent": True,
            "builder": builder, "self_graded": False}


# ---------------------------------------------------------------------------
# COPY-QC teeth — re-derive truth from the ACTUAL rendered slides.json copy[]
# ---------------------------------------------------------------------------

def _copy_run(tmp_path, copy_map, target_minutes=None, report=None):
    """Build a run dir with a slides.json carrying copy_map {slide: [copy[]]}.
    Optionally writes intake.json and the copy-QC report. Returns the run dir."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    slides = [{"slide": s, "scene": "x", "copy": c} for s, c in sorted(copy_map.items())]
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    if target_minutes is not None:
        (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"target_talk_minutes": target_minutes}))
    if report is not None:
        (rd / "working" / "qc" / "copy_qc_report.json").write_text(json.dumps(report))
    return rd


def _copy_report(report, slides):
    """Full per-slide copy-QC report (gate/avg/pass/provenance + per_slide_scores)."""
    return {
        "gate": "Phase 1Q",
        "average": report.get("average", 9.1),
        "triggered_autofails": [],
        "pass": True,
        "qc_independence": _indep(),
        "per_slide_scores": [
            {"slide": s, "average": 9.0, "pass": True, "notes": "clean"}
            for s in slides
        ],
    }


_COMPLIANT = {
    1: ["Northwind Co", "Converting beat one into repeatable revenue"],
    2: ["Northwind Co", "Converting beat two into repeatable revenue"],
}
_HEADLINE_TINY = {1: ["X", "Converting beat one into repeatable revenue"]}
_BULLET_OVER = {
    1: ["Northwind Co", "Converting beat one into repeatable revenue",
        "Established workflow", "Clear call to action", "Measurable results",
        "Fourth bullet here", "Fifth bullet extra"],
}
_SLIDE_TOTAL_SHORT = {1: ["Northwind Co"]}


def test_copy_qc_fabricated_pass_fails_naming_short_headline(tmp_path):
    """A shape-valid pass:true copy-QC report over real copy whose headline is 1 char
    (below the 12-char floor) must FAIL naming the exact discrepancy."""
    rd = _copy_run(tmp_path, _HEADLINE_TINY, target_minutes=30,
                   report=_copy_report({}, [1]))
    reason = bd._chk_copy_qc(rd / "working" / "qc" / "copy_qc_report.json")
    assert reason, "fabricated pass over a 1-char headline must FAIL"
    assert "AF-COPY-QC" in reason, reason
    assert "HEADLINE" in reason and "slide 01" in reason, reason
    assert "1 chars" in reason and "12-60" in reason, reason


def test_copy_qc_fabricated_pass_fails_naming_bullets_and_total(tmp_path):
    """A shape-valid pass:true copy-QC report over real copy with 4 bullets (over the
    3-bullet max) AND a 12-char slide total (under the 40-char floor) must FAIL naming
    both discrepancies."""
    rd = _copy_run(tmp_path, _BULLET_OVER, target_minutes=30,
                   report=_copy_report({}, [1]))
    reason = bd._chk_copy_qc(rd / "working" / "qc" / "copy_qc_report.json")
    assert reason, "fabricated pass over over-bulleted/short-total copy must FAIL"
    assert "AF-COPY-QC" in reason, reason
    assert "4 bullets" in reason, reason
    assert "3-bullet max" in reason, reason


def test_copy_qc_genuine_report_over_compliant_copy_passes(tmp_path):
    """A genuine copy-QC report over band-compliant copy must PASS ("")."""
    rd = _copy_run(tmp_path, _COMPLIANT, target_minutes=30,
                   report=_copy_report({}, [1, 2]))
    assert bd._chk_copy_qc(rd / "working" / "qc" / "copy_qc_report.json") == ""


def test_copy_qc_coverage_gap_fails(tmp_path):
    """A pass:true report grading only 1 of 2 rendered slides is a partial rubber stamp
    and must FAIL naming the uncovered slide."""
    rd = _copy_run(tmp_path, _COMPLIANT, target_minutes=30,
                   report=_copy_report({}, [1]))
    reason = bd._chk_copy_qc(rd / "working" / "qc" / "copy_qc_report.json")
    assert reason, "partial-coverage copy-QC pass must FAIL"
    assert "AF-COPY-QC" in reason and "1 of 2" in reason, reason
    assert "slides 2" in reason, reason


def test_copy_qc_no_slides_json_defers(tmp_path):
    """No slides.json yet (genuine pre-copy state) -> the teeth DEFER; the upstream
    schema / AF-P1 / slide-count gates own that absence. The shape-valid report alone
    passes (the legacy contract)."""
    rd = tmp_path / "run"
    (rd / "working" / "qc").mkdir(parents=True)
    (rd / "working" / "qc" / "copy_qc_report.json").write_text(
        json.dumps(_copy_report({}, [1])))
    assert bd._chk_copy_qc(rd / "working" / "qc" / "copy_qc_report.json") == ""


# ---------------------------------------------------------------------------
# TYPOGRAPHY-QC teeth — re-measure the design-system tokens
# ---------------------------------------------------------------------------

def _typo_run(tmp_path, layout_text, design_system=True, report=None, slides_n=2,
              dark=False):
    """Build a run dir with working/typography/type_layout_system.md (+ optional
    design_system.json + typography-QC report). Returns the run dir."""
    rd = tmp_path / "run"
    (rd / "working" / "typography").mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    if layout_text is not None:
        (rd / "working" / "typography" / "type_layout_system.md").write_text(layout_text)
    if design_system:
        (rd / "working" / "typography" / "design_system.json").write_text(
            json.dumps({"per_slide": [
                {"slide": i, "archetype": "A1-hero"} for i in range(1, slides_n + 1)]}))
    if report is not None:
        (rd / "working" / "qc" / "typography_qc_report.json").write_text(
            json.dumps(report))
    if dark:
        (rd / "working" / "copy").mkdir(parents=True)
        (rd / "working" / "copy" / "intake.json").write_text(
            json.dumps({"client_dark_theme": True}))
    return rd


def _typo_report(slides_n):
    return {
        "gate": "Phase Typography-QC",
        "average": 9.0,
        "triggered_autofails": [],
        "pass": True,
        "qc_independence": _indep("qc-specialist-typography-presentations",
                                  "typography-architect"),
        "per_slide_scores": [
            {"slide": i, "average": 9.0, "pass": True, "archetype": "A1-hero"}
            for i in range(1, slides_n + 1)
        ],
    }


_COMPLIANT_LAYOUT = "# Type Layout System\nmin_body_pt: 24\ntype_scale_steps: 5\nmin_contrast_ratio: 6.5\n"
_SUBFLOOR_LAYOUT = "# Type Layout System\nmin_body_pt: 14\ntype_scale_steps: 6\nmin_contrast_ratio: 3.1\n"


def test_typography_qc_fabricated_pass_fails_naming_tokens(tmp_path):
    """A shape-valid pass:true typography-QC report over a below-floor token set
    (14pt body / 6 steps / 3.1:1) must FAIL naming each exact discrepancy."""
    rd = _typo_run(tmp_path, _SUBFLOOR_LAYOUT, report=_typo_report(2))
    reason = bd._chk_typography_qc(rd / "working" / "qc" / "typography_qc_report.json")
    assert reason, "fabricated typography-QC pass over sub-floor tokens must FAIL"
    assert "AF-TYPOGRAPHY-QC" in reason, reason
    assert "min_body_pt=14" in reason, reason
    assert "type_scale_steps=6" in reason, reason
    assert "min_contrast_ratio=3.1" in reason, reason


def test_typography_qc_genuine_report_over_compliant_tokens_passes(tmp_path):
    """A genuine typography-QC report over a compliant token set (24pt / 5 steps /
    6.5:1) must PASS ("")."""
    rd = _typo_run(tmp_path, _COMPLIANT_LAYOUT, report=_typo_report(2))
    assert bd._chk_typography_qc(rd / "working" / "qc" / "typography_qc_report.json") == ""


def test_typography_qc_design_present_tokens_missing_fails(tmp_path):
    """Design system exists but type_layout_system.md is MISSING -> the report's pass
    claims a design with no measurable tokens and must FAIL (D10: present-input-but-
    broken = fail, mirroring check_font_floor)."""
    rd = _typo_run(tmp_path, None, report=_typo_report(2))
    reason = bd._chk_typography_qc(rd / "working" / "qc" / "typography_qc_report.json")
    assert reason, "missing token file over a present design system must FAIL"
    assert "AF-TYPOGRAPHY-QC" in reason and "type_layout_system.md" in reason, reason


def test_typography_qc_pre_typography_defers(tmp_path):
    """No type tokens AND no design system yet (genuine pre-typography state) -> the
    teeth DEFER; the shape-valid report alone passes (D10: missing input not yet due)."""
    rd = _typo_run(tmp_path, None, design_system=False, report=_typo_report(2))
    assert bd._chk_typography_qc(rd / "working" / "qc" / "typography_qc_report.json") == ""


def test_typography_qc_dark_theme_raises_floors(tmp_path):
    """Under a client_dark_theme opt-in the floors rise to 22pt / 7.0:1; a report
    passing an 18pt / 4.5:1 set must FAIL naming the dark floors."""
    dark_compliant = ("# Type Layout System\nmin_body_pt: 18\ntype_scale_steps: 5\n"
                      "min_contrast_ratio: 4.5\n")
    rd = _typo_run(tmp_path, dark_compliant, report=_typo_report(2), dark=True)
    reason = bd._chk_typography_qc(rd / "working" / "qc" / "typography_qc_report.json")
    assert reason, "a dark-opt-in deck at light floors must FAIL"
    assert "AF-TYPOGRAPHY-QC" in reason, reason
    assert "dark-theme" in reason, reason


# ---------------------------------------------------------------------------
# SPEECH-QC teeth — re-parse the REAL speech file
# ---------------------------------------------------------------------------

def _speech_run(tmp_path, speech_text, target_minutes=30, report=None):
    """Build a run dir with the canonical PRESENTERS-SPEECH.md (plus intake +
    optional speech-QC report). Returns the run dir."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "delivery").mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    if speech_text is not None:
        (rd / "working" / "delivery" / "PRESENTERS-SPEECH.md").write_text(speech_text)
    if target_minutes is not None:
        (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"target_talk_minutes": target_minutes}))
    if report is not None:
        (rd / "working" / "qc" / "speech_qc_report.json").write_text(json.dumps(report))
    return rd


def _speech_report():
    return {
        "gate": "Phase Speech-QC",
        "average": 9.0,
        "triggered_autofails": [],
        "pass": True,
        "qc_independence": _indep("qc-specialist-speech-presentations",
                                  "presenters-speech-writer"),
    }


def test_speech_qc_fabricated_pass_fails_naming_short_speech(tmp_path):
    """A shape-valid pass:true speech-QC report over a real speech of 3,400 words
    (floor for 30 min = 3,600) must FAIL naming the exact word-count discrepancy."""
    rd = _speech_run(tmp_path, " ".join(["word"] * 3400), target_minutes=30,
                     report=_speech_report())
    reason = bd._chk_speech_qc(rd / "working" / "qc" / "speech_qc_report.json")
    assert reason, "fabricated speech-QC pass over a short speech must FAIL"
    assert "AF-SPEECH-QC" in reason, reason
    assert "3400 words" in reason, reason
    assert "3600 words" in reason and "120 wpm" in reason, reason


def test_speech_qc_genuine_report_over_full_speech_passes(tmp_path):
    """A genuine speech-QC report over a speech that fills the duration (3,600 words
    for 30 min) must PASS ("")."""
    rd = _speech_run(tmp_path, " ".join(["word"] * 3600), target_minutes=30,
                     report=_speech_report())
    assert bd._chk_speech_qc(rd / "working" / "qc" / "speech_qc_report.json") == ""


def test_speech_qc_report_without_speech_fails(tmp_path):
    """A speech-QC report grading a speech that does not exist is a FABRICATED pass
    (D10: present-input-but-broken = fail) — the report cannot be trusted."""
    rd = _speech_run(tmp_path, None, target_minutes=30, report=_speech_report())
    reason = bd._chk_speech_qc(rd / "working" / "qc" / "speech_qc_report.json")
    assert reason, "a speech-QC report over a nonexistent speech must FAIL"
    assert "AF-SPEECH-QC" in reason, reason
    assert "PRESENTERS-SPEECH.md" in reason, reason


def test_speech_qc_absent_report_defers(tmp_path):
    """No speech-QC report yet (pre-delivery) -> the gate DEFERS (""), even when the
    speech exists. The report is the gate's trigger; this is the unchanged
    conditional-by-design contract. The manifest calls the checker with None for an
    absent artifact (the checker never sees a dangling path)."""
    rd = _speech_run(tmp_path, " ".join(["word"] * 3600), target_minutes=30)
    # Teeth, called directly, also defer when speech exists but no report does.
    assert bd.check_speech_qc_teeth(rd) == ""
    # The gate itself defers on the absent report (path is None from the manifest).
    assert bd._chk_speech_qc(None) == ""


def test_speech_qc_under_sung_hook_fails(tmp_path):
    """A speech-QC report marked pass over a speech that sings the canonical hook only
    1x (AF-SPEECH-HOOK-COUNT floor is 5) must FAIL naming the hook-count engine
    trigger."""
    hook = "Your pipeline, transformed."
    intake = {"target_talk_minutes": 30, "hook": hook}
    body = " ".join(["word"] * 3600)
    speech = body + "\n" + hook  # exactly one char-exact hook occurrence
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "delivery").mkdir(parents=True)
    (rd / "working" / "qc").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
    (rd / "working" / "delivery" / "PRESENTERS-SPEECH.md").write_text(speech)
    (rd / "working" / "qc" / "speech_qc_report.json").write_text(
        json.dumps(_speech_report()))
    reason = bd._chk_speech_qc(rd / "working" / "qc" / "speech_qc_report.json")
    assert reason, "a pass over an under-sung hook must FAIL"
    assert "AF-SPEECH-QC" in reason, reason
    assert "AF-SPEECH-HOOK-COUNT" in reason, reason
