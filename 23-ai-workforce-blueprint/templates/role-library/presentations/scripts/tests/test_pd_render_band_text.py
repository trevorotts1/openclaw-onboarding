"""PD-219a — the renderer carries only the live prompt band.

The retired house band (9,000 to 14,000 characters) must not survive anywhere in
build_deck.py as a live statement. The one allowed mention is the historical note
that the band is gone and what replaced it (floor 16,000, target 19,000 to 20,000,
ceiling 20,000 characters for the current image model, read from the shared gate).
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "build_deck.py"
STALE_RE = re.compile(r"(?<![\d,])(?:9|14),000")


def test_no_live_retired_band_statement():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    offenders = []
    for i, line in enumerate(lines):
        if STALE_RE.search(line):
            window = "\n".join(lines[max(0, i - 2): i + 3])
            if "gone" not in window and "retired" not in window:
                offenders.append(f"{i + 1}: {line.strip()}")
    assert not offenders, "live retired-band text remains:\n" + "\n".join(offenders)


def test_live_band_is_stated():
    src = " ".join(SRC.read_text(encoding="utf-8").split())
    assert "floor 16,000" in src
    assert "target 19,000 to 20,000" in src
    assert "20,000 characters for the current image model" in src
