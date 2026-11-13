"""PD-027 — the presentations TOOLS.md carries the engine's exit-code contract.

Acceptance row A1 (01-BUILD-SPEC.md, PD-027), verbatim:

    both replacements present; no other line changed (compare line counts:
    the file grows by exactly 7 lines).

Released reading (Trevor, 2026-11-13): the "+7 lines" figure means +6 — the
mandated 12-line block replaces the 6-line block at TOOLS.md 172-177. This test
holds that reading: 12 - 6 = +6, and nothing else in the file is touched.

Fail-closed: the mandated block missing, any stale line from the old block
surviving, or the lane-D clause left in place, fails here.
"""
from __future__ import annotations

from pathlib import Path

DEPT = Path(__file__).resolve().parent.parent.parent          # .../role-library/presentations
TOOLS = DEPT / "TOOLS.md"

# The 6 physical lines the spec names at TOOLS.md 172-177.
OLD_BLOCK = """**Exit codes (the contract you act on):**
- `0` — every slide rendered and the `.pptx` was written. `outputPath` is your deliverable.
- `1` — one or more slides failed (NO `.pptx` written), or assembly failed.
  Read `failures`. Fix `slides.json` if it was a content problem and re-run; otherwise
  report the failure. NEVER substitute an image.
- `2` — fatal config error (no `KIE_API_KEY`, bad `slides.json`, `python-pptx` missing)."""

# The mandated replacement, 01-BUILD-SPEC.md PD-027 fenced block.
NEW_BLOCK = """**Exit codes (the contract you act on):**
- `0` — the engine finished every phase and the bundle gate passed.
- `2` — usage error, or no working Python interpreter.
- `3` — a slide failed to render. `4` — the image account has no credit.
- `5` — an intake gate or the bypass scan refused the build.
- `6` — a required tool is missing on this box.
- `7` — the renderer does not match the pinned version.
- `8` — the GoHighLevel media module cannot be loaded.
- `9` — the engine refused the job, or is not installed.
- `10` — legacy runner only, owner-approved: NOT a full deliverable build.
- `12` — started 3 times in 6 hours without finishing; use `--resume`.
On any non-zero code: read the message, fix what it names, run the same command again. Never substitute an image. Never write your own build script."""

STALE_LANE_D = "is not available to a department agent until lane D plumbs it"
REPLACEMENT_LANE_D = "is not available to a department agent; never hand-run `build_deck.py` to"


def _text() -> str:
    return TOOLS.read_text(encoding="utf-8")


def test_new_block_present_once():
    assert _text().count(NEW_BLOCK) == 1, "mandated 12-line exit-code block absent or duplicated"


def test_old_block_gone():
    text = _text()
    assert OLD_BLOCK not in text, "old render-script exit-code block still present"
    for line in OLD_BLOCK.splitlines()[1:]:
        assert line not in text, f"stale old-block line survived: {line!r}"


def test_block_in_file_is_twelve_lines():
    """Measured on the file: 12 lines in, 6 lines out, so the file grows by 6."""
    text = _text()
    start = text.index("**Exit codes (the contract you act on):**")
    tail = "Never write your own build script."
    block = text[start:text.index(tail, start) + len(tail)]
    assert block == NEW_BLOCK, "exit-code block differs from the mandated text"
    assert len(block.splitlines()) == 12, "mandated block is not 12 physical lines"
    assert len(OLD_BLOCK.splitlines()) == 6, "the spec's 172-177 block is not 6 physical lines"


def test_lane_d_clause_replaced():
    text = _text()
    assert STALE_LANE_D not in text, "lane-D wait clause still present"
    assert text.count(REPLACEMENT_LANE_D) == 1, "replacement lane-D sentence absent or duplicated"
