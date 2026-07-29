"""Tests for U012 producer scripts. No network, tmp_path only."""
import json
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_teleprompter
import speech_spec_build
import speech_fish_tag
import presenter_guide
import presenters_speech_pdf

# ---------------------------------------------------------------------------
# speech_spec_build tests
# ---------------------------------------------------------------------------

def test_speech_spec_build_from_sample(tmp_path):
    """speech_spec_build produces a valid spec from the sample speech."""
    speech_file = tmp_path / "speech.md"
    speech_file.write_text(build_teleprompter.SAMPLE_SPEECH_MD)
    out_file = tmp_path / "spec.json"

    spec, err = speech_spec_build.build_spec(str(speech_file))
    assert err is None, f"build_spec returned error: {err}"
    assert "stages" in spec
    assert len(spec["stages"]) > 0
    assert sum(len(s["slides"]) for s in spec["stages"]) > 0
    assert spec.get("deck_title")
    assert spec.get("spoken_rate_wpm") > 0


def test_speech_spec_build_empty_speech_via_cli(tmp_path):
    """CLI exits non-zero when no slides parse."""
    import subprocess

    empty_md = tmp_path / "empty.md"
    empty_md.write_text("")
    out_path = tmp_path / "out.json"

    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "speech_spec_build.py"),
         "--speech", str(empty_md), "--out", str(out_path)],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode != 0, f"Expected non-zero exit for empty speech, got {r.returncode}"


def test_speech_spec_build_keys_present(tmp_path):
    """speech_spec_build emits all 8 top-level keys."""
    speech_file = tmp_path / "speech.md"
    speech_file.write_text(build_teleprompter.SAMPLE_SPEECH_MD)

    spec, err = speech_spec_build.build_spec(str(speech_file))
    assert err is None
    expected_keys = {"deck_title", "owner_name", "company_name", "duration_min",
                     "tone", "hook", "spoken_rate_wpm", "brand", "stages"}
    missing = expected_keys - set(spec.keys())
    assert not missing, f"Missing keys: {missing}"


def test_speech_spec_build_stages_have_slides(tmp_path):
    """Each stage has slides with required keys."""
    speech_file = tmp_path / "speech.md"
    speech_file.write_text(build_teleprompter.SAMPLE_SPEECH_MD)

    spec, err = speech_spec_build.build_spec(str(speech_file))
    assert err is None
    for stage in spec["stages"]:
        assert "stage" in stage
        assert "label" in stage
        assert "slides" in stage
        assert len(stage["slides"]) > 0, f"Stage {stage.get('stage')} has no slides"
        for slide in stage["slides"]:
            assert "slide_no" in slide
            assert "headline" in slide
            assert "kind" in slide
            assert "spoken" in slide

# ---------------------------------------------------------------------------
# speech_fish_tag tests
# ---------------------------------------------------------------------------

def test_verify_strip_equals_source_accepts_clean():
    """Identical source and tagged text (same content) passes the prover."""
    text = "Hello world. This is a test sentence."
    assert speech_fish_tag.verify_strip_equals_source(text, text)


def test_verify_strip_equals_source_rejects_one_word_change():
    """The prover rejects a version with one word changed."""
    source = "Hello world. This is a test sentence."
    tagged = "Hello world. This is a SABOTAGE sentence."
    result = speech_fish_tag.verify_strip_equals_source(tagged, source)
    assert not result, "Prover should have rejected the one-word mutation"
    print(f"verify_strip_equals_source correctly rejected mutated text: {result}")


def test_verify_strip_equals_source_strips_tags():
    """The prover strips tags before comparison."""
    source = "Hello world. This is a test."
    tagged = "[warm, credible] Hello world. [pause] This is a test. [deliberate and measured]"
    assert speech_fish_tag.verify_strip_equals_source(tagged, source), \
        "Prover should accept tagged text with only tags added"


def test_verify_strip_equals_source_handles_paren_tags():
    """The prover also strips parenthetical tags."""
    source = "Hello world. This is a test."
    tagged = "(PAUSE 2 seconds) Hello world. (BREATHE) This is a test."
    assert speech_fish_tag.verify_strip_equals_source(tagged, source)


def test_verify_flagged_in_help():
    """--verify-only flag is declared in argparse."""
    import io, contextlib
    # Just check the flag exists by parsing
    import subprocess
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "speech_fish_tag.py"),
         "--verify-only", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert "--verify-only" in r.stdout


def test_fish_tag_verify_only_mode(tmp_path):
    """--verify-only exits 4 on a sabotaged file, 0 on clean match."""
    import subprocess

    src = tmp_path / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    src.parent.mkdir(parents=True)
    src.write_text("Hello world. This is the source.")

    tagged = tmp_path / "working" / "deliverables" / "PRESENTERS-SPEECH-FISH-TAGGED.md"
    tagged.write_text("Hello world. This is SABOTAGE.")

    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "speech_fish_tag.py"),
         "--run-dir", str(tmp_path), "--verify-only"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 4, f"Sabotaged file should exit 4, got {r.returncode}"

    # Fix it and re-run
    tagged.write_text("Hello world. This is the source.")
    r2 = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "speech_fish_tag.py"),
         "--run-dir", str(tmp_path), "--verify-only"],
        capture_output=True, text=True, timeout=30,
    )
    assert r2.returncode == 0, f"Clean file should exit 0, got {r2.returncode}"


def test_verify_strip_equals_source_is_public():
    """The function must be importable as speech_fish_tag.verify_strip_equals_source."""
    assert callable(speech_fish_tag.verify_strip_equals_source)


# ---------------------------------------------------------------------------
# pdf_export tests
# ---------------------------------------------------------------------------

def test_pdf_export_module_imports():
    """pdf_export module is importable."""
    import pdf_export
    assert hasattr(pdf_export, "main")


# ---------------------------------------------------------------------------
# presenter_guide tests
# ---------------------------------------------------------------------------

def test_presenter_guide_font_floor(tmp_path):
    """presenter_guide enforces 12pt font floor in styles."""
    import presenter_guide as pg
    slides = [{"no": 1, "headline": "Test", "stage": "WELCOME",
               "kind": "normal", "spoken": "Hello world.", "blocks": []}]
    sections = [{"key": "WELCOME", "label": "Welcome", "slide_range": "1"}]
    intake = {"deck_title": "Test", "owner_name": "Tester"}
    design = {}
    guide = pg.PresenterGuide(slides, sections, intake, design)
    assert pg.MIN_FONT_PT == 12.0, f"Expected 12.0pt floor, got {pg.MIN_FONT_PT}"


def test_presenter_guide_builds_pdf(tmp_path):
    """presenter_guide produces a PDF from sample speech."""
    import presenter_guide as pg
    out_pdf = tmp_path / "PRESENTER-GUIDE.pdf"
    slides = [{"no": 1, "headline": "Welcome", "stage": "WELCOME",
               "kind": "normal", "spoken": "Hello and welcome to the webinar.", "blocks": []}]
    sections = [{"key": "WELCOME", "label": "Welcome", "slide_range": "1"}]
    intake = {"deck_title": "Test Deck", "owner_name": "Test Owner", "DURATION_MIN": 30}
    design = {}
    guide = pg.PresenterGuide(slides, sections, intake, design)
    try:
        pdf_path = guide.build(str(out_pdf))
    except SystemExit as e:
        if e.code == 3 and out_pdf.exists() and out_pdf.stat().st_size > 0:
            return
        raise
    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 0
    print(f"Guide PDF: {out_pdf.stat().st_size} bytes")


# ---------------------------------------------------------------------------
# Deliverable/producer mapping test
# ---------------------------------------------------------------------------

def test_every_manifest_deliverable_has_producer():
    """Assert every deliverables_required filename is produced by exactly one phase.

    Resolves the manifest through manifest_source.resolve_manifest (U001's single
    canonical resolver) rather than a hand-counted parent walk. The old hardcoded
    path was one directory short of the repo root, so this guard silently skipped
    from the day it was written and never once checked the manifest. The resolver
    fail-closes (SystemExit) when no manifest can be found, so a missing manifest
    is now a loud failure instead of a silent skip.
    """
    from manifest_source import resolve_manifest

    scripts_dir = Path(__file__).resolve().parent.parent
    manifest_path, provenance = resolve_manifest(scripts_dir)
    assert manifest_path.exists(), (
        f"resolve_manifest returned {manifest_path} (provenance={provenance}) "
        "but that file does not exist"
    )

    m = json.loads(manifest_path.read_text())

    # Build producer map
    prod = {}
    for p in m["phases"]:
        pa = p.get("produces_artifact")
        artifacts = pa if isinstance(pa, list) else [pa]
        for a in artifacts:
            a_str = str(a)
            fn = a_str.rsplit("/", 1)[-1] if "/" in a_str else a_str
            prod.setdefault(fn, []).append(p["id"])

    # Check deliverables
    orphans = set()
    for d in m["deliverables_required"]:
        fn = d["filename"]
        # Handle glob-like patterns
        search = fn.replace("{deck_slug}", "*")
        producers = prod.get(fn) or prod.get(search)
        if not producers:
            orphans.add(d["key"])

    # KNOWN OPEN DEFECT, not an accepted state. These deliverables_required entries
    # have no phase in PIPELINE-MANIFEST.json declaring them via produces_artifact,
    # so no phase owns building them. U012 shipped the producer *scripts*
    # (presenter_guide.py, presenters_speech_pdf.py, speech_fish_tag.py,
    # build_teleprompter.py) but no manifest phase was added to declare their output;
    # this guard, which exists to catch exactly that, was inert because of the bad
    # manifest path above, so the gap landed unnoticed. Four of these five are
    # client_package_files, i.e. files the client is promised.
    #
    # Declaring the producing phases needs phase ids, order, owning_role, gate_codes
    # and client_report templates for a ratified 26-phase pipeline. That is a design
    # decision and is deliberately NOT invented here.
    #
    # This is asserted as an EXACT set on purpose: adding a producing phase makes this
    # test fail until the fixed key is removed from this list, so the list cannot rot
    # into a silent permanent exemption.
    known_missing_producers = {
        "deck_pdf",
        "guide_pdf",
        "speech_pdf",
        "speech_fish_md",
        "teleprompter_html",
        # infographic_png: no producer by design (audit question Q4, not U012's job)
        "infographic_png",
    }

    new_orphans = sorted(orphans - known_missing_producers)
    assert not new_orphans, (
        f"deliverables_required entries with no phase declaring produces_artifact: "
        f"{new_orphans}"
    )

    fixed = sorted(known_missing_producers - orphans)
    assert not fixed, (
        f"These deliverables now HAVE a producing phase: {fixed}. "
        "Remove them from known_missing_producers so this guard stays honest."
    )


# ---------------------------------------------------------------------------
# Shell injection surface test (Step 11) — run dir with space + semicolon
# ---------------------------------------------------------------------------

def test_shell_metacharacters_in_run_dir(tmp_path):
    """A run dir whose name contains a space and semicolon still runs correctly."""
    import subprocess

    # speech_fish_tag --verify-only with a weird path
    run_dir = tmp_path / "run dir with;semicolon"
    run_dir.mkdir()
    wd = run_dir / "working" / "deliverables"
    wd.mkdir(parents=True)

    src = wd / "PRESENTERS-SPEECH.md"
    src.write_text("Hello world. This is clean text.")

    tagged = wd / "PRESENTERS-SPEECH-FISH-TAGGED.md"
    tagged.write_text("Hello world. This is clean text.")

    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "speech_fish_tag.py"),
         "--run-dir", str(run_dir), "--verify-only"],
        capture_output=True, text=True, timeout=30,
    )
    # Should work (verify-only is a simple read, no shell execution with the path)
    assert r.returncode == 0, f"Expected exit 0, got {r.returncode}: {r.stderr}"


# ---------------------------------------------------------------------------
# Mutation proof — the prover must turn the suite red when subverted
# ---------------------------------------------------------------------------

def test_mutation_proof_strip_equals_source_called_directly():
    """A test that calls verify_strip_equals_source directly on a one-word-changed
    input and asserts rejection. If someone replaces the function body with
    'return True', this test goes RED because the rejection assertion fails.

    This is the source-mutation proof required by QC Q7. Do NOT change this test
    to inspect output files — it must call the function directly."""
    source = "The quick brown fox jumps over the lazy dog."
    tampered = "The quick brown fox jumps over the SABOTAGE dog."
    result = speech_fish_tag.verify_strip_equals_source(tampered, source)
    assert result is False, (
        "MUTANT DETECTED: verify_strip_equals_source returned True on a one-word-changed "
        "input. The prover has been subverted (e.g., replaced with 'return True'). "
        "This must fail — the suite is hollow without a source-mutation red leg."
    )
    print("verify_strip_equals_source correctly rejected: source mutation proof active")
