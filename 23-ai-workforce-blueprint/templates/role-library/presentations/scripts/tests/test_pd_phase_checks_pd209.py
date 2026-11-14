#!/usr/bin/env python3
"""test_pd_phase_checks_pd209.py — PD-209 (Moderate, lane FL17).

Six step checks proved only that a file exists and is not empty. Each now
proves the content rule its own consumer already required:

  P0A-INTAKE            the intake passes build_deck._chk_intake
  P0B-PRIORITY          true_goal and a non-empty priority_stack
  P-3.5-RESEARCH-MAP    a non-empty slides list
  P-STYLE-PREVIEW       the manifest AND nine PNG sample images
  P7-TELEPROMPTER       the size floor AND the teleprompter content check
  P9-SPEECH-WEBINAR-INTRO  the audio file only (the framing template test
                        moved here, out of the step check)

Acceptance row A1 (PASS5-GATES.md, PD-209): one failing and one passing
fixture per step; the old self-test fixture `{"slides": [{"idx": 1}]}` no
longer passes P0A-INTAKE.

No network, no model call, no live service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64


def _run_dir(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    (rd / "working").mkdir(parents=True, exist_ok=True)
    return rd


def _write(rd: Path, rel: str, data) -> Path:
    p = rd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        p.write_text(json.dumps(data), encoding="utf-8")
    elif isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(data, encoding="utf-8")
    return p


def _real_intake(rd: Path, *, with_ledger: bool = True) -> Path:
    """A fully-provenanced intake.json (the shape build_deck._chk_intake wants)."""
    p = _write(rd, "working/copy/intake.json", {
        "interview_confirmed": True,
        "presentation_mode": "general",
        "audience_mode": "GENERAL",
        "target_talk_minutes": 20,
        "pre_presentation_capture": {
            "REPRESENTATION_MIX": "two presenters, mixed",
            "AUDIENCE_COMPOSITION": "founders and operators",
            "GROUNDED_CONTENT": "client notes plus three cited sources",
            "VISUAL_MIX": "photographic and diagram",
            "DARK_OK": True,
            "HOOK_SEED": "the number nobody expected",
        },
    })
    if with_ledger:
        _write(rd, "working/interview/intake_ledger.json", {
            "status": "complete",
            "entries": {qid: {"validated": True} for qid in (
                "representation_mix", "audience_composition_note",
                "grounded_content", "visual_mix", "dark_ok", "hook_seed")},
        })
    return p


# ---------------------------------------------------------------------------
# P0A-INTAKE
# ---------------------------------------------------------------------------
def test_p0a_real_intake_passes(tmp_path):
    rd = _run_dir(tmp_path)
    _real_intake(rd)
    ok, reasons = pv.PHASE_VERIFIERS["P0A-INTAKE"](rd)
    assert ok, f"a fully-provenanced intake must pass, got reasons={reasons}"


def test_p0a_bare_slides_json_fails(tmp_path):
    """The fixture the self-test used to call "valid" proves nothing."""
    rd = _run_dir(tmp_path)
    _write(rd, "working/copy/intake.json", {"slides": [{"idx": 1}]})
    ok, reasons = pv.PHASE_VERIFIERS["P0A-INTAKE"](rd)
    assert not ok, "a bare {\"slides\": [...]} intake.json must FAIL P0A-INTAKE"
    assert any("interview_confirmed" in r for r in reasons), f"got reasons={reasons}"


def test_p0a_intake_without_ledger_fails(tmp_path):
    """The six fields claimed but no turn-gated ledger = unprovenanced."""
    rd = _run_dir(tmp_path)
    _real_intake(rd, with_ledger=False)
    ok, reasons = pv.PHASE_VERIFIERS["P0A-INTAKE"](rd)
    assert not ok, "an intake without intake_ledger.json must FAIL"
    assert any("intake_ledger.json" in r for r in reasons), f"got reasons={reasons}"


# ---------------------------------------------------------------------------
# P0B-PRIORITY
# ---------------------------------------------------------------------------
def test_p0b_full_spec_passes(tmp_path):
    rd = _run_dir(tmp_path)
    _write(rd, "working/copy/priority_shift_spec.json", {
        "true_goal": "make the audience re-rank their own priorities",
        "priority_stack": ["speed", "cost", "trust"],
    })
    ok, reasons = pv.PHASE_VERIFIERS["P0B-PRIORITY"](rd)
    assert ok, f"a spec with true_goal and a stack must pass, got reasons={reasons}"


@pytest.mark.parametrize("spec,needle", [
    ({"true_goal": "", "priority_stack": ["speed"]}, "true_goal"),
    ({"true_goal": "a destination", "priority_stack": []}, "priority_stack"),
])
def test_p0b_empty_fields_fail(tmp_path, spec, needle):
    rd = _run_dir(tmp_path)
    _write(rd, "working/copy/priority_shift_spec.json", spec)
    ok, reasons = pv.PHASE_VERIFIERS["P0B-PRIORITY"](rd)
    assert not ok, f"{spec} must FAIL P0B-PRIORITY"
    assert any(needle in r for r in reasons), f"got reasons={reasons}"


# ---------------------------------------------------------------------------
# P-3.5-RESEARCH-MAP
# ---------------------------------------------------------------------------
def test_research_map_with_slides_passes(tmp_path):
    rd = _run_dir(tmp_path)
    _write(rd, "working/research/research_map.json",
           {"slides": [{"slide": 1, "research": ["r1"]}]})
    ok, reasons = pv.PHASE_VERIFIERS["P-3.5-RESEARCH-MAP"](rd)
    assert ok, f"a map with slides must pass, got reasons={reasons}"


def test_research_map_without_slides_fails(tmp_path):
    rd = _run_dir(tmp_path)
    _write(rd, "working/research/research_map.json", {"notes": "some prose"})
    ok, reasons = pv.PHASE_VERIFIERS["P-3.5-RESEARCH-MAP"](rd)
    assert not ok, "a map with no slides list must FAIL"
    assert any("slides" in r for r in reasons), f"got reasons={reasons}"


# ---------------------------------------------------------------------------
# P-STYLE-PREVIEW
# ---------------------------------------------------------------------------
def _style_samples(rd: Path, count: int, payload: bytes = PNG) -> None:
    _write(rd, "working/style-preview/style_samples_manifest.json",
           {"variants": ["a", "b", "c"]})
    for variant in "abc":
        for slide in range(1, (count // 3) + 1):
            _write(rd, f"working/style-preview/variant-{variant}-slide-{slide}.png",
                   payload)


def test_style_preview_nine_pngs_pass(tmp_path):
    rd = _run_dir(tmp_path)
    _style_samples(rd, 9)
    ok, reasons = pv.PHASE_VERIFIERS["P-STYLE-PREVIEW"](rd)
    assert ok, f"nine real PNG samples must pass, got reasons={reasons}"


def test_style_preview_manifest_only_fails(tmp_path):
    rd = _run_dir(tmp_path)
    _write(rd, "working/style-preview/style_samples_manifest.json",
           {"variants": ["a", "b", "c"]})
    ok, reasons = pv.PHASE_VERIFIERS["P-STYLE-PREVIEW"](rd)
    assert not ok, "the manifest alone must FAIL P-STYLE-PREVIEW"
    assert any("sample image" in r for r in reasons), f"got reasons={reasons}"


def test_style_preview_renamed_text_png_fails(tmp_path):
    rd = _run_dir(tmp_path)
    _style_samples(rd, 9, payload=b"not a png at all" * 8)
    ok, reasons = pv.PHASE_VERIFIERS["P-STYLE-PREVIEW"](rd)
    assert not ok, "a renamed text file must not count as a sample PNG"
    assert any("not a PNG" in r for r in reasons), f"got reasons={reasons}"


# ---------------------------------------------------------------------------
# P7-TELEPROMPTER
# ---------------------------------------------------------------------------
_TELEPROMPTER_FLOOR = pv._MIN_BYTES["teleprompter_html"]


def test_teleprompter_real_html_passes(tmp_path):
    rd = _run_dir(tmp_path)
    body = "<div class=\"slide\">Speak this line aloud.</div>\n"
    html = ("<html><body>" + body * (_TELEPROMPTER_FLOOR // len(body) + 1)
            + "</body></html>")
    _write(rd, "working/deliverables/presenter-teleprompter.html", html)
    ok, reasons = pv.PHASE_VERIFIERS["P7-TELEPROMPTER"](rd)
    assert ok, f"a real teleprompter must pass, got reasons={reasons}"


def test_teleprompter_renamed_text_passes_size_but_fails_content(tmp_path):
    rd = _run_dir(tmp_path)
    txt = "just some plain text. " * (_TELEPROMPTER_FLOOR // 20 + 1)
    _write(rd, "working/deliverables/presenter-teleprompter.html", txt)
    ok, reasons = pv.PHASE_VERIFIERS["P7-TELEPROMPTER"](rd)
    assert not ok, "a renamed text file must FAIL P7-TELEPROMPTER"
    assert any("not HTML" in r for r in reasons), f"got reasons={reasons}"


# ---------------------------------------------------------------------------
# P9-SPEECH-WEBINAR-INTRO
# ---------------------------------------------------------------------------
def _mp3(rd: Path) -> Path:
    return _write(rd, "working/delivery/PRESENTER-AUDIO-WEBINAR.mp3",
                  b"\xff\xfb\x90\x00" + b"\x00" * 12_000)


def test_webinar_speech_real_audio_passes(tmp_path):
    rd = _run_dir(tmp_path)
    _mp3(rd)
    ok, reasons = pv.PHASE_VERIFIERS["P9-SPEECH-WEBINAR-INTRO"](rd)
    assert ok, f"a valid MP3 must pass, got reasons={reasons}"


def test_webinar_speech_missing_audio_fails(tmp_path):
    rd = _run_dir(tmp_path)
    ok, reasons = pv.PHASE_VERIFIERS["P9-SPEECH-WEBINAR-INTRO"](rd)
    assert not ok, "no audio must FAIL the step"
    assert any("not found" in r for r in reasons), f"got reasons={reasons}"


def test_webinar_framing_template_proves_the_code_not_the_audio():
    """The template test now lives HERE, as a unit test — PD-209.

    It is a fact about the generator, not about the produced audio, so it must
    not be a step check. Keep the assertion so the wiring is still covered.
    """
    import webinar_intro_outro as _w

    framing = _w.build_framing_markdown()
    for label in ("WELCOME", "QNA", "CLOSE"):
        assert f"## Section {label}" in framing, f"framing layer missing {label}"

    report = _w.verify_sections()
    for name, r in report.items():
        assert r["within_band"], (
            f"{name} framing is {r['words']} words, outside "
            f"+/-{_w.TOLERANCE:.0%} of target {r['target']}")
        assert r["n_distinct_tags"] >= 2, (
            f"{name} framing has flat reader tags (fewer than 2 distinct)")


# ---------------------------------------------------------------------------
# PD-209 / PD-218 half: a missing instrument is a named failure, never a pass
# ---------------------------------------------------------------------------
def test_missing_instrument_is_named_not_silent(tmp_path, monkeypatch):
    """Arc allocation: no presentation_job.arc_slides => named FAIL.

    Simulated by patching the import the verifier performs. The degrade is only
    allowed in the documented test context, so the test context marker is
    removed first.
    """
    rd = _run_dir(tmp_path)
    _write(rd, "working/copy/arc_allocation.json",
           {"slides": [{"slide": 1, "arc_marks": {"peak": "x", "ending": "y"}}]})

    real_import = __import__

    def _boom(name, *a, **k):
        if name == "presentation_job":
            raise ImportError("simulated: arc_slides absent")
        return real_import(name, *a, **k)

    monkeypatch.delenv("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("OPENCLAW_TEST", raising=False)
    monkeypatch.setattr("builtins.__import__", _boom)

    ok, reasons = pv.PHASE_VERIFIERS["P3-ARC"](rd)
    assert not ok, "a missing arc_slides instrument must not pass in production"
    assert any("AF-ARC-INSTRUMENT" in r for r in reasons), f"got reasons={reasons}"
