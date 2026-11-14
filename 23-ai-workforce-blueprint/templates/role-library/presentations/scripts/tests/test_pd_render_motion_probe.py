"""PD-212 — a motion package is MEASURED, not just cross-checked.

What this proves, in the words of the unit's acceptance row
(01-BUILD-SPEC.md, PD-212, row A1):

    "package whose record says 6.0 seconds over a 2-second clip ->
     degraded; receipt without status -> degraded; `ffprobe` hidden from
     the path -> `MOTION_PROBE_UNAVAILABLE`; a correct package ->
     validated. Tests build clips with `ffmpeg` and FAIL LOUDLY when it
     is not on PATH." (L1 binding law forbids a test-level skip; the
     ffmpeg/ffprobe precondition is asserted instead, so a missing
     instrument is a named failure rather than a silently unrun row.)

Before this unit the validator read the package record's own `probe`
block and nothing else: a clip could hash to the record's sha256 while
the record described a different duration, codec or stream count, and
the piece was embedded on that paperwork. The four tests below are the
four acceptance rows, in order.

Every test here needs real media. Rather than a skip, the `media`
fixture ASSERTS ffmpeg and ffprobe are on PATH (named failure), so a
missing instrument can never look like a pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# The fixture builders (a real staged MG-035 package, clips produced by
# ffmpeg) live in the MG-036 suite; reuse them rather than growing a
# second copy of the same 120-line builder. pytest puts the scripts/
# directory on sys.path, not tests/, so add our own directory first.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_mg036_motion_integration as base  # noqa: E402

import build_deck  # noqa: E402
from presentation_job import motion as pm  # noqa: E402

@pytest.fixture(scope="module")
def media(tmp_path_factory):
    """The canonical 6.0 s governed component plus its poster and the
    probe ffprobe reports for the real file."""
    assert base.FFMPEG and base.FFPROBE, (
        "ffmpeg and ffprobe must both be on PATH for the PD-212 rows: the "
        "acceptance row builds a real clip and measures it, so a missing "
        "instrument is a failure here, never a pass")
    d = tmp_path_factory.mktemp("pd212-media")
    clip = d / "component.mp4"
    base._make_component_clip(clip)
    return base._media_from_clip(clip)


def _validate(run_dir: Path, ordinal: int = 1) -> dict:
    slides = base._slides_of(run_dir)
    return build_deck.validate_motion_slide_artifacts(
        run_dir, ordinal, slides[ordinal - 1]["media"],
        election=pm.election_for_run(run_dir),
        copy_lines=list(base.COPY_LINES) if ordinal == 1 else None)


def _package_record_path(run_dir: Path, ordinal: int = 1) -> Path:
    return (run_dir / "working" / "motion" / f"slide-{ordinal:02d}"
            / "package" / "package-record.json")


def _receipt_path(run_dir: Path, ordinal: int = 1) -> Path:
    return (run_dir / "working" / "motion" / f"slide-{ordinal:02d}"
            / "renders" / "artifacts.json")


# ---------------------------------------------------------------------------
# A1 row 4 — the control: a correct package still validates.
# Run FIRST so a broken staging shows up before the degrade rows, and so
# every degrade row below is proved against a package that would
# otherwise pass.
# ---------------------------------------------------------------------------

def test_pd212_correct_package_is_validated(media, tmp_path):
    run_dir = base.build_run(tmp_path, media)
    outcome = _validate(run_dir)
    assert outcome["status"] == "validated", outcome
    assert outcome["reason_code"] is None, outcome
    assert "_embed" in outcome, outcome


# ---------------------------------------------------------------------------
# A1 row 1 — the record says 6.0 seconds over a 2-second clip.
# The bytes hash true (the sha256 is computed from the same file), so
# nothing but measuring the file can catch this.
# ---------------------------------------------------------------------------

def test_pd212_record_duration_lie_over_a_two_second_clip_degrades(
        tmp_path):
    d = tmp_path / "media-2s"
    d.mkdir()
    clip = d / "component.mp4"
    base._run_ffmpeg([
        "-f", "lavfi", "-i", "color=c=0xF7F4EE:s=1920x1080:r=30:d=2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", str(clip)])
    media_2s = base._media_from_clip(clip)
    measured = media_2s["probe"]["duration_seconds"]
    assert 1.9 <= measured <= 2.2, measured   # the clip really is ~2 s

    run_dir = base.build_run(tmp_path / "run", media_2s)

    # The record now CLAIMS a compliant 6.0 s the file does not have.
    rec_path = _package_record_path(run_dir)
    record = json.loads(rec_path.read_text(encoding="utf-8"))
    record["artifact"]["probe"]["duration_seconds"] = 6.0
    rec_path.write_text(json.dumps(record), encoding="utf-8")

    outcome = _validate(run_dir)
    assert outcome["status"] == "degraded", outcome
    assert outcome["reason_code"] == pm.MOTION_HASH_MISMATCH, outcome
    assert "does not match its own record" in outcome["detail"], outcome
    assert "duration_seconds" in outcome["detail"], outcome
    assert "_embed" not in outcome, outcome


# ---------------------------------------------------------------------------
# A1 row 2 — a receipt with no status string is refused as unreadable.
# ---------------------------------------------------------------------------

def test_pd212_receipt_without_status_degrades(media, tmp_path):
    run_dir = base.build_run(tmp_path, media)
    receipt_path = _receipt_path(run_dir)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("status", None)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    outcome = _validate(run_dir)
    assert outcome["status"] == "degraded", outcome
    assert outcome["reason_code"] == pm.MOTION_RECEIPT_UNREADABLE, outcome
    assert "_embed" not in outcome, outcome


# ---------------------------------------------------------------------------
# A1 row 3 — ffprobe hidden from the path is a named degrade, never a
# pass on the record's word.
# ---------------------------------------------------------------------------

def test_pd212_ffprobe_absent_degrades_probe_unavailable(
        media, tmp_path, monkeypatch):
    run_dir = base.build_run(tmp_path, media)
    real_which = build_deck.shutil.which

    def hidden(name, *args, **kwargs):
        if name == "ffprobe":
            return None
        return real_which(name, *args, **kwargs)

    monkeypatch.setattr(build_deck.shutil, "which", hidden)

    outcome = _validate(run_dir)
    assert outcome["status"] == "degraded", outcome
    assert outcome["reason_code"] == pm.MOTION_PROBE_UNAVAILABLE, outcome
    assert "_embed" not in outcome, outcome
