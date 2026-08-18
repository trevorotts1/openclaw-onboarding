"""TRUST BOUNDARY, SLICE 3 — composite / multi-artifact / deferred-when-None
gate conversion tests.

Covers the six slice-3 gates converted onto the sealed-RunFacts verifier
pattern (runfacts.py verify_* verdicts + verifier_registry composite_verifier
specs, wired through phase_verifiers._shadow_composite_verifier):

  P9-DELIVER         -> verify_deliverables   (10-key bundle: size + magic + substance)
  P9.2-GHL-UPLOAD    -> verify_media_library  (local ledger; the network list-back
                                                stays in the legacy verifier)
  P8.25-WORKBOOK     -> verify_workbook       (dual PDF: regular image-only + fillable)
  P9.6-WEBINAR-VIDEO -> verify_webinar_video  (mp4 ftyp + contiguous timing track)
  P9.5-NOTES-SYNC    -> verify_notes_sync     (record status + empty-notes-pane scan)
  P8.4-FISH-TAG      -> verify_fish_tag       (dual-file strip-equals prover)

Both-direction pattern per gate (the mandate's exact rubric):
  * FABRICATED artifact — present, parses, but fails the rubric — is REJECTED,
    the rejection reason naming the EXACT discrepancy;
  * GENUINE artifact — a real file that satisfies every floor — PASSES.

Fixtures are real magic-byte files (ZIP/PPTX b'PK\\x03\\x04', PDF b'%PDF',
MP3 b'ID3' + a real MPEG frame header, PNG b'\\x89PNG', MP4 ftyp+moov, pypdf
AcroForm PDFs) so a decoy cannot ride a weak check. MIN-BYTE FLOORS: the
bundle spec demands large files (deck_pptx 1 048 576, audio_mp3 512 000,
webinar_mp4 1 048 576 — reconciled to build_deck.py's DELIVERABLES_REQUIRED,
2026-08-18 split-brain fix) — fixtures pad with real container-compatible
content after the magic header, the same way a real build's files do.

Every verdict is pure (gate_integrity_check --purity asserts all seven by
name); every run_verifier call below re-seals the run dir (force=True inside
VerifierSpec.seal_into) so fixture mutation between directions is picked up.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import runfacts as rf  # noqa: E402
from verifier_registry import (  # noqa: E402
    both_directions,
    register_slice3,
    run_gate,
    write_fixture,
)


def _fresh(tmp_path: pathlib.Path, name: str = "run") -> pathlib.Path:
    rd = tmp_path / name
    rd.mkdir(parents=True, exist_ok=True)
    rf.reset_cache_for_tests()
    return rd


# ---------------------------------------------------------------------------
# Fixture builders — real magic-byte files that satisfy the gates' floors
# ---------------------------------------------------------------------------

def _write_pdf(path: pathlib.Path, n_pages: int = 3, acroform: bool = False,
               fields: int = 0, min_bytes: int = 0) -> pathlib.Path:
    """Write a real PDF via reportlab, optionally with an AcroForm overlay built
    with pypdf's low-level objects (the /Fields array + /NeedAppearances flag the
    workbook gate reads). %PDF magic + pypdf-parseable + padded to min_bytes."""
    from reportlab.pdfgen import canvas as _rl_canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    base = path.with_name(path.name + ".base.pdf")
    c = _rl_canvas.Canvas(str(base))
    for i in range(n_pages):
        c.drawString(72, 720 - i * 40, f"Slide {i + 1}")
    c.save()

    if not acroform:
        data = base.read_bytes()
        base.unlink()
        if min_bytes and len(data) < min_bytes:
            data += b"%" + b"0" * (min_bytes - len(data) - 1)
        path.write_bytes(data)
        return path

    from pypdf import PdfReader as _R, PdfWriter as _W
    from pypdf.generic import (ArrayObject, BooleanObject, DictionaryObject,
                               NameObject, NumberObject, TextStringObject)

    w = _W()
    w.append(str(base))
    base.unlink()
    acro = DictionaryObject()
    fld_arr = ArrayObject()
    for j in range(fields):
        fld = DictionaryObject()
        fld[NameObject("/FT")] = NameObject("/Tx")
        fld[NameObject("/T")] = TextStringObject(f"Field{j}")
        fld[NameObject("/Type")] = NameObject("/Annot")
        fld[NameObject("/Subtype")] = NameObject("/Widget")
        fld[NameObject("/Rect")] = ArrayObject(
            [NumberObject(100), NumberObject(700 - 20 * j),
             NumberObject(300), NumberObject(720 - 20 * j)])
        fld_arr.append(w._add_object(fld))
    acro[NameObject("/Fields")] = fld_arr
    acro[NameObject("/NeedAppearances")] = BooleanObject(True)
    root = w._root_object.get_object()
    root[NameObject("/AcroForm")] = w._add_object(acro)
    w.write(str(path))
    # pypdf does not emit a startxref-consistent trailer for _add_object refs;
    # re-run through pypdf to normalize offsets into a fully parseable file.
    _R(str(path))  # raises if broken
    data = path.read_bytes()
    if min_bytes and len(data) < min_bytes:
        data += b"%" + b"0" * (min_bytes - len(data) - 1)  # trailing comment, still valid PDF
        path.write_bytes(data)
    return path


def _write_pptx(path: pathlib.Path, min_bytes: int) -> pathlib.Path:
    """A real ZIP container with the PPTX magic (PK\\x03\\x04) and enough body
    to clear min_bytes. python-pptx is not needed for the gate — only the
    container magic + size are measured."""
    import zipfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
                    "<?xml version='1.0'?><Types xmlns='http://schemas."
                    "openxmlformats.org/package/2006/content-types'/>")
        zf.writestr("ppt/slides/slide1.xml",
                    "<p:sld xmlns:p='http://schemas.openxmlformats.org/"
                    "presentationml/2006/main'><p:cSld><p:spTree/></p:cSld></p:sld>")
        filler = b"0" * (min_bytes + 4096)
        zf.writestr("customXml/body.bin", filler)
    if path.stat().st_size < min_bytes:
        with path.open("ab") as fh:
            fh.write(b"0" * (min_bytes - path.stat().st_size))
    return path


def _write_mp3(path: pathlib.Path, min_bytes: int) -> pathlib.Path:
    """Real ID3v2 header (with correct syncsafe size) + a valid MPEG audio
    frame header (0xFF 0xFB 0x90 0x64) — passes verify_mp3's frame probe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = b"0" * 256  # ID3 tag payload
    size = len(body)
    syncsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F,
                      (size >> 7) & 0x7F, size & 0x7F])
    frame = b"\xff\xfb\x90\x64" + b"0" * (min_bytes + 1024)
    path.write_bytes(b"ID3\x04\x00\x00" + syncsafe + body + frame)
    return path


def _write_png(path: pathlib.Path, min_bytes: int) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr_len = (13).to_bytes(4, "big")
    ihdr_type = b"IHDR"
    ihdr_data = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
    ihdr_crc = (0x0B4C0A81).to_bytes(4, "big")  # correct CRC for the 13-byte IHDR
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr_len + ihdr_type + ihdr_data + ihdr_crc
                     + b"0" * max(0, min_bytes - 33))
    return path


def _write_html(path: pathlib.Path, min_bytes: int) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ("<!DOCTYPE html><html><head><title>Teleprompter</title></head>"
            "<body><div class='slide'>Slide one</div><div class='slide'>Slide two</div>"
            "<script>window.slide = 1;</script></body></html>")
    path.write_bytes(body.encode("utf-8") + b"\n<!-- " + b"0" * max(0, min_bytes - len(body) - 10) + b" -->")
    return path


def _write_mp4(path: pathlib.Path, min_bytes: int) -> pathlib.Path:
    """Real ftyp box at offset 4 + a moov atom inside the first 256 KiB + body
    to clear min_bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ftyp = (24).to_bytes(4, "big") + b"ftypisom" + (0).to_bytes(4, "big") + b"isomiso2"
    moov = (56).to_bytes(4, "big") + b"moov" + (32).to_bytes(4, "big") + b"mvhd" + b"0" * 24
    body = b"0" * max(0, min_bytes - len(ftyp) - len(moov))
    path.write_bytes(ftyp + moov + body)
    return path


def _genuine_bundle(rd: pathlib.Path) -> None:
    """The full 10-key bundle, every artifact a real magic-byte file above its
    spec floor."""
    dl = rd / "working" / "delivery"
    dls = rd / "working" / "deliverables"
    dl.mkdir(parents=True, exist_ok=True)
    dls.mkdir(parents=True, exist_ok=True)
    _write_pptx(dl / "demo-FINAL.pptx", 1_048_576)  # doctrine floor (split-brain fix, was 50_000)
    _write_pdf(dl / "demo-FINAL.pdf", 51_200)
    _write_pdf(dls / "PRESENTER-GUIDE.pdf", 51_200)  # doctrine floor (split-brain fix, was 20_000)
    speech = "This is the presenter speech. " * 300  # > 2048 bytes
    (dls / "PRESENTERS-SPEECH.md").write_text(speech)
    _write_pdf(dls / "PRESENTERS-SPEECH.pdf", 20_000)  # clears the 3_000 doctrine floor
    (dls / "PRESENTERS-SPEECH-FISH-TAGGED.md").write_text(
        "This [fish calm] is the presenter [fish slow] speech. [fish warm] " * 300)
    _write_mp3(dl / "PRESENTER-AUDIO.mp3", 512_000)  # doctrine floor (split-brain fix, was 100_000)
    _write_png(dl / "infographic.png", 102_400)  # doctrine floor, Part 6 #8 (was 10_000)
    _write_html(dls / "presenter-teleprompter.html", 20_000)  # doctrine floor (split-brain fix, was 5_000)
    _write_mp4(dl / "demo-WEBINAR.mp4", 1_048_576)  # doctrine floor (split-brain fix, was 500_000)


# ---------------------------------------------------------------------------
# P9-DELIVER (deliverables:bundle)
# ---------------------------------------------------------------------------

def test_deliverables_fabricated_rejected_genuine_passes(tmp_path):
    spec = run_gate and next(s for s in __import__("verifier_registry").slice3_verifiers()
                             if s.gate == "deliverables:bundle")

    def fabricate(rd):
        _genuine_bundle(rd)
        # Decoy: swap the PDF for a plain text file (fails magic).
        (rd / "working" / "delivery" / "demo-FINAL.pdf").write_bytes(
            b"not a pdf at all" * 5000)
        # Missing: no audio at all (fails existence).
        (rd / "working" / "delivery" / "PRESENTER-AUDIO.mp3").unlink()

    def genuine(rd):
        _genuine_bundle(rd)

    res = both_directions(spec, _fresh(tmp_path), fabricate=fabricate, genuine=genuine)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "fabricated bundle must be REJECTED"
    joined = "; ".join(f_reasons)
    for needle in ("deck_pdf", "not a valid", "audio_mp3", "no matching file"):
        assert needle in joined, f"rejection must name {needle!r}: {joined}"

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine bundle must PASS, got {g_reasons}"


def test_deliverables_empty_run_fails_closed(tmp_path):
    """D10: a bundle gate whose inputs are absent does not pass."""
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "deliverables:bundle")
    ok, reasons = spec.run_verifier(_fresh(tmp_path))
    assert not ok
    joined = "; ".join(reasons)
    assert "no input artifact found" in joined or "no matching file" in joined


# ---------------------------------------------------------------------------
# P9.2-GHL-UPLOAD (ghl_upload:ledger)
# ---------------------------------------------------------------------------

def test_media_library_fabricated_rejected_genuine_passes(tmp_path):
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "ghl_upload:ledger")

    def fabricate(rd):
        write_fixture(rd, "working/checkpoints/media_library.json", {
            "slides": [{"ghl_media_id": "file-1", "ghl_upload_status": "complete"},
                       {"file_id": "x2", "ghl_upload_status": "failed"}],
            # no ghl_folder_id, no pptx_ghl_media_id
        })

    def genuine(rd):
        write_fixture(rd, "working/checkpoints/media_library.json", {
            "ghl_folder_id": "folder-1234567890",
            "pptx_ghl_media_id": "file-abc123",
            "slides": [{"ghl_media_id": "file-1", "ghl_upload_status": "complete"},
                       {"file_id": "file-2", "ghl_upload_status": "complete"}],
        })

    res = both_directions(spec, _fresh(tmp_path), fabricate=fabricate, genuine=genuine)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "incomplete ledger must be REJECTED"
    joined = "; ".join(f_reasons)
    for needle in ("ghl_folder_id", "slide uploads are incomplete", "pptx_ghl_media_id"):
        assert needle in joined, f"rejection must name {needle!r}: {joined}"

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine ledger must PASS, got {g_reasons}"


def test_media_library_absent_fails_closed(tmp_path):
    """D10: a ledger that was never written means the upload phase did not run —
    the gate FAILs, it does not defer into a pass (the legacy NOTE-degrade)."""
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "ghl_upload:ledger")
    ok, reasons = spec.run_verifier(_fresh(tmp_path))
    assert not ok
    assert any("no input artifact found" in r for r in reasons)


# ---------------------------------------------------------------------------
# P8.25-WORKBOOK (workbook:both)
# ---------------------------------------------------------------------------

def test_workbook_fabricated_rejected_genuine_passes(tmp_path):
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "workbook:both")

    def fabricate(rd):
        # Both PDFs present, but the fillable carries ZERO AcroForm fields —
        # the form did not survive (AF-WORKBOOK-BOTH substance failure).
        d = rd / "working" / "deliverables"
        d.mkdir(parents=True, exist_ok=True)
        _write_pdf(d / "demo-WORKBOOK.pdf", n_pages=4, acroform=False, min_bytes=2048)
        _write_pdf(d / "demo-WORKBOOK-FILLABLE.pdf", n_pages=4, acroform=False,
                   min_bytes=2048)

    def genuine(rd):
        d = rd / "working" / "deliverables"
        d.mkdir(parents=True, exist_ok=True)
        _write_pdf(d / "demo-WORKBOOK.pdf", n_pages=4, acroform=False, min_bytes=2048)
        _write_pdf(d / "demo-WORKBOOK-FILLABLE.pdf", n_pages=4, acroform=True,
                   fields=3, min_bytes=2048)

    res = both_directions(spec, _fresh(tmp_path), fabricate=fabricate, genuine=genuine)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "field-less fillable must be REJECTED"
    joined = "; ".join(f_reasons)
    assert "ZERO AcroForm" in joined, f"rejection must name the empty form: {joined}"

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine dual workbook must PASS, got {g_reasons}"


# ---------------------------------------------------------------------------
# P9.6-WEBINAR-VIDEO (webinar_video:video)
# ---------------------------------------------------------------------------

def test_webinar_video_fabricated_rejected_genuine_passes(tmp_path):
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "webinar_video:video")

    def fabricate(rd):
        d = rd / "working" / "delivery"
        d.mkdir(parents=True, exist_ok=True)
        _write_mp4(d / "demo-WEBINAR.mp4", 500_000)  # real video
        write_fixture(rd, "working/checkpoints/webinar_timing.json", {
            "timing": [{"slide": 1, "duration": 5.2},
                       {"slide": 3, "duration": 4.1}]})  # NOT contiguous (2 missing)

    def genuine(rd):
        d = rd / "working" / "delivery"
        d.mkdir(parents=True, exist_ok=True)
        _write_mp4(d / "demo-WEBINAR.mp4", 500_000)
        write_fixture(rd, "working/checkpoints/webinar_timing.json", {
            "timing": [{"slide": 1, "duration": 5.2},
                       {"slide": 2, "duration": 4.1},
                       {"slide": 3, "duration": 6.0}]})

    res = both_directions(spec, _fresh(tmp_path), fabricate=fabricate, genuine=genuine)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "non-contiguous timing must be REJECTED"
    joined = "; ".join(f_reasons)
    assert "contiguous 1..N" in joined, f"rejection must name contiguity: {joined}"

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine video+timing must PASS, got {g_reasons}"


def test_webinar_video_decoy_mp4_rejected(tmp_path):
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "webinar_video:video")
    rd = _fresh(tmp_path)
    d = rd / "working" / "delivery"
    d.mkdir(parents=True, exist_ok=True)
    # Renamed text file with no ftyp box.
    (d / "demo-WEBINAR.mp4").write_bytes(b"0" * 9000)
    write_fixture(rd, "working/checkpoints/webinar_timing.json",
                  {"timing": [{"slide": 1, "duration": 3.0}]})
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    joined = "; ".join(reasons)
    assert "not a real MP4" in joined, f"decoy must be named: {joined}"


# ---------------------------------------------------------------------------
# P9.5-NOTES-SYNC (notes_sync:sync)
# ---------------------------------------------------------------------------

def test_notes_sync_no_speech_is_hard_fail(tmp_path):
    """'no_speech' is a HARD FAIL (legacy rubric: by this phase's precondition
    the speech MUST exist) — the conversion must preserve that, never degrade."""
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "notes_sync:sync")
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/checkpoints/notes_sync.json", {
        "status": "no_speech", "slides_total": 0, "slides_with_notes": 0,
        "speech_source": None, "reason": "no presenter speech found",
    })
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    assert any("no_speech" in r for r in reasons)


def test_notes_sync_status_error_fails(tmp_path):
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "notes_sync:sync")
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/checkpoints/notes_sync.json", {
        "status": "error", "slides_total": 12, "slides_with_notes": 0,
        "speech_source": None, "reason": "python-pptx is not installed",
    })
    ok, reasons = spec.run_verifier(rd)
    assert not ok
    assert any("status=error" in r for r in reasons)


def test_notes_sync_synced_passes(tmp_path):
    """Genuine: status synced, notes pane scan clean (no bundle_pptx -> the
    scan has nothing to open and returns clean — the legacy fn's own shape)."""
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "notes_sync:sync")
    rd = _fresh(tmp_path)
    write_fixture(rd, "working/checkpoints/notes_sync.json", {
        "status": "synced", "slides_total": 12, "slides_with_notes": 12,
        "speech_source": "working/deliverables/PRESENTERS-SPEECH.md",
        "reason": None,
    })
    ok, reasons = spec.run_verifier(rd)
    assert ok, reasons


# ---------------------------------------------------------------------------
# P8.4-FISH-TAG (fish_tag:strip_equals)
# ---------------------------------------------------------------------------

def test_fish_tag_fabricated_rejected_genuine_passes(tmp_path):
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "fish_tag:strip_equals")

    def fabricate(rd):
        d = rd / "working" / "deliverables"
        d.mkdir(parents=True, exist_ok=True)
        (d / "PRESENTERS-SPEECH.md").write_text("Hello world. " * 300)
        (d / "PRESENTERS-SPEECH-FISH-TAGGED.md").write_text(
            "Hello DIFFERENT content. [fish calm] " * 300)

    def genuine(rd):
        d = rd / "working" / "deliverables"
        d.mkdir(parents=True, exist_ok=True)
        (d / "PRESENTERS-SPEECH.md").write_text("Hello world. " * 300)
        (d / "PRESENTERS-SPEECH-FISH-TAGGED.md").write_text(
            "Hello [fish calm] world. [fish slow] " * 300)

    res = both_directions(spec, _fresh(tmp_path), fabricate=fabricate, genuine=genuine)
    f_ok, f_reasons = res["fabricated"]
    assert not f_ok, "divergent tagged speech must be REJECTED"
    assert any("strip-equals" in r for r in f_reasons)

    g_ok, g_reasons = res["genuine"]
    assert g_ok, f"genuine fish-tagged speech must PASS, got {g_reasons}"


def test_fish_tag_missing_files_fail(tmp_path):
    spec = next(s for s in __import__("verifier_registry").slice3_verifiers()
                if s.gate == "fish_tag:strip_equals")
    ok, reasons = spec.run_verifier(_fresh(tmp_path))
    assert not ok
    assert any("no input artifact found" in r for r in reasons)


# ---------------------------------------------------------------------------
# Phase-level wiring: PHASE_VERIFIERS entries shadow the registry verdicts
# ---------------------------------------------------------------------------

def test_phase_level_report_only_keeps_legacy_result(tmp_path):
    """Report-only default: verify() returns the LEGACY verdict; the RunFacts
    shadow runs in the background (a fabricated artifact produces a
    TRUST-BOUNDARY-DIVERGENCE line, never a changed return)."""
    import os
    import phase_verifiers as pv

    rd = _fresh(tmp_path)
    _genuine_bundle(rd)
    # Fabricate: deck PDF is a decoy — the RunFacts verdict FAILs, legacy
    # _verify_delivery also FAILs (it checks magic itself) so no divergence;
    # then genuine: both PASS.
    (rd / "working" / "delivery" / "demo-FINAL.pdf").write_bytes(b"0" * 60_000)

    os.environ.pop(rf.ENFORCE_ENV, None)
    try:
        ok, reasons = pv.verify("P9-DELIVER", rd)
        # Legacy verifier fails the decoy too — report-only returns its verdict.
        assert not ok
        assert any("not a valid" in r for r in reasons)
    finally:
        os.environ.pop(rf.ENFORCE_ENV, None)


def test_phase_level_enforcing_flips_to_runfacts_verdict(tmp_path):
    """With PRES_TRUST_BOUNDARY_ENFORCE=1 the RunFacts verdict is what the
    phase returns (stricter, never weaker)."""
    import os
    import phase_verifiers as pv

    rd = _fresh(tmp_path)
    _genuine_bundle(rd)
    os.environ[rf.ENFORCE_ENV] = "1"
    try:
        ok, reasons = pv.verify("P9-DELIVER", rd)
        assert ok, f"genuine bundle must PASS under enforcing, got {reasons}"
    finally:
        os.environ.pop(rf.ENFORCE_ENV, None)


def test_registered_slice3_gates_are_known(tmp_path):
    import verifier_registry as vr
    vr.register_slice3()
    gates = set(vr.known_gates())
    for want in ("deliverables:bundle", "ghl_upload:ledger", "workbook:both",
                 "webinar_video:video", "notes_sync:sync", "fish_tag:strip_equals"):
        assert want in gates, f"{want} not registered: {gates}"
