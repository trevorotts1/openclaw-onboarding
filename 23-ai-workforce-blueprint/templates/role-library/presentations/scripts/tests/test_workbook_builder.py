#!/usr/bin/env python3
"""test_workbook_builder.py — Feature L2-D (fillable PDF workbook) unit tests.

Covers the offline, deterministic surfaces of the workbook pipeline:
  1. The P8.25-WORKBOOK phase is declared in PIPELINE-MANIFEST.json with a script
     executor + verifier (the SOP-SLIDE-06 step-(i) lockstep requirement).
  2. workbook_builder's page-prompt template clears the 9,000-18,000 band (the
     Presentations rich-prompt gate, WORKBOOK-REDESIGN-PLAN.md §2.1) AND the full
     shared rich-prompt gate — so a workbook page prompt can never be a thin stub.
  3. reportlab assembly + pypdf read-back produces a fillable PDF (fields + pages +
     /NeedAppearances true) — the CRITICAL string-literal gotcha is exercised.
  4. phase_verifiers._verify_workbook passes on a real fillable PDF and fails on a
     missing/empty workbook.
  5. workbook_mapper determinism (WORKBOOK-REDESIGN-PLAN.md §1.3): the content →
     workbook.json mapper is a PURE function of the deck ledgers — identical sources,
     byte-identical manifest; every page is content-bearing and field types are valid.
  6. Front-door nonce refusal: a workbook invocation that could upload to GHL without
     the canonical-entry nonce handshake is REFUSED (AF-CANONICAL-RENDER-BYPASS).

NO network, NO kie.ai spend. Runs entirely on synthetic page backgrounds and synthetic
golden ledgers.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest

import phase_verifiers
import workbook_builder as wb


# ---------------------------------------------------------------------------
# 1) Manifest wiring (SOP-SLIDE-06 step i)
# ---------------------------------------------------------------------------
def _resolve_manifest():
    from manifest_source import resolve_manifest
    manifest_path, _ = resolve_manifest(SCRIPTS)
    return json.loads(manifest_path.read_text())


def test_workbook_phase_declared_in_manifest():
    m = _resolve_manifest()
    phases = {p["id"]: p for p in m["phases"]}
    assert "P8.25-WORKBOOK" in phases, (
        "P8.25-WORKBOOK phase missing from PIPELINE-MANIFEST.json — SOP-SLIDE-06 step (i)")
    ph = phases["P8.25-WORKBOOK"]
    assert ph["order"] == 8.25
    assert ph["executor"]["kind"] == "script"
    # D4 (canonical-entry routing, manifest v45): the workbook phase runs through
    # the canonical entry script (--resume --run-dir {run_dir}), NOT by invoking
    # workbook_builder.py directly — the canonical entry is the single sanctioned
    # door, and the entry's phase dispatch hands off to the builder by phase id.
    cmd = ph["executor"]["cmd"]
    assert "presentation-canonical-entry.sh" in cmd, cmd
    assert "--resume" in cmd and "--run-dir" in cmd, cmd
    assert ph["verifier"] == "phase_verifiers.verify"
    # owning_role must be a real role stem (sync_check A6 would fail otherwise).
    assert ph["owning_role"] == "pptx-assembly-specialist"
    # the SOP ref must exist (sync_check A7).
    assert ph["sop_refs"], "workbook phase must reference a real sops/ file"


def test_workbook_verifier_registered():
    assert "P8.25-WORKBOOK" in phase_verifiers.PHASE_VERIFIERS


# ---------------------------------------------------------------------------
# 2) Prompt band + rich gate + AF-WORKBOOK-PROMPT-NO-CONTENT (content-in-image)
# ---------------------------------------------------------------------------
_SAMPLE_CONTENT = {
    "headline": "My Goals",
    "subhead": "Name the outcomes you want",
    "bullets": [
        "One goal I will commit to.",
        "One habit that helps me move.",
        "One result I want this month.",
    ],
    "question": "What is the one thing I must start today?",
    "affirmation": "My commitment is:",
}


def _sample_brand():
    return {"primary": wb.DEFAULT_PRIMARY, "secondary": wb.DEFAULT_SECONDARY,
            "accent": wb.DEFAULT_ACCENT, "base": wb.DEFAULT_BASE, "ink": wb.DEFAULT_INK}


def test_workbook_prompt_clears_band_and_rich_gate():
    brand = _sample_brand()
    p = wb.build_page_prompt(page_role="My Goals", motif_position="top-right", brand=brand,
                             client_name="Test Client", is_i2i=True, page_index=1,
                             page_count_total=3, content=_SAMPLE_CONTENT)
    n = len(p.strip())
    assert wb.PROMPT_FLOOR <= n <= wb.PROMPT_CEILING, (
        f"prompt {n} chars outside band {wb.PROMPT_FLOOR}-{wb.PROMPT_CEILING}")
    assert n >= wb.PROMPT_TARGET_MIN, f"prompt {n} chars below target {wb.PROMPT_TARGET_MIN}"
    # The full shared rich gate (what kie_generate.py applies under the
    # presentations context) must also pass — structural blocks + 8-class negative
    # + spelling-lock + density.
    if wb.prompt_gate is not None:
        wb.prompt_gate.verify_prompt(p, slide_id="page-01")  # raises on failure


def test_workbook_content_baked_verbatim():
    """The page's real content strings must ride the prompt verbatim (AF-P-VERBATIM-style),
    so the OCR content gate (AF-WORKBOOK-EMPTY) can read them back after render."""
    brand = _sample_brand()
    p = wb.build_page_prompt(page_role="My Goals", motif_position="top-right", brand=brand,
                             client_name="Test Client", is_i2i=True, page_index=1,
                             page_count_total=3, content=_SAMPLE_CONTENT)
    strings = wb._page_content_strings(_SAMPLE_CONTENT)
    assert len(strings) >= 6
    missing = [c for c in strings if wb._norm_content_ws(c) not in wb._norm_content_ws(p)]
    assert not missing, f"content strings NOT baked verbatim into prompt: {missing}"


def test_workbook_content_gate_accepts_content_bearing():
    """A content-bearing page prompt PASSES AF-WORKBOOK-PROMPT-NO-CONTENT."""
    brand = _sample_brand()
    p = wb.build_page_prompt(page_role="My Goals", motif_position="top-right", brand=brand,
                             client_name="Test Client", is_i2i=True, page_index=1,
                             page_count_total=3, content=_SAMPLE_CONTENT)
    wb._assert_content_in_prompt({"id": "page-01", "content": _SAMPLE_CONTENT}, p)  # no raise


def test_workbook_content_gate_rejects_zero_content():
    """A page with ZERO content strings FAILS AF-WORKBOOK-PROMPT-NO-CONTENT — the
    background-only regression must be blocked pre-submit."""
    with pytest.raises(RuntimeError) as ei:
        wb._assert_content_in_prompt(
            {"id": "page-empty", "content": {}},
            "DESIGN A PRINTABLE WORKBOOK PAGE BACKGROUND, PORTRAIT, US-LETTER...")
    assert "AF-WORKBOOK-PROMPT-NO-CONTENT" in str(ei.value)
    assert "ZERO content strings" in str(ei.value)


def test_workbook_content_gate_rejects_wireframe_directive():
    """A prompt carrying the literal BACKGROUND ONLY / NO text / NO labels directive FAILS
    AF-WORKBOOK-PROMPT-NO-CONTENT even when content strings are present."""
    with pytest.raises(RuntimeError) as ei:
        wb._assert_content_in_prompt(
            {"id": "page-wire", "content": _SAMPLE_CONTENT},
            "This is the BACKGROUND ONLY for a fillable PDF form page. NO text, NO labels.")
    assert "AF-WORKBOOK-PROMPT-NO-CONTENT" in str(ei.value)
    assert "wireframe directive" in str(ei.value)


def test_workbook_content_gate_rejects_missing_string():
    """A content string absent from the prompt (a verbatim break) FAILS the guard."""
    brand = _sample_brand()
    # Build a prompt then strip one content string out of it.
    p = wb.build_page_prompt(page_role="My Goals", motif_position="top-right", brand=brand,
                             client_name="Test Client", is_i2i=True, page_index=1,
                             page_count_total=3, content=_SAMPLE_CONTENT)
    broken = p.replace(_SAMPLE_CONTENT["headline"], "A different headline")
    with pytest.raises(RuntimeError) as ei:
        wb._assert_content_in_prompt({"id": "page-01", "content": _SAMPLE_CONTENT}, broken)
    assert "NOT baked verbatim" in str(ei.value)


# ---------------------------------------------------------------------------
# 3) Assembly + pypdf read-back
# ---------------------------------------------------------------------------
def _make_bg(path: Path) -> str:
    from PIL import Image
    Image.new("RGB", (2016, 2688), (242, 230, 215)).save(path)
    return str(path)


def test_workbook_assembly_and_pypdf_readback(tmp_path):
    from pypdf import PdfReader
    bg = _make_bg(tmp_path / "bg.png")
    brand = {"primary": wb.DEFAULT_PRIMARY, "secondary": wb.DEFAULT_SECONDARY,
             "accent": wb.DEFAULT_ACCENT, "base": wb.DEFAULT_BASE, "ink": wb.DEFAULT_INK}
    m = {
        "client_name": "Test Client", "brand": brand, "page_count": 2,
        "pages": [
            {"id": "p1", "fields": [
                {"name": "ClientName", "type": "text", "x": 1080, "y": 240,
                 "w": 760, "h": 90, "flags": ""},
                {"name": "Notes", "type": "textarea", "x": 220, "y": 1180,
                 "w": 1576, "h": 420, "flags": "multiline"},
            ]},
            {"id": "p2", "fields": [
                {"name": "Agree", "type": "checkbox", "x": 220, "y": 560,
                 "w": 40, "h": 40, "flags": ""},
                {"name": "Category", "type": "choice", "x": 220, "y": 760,
                 "w": 400, "h": 60, "flags": "", "options": ["Executive", "Coach"]},
            ]},
        ],
    }
    pdf = tmp_path / "wb.pdf"
    fc = wb.assemble_workbook(m, [bg, bg], pdf, brand)
    assert fc == 4, f"expected 4 fields, got {fc}"
    v = wb.verify_pdf(pdf, 2, fc)
    assert v["pages"] == 2
    assert v["fields"] == 4
    assert v["need_appearances"] is True, "NeedAppearances must be read back as true"
    # pypdf must see real field types.
    r = PdfReader(str(pdf))
    flds = r.get_fields() or {}
    assert flds["ClientName"]["/FT"] == "/Tx"
    assert flds["Agree"]["/FT"] == "/Btn"
    assert flds["Category"]["/FT"] == "/Ch"


# ---------------------------------------------------------------------------
# 4) phase_verifiers._verify_workbook
# ---------------------------------------------------------------------------
def test_verify_workbook_missing(tmp_path):
    ok, reasons = phase_verifiers._verify_workbook(tmp_path)
    assert not ok
    assert any("WORKBOOK.pdf" in r for r in reasons)


def _assemble_both_pdfs(tmp_path, m=None, brand=None):
    """Assemble BOTH the regular and the fillable workbook PDFs (the dual contract)."""
    from PIL import Image
    bg = tmp_path / "bg.png"
    Image.new("RGB", (2016, 2688), (242, 230, 215)).save(bg)
    brand = brand or {"primary": wb.DEFAULT_PRIMARY, "secondary": wb.DEFAULT_SECONDARY,
                      "accent": wb.DEFAULT_ACCENT, "base": wb.DEFAULT_BASE, "ink": wb.DEFAULT_INK}
    m = m or {"client_name": "T", "brand": brand, "page_count": 1,
              "pages": [{"id": "p1", "fields": [
                  {"name": "N", "type": "text", "x": 100, "y": 100,
                   "w": 300, "h": 60, "flags": ""}]}]}
    dl = tmp_path / "working" / "deliverables"
    dl.mkdir(parents=True)
    reg = dl / "demo-WORKBOOK.pdf"
    fill = dl / "demo-WORKBOOK-FILLABLE.pdf"
    wb.assemble_regular(m, [str(bg)], reg)
    wb.assemble_workbook(m, [str(bg)], fill, brand)
    return reg, fill


def test_verify_workbook_accepts_real(tmp_path):
    _assemble_both_pdfs(tmp_path)
    ok, reasons = phase_verifiers._verify_workbook(tmp_path)
    assert ok, reasons


def test_verify_workbook_missing_fillable_fails(tmp_path):
    """AF-WORKBOOK-BOTH: a regular-only workbook must FAIL — both deliverables required."""
    _assemble_both_pdfs(tmp_path)
    fill = tmp_path / "working" / "deliverables" / "demo-WORKBOOK-FILLABLE.pdf"
    fill.unlink()
    ok, reasons = phase_verifiers._verify_workbook(tmp_path)
    assert not ok
    assert any("WORKBOOK-FILLABLE" in r for r in reasons)


def test_verify_workbook_rejects_tiny(tmp_path):
    pdf = tmp_path / "working" / "deliverables" / "demo-WORKBOOK.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 512)  # too small -> fails
    fill = tmp_path / "working" / "deliverables" / "demo-WORKBOOK-FILLABLE.pdf"
    fill.write_bytes(b"%PDF-1.7\n" + b"\x00" * 512)  # too small -> fails
    ok, reasons = phase_verifiers._verify_workbook(tmp_path)
    assert not ok
    assert any("too small" in r for r in reasons)


# ---------------------------------------------------------------------------
# 5) workbook_mapper determinism (WORKBOOK-REDESIGN-PLAN.md §1.3 — pure function)
# ---------------------------------------------------------------------------
def _golden_run_dir(tmp_path):
    """A synthetic golden run dir whose ledgers mirror the real signature-deck
    structure (sp_structure.json with phase bands + slides.json with the verbatim
    'Rule n' copy + speech_spec.json one-liners). No client names — a neutral deck."""
    run = tmp_path / "run"
    copy = run / "working" / "copy"
    dl = run / "working" / "deliverables"
    copy.mkdir(parents=True)
    dl.mkdir(parents=True)

    sp = {
        "deck_type": "signature_presentation",
        "deck_slug": "demo-deck",
        "title": "The Easy Offer Method",
        "teaching_steps": 3,
        "hook_package": {
            "central_hook": "Friction is the tax on every hesitation.",
            "section_hooks": ["The easiest path wins.", "Clarity beats complexity."],
        },
        "slides": [
            {"slide": 1, "phase": "avatar", "label_slide": True, "tags": ["N.E.E.I.T."]},
            {"slide": 2, "phase": "avatar", "label_slide": False, "tags": []},
            {"slide": 3, "phase": "story", "label_slide": True, "tags": ["MESSAGE"]},
            {"slide": 4, "phase": "story", "label_slide": False, "tags": []},
            {"slide": 5, "phase": "teaching", "label_slide": True, "tags": ["METHODOLOGY"]},
            {"slide": 6, "phase": "teaching", "label_slide": False, "tags": []},
            {"slide": 7, "phase": "teaching", "label_slide": False, "tags": []},
            {"slide": 8, "phase": "teaching", "label_slide": False, "tags": []},
            {"slide": 9, "phase": "pitch", "label_slide": True, "tags": []},
            {"slide": 10, "phase": "pitch", "label_slide": False, "tags": ["CASE_STUDY"]},
        ],
    }
    (copy / "sp_structure.json").write_text(json.dumps(sp))

    # slides.json: the VERBATIM per-slide copy (index 0 = headline, 1 = subhead).
    slides = [
        {"slide": 1, "copy": ["The Easy Offer Method", "Friction is the tax on every hesitation."]},
        {"slide": 2, "copy": ["See yourself in the story", "You have felt the friction."]},
        {"slide": 3, "copy": ["The pattern became a framework", "Three moves that make buying easy."]},
        {"slide": 4, "copy": ["The old way was hard", "The new way removes friction."]},
        {"slide": 5, "copy": ["The Easy Offer Method", "Three rules, one path."]},
        {"slide": 6, "copy": ["Rule 1 - Name the offer in one sentence", "If they cannot say what it is, they cannot say yes."]},
        {"slide": 7, "copy": ["Rule 2 - Remove every step that is not a yes", "Each extra click costs the sale."]},
        {"slide": 8, "copy": ["Rule 3 - Show the value before the price", "Price is only painful when value is unclear."]},
        {"slide": 9, "copy": ["Your Easy Offer", "A clear path to a faster yes."]},
        {"slide": 10, "copy": ["Real results", "A shift in the first conversation."]},
    ]
    (copy / "slides.json").write_text(json.dumps(slides))

    intake = {
        "deck_type": "signature_presentation",
        "deck_slug": "demo-deck",
        "client_name": "Demo Client",
        "offer_name": "The Easy Offer Method",
        "transformation_promise": "Before: a hard offer. After: an easy yes.",
        "cta_action": "Book a call to apply the method",
        "final_price": "one honest price",
        "audience": "Business owners who want a faster yes",
        "hook": "Friction is the tax on every hesitation.",
        "brand": {"palette": {"primary": "#212748", "secondary": "#B38456",
                              "accent": "#C49A70", "base": "#F2E6D7", "ink": "#1A1A1A"}},
    }
    (copy / "intake.json").write_text(json.dumps(intake))

    (copy / "arc_allocation.json").write_text(json.dumps({
        "bands": {
            "avatar": {"start": 1, "end": 2, "count": 2, "label": "Avatar"},
            "story": {"start": 3, "end": 4, "count": 2, "label": "Signature Story"},
            "teaching": {"start": 5, "end": 8, "count": 4, "label": "Transformational Teaching"},
            "pitch": {"start": 9, "end": 10, "count": 2, "label": "Purpose Pitch"},
        }
    }))
    (copy / "sp_intake.json").write_text(json.dumps({"record_committed_atomically": True}))

    (dl / "speech_spec.json").write_text(json.dumps({
        "deck_title": "Presenter's Speech",
        "hook": "Friction is the tax on every hesitation.",
        "stages": [
            {"stage": "TEACHING", "slides": [
                {"slide_no": 6, "headline": "Rule 1 - Name the offer in one sentence",
                 "spoken": "Welcome. Rule 1 - Name the offer in one sentence. If they "
                           "cannot say what it is, they cannot say yes. That is the whole game."},
            ]},
        ],
    }))
    return run


def test_mapper_determinism_byte_identical(tmp_path):
    """§1.3 determinism: mapping the SAME golden ledgers twice produces byte-identical
    workbook.json. The mapper is a pure function of the sources — no timestamps, no
    randomness, no LLM judgement at build time."""
    import workbook_mapper as wm
    run = _golden_run_dir(tmp_path)
    m1 = wm.map_workbook(run)
    m2 = wm.map_workbook(run)
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)


def test_mapper_golden_page_list(tmp_path):
    """§1.3 golden fixture: the synthetic 3-step deck maps to the expected page taxonomy
    (cover -> roadmap -> avatar -> story -> 3 teaching -> quotes -> questions -> quiz ->
    action -> contact = 12 pages) and every page id is stable."""
    import workbook_mapper as wm
    run = _golden_run_dir(tmp_path)
    m = wm.map_workbook(run)
    types = [p["page_type"] for p in m["pages"]]
    assert types[0] == "cover"
    assert types[-1] == "contact"
    assert types.count("teaching") == 3
    assert types == [
        "cover", "roadmap", "avatar", "story",
        "teaching", "teaching", "teaching",
        "quotes", "questions", "quiz", "action", "contact",
    ], types
    assert m["page_count"] == 12
    assert m["teaching_steps"] == 3
    assert all(p["id"] for p in m["pages"])
    assert len({p["id"] for p in m["pages"]}) == len(m["pages"])


def test_mapper_content_verbatim_from_sources(tmp_path):
    """§1.3 grounding rule: every deck-sourced content string on every page is a VERBATIM
    copy from a source ledger — the Rule titles and subheads must appear word-for-word."""
    import workbook_mapper as wm
    run = _golden_run_dir(tmp_path)
    m = wm.map_workbook(run)
    rule_pages = [p for p in m["pages"] if p["page_type"] == "teaching"]
    assert len(rule_pages) == 3
    assert rule_pages[0]["content"]["headline"] == \
        "Rule 1 - Name the offer in one sentence"
    assert rule_pages[1]["content"]["headline"] == \
        "Rule 2 - Remove every step that is not a yes"
    assert rule_pages[2]["content"]["headline"] == \
        "Rule 3 - Show the value before the price"
    assert rule_pages[0]["content"]["subhead"] == \
        "If they cannot say what it is, they cannot say yes."
    # the mapper never invents a headline — every headline is from slides.json
    source_headlines = {s["copy"][0] for s in json.loads(
        (run / "working" / "copy" / "slides.json").read_text())}
    for p in m["pages"]:
        head = (p.get("content") or {}).get("headline", "")
        if p["page_type"] == "teaching":
            assert head in source_headlines, f"invented teaching headline: {head!r}"


def test_mapper_every_page_content_bearing(tmp_path):
    """§4.3 anti-wireframe invariant: the mapper attaches non-empty content_strings[]
    to every page — a page with zero content strings is the background-only regression
    and the prompt gate refuses it pre-submit."""
    import workbook_mapper as wm
    run = _golden_run_dir(tmp_path)
    m = wm.map_workbook(run)
    for p in m["pages"]:
        strings = p.get("content_strings") or []
        assert strings, f"{p['id']}: mapper attached ZERO content_strings"
        assert all(len(s.strip()) >= 3 for s in strings)


def test_mapper_field_types_valid(tmp_path):
    """§1.4 field manifest: every emitted field uses one of the 4+1 AcroForm types the
    assembly step knows how to draw."""
    import workbook_mapper as wm
    run = _golden_run_dir(tmp_path)
    m = wm.map_workbook(run)
    for p in m["pages"]:
        for f in p["fields"]:
            assert f["type"] in ("text", "textarea", "checkbox", "choice", "radio"), \
                f"{p['id']}: bad field type {f['type']!r}"
            assert all(k in f for k in ("name", "x", "y", "w", "h"))


def test_mapper_selfcheck_green(tmp_path):
    """--selfcheck must stay green offline: deterministic, all pages content-bearing,
    valid field types."""
    import workbook_mapper as wm
    run = _golden_run_dir(tmp_path)
    fails = wm.selfcheck(run)
    assert not fails, fails


# ---------------------------------------------------------------------------
# 6) Front-door nonce refusal (AF-CANONICAL-RENDER-BYPASS)
# ---------------------------------------------------------------------------
def test_workbook_nonce_refuses_no_env(tmp_path, monkeypatch):
    """A workbook invocation with NO OC_DECK_ENTRY_NONCE must refuse the upload path —
    the canonical entry mints the nonce, so a hand-rolled run fails closed."""
    monkeypatch.delenv("OC_DECK_ENTRY_NONCE", raising=False)
    assert not wb._verify_entry_nonce(tmp_path)


def test_workbook_nonce_refuses_short_env(tmp_path, monkeypatch):
    """A too-short nonce (the minted value is a long random hex) is refused."""
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", "abc")
    assert not wb._verify_entry_nonce(tmp_path)


def test_workbook_nonce_accepts_minted(tmp_path, monkeypatch):
    """Only the canonical entry mints the run-scoped file; when OC_DECK_ENTRY_NONCE
    equals that file, the door opens (constant-time compare)."""
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", "a" * 32)
    nf = tmp_path / "working" / "checkpoints" / ".canonical-entry-nonce"
    nf.parent.mkdir(parents=True)
    nf.write_text("a" * 32)
    assert wb._verify_entry_nonce(tmp_path)


def test_workbook_nonce_refuses_mismatch(tmp_path, monkeypatch):
    """A guessed/stale nonce (file exists but differs) is refused."""
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", "b" * 32)
    nf = tmp_path / "working" / "checkpoints" / ".canonical-entry-nonce"
    nf.parent.mkdir(parents=True)
    nf.write_text("a" * 32)
    assert not wb._verify_entry_nonce(tmp_path)


def test_workbook_nonce_refuses_file_without_env(tmp_path, monkeypatch):
    """The nonce file alone (no env) is never enough — the env nonce must also be set."""
    monkeypatch.delenv("OC_DECK_ENTRY_NONCE", raising=False)
    nf = tmp_path / "working" / "checkpoints" / ".canonical-entry-nonce"
    nf.parent.mkdir(parents=True)
    nf.write_text("a" * 32)
    assert not wb._verify_entry_nonce(tmp_path)


def test_workbook_upload_path_requires_nonce(tmp_path, monkeypatch, capsys):
    """AF-CANONICAL-RENDER-BYPASS at the main() level: an upload-attempting invocation
    (no --no-upload) with a missing nonce exits 2 BEFORE any render/upload and prints the
    refusal. --no-upload offline smoke builds are exempt from the nonce demand — they
    must NOT print the bypass FATAL (they may still fail later on missing assets)."""
    import workbook_mapper  # noqa: F401  (mapper importable alongside)
    monkeypatch.delenv("OC_DECK_ENTRY_NONCE", raising=False)

    rc = wb.main(["--run-dir", str(tmp_path), "--skip-design", "--pages", "1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "AF-CANONICAL-RENDER-BYPASS" in err

    # --no-upload smoke: nonce gate is bypassed (no bypass FATAL printed), even though
    # the build still fails on missing page PNGs.
    rc2 = wb.main(["--run-dir", str(tmp_path), "--skip-design", "--pages", "1",
                   "--no-upload"])
    err2 = capsys.readouterr().err
    assert "AF-CANONICAL-RENDER-BYPASS" not in err2
