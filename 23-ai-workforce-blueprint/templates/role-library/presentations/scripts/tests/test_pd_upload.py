"""PD-301 — the upload step sends the deck.

The `--run-dir`-only upload is the assembled deck pair at its DECLARED paths
(presentation_job.deliverable_paths: deck_pptx / deck_pdf), and an over-cap deck
PPTX is left out of the upload list so the deck-PDF twin branch runs instead of
the oversize POST raising first.

No network: every transport call is stubbed with a local opener replacement.
"""

from __future__ import annotations

import json
import pathlib
import sys
import zipfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import delivery_gate  # noqa: E402
import ghl_media  # noqa: E402
import ghl_media_push as gmp  # noqa: E402
import ghl_media_upload  # noqa: E402
from presentation_job.gates import Gates  # noqa: E402

SLUG = "demo-deck"

_REAL_PDF = b"%PDF-1.7\n" + b"\x00" * 128


def _env(monkeypatch):
    monkeypatch.setenv("GHL_API_KEY", "pit-" + "a" * 40)
    monkeypatch.setenv("GHL_LOCATION_ID", "loc-" + "a" * 40)


def _stub_transport(monkeypatch):
    """Replace only the transport; the push module's own gate still runs."""
    calls: list[str] = []

    def _stub(local_path, location_id, name, pit, **kwargs):
        calls.append(str(local_path))
        stem = pathlib.Path(str(local_path)).stem
        return {"fileId": f"file_{stem}", "url": f"https://example.invalid/{stem}",
                "http": 200}

    monkeypatch.setattr(ghl_media, "upload_media", _stub)
    return calls


def _governed_run(base: pathlib.Path) -> pathlib.Path:
    """A complete governed run dir with the deck pair at the DECLARED canon."""
    deck = delivery_gate._mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
    declared = base / "working" / "delivery"
    declared.mkdir(parents=True, exist_ok=True)
    (declared / f"{SLUG}-FINAL.pptx").write_bytes(deck.read_bytes())
    (declared / f"{SLUG}-FINAL.pdf").write_bytes(_REAL_PDF)
    renders = base / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / "slide-01.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    intake = base / "working" / "copy"
    intake.mkdir(parents=True, exist_ok=True)
    (intake / "intake.json").write_text(json.dumps(
        {"deck_slug": SLUG, "has_ghl": True}))
    return declared


def _pad_past_cap(path: pathlib.Path, over_bytes: int = 5 * 1024 * 1024):
    """Grow a REAL OOXML pptx past GHL_MEDIA_MAX_BYTES (25 MB) with a stored part,
    so the artifact stays readable to the delivery gate."""
    with zipfile.ZipFile(path, "a", zipfile.ZIP_STORED) as zf:
        zf.writestr("ppt/media/pd301-pad.bin", b"\x00" * (
            ghl_media_upload.GHL_MEDIA_MAX_BYTES - path.stat().st_size + over_bytes))


def _run_main(monkeypatch, run_dir):
    monkeypatch.setattr(sys, "argv", ["ghl_media_push.py", "--run-dir", str(run_dir)])
    return gmp.main()


# ---------------------------------------------------------------------------
# A1a — `--run-dir` only: the deck is sent, its id recorded, Gates._ghl_gate passes
# ---------------------------------------------------------------------------

def test_run_dir_only_uploads_declared_deck_and_gate_passes(tmp_path, monkeypatch, capsys):
    base = tmp_path / "run"
    declared = _governed_run(base)
    _env(monkeypatch)
    calls = _stub_transport(monkeypatch)

    rc = _run_main(monkeypatch, base)

    assert rc == 0, capsys.readouterr()
    # The DECLARED deck was among the uploads (not a hand-typed path).
    assert str(declared / f"{SLUG}-FINAL.pptx") in calls
    ledger = json.loads(
        (base / "working" / "checkpoints" / "media_library.json").read_text())
    assert ledger.get("pptx_ghl_media_id") == f"file_{SLUG}-FINAL"
    gate = Gates(base, {})._ghl_gate()
    assert gate["state"] == "pass", gate


# ---------------------------------------------------------------------------
# A1b — a 30 MB deck pptx + the deck PDF: the PPTX is never POSTed, the deck PDF
#       hosts the deck, and the standard over-cap receipt is valid
# ---------------------------------------------------------------------------

def test_over_cap_deck_is_left_out_and_hosted_as_pdf(tmp_path, monkeypatch, capsys):
    base = tmp_path / "big"
    declared = _governed_run(base)
    big_pptx = declared / f"{SLUG}-FINAL.pptx"
    _pad_past_cap(big_pptx)
    assert ghl_media_upload.is_over_cap(big_pptx)
    _env(monkeypatch)
    calls = _stub_transport(monkeypatch)

    rc = _run_main(monkeypatch, base)

    assert rc == 0, capsys.readouterr()
    assert str(big_pptx) not in calls, "the over-cap pptx was sent to the transport"
    ledger = json.loads(
        (base / "working" / "checkpoints" / "media_library.json").read_text())
    assert ledger.get("deck_upload_kind") == "pdf"
    receipt = ledger.get("deck_upload_receipt")
    assert ghl_media_upload.receipt_ok(receipt), receipt
    assert receipt.get("pptx_local_path") == str(big_pptx)
    assert ledger.get("pptx_ghl_media_id") == f"file_{SLUG}-FINAL"


# ---------------------------------------------------------------------------
# A1b' — the oversize upload can never raise FIRST: handed both files straight to
#        push_deck_media, the transport must never even be offered the over-cap pptx
# ---------------------------------------------------------------------------

def test_push_never_hands_over_cap_pptx_to_the_transport(tmp_path, monkeypatch):
    base = tmp_path / "direct"
    declared = _governed_run(base)
    big_pptx = declared / f"{SLUG}-FINAL.pptx"
    _pad_past_cap(big_pptx)
    _env(monkeypatch)

    def _stub(local_path, location_id, name, pit, **kwargs):
        assert not str(local_path).endswith(".pptx"), \
            "the over-cap pptx reached the transport"
        return {"fileId": "file_pdf", "url": "https://example.invalid/pdf", "http": 200}

    monkeypatch.setattr(ghl_media, "upload_media", _stub)

    out = gmp.push_deck_media(
        base, [str(base / "renders" / "slide-01.png")],
        extra_files=[str(big_pptx), str(declared / f"{SLUG}-FINAL.pdf")], retries=1)

    assert out.get("deck_upload_kind") == "pdf"
    assert ghl_media_upload.receipt_ok(out.get("deck_upload_receipt")), out


# ---------------------------------------------------------------------------
# A1c — no deck on disk: exit 1 naming the declared path
# ---------------------------------------------------------------------------

def test_missing_deck_is_exit_one(tmp_path, monkeypatch, capsys):
    base = tmp_path / "empty"
    (base / "working" / "copy").mkdir(parents=True)
    (base / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"deck_slug": SLUG, "has_ghl": True}))
    _env(monkeypatch)
    calls = _stub_transport(monkeypatch)

    rc = _run_main(monkeypatch, base)

    err = capsys.readouterr().err
    assert rc == 1
    assert f"the assembled deck is not at {base / 'working' / 'delivery' / (SLUG + '-FINAL.pptx')}" in err
    assert calls == []


# ---------------------------------------------------------------------------
# PD-316 A1 — the completion list-back reads every page: 450 entries with the
# deck on page 3 is found (the old single-page read reported it missing)
# ---------------------------------------------------------------------------

def _list_back_fixture(tmp_path, monkeypatch):
    """Upload once to get a real ledger, then return (base, hosted_id, remote_name)."""
    base = tmp_path / "listback"
    _governed_run(base)
    _env(monkeypatch)
    _stub_transport(monkeypatch)
    assert _run_main(monkeypatch, base) == 0
    ledger = json.loads(
        (base / "working" / "checkpoints" / "media_library.json").read_text())
    monkeypatch.setattr(ghl_media, "resolve_location_pit", lambda: "pit-test")
    monkeypatch.setattr(ghl_media, "resolve_location_id", lambda: "loc-test")
    return base, ledger["pptx_ghl_media_id"], str(ledger.get("pptx_ghl_remote_name") or "")


def test_list_back_pages_until_deck_found(tmp_path, monkeypatch, capsys):
    base, hosted_id, remote_name = _list_back_fixture(tmp_path, monkeypatch)
    others = [{"fileId": f"file_other_{i}", "name": f"other-{i}.png"} for i in range(449)]
    entries = others[:400] + [{"fileId": hosted_id, "name": remote_name}] + others[400:]
    assert len(entries) == 450 and entries[400]["fileId"] == hosted_id
    seen_offsets: list[int] = []

    def _list(location_id, pit, *, media_type="file", parent_id=None, query=None,
              limit=50, offset=0, timeout=60, opener=None):
        seen_offsets.append(offset)
        page = entries[offset:offset + limit]
        return {"http": 200, "data": page, "count": len(page)}

    monkeypatch.setattr(ghl_media, "list_media", _list)

    ok, reasons = gmp.gate_ghl_media_complete(base)

    assert ok is True, reasons
    assert not any("NOT present" in r for r in reasons), reasons
    # It really paged: page 1, page 2, page 3 (the deck is the first entry of page 3).
    assert seen_offsets[:3] == [0, 200, 400], seen_offsets


# ---------------------------------------------------------------------------
# PD-316 A1 — a listing error produces the NOTE (never a silent pass or a
# false "deck missing" verdict)
# ---------------------------------------------------------------------------

def test_list_back_error_produces_note(tmp_path, monkeypatch, capsys):
    base, _hosted_id, _remote_name = _list_back_fixture(tmp_path, monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("media list HTTP 502")

    monkeypatch.setattr(ghl_media, "list_media", _boom)

    ok, reasons = gmp.gate_ghl_media_complete(base)

    assert ok is True, reasons
    assert "NOTE: remote list-back not performed" in reasons, reasons
