"""PD-062 -- the assembly and notes steps have a working executor (rows A3, A4).

The defect: `P8-ASSEMBLE` and `P9.5-NOTES-SYNC` were AGENT steps with no
executor. The render writes the deck to `working/deliverables/out-FINAL.pptx`
but the manifest declared `produces_artifact: "*-FINAL.pptx"` (the run top), so
the deck's consumers looked where nothing wrote, and the dispatcher declined
both phases by name.

Pinned here, on a scratch run with a stub deck and a stub speech:

  A3  the notes step leaves the notes IN THE DELIVERED DECK. `build_deck.py
      --notes-sync --run-dir <run> --out <run>/working/deliverables` writes a
      non-empty notes pane onto every slide that has a speech block, and leaves
      a slide without a block with no notes. BEFORE the run every pane is empty;
      a run against a run with the speech deleted leaves them empty (`no_speech`)
      -- the control that shows the assertion is not a tautology.

  A4  `pd_assemble_step.py --run-dir <run>` exits 0 on the stub deck at the
      path the render uses; with no deck and no renders it exits non-zero and
      names what is missing; an invalid deck IS rebuilt from the banked renders
      and the rebuilt bytes are proven to be a real PPTX with one slide per row.

Both are proven on the ARTIFACT (the saved .pptx on disk and the exit status of
the real child process), never on a returned value.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS.parents[4]
MANIFEST = REPO_ROOT / "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
BUILD_DECK = SCRIPTS / "build_deck.py"
ASSEMBLE_STEP = SCRIPTS / "pd_assemble_step.py"
DECK_REL = "working/deliverables/*-FINAL.pptx"
NONCE = "a1b2c3d4e5f60718"  # 16 chars, the documented minimum

SPEECH = (
    "## Slide 1\n\nSpoken words for slide one.\n\n"
    "## Slide 3\n\nSpoken words for slide three.\n"
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def _run_dir(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    (rd / "working/copy").mkdir(parents=True)
    (rd / "working/deliverables").mkdir(parents=True)
    (rd / "working/checkpoints").mkdir(parents=True)
    return rd


def _stub_deck(path: Path, slides: int) -> None:
    from pptx import Presentation

    prs = Presentation()
    blank = prs.slide_layouts[6]
    for _ in range(slides):
        prs.slides.add_slide(blank)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))


def _notes(deck: Path) -> list[str]:
    from pptx import Presentation

    prs = Presentation(str(deck))
    return [s.notes_slide.notes_text_frame.text if s.has_notes_slide else ""
            for s in prs.slides]


def _png(path: Path) -> None:
    """A real 2x2 PNG -- assemble_pptx embeds the bytes verbatim."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw))
                     + chunk(b"IEND", b""))
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def _mint_nonce(run: Path) -> dict:
    """The handshake the engine's _run_script_phase actually mints (FIX 25)."""
    nonce_file = run / "working/checkpoints/.nonce-P9.5-NOTES-SYNC"
    nonce_file.write_text(NONCE)
    os.chmod(nonce_file, 0o600)
    env = dict(os.environ)
    env["OC_DECK_ENTRY_NONCE"] = NONCE
    env["OC_DECK_ENTRY_NONCE_FILE"] = "P9.5-NOTES-SYNC"
    return env


def _notes_sync(run: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD_DECK),
         str(run / "working/copy/slides.json"), str(run / "out.pptx"),
         "--notes-sync", "--run-dir", str(run),
         "--out", str(run / "working/deliverables")],
        capture_output=True, text=True, env=env, timeout=120)


# --------------------------------------------------------------------------
# A3 -- the notes land in the delivered deck
# --------------------------------------------------------------------------
def test_a3_notes_sync_writes_notes_into_the_delivered_deck(tmp_path: Path):
    run = _run_dir(tmp_path)
    slides = [{"slide": n, "title": f"S{n}"} for n in (1, 2, 3)]
    (run / "working/copy/slides.json").write_text(json.dumps(slides))
    (run / "working/deliverables/PRESENTERS-SPEECH.md").write_text(SPEECH)
    deck = run / "working/deliverables/out-FINAL.pptx"
    _stub_deck(deck, 3)

    # BEFORE: the assembled deck carries no notes at all (the real defect).
    assert _notes(deck) == ["", "", ""]

    proc = _notes_sync(run, _mint_nonce(run))
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # AFTER: every slide that has a speech block has a non-empty notes pane.
    after = _notes(deck)
    assert after[0] == "Spoken words for slide one."
    assert after[1] == ""  # no block for slide 2 -> no notes, never a blank write
    assert after[2] == "Spoken words for slide three."

    record = json.loads((run / "working/checkpoints/notes_sync.json").read_text())
    assert record["status"] == "synced"
    assert record["slides_with_notes"] == 2
    assert Path(record["bundle_pptx"]) == deck


def test_a3_control_without_speech_the_panes_stay_empty(tmp_path: Path):
    """Turn the proof RED: no speech on disk -> no injection, and it says so."""
    run = _run_dir(tmp_path)
    (run / "working/copy/slides.json").write_text(json.dumps([{"slide": 1}]))
    deck = run / "working/deliverables/out-FINAL.pptx"
    _stub_deck(deck, 1)

    proc = _notes_sync(run, _mint_nonce(run))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _notes(deck) == [""]  # nothing invented
    record = json.loads((run / "working/checkpoints/notes_sync.json").read_text())
    assert record["status"] == "no_speech"


# --------------------------------------------------------------------------
# A4 -- the assembly step confirms or rebuilds the deck
# --------------------------------------------------------------------------
def test_a4_valid_stub_deck_exits_zero_and_is_not_rewritten(tmp_path: Path):
    run = _run_dir(tmp_path)
    (run / "working/copy/slides.json").write_text(
        json.dumps([{"slide": n} for n in (1, 2, 3)]))
    deck = run / "working/deliverables/out-FINAL.pptx"
    _stub_deck(deck, 3)
    before = deck.read_bytes()

    proc = subprocess.run([sys.executable, str(ASSEMBLE_STEP),
                           "--run-dir", str(run), "--json"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["action"] == "verified"
    assert payload["slides"] == 3
    assert deck.read_bytes() == before  # verified, not re-rendered


def test_a4_control_no_deck_and_no_renders_exits_non_zero_naming_what_is_missing(
        tmp_path: Path):
    run = _run_dir(tmp_path)
    (run / "working/copy/slides.json").write_text(json.dumps([{"slide": 1}]))

    proc = subprocess.run([sys.executable, str(ASSEMBLE_STEP),
                           "--run-dir", str(run)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "no *-FINAL.pptx" in proc.stderr
    assert "no banked renders at" in proc.stderr


def test_a4_invalid_deck_is_rebuilt_from_the_banked_renders(tmp_path: Path):
    run = _run_dir(tmp_path)
    (run / "working/copy/slides.json").write_text(
        json.dumps([{"slide": 1}, {"slide": 2}]))
    (run / "renders").mkdir()
    _png(run / "renders/slide-01.png")
    _png(run / "renders/slide-02.png")
    broken = run / "working/deliverables/x-FINAL.pptx"
    broken.write_text("not a zip")

    proc = subprocess.run([sys.executable, str(ASSEMBLE_STEP),
                           "--run-dir", str(run), "--json"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["action"] == "reassembled"

    # Prove the ARTEFACT: a real PPTX holding one slide per slides.json row.
    assert zipfile.is_zipfile(broken)
    with zipfile.ZipFile(broken) as zf:
        names = zf.namelist()
    assert "ppt/presentation.xml" in names
    assert sum(1 for n in names if n == "ppt/slides/slide1.xml") == 1
    assert sum(1 for n in names if n == "ppt/slides/slide2.xml") == 1


def test_a4_slide_count_mismatch_fails_loudly(tmp_path: Path):
    run = _run_dir(tmp_path)
    (run / "working/copy/slides.json").write_text(
        json.dumps([{"slide": n} for n in (1, 2, 3)]))
    _stub_deck(run / "working/deliverables/out-FINAL.pptx", 2)

    proc = subprocess.run([sys.executable, str(ASSEMBLE_STEP),
                           "--run-dir", str(run)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "has 2 slide(s)" in proc.stderr
    assert "3 row(s)" in proc.stderr


# --------------------------------------------------------------------------
# the manifest wiring itself
# --------------------------------------------------------------------------
def test_manifest_wires_both_steps_to_scripts_and_moves_every_consumer():
    manifest = json.loads(MANIFEST.read_text())
    phases = {p["id"]: p for p in manifest["phases"]}

    assert phases["P8-ASSEMBLE"]["produces_artifact"] == DECK_REL
    assert phases["P8-ASSEMBLE"]["executor"]["kind"] == "script"
    assert "pd_assemble_step.py" in phases["P8-ASSEMBLE"]["executor"]["cmd"]
    assert phases["P9.5-NOTES-SYNC"]["executor"]["kind"] == "script"
    assert "--notes-sync" in phases["P9.5-NOTES-SYNC"]["executor"]["cmd"]

    # No consumer may still name the run-top pattern the render never writes.
    stale = [p["id"] for p in manifest["phases"]
             if "*-FINAL.pptx" in (p.get("consumes") or [])]
    assert stale == []
