"""Regression: slide_geometry.check_spelling must tolerate schema-mandated
list-typed slide copy (LATENT-FIX 2026-08-31).

slides.schema.json mandates copy = list[str]. Pre-fix, check_spelling assigned
slide_obj.get("copy") straight into approved_blob and _normalise called .lower()
on it -> AttributeError('list' object has no attribute 'lower') for every slide
ordinal that indexed in range. The committed fixtures dodged it only because
their ordinals were out of range.

These tests patch ocr_engine and word_boxes so they need no real renders, no
Tesseract, and no PIL — the coercion boundary is what is under test.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

THIS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(THIS_DIR))
spec = importlib.util.spec_from_file_location(
    "slide_geometry", str(THIS_DIR / "slide_geometry.py"))
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)


# ── unit: _copy_to_text / _normalise boundary coercion ──────────────────────

def test_copy_to_text_passthrough_str():
    assert sg._copy_to_text("HELLO WORLD") == "HELLO WORLD"

def test_copy_to_text_joins_list_of_str():
    assert sg._copy_to_text(["HEADLINE", "body line"]) == "HEADLINE body line"

def test_copy_to_text_tolerates_dict_items():
    assert sg._copy_to_text([{"text": "A"}, "B", {"no_text": 1}]) == "A B"

def test_copy_to_text_bare_dict_text_field():
    assert sg._copy_to_text({"text": "solo"}) == "solo"

def test_copy_to_text_unknown_shapes_degrade_empty():
    assert sg._copy_to_text(None) == ""
    assert sg._copy_to_text(12345) == ""
    assert sg._copy_to_text({"no_text": 1}) == ""
    assert sg._copy_to_text([None, 7]) == ""

def test_normalise_accepts_list_without_crash():
    # pre-fix this raised AttributeError: 'list' object has no attribute 'lower'
    assert sg._normalise(["Hello", "World!"]) == "helloworld"

def test_normalise_str_unchanged():
    assert sg._normalise("Hello, World!") == "helloworld"


# ── integration: check_spelling over an in-range list-copy slide ────────────

def _run_dir_with_slides(slides_obj):
    rd = Path(tempfile.mkdtemp())
    (rd / "renders").mkdir()
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text("{}")
    (rd / "renders" / "slide-01.png").write_bytes(b"\x89PNG fake")
    (rd / "renders" / "slide-02.png").write_bytes(b"\x89PNG fake")
    slides_path = rd / "working" / "copy" / "slides.json"
    slides_path.write_text(json.dumps(slides_obj))
    return rd, slides_path


def _tokens(*words):
    return [{"text": w, "x": 100, "y": 100, "w": 50, "h": 20, "line_num": 1}
            for w in words]


def test_check_spelling_in_range_list_copy_passes():
    """Schema-shaped list copy, ordinal in range: no crash, no false finding."""
    slides = [
        {"slide": 1, "scene": "x", "copy": ["REAL REVENUE GROWTH", "line two"]},
        {"slide": 2, "scene": "y", "copy": ["PIPELINE WIDENS"]},
    ]
    rd, sp = _run_dir_with_slides(slides)
    boxes = {"slide-01": _tokens("REAL", "REVENUE", "GROWTH"),
             "slide-02": _tokens("PIPELINE", "WIDENS")}
    with patch.object(sg, "ocr_engine", return_value=(object(), object())), \
         patch.object(sg, "word_boxes",
                      side_effect=lambda p: boxes[Path(p).stem]):
        result = sg.check_spelling(rd, sp)
    assert result == "", f"list copy should pass, got: {result}"


def test_check_spelling_list_copy_typo_fails():
    """Tokens absent from the joined list copy still report AF-SPELLING."""
    slides = [{"slide": 1, "scene": "x", "copy": ["REAL REVENUE GROWTH"]}]
    rd, sp = _run_dir_with_slides(slides)
    boxes = {"slide-01": _tokens("REAL", "REVENUE", "GROWHT"),
             "slide-02": _tokens("IRRELEVANT")}
    with patch.object(sg, "ocr_engine", return_value=(object(), object())), \
         patch.object(sg, "word_boxes",
                      side_effect=lambda p: boxes[Path(p).stem]):
        result = sg.check_spelling(rd, sp)
    assert "AF-SPELLING" in result and "slide-01" in result
    assert "GROWHT" in result


def test_check_spelling_unknown_copy_shape_degrades_not_crashes():
    """Garbage copy shape: checker reports per-slide unknowns, never crashes."""
    slides = [{"slide": 1, "scene": "x", "copy": 12345}]
    rd, sp = _run_dir_with_slides(slides)
    boxes = {"slide-01": _tokens("QWIXBFUDGLE"), "slide-02": []}
    with patch.object(sg, "ocr_engine", return_value=(object(), object())), \
         patch.object(sg, "word_boxes",
                      side_effect=lambda p: boxes[Path(p).stem]):
        result = sg.check_spelling(rd, sp)
    assert "AF-SPELLING" in result and "slide-01" in result


def test_check_spelling_dict_copy_items_read_back():
    """Dict-shaped copy items with a text field count as approved."""
    slides = [{"slide": 1, "scene": "x",
               "copy": [{"text": "APPROVED WORDMARK"}, "second"]}]
    rd, sp = _run_dir_with_slides(slides)
    boxes = {"slide-01": _tokens("APPROVED", "WORDMARK"), "slide-02": []}
    with patch.object(sg, "ocr_engine", return_value=(object(), object())), \
         patch.object(sg, "word_boxes",
                      side_effect=lambda p: boxes[Path(p).stem]):
        result = sg.check_spelling(rd, sp)
    assert result == "", f"dict-item text should pass, got: {result}"
