#!/usr/bin/env python3
"""test_workbook_builder.py — Feature L2-D (fillable PDF workbook) unit tests.

Covers the offline, deterministic surfaces of the workbook pipeline:
  1. The P8.25-WORKBOOK phase is declared in PIPELINE-MANIFEST.json with a script
     executor + verifier (the SOP-SLIDE-06 step-(i) lockstep requirement).
  2. workbook_builder's page-prompt template clears the 5,000-19,000 band AND the
     full shared rich-prompt gate (>=9,000 chars) — so a workbook page prompt can
     never be a thin stub.
  3. reportlab assembly + pypdf read-back produces a fillable PDF (fields + pages +
     /NeedAppearances true) — the CRITICAL string-literal gotcha is exercised.
  4. phase_verifiers._verify_workbook passes on a real fillable PDF and fails on a
     missing/empty workbook.

NO network, NO kie.ai spend. Runs entirely on synthetic page backgrounds.
"""
from __future__ import annotations

import json
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
    assert "workbook_builder.py" in ph["executor"]["cmd"]
    assert ph["verifier"] == "phase_verifiers.verify"
    # owning_role must be a real role stem (sync_check A6 would fail otherwise).
    assert ph["owning_role"] == "pptx-assembly-specialist"
    # the SOP ref must exist (sync_check A7).
    assert ph["sop_refs"], "workbook phase must reference a real sops/ file"


def test_workbook_verifier_registered():
    assert "P8.25-WORKBOOK" in phase_verifiers.PHASE_VERIFIERS


# ---------------------------------------------------------------------------
# 2) Prompt band + rich gate
# ---------------------------------------------------------------------------
def test_workbook_prompt_clears_band_and_rich_gate():
    brand = {"primary": wb.DEFAULT_PRIMARY, "secondary": wb.DEFAULT_SECONDARY,
             "accent": wb.DEFAULT_ACCENT, "base": wb.DEFAULT_BASE, "ink": wb.DEFAULT_INK}
    p = wb.build_page_prompt(page_role="My Goals", motif_position="top-right", brand=brand,
                             client_name="Test Client", is_i2i=True, page_index=1,
                             page_count_total=3)
    n = len(p.strip())
    assert wb.PROMPT_FLOOR <= n <= wb.PROMPT_CEILING, (
        f"prompt {n} chars outside band {wb.PROMPT_FLOOR}-{wb.PROMPT_CEILING}")
    assert n >= wb.PROMPT_TARGET_MIN, f"prompt {n} chars below target {wb.PROMPT_TARGET_MIN}"
    # The full shared rich gate (what kie_generate.py applies under the
    # presentations context) must also pass — structural blocks + 8-class negative
    # + spelling-lock + density.
    if wb.prompt_gate is not None:
        wb.prompt_gate.verify_prompt(p, slide_id="page-01")  # raises on failure


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


def test_verify_workbook_accepts_real(tmp_path):
    from PIL import Image
    bg = tmp_path / "bg.png"
    Image.new("RGB", (2016, 2688), (242, 230, 215)).save(bg)
    brand = {"primary": wb.DEFAULT_PRIMARY, "secondary": wb.DEFAULT_SECONDARY,
             "accent": wb.DEFAULT_ACCENT, "base": wb.DEFAULT_BASE, "ink": wb.DEFAULT_INK}
    m = {"client_name": "T", "brand": brand, "page_count": 1,
         "pages": [{"id": "p1", "fields": [
             {"name": "N", "type": "text", "x": 100, "y": 100, "w": 300, "h": 60, "flags": ""}]}]}
    pdf = tmp_path / "working" / "deliverables" / "demo-WORKBOOK.pdf"
    pdf.parent.mkdir(parents=True)
    wb.assemble_workbook(m, [str(bg)], pdf, brand)
    ok, reasons = phase_verifiers._verify_workbook(tmp_path)
    assert ok, reasons


def test_verify_workbook_rejects_tiny(tmp_path):
    pdf = tmp_path / "working" / "deliverables" / "demo-WORKBOOK.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 512)  # too small -> fails
    ok, reasons = phase_verifiers._verify_workbook(tmp_path)
    assert not ok
    assert any("too small" in r for r in reasons)
