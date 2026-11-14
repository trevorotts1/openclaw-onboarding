#!/usr/bin/env python3
"""test_pd_phase_checks_audio.py — PD-064 (Critical, lane FL17).

The step named Delivery (``P9-DELIVER``) was checked against all ten
deliverables at once. A run that never made the audio still passed the step
whenever the rest of the bundle was present — the step attested a file it never
opened, and the one artifact it exists to prove went unchecked.

After the fix:

  * ``P9-DELIVER`` checks the audio ALONE — existence, the canonical byte floor
    and the ID3 magic bytes it already had a spec row for.
  * The ten-deliverable check is not deleted: ``_verify_delivery`` still holds
    every rule, and ``P-BUNDLE-GATE`` (``_verify_bundle_gate``) runs it at the
    step that owns the bundle.
  * Each key in ``_DELIVERY_PATTERN_BY_KEY`` reads the path its manifest
    producer declares (deck, deck PDF and infographic under
    ``working/deliverables/``; audio under ``working/delivery/``).

Rows (01-BUILD-SPEC.md, section PD-064 — A1 and the consolidation row):

  A1a  audio present, nothing else            -> P9-DELIVER passes
  A1b  audio absent                           -> P9-DELIVER fails, names it
  A1c  full ten-file set at manifest paths    -> P-BUNDLE-GATE passes
  A1d  any one of the ten missing             -> P-BUNDLE-GATE fails, names it
  A2   every delivery pattern equals the path its manifest producer declares

No network, no model call, no live service; every fixture is a stubbed file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

# The phase whose `produces_artifact` the delivery pattern for each canonical
# key must equal (the manifest is the authority, never our own memory).
KEY_TO_PRODUCER = {
    "deck_pptx":         "P8-ASSEMBLE",
    "deck_pdf":          "P8.1-PDF-EXPORT",
    "guide_pdf":         "P8.2-GUIDE",
    "speech_md":         "P9-SPEECH",
    "speech_pdf":        "P9.1-SPEECH-PDF",
    "speech_fish_md":    "P8.4-FISH-TAG",
    "audio_mp3":         "P9-DELIVER",
    "infographic_png":   "P8.3-INFOGRAPHIC",
    "teleprompter_html": "P7-TELEPROMPTER",
    "webinar_mp4":       "P9.6-WEBINAR-VIDEO",
}

# A2 allow-list: key -> the unit that owns correcting the other side.
# PD-062 (lane FL04, decision D-12) moves P8-ASSEMBLE's `produces_artifact` to
# `working/deliverables/*-FINAL.pptx`. Until that lands the manifest still
# declares the run-top `*-FINAL.pptx`, so the deck key accepts EITHER spelling —
# the same both-directions tolerance PD-062v (this lane) gives the deck
# resolver, which is why this unit is safe to merge before or after PD-062.
A2_TOLERATED = {
    "deck_pptx": ("*-FINAL.pptx", "working/deliverables/*-FINAL.pptx"),
}


# ---------------------------------------------------------------------------
# Fixtures — real magic bytes above every canonical floor
# ---------------------------------------------------------------------------

def _write(rel: Path, head: bytes, floor: int) -> Path:
    rel.parent.mkdir(parents=True, exist_ok=True)
    rel.write_bytes(head + b"x" * max(0, floor - len(head)))
    return rel


def _speech(run_dir: Path) -> Path:
    p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Presenter speech\n\n" + "Speak this line aloud. " * 200,
                 encoding="utf-8")
    return p


def _fish_speech(run_dir: Path) -> Path:
    p = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH-FISH-TAGGED.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Tagged speech\n\n" + "[warm and welcoming] Say this line. "
                 "[pause] Then this one. [long pause] And this. " * 60,
                 encoding="utf-8")
    return p


def _teleprompter(run_dir: Path) -> Path:
    p = run_dir / "working" / "deliverables" / "presenter-teleprompter.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<!DOCTYPE html><html><head><title>Teleprompter</title></head>"
                 "<body><div class=\"slide\">Slide one</div>"
                 + "<div class=\"slide\">Speak this line.</div>" * 700
                 + "</body></html>", encoding="utf-8")
    return p


def _webinar_video(run_dir: Path) -> Path:
    p = run_dir / "working" / "delivery" / "demo-WEBINAR.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"moov" + b"x" * 1_048_576)
    return p


def _audio(run_dir: Path) -> Path:
    return _write(run_dir / "working" / "delivery" / "PRESENTER-AUDIO.mp3",
                  b"ID3", pv._MIN_BYTES["audio_mp3"])


def _full_bundle(run_dir: Path) -> None:
    """Every one of the ten deliverables at the path its producer declares."""
    _write(run_dir / "working" / "deliverables" / "demo-FINAL.pptx",
           b"PK\x03\x04", pv._MIN_BYTES["deck_pptx"])
    _write(run_dir / "working" / "deliverables" / "demo-FINAL.pdf",
           b"%PDF", pv._MIN_BYTES["deck_pdf"])
    _write(run_dir / "working" / "deliverables" / "PRESENTER-GUIDE.pdf",
           b"%PDF", pv._MIN_BYTES["guide_pdf"])
    _speech(run_dir)
    _write(run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.pdf",
           b"%PDF", pv._MIN_BYTES["speech_pdf"])
    _fish_speech(run_dir)
    _audio(run_dir)
    _write(run_dir / "working" / "deliverables" / "infographic.png",
           b"\x89PNG", pv._MIN_BYTES["infographic_png"])
    _teleprompter(run_dir)
    _webinar_video(run_dir)
    gate = run_dir / "working" / "checkpoints" / "bundle_gate.json"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(json.dumps({"ok": True}), encoding="utf-8")


def _remove(run_dir: Path, rel: str) -> None:
    (run_dir / rel).unlink()


# ---------------------------------------------------------------------------
# A1 — the audio step is checked for the audio
# ---------------------------------------------------------------------------

def test_a1a_audio_alone_passes_the_delivery_step(tmp_path):
    """A1a: the audio is the step's artifact — audio present, nothing else."""
    run_dir = tmp_path / "run"
    _audio(run_dir)
    ok, reasons = pv.verify("P9-DELIVER", run_dir)
    assert ok, f"audio present must satisfy the delivery step, got {reasons}"


def test_a1b_audio_absent_fails_the_delivery_step(tmp_path):
    """A1b: no audio is the failure this step exists to report."""
    run_dir = tmp_path / "run"
    _speech(run_dir)          # a non-audio deliverable must not stand in for it
    ok, reasons = pv.verify("P9-DELIVER", run_dir)
    assert not ok, "a run with no audio must fail the delivery step"
    joined = "; ".join(reasons)
    assert "audio_mp3" in joined, f"the failure must name the audio, got {reasons}"


def test_a1c_full_bundle_at_manifest_paths_passes_the_bundle_gate(tmp_path):
    """A1c: the ten-file check still runs — at P-BUNDLE-GATE."""
    run_dir = tmp_path / "run"
    _full_bundle(run_dir)
    ok, reasons = pv.verify("P-BUNDLE-GATE", run_dir)
    assert ok, f"a complete bundle at the manifest paths must pass, got {reasons}"


def test_a1d_one_missing_deliverable_fails_the_bundle_gate_naming_it(tmp_path):
    """A1d: absence is named, never a vacuous pass."""
    run_dir = tmp_path / "run"
    _full_bundle(run_dir)
    _remove(run_dir, "working/deliverables/infographic.png")
    ok, reasons = pv.verify("P-BUNDLE-GATE", run_dir)
    assert not ok, "a bundle missing one deliverable must fail"
    joined = "; ".join(reasons)
    assert "infographic_png" in joined, f"the failure must name it, got {reasons}"
    # The gate's own record is still present and passing: the failure came from
    # the deliverable check itself, not from a missing verdict record.
    assert (run_dir / "working" / "checkpoints" / "bundle_gate.json").is_file()


def test_the_delivery_step_is_narrowed_to_the_audio():
    """The registration itself is the fix: audio only, from one whitelist."""
    fn = pv.PHASE_VERIFIERS["P9-DELIVER"]
    assert getattr(fn, "scoped_keys", None) == ("audio_mp3",), (
        "P9-DELIVER must check the audio key alone")
    assert any(getattr(c, "cell_contents", None) is pv._verify_delivery
               for c in (fn.__closure__ or ())), (
        "the narrowed check must still delegate to the single-sourced "
        "_verify_delivery — no second copy of the whitelist")


# ---------------------------------------------------------------------------
# A2 — every delivery pattern is the path its manifest producer declares
# ---------------------------------------------------------------------------

def _manifest_artifact(pid: str):
    assert CLUSTER_MANIFEST.exists(), f"manifest not found at {CLUSTER_MANIFEST}"
    m = json.loads(CLUSTER_MANIFEST.read_text(encoding="utf-8"))
    row = next((p for p in m["phases"] if p.get("id") == pid), None)
    assert row is not None, f"{pid} is not in the manifest"
    return row.get("produces_artifact")


def test_a2_every_delivery_pattern_is_its_producers_path():
    """A2: the whole table against the manifest, not a hand-picked sample."""
    assert set(KEY_TO_PRODUCER) == set(pv._DELIVERY_PATTERN_BY_KEY), (
        "the delivery table and the producer map must cover the same keys: "
        f"only-in-table={sorted(set(pv._DELIVERY_PATTERN_BY_KEY) - set(KEY_TO_PRODUCER))}, "
        f"only-in-map={sorted(set(KEY_TO_PRODUCER) - set(pv._DELIVERY_PATTERN_BY_KEY))}")

    mismatches = []
    for key, pid in sorted(KEY_TO_PRODUCER.items()):
        pattern = pv._DELIVERY_PATTERN_BY_KEY[key]
        declared = _manifest_artifact(pid)
        # {deck_slug} is the engine's own placeholder for the same glob the
        # pattern spells as `*`.
        if isinstance(declared, list):
            declared = [d.replace("{deck_slug}", "*") for d in declared]
            tolerated = A2_TOLERATED.get(key, ())
            if pattern in declared or pattern in tolerated:
                continue
            mismatches.append(f"{key}: reads {pattern!r}; {pid} declares {declared!r}")
            continue
        declared = declared.replace("{deck_slug}", "*")
        if pattern == declared:
            continue
        if key in A2_TOLERATED and declared in A2_TOLERATED[key] and \
                pattern in A2_TOLERATED[key]:
            continue
        mismatches.append(f"{key}: reads {pattern!r}; {pid} declares {declared!r}")

    assert not mismatches, (
        "BLOCKED-FOLLOWUP — these delivery patterns are not the paths their "
        "manifest producers declare: " + "; ".join(mismatches))
