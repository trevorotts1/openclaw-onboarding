#!/usr/bin/env python3
"""
deliverable_floors.py -- THE single source of truth for per-deck scaled
deliverable byte floors (U-scaled-floors / MASTER Part 8 FIX 3).

WHY THIS EXISTS:
Before this module the presenter-guide floor existed as FOUR independent,
diverging copies that each re-derived it from different calibrations:

  1. presenter_guide.py: MIN_BYTES_PER_SLIDE (1600) x slide count, versus
     MIN_BYTES_ABSOLUTE (51,200) -- the 51,200 figure was calibrated on the
     34-slide reference deck (~1,506 bytes/slide), so a 12-slide deck was
     structurally unpassable (12 x 1600 = 19,200 < 51,200) and the gate
     auto-failed every short deck regardless of guide richness (F36).
  2. artifacts.py's banked-revalidation path, which scaled the UNSCALED
     spec floor inline as max(min_bytes * n // 34, 8192) with its own
     slide-count read (F43d) -- a THIRD divergent formula, flagged a
     12-slide deck's correct 21,749-byte guide banked_invalid on every
     resume and made P8.2-GUIDE re-run each cycle.
  3. build_deck.py DELIVERABLES_REQUIRED / PIPELINE-MANIFEST.json, which
     carry the raw 51,200 reference floor.
  4. deliverables.py DELIVERABLE_AUDIT_SPEC (guide_pdf.min_bytes), same
     raw 51,200, with a comment promising "FLOOR(n) computed per run by
     audit_all".

That is the exact four-sources-of-truth drift class that produced the
original bundle-completeness errors (see deliverables.py's own docstring
for the canonical write-up of that incident).

THIS FILE is now the ONE place the scaled floor is defined. One formula:

    guide_floor(n) = max(1600 * n, 12000)

  - 1600 bytes/slide: presenter_guide.py's per-slide floor, tuned for
    thin (~230 chars/note) as well as rich production decks.
  - 12,000-byte absolute: the never-below-any-deck guardrail -- an empty
    or garbled guide fails even on a 1-slide deck (where 1600 x 1 would
    otherwise admit a stub). Replaces the legacy 51,200 absolute, which
    was a 34-slide reference value, not a true absolute.

Consumers import THIS helper; nobody re-derives the arithmetic:

  - presenter_guide.py (P8.2-GUIDE writer self-gate)          [W04-B1]
  - presentation_job/artifacts.py (banked validator)           [wired]
  - build_deck.py DELIVERABLES_REQUIRED (guide_pdf.min_bytes) [W04 lane]
  - presentation_job/deliverables.py DELIVERABLE_AUDIT_SPEC   [W02-B4]
  - Command Center completion-evidence.ts /
    presentation-deliverables.ts (via task.slide_count)       [W16-B1]

Expected values (FIX 3 proof): guide_floor(12) == 19,200,
guide_floor(34) == 54,400, guide_floor(60) == 96,000.

Zero third-party deps (stdlib only) -- this module must import cleanly on
a deployed client box with no extra packages installed.
"""

from __future__ import annotations

__all__ = [
    "BYTES_PER_SLIDE",
    "MIN_BYTES_ABSOLUTE",
    "guide_floor",
    "guide_floor_min",
    # FIX 103 (MASTER Part 8, SMOKE-1 addenda): every deck-size floor scales by
    # slide count, from ONE helper. This module grows the two remaining floor
    # formulas (pdf_floor, qc_verdict_floor) and the one slide-count reader
    # (slide_count) every floor site imports -- no site re-derives arithmetic
    # and no site keeps a 51,200 / 20-slide / 34-slide literal.
    "PDF_BYTES_PER_SLIDE",
    "PDF_FLOOR_ABSOLUTE",
    "pdf_floor",
    "qc_verdict_floor",
    "slide_count",
]

# Calibrated constants -- named so consumers can reference the components
# without re-deriving them.
BYTES_PER_SLIDE = 1600      # presenter_guide.py per-slide floor (thin-copy tuned)
MIN_BYTES_ABSOLUTE = 12000  # never-below guardrail for any deck size (1-slide decks)
# Legacy 34-slide reference floor kept ONLY as documentation of where the old
# absolute came from; no code path uses it. 51200 / 34 == 1506 bytes/slide,
# which is why 12-slide decks could not pass under the old regime.
LEGACY_REFERENCE_SLIDES = 34
LEGACY_REFERENCE_FLOOR = 51200


def guide_floor(n_slides: int) -> int:
    """Return the scaled presenter-guide floor for a deck of ``n_slides`` slides.

    ONE formula, one place: max(1600 * n, 12000).

    The 1600 bytes/slide calibration comes from presenter_guide.py's
    MIN_BYTES_PER_SLIDE (tuned for thin copy); the 12,000-byte absolute
    replaces the legacy 51,200 figure, which was calibrated on the 34-slide
    reference deck and made short decks structurally unpassable (F36/F43d).

    Non-integer or negative inputs are coerced: floats floor-truncate,
    negatives and None-ish values fall back to the absolute guardrail, so a
    caller that could not determine slide count still gets a sane floor
    rather than a crash or a zero floor.
    """
    try:
        n = int(n_slides)
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0
    return max(BYTES_PER_SLIDE * n, MIN_BYTES_ABSOLUTE)


def guide_floor_min(n_slides: int) -> int:
    """Alias kept for callers that used the F43d inline name ``min_b``.

    Identical to guide_floor(); exists so a consumer can switch to the
    helper without renaming its own local variable semantics.
    """
    return guide_floor(n_slides)


# ---------------------------------------------------------------------------
# FIX 103 (MASTER Part 8, SMOKE-1 addenda): the remaining deck-size floors.
#
# The 34-slide reference deck left TWO more unscaled floors beyond the guide:
#
#   * the bundle PDF floor -- 51,200 bytes on deck_pdf / speech_pdf rows in
#     build_deck.py DELIVERABLES_REQUIRED and presentation_job/deliverables.py,
#     plus the point-of-production check in pdf_export.py. A 12-slide deck's
#     honest PDF export is ~18-20KB, so a flat 51,200 blocks every short deck.
#   * the QC per-slide verdict floor -- min(20, n). The 20 was tuned on the
#     reference deck; a 12-slide deck can never carry 20 honest verdicts, so
#     padding was the only way past the gate (the definition of a fabricated
#     report). This is Fix 6's formula, now in the ONE shared helper.
#
# pdf_floor(n) = max(PDF_BYTES_PER_SLIDE * n, PDF_FLOOR_ABSOLUTE)
#   - 1,506 bytes/slide reproduces the reference calibration exactly
#     (51,200 / 34 == 1,506): a 34-slide deck floors at the same 51,200 the
#     old constant enforced, so nothing that passed before gets looser.
#   - 8,192-byte absolute: the same never-below guardrail the F43/F49 inline
#     scalers used, so a 1-slide deck still floors a stub header out.
#
# qc_verdict_floor(n) = min(20, n): an honest n-slide deck can carry at most
#   n per-slide verdicts; the floor must never exceed what honesty can
#   produce. The parametrised test (n in {5, 12, 20, 34, 60}) pins this.
# ---------------------------------------------------------------------------

PDF_BYTES_PER_SLIDE = 1506   # 51,200 / 34 == 1,506 (reference calibration, exact)
PDF_FLOOR_ABSOLUTE = 8192    # the F43/F49 guardrail, kept as the never-below floor


def pdf_floor(n_slides: int) -> int:
    """Scaled bundle-PDF byte floor for a deck of ``n_slides`` slides.

    ONE formula: max(1506 * n, 8192). At n == 34 this reproduces the legacy
    51,200-byte reference floor exactly (1506 * 34 = 51,204 >= 51,200), so
    the reference deck's enforcement is unchanged; below 34 the floor scales
    down with the deck; a 1-slide deck still floors at 8,192 so a stub never
    passes. Coercion matches guide_floor(): bad input falls back to the
    absolute guardrail.
    """
    try:
        n = int(n_slides)
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0
    return max(PDF_BYTES_PER_SLIDE * n, PDF_FLOOR_ABSOLUTE)


def qc_verdict_floor(n_slides: int) -> int:
    """Scaled per-slide QC verdict floor (Fix 6): min(20, n).

    An honest n-slide QC report can carry at most n real per-slide verdicts,
    so the floor may never exceed n -- a floor above the slide count is
    unpassable for any deck under 20 slides and demands fabrication. The
    20 (the reference-deck calibration) is kept as the ceiling so long decks
    still carry at least 20 graded slides. Coercion matches guide_floor():
    a determinable n is clamped into [0, 20]; 0 (undeterminable) means the
    caller cannot scale and must decide (callers here pass a real count or
    treat 0 as "use the 20-slide reference ceiling", preserving the
    fail-closed behavior of the pre-F103 gates).
    """
    try:
        n = int(n_slides)
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0
    return min(20, n)


def slide_count(run_dir) -> int:
    """Count THIS deck's slides from the run dir's slides.json -- never a constant.

    Reads the same canonical spots the existing gates read (build_deck's
    _count_output_slides order and self_audit's F49 walker), accepting both
    the JSON-list form and the {"slides": [...]} dict form, then
    arc_allocation.json's slot list. Returns 0 when the count is
    undeterminable -- callers decide their own fallback (e.g. keep the raw
    spec floor); this helper NEVER returns a hardcoded slide count, which is
    exactly the 20-slide / 34-slide literal this fix deletes.
    """
    import json as _json
    from pathlib import Path as _Path

    root = _Path(run_dir)
    candidates = [
        root / "working" / "copy" / "slides.json",
        root / "slides.json",
        root / "working" / "slides.json",
        root / "working" / "copy" / "slides_copy.json",
    ]
    # deliverables/ sibling layout (self_audit's parent-walk case)
    if root.name == "deliverables":
        candidates.append(root.parent / "working" / "copy" / "slides.json")
        candidates.append(root.parent.parent / "working" / "copy" / "slides.json")
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            data = _json.loads(cand.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict) and isinstance(data.get("slides"), list):
            return len(data["slides"])
    # arc_allocation.json -- per-slide arc-section slot list.
    arc = root / "working" / "copy" / "arc_allocation.json"
    try:
        if arc.is_file():
            obj = _json.loads(arc.read_text(encoding="utf-8", errors="replace"))
            slots = obj if isinstance(obj, list) else (
                obj.get("slots") or obj.get("allocation") or obj.get("slides"))
            if isinstance(slots, list):
                return len(slots)
    except (OSError, ValueError):
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover - operator smoke check
    for _n in (12, 34, 60):
        print(_n, guide_floor(_n))
