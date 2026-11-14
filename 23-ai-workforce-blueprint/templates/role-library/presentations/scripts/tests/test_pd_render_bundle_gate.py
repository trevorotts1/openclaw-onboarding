"""PD-060 — the bundle check comes out of the render.

The render used to end at `run_postflight_gate`, which looks for the eight
deliverables the render does not produce yet — so the render exited 5 on every
deck before the bundle existed. P-BUNDLE-GATE owns that check now.

Pinned here:

  A1  a stubbed render, no other deliverables, WITHOUT --bundle-gate → exit 0 and
      the line "RENDER COMPLETE — bundle not checked here (P-BUNDLE-GATE owns it)".
  A2  the same inputs WITH --bundle-gate → exit 5 (AF-BUNDLE-COMPLETE).
  A3  a missing slide render → exit 1 in BOTH modes (the render-scoped AF-I14
      check fails; the bundle scan never decides it).
  A4  --bundle-gate is a known flag — no "unknown flag" refusal.

Transport and assembly are stubbed, exactly as the unit allows: no image call,
no server, no browser. A1/A2 stub the three render-scoped checkers because they
pin the WIRING (which check runs, and what exits); A3 runs the real
`_chk_kie_baked` against the real process_manifest.json this render writes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck  # noqa: E402

NONCE = "pd060-test-nonce-0123456789abcdef"
RENDER_LINE = "RENDER COMPLETE — bundle not checked here (P-BUNDLE-GATE owns it)"

CHECK_NAMES = ("_chk_kie_baked", "_chk_no_overlay", "check_canonical_render_path")


def _rig(monkeypatch, tmp_path, *, stub_checks, bundle_gate):
    """Build a bare-but-real run dir and stub the paid transport.

    Returns (exit_code, stdout_text, stderr_text, bundle_dir).
    """
    run_dir = tmp_path / "run"
    ckpt = run_dir / "working" / "checkpoints"
    ckpt.mkdir(parents=True)
    (ckpt / ".canonical-entry-nonce").write_text(NONCE)  # front-door handshake
    monkeypatch.setenv("OC_DECK_ENTRY_NONCE", NONCE)
    monkeypatch.delenv("OC_DECK_ENTRY_NONCE_FILE", raising=False)

    slides = tmp_path / "slides.json"
    slides.write_text(json.dumps([
        {"slide": 1, "copy": ["one"]},
        {"slide": 2, "copy": ["two"]},
    ]))
    out_path = tmp_path / "deck.pptx"
    bundle_dir = tmp_path / "bundle"
    renders_dir = tmp_path / "renders"

    # Stub renders. The image files are NOT written: A3 needs a slide render that
    # is missing on disk, which is the failure AF-I14 must report.
    rendered = [
        {"slide": 1, "taskId": "task-1", "file": str(renders_dir / "slide-01.png")},
        {"slide": 2, "taskId": "task-2", "file": str(renders_dir / "slide-02.png")},
    ]
    monkeypatch.setattr(
        build_deck, "render_slides_batch",
        lambda *a, **k: {"rendered": [dict(r) for r in rendered], "failures": []})
    # No pptx is written: the bundle must stay empty so A2's exit 5 comes from the
    # missing-deliverable scan, not from a half-real deck.
    monkeypatch.setattr(build_deck, "assemble_pptx", lambda *a, **k: None)
    monkeypatch.setattr(build_deck, "discover_speech_chunks", lambda *a, **k: None)
    monkeypatch.setattr(build_deck, "plan_motion_media", lambda *a, **k: ({}, []))

    if stub_checks:
        for name in CHECK_NAMES:
            monkeypatch.setattr(build_deck, name, lambda *a, **k: "")

    argv = [
        "build_deck.py", str(slides), str(out_path), str(renders_dir),
        "--run-dir", str(run_dir), "--out", str(bundle_dir),
        "--adhoc-no-process",
    ]
    if bundle_gate:
        argv.append("--bundle-gate")
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc:
        build_deck.main()
    return exc.value.code, bundle_dir


def test_a1_no_flag_renders_and_says_the_bundle_was_not_checked(
        monkeypatch, tmp_path, capsys):
    code, _bundle = _rig(monkeypatch, tmp_path, stub_checks=True, bundle_gate=False)
    out = capsys.readouterr()
    assert code == 0, out.err
    assert RENDER_LINE in out.out
    # The bare word COMPLETE is never printed: every line carrying it is the full line.
    for line in out.out.splitlines():
        if "COMPLETE" in line:
            assert line.strip() == RENDER_LINE, line


def test_a2_bundle_gate_exits_5_on_an_incomplete_bundle(
        monkeypatch, tmp_path, capsys):
    code, _bundle = _rig(monkeypatch, tmp_path, stub_checks=True, bundle_gate=True)
    out = capsys.readouterr()
    assert code == 5, out.err
    # The render line is the WITHOUT-flag path only.
    assert RENDER_LINE not in out.out


def test_a3_a_missing_slide_render_exits_1_in_both_modes(
        monkeypatch, tmp_path, capsys):
    for bundle_gate in (False, True):
        code, _bundle = _rig(
            monkeypatch, tmp_path / f"mode-{bundle_gate}",
            stub_checks=False, bundle_gate=bundle_gate)
        out = capsys.readouterr()
        assert code == 1, f"bundle_gate={bundle_gate} exited {code}: {out.err}"
        assert "RENDER CHECK FAILED" in out.err
        assert "AF-I14" in out.err
        assert RENDER_LINE not in out.out


def test_a4_bundle_gate_is_a_known_flag(monkeypatch, tmp_path, capsys):
    _rig(monkeypatch, tmp_path, stub_checks=True, bundle_gate=True)
    err = capsys.readouterr().err
    assert "unknown flag" not in err
