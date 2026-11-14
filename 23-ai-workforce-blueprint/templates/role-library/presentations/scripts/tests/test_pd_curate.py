"""PD-303 — Curate from declared paths only (D-32).

Bar (01-BUILD-SPEC.md, section PD-303):
  * curation resolves each key from ``deliverable_paths.CANONICAL_PATHS`` and a
    larger file with the same suffix elsewhere in the run never wins;
  * the whole-tree fuzzy locate is not called by ``curate()`` unless the caller
    passes ``fuzzy=True`` (the command-line ``--fuzzy`` flag, default off);
  * ``working/delivery`` is one of the searched staging directories;
  * the curation manifest records a source hash for every file;
  * ``self_audit``'s MP4 ftyp branch is bound to the canonical key
    ``webinar_mp4`` (it tested ``webinar_video`` and never fired).

No network. Stdlib + pytest only, matching the repo's other flat-import tests.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import self_audit  # noqa: E402
from presentation_job import curate  # noqa: E402
from presentation_job.deliverable_paths import CANONICAL_PATHS  # noqa: E402


SLUG = "out"

# Distinct, wrong-file-detectable bytes for each canonical key. Sizes only need
# to be non-zero for curation; the decoys are the "larger" files.
CANONICAL_BYTES = {
    "deck_pptx": b"PK\x03\x04-deck-final-pptx-original",
    "deck_pdf": b"%PDF-1.4-deck-final-pdf-original",
    "guide_pdf": b"%PDF-1.4-guide",
    "speech_md": b"# speech",
    "speech_pdf": b"%PDF-1.4-speech",
    "speech_fish_md": b"# fish",
    "teleprompter_html": b"<!DOCTYPE html><html></html>",
    "audio_mp3": b"ID3-presenter-audio-original",
    "infographic_png": b"\x89PNG\r\n\x1a\ninfographic",
    "webinar_mp4": b"\x00\x00\x00\x18ftypmp42-webinar",
}


def _declared_path(run_dir: pathlib.Path, key: str, slug: str = SLUG) -> pathlib.Path:
    """The path the producing step declares for a key (the canon under test)."""
    return run_dir / CANONICAL_PATHS[key].replace("{deck_slug}", slug)


def _write(path: pathlib.Path, data: bytes) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _seed_canonical_bundle(run_dir: pathlib.Path, *, skip=()) -> dict:
    """Seed all ten deliverables at their DECLARED canonical paths."""
    run_dir.mkdir(parents=True, exist_ok=True)
    _write(run_dir / "working" / "copy" / "intake.json",
           json.dumps({"deck_slug": SLUG}).encode())
    for key, data in CANONICAL_BYTES.items():
        if key in skip:
            continue
        _write(_declared_path(run_dir, key), data)
    return dict(CANONICAL_BYTES)


def _manifest(run_dir: pathlib.Path) -> dict:
    path = run_dir / "working" / "checkpoints" / "curation_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _entry(run_dir: pathlib.Path, key: str) -> dict:
    for row in _manifest(run_dir)["files"]:
        if row.get("key") == key:
            return row
    raise AssertionError(f"{key} absent from curation manifest")


# ---------------------------------------------------------------------------
# A1 — a larger workbook PDF must never become DECK-FINAL.pdf
# ---------------------------------------------------------------------------
def test_canonical_deck_pdf_beats_larger_workbook(tmp_path):
    run_dir = tmp_path / "run-a1"
    _seed_canonical_bundle(run_dir)

    # The exact probe situation: a 300 KB workbook with the same suffix.
    workbook = _write(
        run_dir / "working" / "deliverables" / f"{SLUG}-WORKBOOK-FILLABLE.pdf",
        b"%PDF-1.4-workbook" + b"W" * 300_000,
    )
    deck_bytes = CANONICAL_BYTES["deck_pdf"]
    assert workbook.stat().st_size > len(deck_bytes)

    curate.curate(run_dir)  # no deck_slug, exactly how close() calls it

    row = _entry(run_dir, "deck_pdf")
    assert row["source"] == str(_declared_path(run_dir, "deck_pdf").resolve())
    # Prove the ARTEFACT, not the returned value.
    delivered = (run_dir / "deliverables" / "DECK-FINAL.pdf").read_bytes()
    assert delivered == deck_bytes


# ---------------------------------------------------------------------------
# A2 — with both audio files present, PRESENTER-AUDIO.mp3 comes from its own name
# ---------------------------------------------------------------------------
def test_canonical_presenter_audio_beats_larger_webinar_audio(tmp_path):
    run_dir = tmp_path / "run-a2"
    _seed_canonical_bundle(run_dir)

    webinar_audio = _write(
        run_dir / "working" / "delivery" / "PRESENTER-AUDIO-WEBINAR.mp3",
        b"ID3-webinar" + b"A" * 300_000,
    )
    presenter_bytes = CANONICAL_BYTES["audio_mp3"]
    assert webinar_audio.stat().st_size > len(presenter_bytes)

    curate.curate(run_dir)

    row = _entry(run_dir, "audio_mp3")
    assert row["source"] == str(
        _declared_path(run_dir, "audio_mp3").resolve()
    )
    delivered = (run_dir / "deliverables" / "PRESENTER-AUDIO.mp3").read_bytes()
    assert delivered == presenter_bytes
    assert delivered != webinar_audio.read_bytes()


# ---------------------------------------------------------------------------
# A3 — nothing at the declared path: AFBundleIncomplete naming the key, even when
#      a loose file the old whole-tree fuzzy locate WOULD have taken sits there
# ---------------------------------------------------------------------------
def test_missing_declared_path_raises_af_bundle_incomplete_naming_key(tmp_path):
    run_dir = tmp_path / "run-a3"
    _seed_canonical_bundle(run_dir, skip=("deck_pptx",))

    # The probe's old false positive: out.pptx at the run root, larger than the
    # declared -FINAL deck. The declared path is absent; curation must refuse.
    _write(run_dir / "out.pptx", b"PK\x03\x04-stray" + b"P" * 2_000_000)

    with pytest.raises(curate.AFBundleIncomplete) as exc_info:
        curate.curate(run_dir)

    assert "deck_pptx" in exc_info.value.missing_keys
    assert "deck_pptx" in str(exc_info.value)


def test_fuzzy_locate_only_runs_when_caller_asks(tmp_path):
    """Item (2): deleted from curate() by default, retained for --fuzzy only."""
    run_dir = tmp_path / "run-fuzzy"
    _seed_canonical_bundle(run_dir, skip=("deck_pptx",))
    stray = _write(run_dir / "out.pptx", b"PK\x03\x04-stray" + b"P" * 2_000_000)

    with pytest.raises(curate.AFBundleIncomplete):
        curate.curate(run_dir)

    # Opt-in, exactly what the CLI --fuzzy flag passes.
    curate.curate(run_dir, fuzzy=True)
    row = _entry(run_dir, "deck_pptx")
    assert row["source"] == str(stray.resolve())


# ---------------------------------------------------------------------------
# Item (1) — deck_slug comes from the run's intake when the caller passes none
# ---------------------------------------------------------------------------
def test_deck_slug_resolved_from_run_intake_when_none(tmp_path):
    run_dir = tmp_path / "run-slug"
    _seed_canonical_bundle(run_dir)
    assert CANONICAL_PATHS["deck_pdf"].startswith("working/delivery/{deck_slug}")

    curate.curate(run_dir)  # deck_slug omitted

    assert _entry(run_dir, "deck_pdf")["source"] == str(
        _declared_path(run_dir, "deck_pdf").resolve()
    )
    # And the templated name really is the intake slug, not the directory name.
    assert (run_dir / "working" / "delivery" / f"{SLUG}-FINAL.pdf").is_file()


# ---------------------------------------------------------------------------
# Item (3) — working/delivery is a searched staging directory
# ---------------------------------------------------------------------------
def test_search_subdirs_include_working_delivery():
    assert "working/delivery" in curate.SEARCH_SUBDIRS


# ---------------------------------------------------------------------------
# Item (4) — the manifest records the source hash of every file
# ---------------------------------------------------------------------------
def test_manifest_records_source_sha256_for_every_file(tmp_path):
    run_dir = tmp_path / "run-hash"
    _seed_canonical_bundle(run_dir)
    curate.curate(run_dir)

    manifest = _manifest(run_dir)
    assert manifest["files"], "manifest must list the curated files"
    for row in manifest["files"]:
        assert row.get("source_sha256"), f"{row.get('key')} has no source hash"
        assert len(row["source_sha256"]) == 64

    expected = hashlib.sha256(CANONICAL_BYTES["deck_pdf"]).hexdigest()
    assert _entry(run_dir, "deck_pdf")["source_sha256"] == expected
    # The hash is of the SOURCE bytes and the delivered bytes are the same bytes.
    delivered = (run_dir / "deliverables" / "DECK-FINAL.pdf").read_bytes()
    assert hashlib.sha256(delivered).hexdigest() == expected


# ---------------------------------------------------------------------------
# Item (5)/A4 — self-audit's MP4 ftyp branch is bound to the canonical key
# ---------------------------------------------------------------------------
def _webinar_item() -> dict:
    return next(
        item for item in self_audit.DELIVERABLE_AUDIT_LIST
        if item["key"] == "webinar_mp4"
    )


def test_self_audit_zero_byte_video_fails_ftyp(tmp_path):
    item = _webinar_item()
    # "zero bytes": a file whose CONTENT is zero bytes, large enough to clear the
    # 1 MB floor so the content check is the thing that must reject it.
    bad = _write(tmp_path / "WEBINAR-VIDEO.mp4", b"\x00" * item["min_bytes"])
    result = self_audit.audit_deliverable(str(bad), item)

    assert result["verdict"] == "FAIL"
    assert "ftyp" in result["reason"]


def test_self_audit_real_ftyp_video_passes(tmp_path):
    item = _webinar_item()
    good = _write(
        tmp_path / "WEBINAR-VIDEO.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * item["min_bytes"],
    )
    result = self_audit.audit_deliverable(str(good), item)

    assert result["verdict"] == "PASS", result["reason"]
