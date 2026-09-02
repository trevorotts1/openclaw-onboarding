#!/usr/bin/env python3
"""
deliverables.py — U05: THE single source of truth for the deliverable whitelist.

WHY THIS EXISTS:
Before this file, the ten-piece deliverable whitelist was copy-pasted into FOUR
places that drifted independently:
  1. fix_bundle_complete.py's DELIVERABLE_AUDIT_SPEC (the canonical live version).
  2. The repo's own fix_bundle_complete.py, which had gone stale at NINE pieces
     (missing webinar_mp4) while the live deployed copy had moved to ten.
  3. phase_verifiers.py's hardcoded _DELIVERY_DELIVERABLES, which had swapped in
     a "workbook_pdf" key that is NOT part of the canonical bundle (the workbook
     is a separate P8.25-WORKBOOK deliverable with its own gate) while dropping
     "speech_md" — a real, silent whitelist drift.
  4. self_audit.py's inline fallback list, which duplicated the spec by hand and
     could silently diverge from it if the primary import ever failed.

That is exactly the class of drift that produced the original bundle-completeness
errors: four "sources of truth" that were never mechanically forced to agree.

THIS FILE is now the ONE place the ten-piece spec is defined. Every consumer
(fix_bundle_complete.py, presentation_job/curate.py, phase_verifiers.py,
self_audit.py) imports DELIVERABLE_AUDIT_SPEC (and/or its derived views) from
here. No file may hardcode a deliverable list of its own — a hardcoded literal
list of deliverable keys anywhere else in this codebase is the bug this file
exists to prevent from recurring.

Fields on each DELIVERABLE_AUDIT_SPEC entry:
  key                — canonical key (also used as REQUIRED_KEYS element)
  filename_template  — {deck_slug}-templated source filename (for the bundle gate)
  standardized_dest  — filename in the flat deliverables/ folder after curation
  label              — human-readable description
  expected_suffix    — file extension for type-matching (curate._name_matches_type)
  min_bytes          — minimum byte threshold (fuzzy_locate floor + self-audit gate)
  magic_bytes        — expected magic bytes for self-audit (None = content check)
  magic_offset       — byte offset for magic-bytes read (0 unless noted)
  magic_desc         — human description of the expected file type
  content_marker     — None, or string to scan for (HTML, MD)

Order matches build_deck.py DELIVERABLES_REQUIRED and
PIPELINE-MANIFEST.build_bundle_files (universal-sops/presentation-slide-craft/
PIPELINE-MANIFEST.json) — the self-test in fix_bundle_complete.py asserts these
never drift apart.

Zero third-party deps (stdlib only) — this module must import cleanly on a
deployed client box with no extra packages installed.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# THE SINGLE SOURCE OF TRUTH — all deliverable metadata lives here.
# fix_bundle_complete.py, presentation_job/curate.py, phase_verifiers.py, and
# self_audit.py all import this constant (and/or its derived views below) and
# derive their runtime maps from it. No other file may hardcode a deliverable
# list.
# ---------------------------------------------------------------------------
DELIVERABLE_AUDIT_SPEC = [
    {
        "key": "deck_pptx",
        "filename_template": "{deck_slug}-FINAL.pptx",
        "standardized_dest": "DECK-FINAL.pptx",
        "label": "assembled deck PPTX",
        "expected_suffix": ".pptx",
        # RECONCILED (split-brain fix, 2026-08-18) to build_deck.py's DELIVERABLES_REQUIRED
        # value, which PIPELINE-MANIFEST.json's deck_pptx entry also carries verbatim:
        # "a real multi-slide rendered deck with 2K images is always several MB; < 1 MB
        # implies the pptx is empty or contains placeholder content (zero-image shell
        # < 100KB)." deliverables.py had carried a never-chosen 50_000 (21x looser) that
        # no doctrine source cites — build_deck.py's own P8-ASSEMBLE gate (which runs
        # first, in production, on every real build) already rejects anything under
        # 1_048_576, so this only closes a gap the audit-side gate never should have had.
        "min_bytes": 1_048_576,           # 1 MB — multi-slide 2K-image deck floor
        "magic_bytes": b"PK\x03\x04",
        "magic_offset": 0,
        "magic_desc": "ZIP/PPTX container",
        "content_marker": None,
    },
    {
        "key": "deck_pdf",
        "filename_template": "{deck_slug}-FINAL.pdf",
        "standardized_dest": "DECK-FINAL.pdf",
        "label": "deck PDF export",
        "expected_suffix": ".pdf",
        # RECONCILED (split-brain fix, 2026-08-18): build_deck.py's DELIVERABLES_REQUIRED
        # and PIPELINE-MANIFEST.json both carry 51_200 ("a minimal 1-slide PDF export is
        # ~20-30KB; 50KB ensures at least two slides' worth of rendered content").
        # deliverables.py had carried 50_000 — a 1,200-byte rounding drift, not a real
        # doctrine disagreement.
        "min_bytes": 51_200,              # 50 KB — PDF export of at least 2 slides
        "magic_bytes": b"%PDF",
        "magic_offset": 0,
        "magic_desc": "PDF document",
        "content_marker": None,
    },
    {
        "key": "guide_pdf",
        "filename_template": "PRESENTER-GUIDE.pdf",
        "standardized_dest": "PRESENTER-GUIDE.pdf",
        "label": "presenter guide PDF",
        "expected_suffix": ".pdf",
        # RECONCILED (split-brain fix, 2026-08-18) to build_deck.py's DELIVERABLES_REQUIRED
        # / PIPELINE-MANIFEST.json value: "a minimal guide covers all slides with talking
        # points and timing; < 50KB implies only a stub header." deliverables.py had
        # carried a never-chosen 20_000 that no doctrine source cites.
        # F49 (SMOKE-1, 2026-09-01): floor is per-deck, not absolute — the 50KB reference
        # was measured on the 34-slide deck; the P8.2 phase verifier and the bundle gate
        # both scale it by slide count (max(51200*n//34, 8192)). The self-audit reads this
        # list statically, so scale here too: FLOOR(n) computed per run by audit_all.
        "min_bytes": 51_200,              # 50 KB — reference-deck floor; scaled per deck
        "magic_bytes": b"%PDF",
        "magic_offset": 0,
        "magic_desc": "PDF document",
        "content_marker": None,
    },
    {
        "key": "speech_md",
        "filename_template": "PRESENTERS-SPEECH.md",
        "standardized_dest": "PRESENTERS-SPEECH.md",
        "label": "presenter speech markdown (pure)",
        "expected_suffix": ".md",
        # RECONCILED (split-brain fix, 2026-08-18) to build_deck.py's DELIVERABLES_REQUIRED
        # / PIPELINE-MANIFEST.json value: "a word-for-word script for any real webinar
        # talk will be thousands of words; 2KB floors an obvious empty or stub."
        # deliverables.py had carried a never-chosen 5_000 that no doctrine source cites.
        "min_bytes": 2_048,               # 2 KB — word-for-word script stub floor
        "magic_bytes": None,
        "magic_offset": 0,
        "magic_desc": "text/markdown (no magic bytes — content check only)",
        "content_marker": None,
    },
    {
        "key": "speech_pdf",
        "filename_template": "PRESENTERS-SPEECH.pdf",
        "standardized_dest": "PRESENTERS-SPEECH.pdf",
        "label": "presenter speech teleprompter PDF",
        "expected_suffix": ".pdf",
        # RECONCILED (split-brain fix, 2026-08-18) to the doctrine-ratified floor:
        # presentations/presenters-speech-writer.md + sops/presenters-speech-writer-sops.md
        # AF-BUNDLE-COMPLETE gate-tie-in line states verbatim "PDF >= 3,000 bytes" — the
        # same text build_deck.py's DELIVERABLES_REQUIRED entry cites (commit eaae2e33,
        # 2026-07-12, "P3-01(c)5 — RECONCILED to the doctrine-ratified floor"). This is a
        # LOWER number than deliverables.py's prior 20_000: PIPELINE-MANIFEST.json still
        # carries an orphaned 20_480 dated 2026-06-17 (git blame), which PREDATES the
        # 2026-07-12 doctrine reconciliation and was never updated afterward — it is the
        # stale copy, not build_deck.py's 3_000. Trusting the manifest's raw number over
        # its own SOP's plain-English floor is the exact trap: the SOP text is the
        # deliberate, dated, human-authored decision; the orphaned JSON field is not.
        "min_bytes": 3_000,               # 3 KB — doctrine floor (AF-BUNDLE-COMPLETE)
        "magic_bytes": b"%PDF",
        "magic_offset": 0,
        "magic_desc": "PDF document",
        "content_marker": None,
    },
    {
        "key": "speech_fish_md",
        "filename_template": "PRESENTERS-SPEECH-FISH-TAGGED.md",
        "standardized_dest": "PRESENTERS-SPEECH-FISH-TAGGED.md",
        "label": "presenter speech (Fish-Audio expression-tagged)",
        "expected_suffix": ".md",
        # RECONCILED (split-brain fix, 2026-08-18) to build_deck.py's DELIVERABLES_REQUIRED
        # / PIPELINE-MANIFEST.json value: the fish-tagged variant carries the same 2KB
        # script-stub floor as speech_md. deliverables.py had carried a never-chosen
        # 5_000 that no doctrine source cites.
        "min_bytes": 2_048,               # 2 KB — fish-tagged variant of the script floor
        "magic_bytes": None,
        "magic_offset": 0,
        "magic_desc": "text/markdown (no magic bytes — content check only)",
        "content_marker": None,
    },
    {
        "key": "audio_mp3",
        "filename_template": "PRESENTER-AUDIO.mp3",
        "standardized_dest": "PRESENTER-AUDIO.mp3",
        "label": "presenter audio MP3",
        "expected_suffix": ".mp3",
        # RECONCILED (split-brain fix, 2026-08-18) to build_deck.py's DELIVERABLES_REQUIRED
        # / PIPELINE-MANIFEST.json value: "a real Fish Audio S2 rendition of a 30-min
        # script is typically 50-150MB; 500KB floors the obvious failure case (silence
        # stub or failed render < 100KB per SOP-PITCH-05)." deliverables.py had carried a
        # never-chosen 100_000 that no doctrine source cites.
        "min_bytes": 512_000,             # 500 KB — real Fish Audio S2 rendition floor
        "magic_bytes": b"ID3",
        "magic_offset": 0,
        "magic_desc": "MP3 audio (ID3 tag)",
        "content_marker": None,
    },
    {
        "key": "infographic_png",
        "filename_template": "infographic.png",
        "standardized_dest": "INFOGRAPHIC.png",
        "label": "infographic checklist PNG",
        "expected_suffix": ".png",
        # RECONCILED (Part 6 #8, 2026-08-18) to the doctrine floor: PIPELINE-MANIFEST.json
        # ">100KB; one-page infographic slide exported as PNG" and build_deck.py's own
        # DELIVERABLES_REQUIRED entry ("min_bytes": 102_400, "a real 2K-resolution
        # infographic floor"). Single-sourcing this file (U05) had carried it at 10_000 --
        # an unchosen side effect nobody picked and no test pinned -- which silently
        # accepted a 10-99KB placeholder/thumbnail that the doctrine floor rejects.
        "min_bytes": 102_400,             # 100 KB — real 2K-resolution infographic floor
        "magic_bytes": b"\x89PNG",
        "magic_offset": 0,
        "magic_desc": "PNG image",
        "content_marker": None,
    },
    {
        "key": "teleprompter_html",
        "filename_template": "presenter-teleprompter.html",
        "standardized_dest": "presenter-teleprompter.html",
        "label": "presenter teleprompter web app",
        "expected_suffix": ".html",
        # RECONCILED (split-brain fix, 2026-08-18) to the doctrine-ratified floor:
        # presentations/presenters-speech-writer.md + sops/presenters-speech-writer-sops.md
        # AF-BUNDLE-COMPLETE gate-tie-in line states verbatim "HTML >= 20,000 bytes" — the
        # same text build_deck.py's DELIVERABLES_REQUIRED entry cites (commit eaae2e33,
        # 2026-07-12, "P3-01(c)5"), and build_teleprompter.py's own TELEPROMPTER_MIN_BYTES
        # self-check (20_000) enforces at the point of production. deliverables.py had
        # carried a never-chosen 5_000. PIPELINE-MANIFEST.json still carries an orphaned
        # 10_240 dated 2026-06-17 (git blame) that PREDATES the doctrine reconciliation —
        # the SOP text and the producer's own hard-fail floor decide this one, not the
        # stale manifest copy.
        "min_bytes": 20_000,              # 20 KB — a real self-contained scrolling
        "magic_bytes": None,
        "magic_offset": 0,
        "magic_desc": "text/html (no magic bytes — content check: must contain <html or <!DOCTYPE)",
        "content_marker": None,
    },
    # Feature L2-G (P9.6-WEBINAR-VIDEO): the webinar video is a TENTH, video-phase-owned
    # build deliverable. It is produced AFTER P8 assembly — build_deck.DELIVERABLES_REQUIRED
    # carries it with `produced_later: True` so the P8 postflight gate skips it, and the
    # P9.6 phase + the bundle gate + the delivery gate own its real presence. It is NOT a
    # loose client file (it is hosted in GHL via the v3 tier — never in client_package_files).
    # It IS required for the final closeout bundle: a build whose webinar never rendered
    # must not be reported done.
    {
        "key": "webinar_mp4",
        "filename_template": "{deck_slug}-WEBINAR.mp4",
        "standardized_dest": "WEBINAR-VIDEO.mp4",
        "label": "webinar video mp4",
        "expected_suffix": ".mp4",
        # RECONCILED (split-brain fix, 2026-08-18) to build_deck.py's DELIVERABLES_REQUIRED
        # / PIPELINE-MANIFEST.json value (both 1_048_576, dated 2026-08-07, Feature L2-G /
        # Gauntlet Loop 2 — "the fluid webinar video slideshow ... always several MB").
        # deliverables.py had carried 500_000 from a 2026-08-13 bulk copy-in of a stale
        # external source (commit 56d18ad2e, "copied verbatim ... the only copy anywhere
        # on this machine") that predates neither doctrine value — it was simply never
        # cross-checked against build_deck.py at copy time. Found during this reconciliation
        # pass; not one of the 9 keys in the original review table, but the same class of
        # drift and caught by the same drift guard.
        "min_bytes": 1_048_576,           # 1 MB — a real rendered webinar video floor
        "magic_bytes": None,
        "magic_offset": 4,
        "magic_desc": "MP4 video (ftyp box at offset 4 — checked via content scan)",
        "content_marker": None,
    },
]

# Derived views — NEVER edit these by hand; edit DELIVERABLE_AUDIT_SPEC above.
REQUIRED_DELIVERABLES = [
    {"key": s["key"], "filename": s["filename_template"], "label": s["label"]}
    for s in DELIVERABLE_AUDIT_SPEC
]
REQUIRED_KEYS = [s["key"] for s in DELIVERABLE_AUDIT_SPEC]

# Convenience: the number of items in the spec (10).
DELIVERABLE_COUNT = len(DELIVERABLE_AUDIT_SPEC)

# The gate artifact written on pass by fix_bundle_complete.run_bundle_gate().
BUNDLE_COMPLETE_FILENAME = "bundle_complete.json"

# The failure code emitted by the bundle-completeness gates. Registered in
# PIPELINE-MANIFEST.autofails so sync_check's C1 registry check resolves it.
AF_BUNDLE_INCOMPLETE = "AF-BUNDLE-INCOMPLETE"

# ---------------------------------------------------------------------------
# ARTIFACTS PRODUCED AND PHASE-GATED, BUT DELIBERATELY OUTSIDE THIS 10-ITEM
# CANONICAL BUNDLE (B1, 2026-08-19 — see CONTROL/FABLE-TRUTH.md §2 and
# CONTROL/MASTER-WORK-ORDER-20260818.md Wave B, unit B1).
#
# The B1 work order gave two options for the two workbook PDFs (and, by the
# same reasoning, PRESENTER-AUDIO-WEBINAR.mp3): (1) fold them into
# DELIVERABLE_AUDIT_SPEC as a documented 12, or (2) — if that breaks the
# 10-file bundle gate — leave DELIVERABLE_AUDIT_SPEC at 10 and record HERE,
# with code references, why each artifact is gated separately.
#
# EVIDENCE FOR (2), gathered 2026-08-19 by reading every consumer + test below:
#   * REQUIRED_KEYS (derived from DELIVERABLE_AUDIT_SPEC above) is asserted
#     byte-for-byte equal to PIPELINE-MANIFEST.json's `build_bundle_files`
#     (10 keys, manifest_version 50, universal-sops/presentation-slide-craft/
#     PIPELINE-MANIFEST.json) by FOUR independent hard-pinned checks:
#       - tests/test_deliverables_single_source.py::test_canonical_spec_has_ten_unique_keys
#         (asserts len(DELIVERABLE_AUDIT_SPEC) == 10 and DELIVERABLE_COUNT == 10)
#       - tests/test_deliverables_single_source.py::test_canonical_spec_matches_pipeline_manifest
#         (asserts sorted(manifest.build_bundle_files) == sorted(REQUIRED_KEYS))
#       - tests/test_fix8_bundle_complete.py::test_full_bundle_passes_and_writes_gate
#         (asserts bundle_complete.json's deliverable_count == len(REQUIRED_KEYS) == 10)
#       - tests/test_fix8_bundle_complete.py::test_manifest_lockstep
#         (same manifest<->REQUIRED_KEYS equality)
#     PLUS fix_bundle_complete.py's own `_selftest()` CASE E (manifest cross-check,
#     fix_bundle_complete.py lines ~206-227).
#   * PIPELINE-MANIFEST.json is hash-registered in three registries (the manifest
#     file itself, MANIFEST-SOURCE.txt, and universal-sops/_content-manifest.json)
#     and may only be changed via the full scripts/bump-version.sh +
#     scripts/version-markers.json lockstep — out of scope for this unit; only
#     the orchestrator runs that lockstep.
#   * Therefore: adding these keys to DELIVERABLE_AUDIT_SPEC WITHOUT the manifest
#     lockstep would immediately break all four tests above plus the selftest.
#     Option (2) is the correct, non-breaking choice until the lockstep runs.
#     (This B1 unit prepared, but did NOT apply, the manifest patch that would
#     be needed to promote these to Option (1) — see the B1 unit report.)
#
# THE TWO WORKBOOK PDFs — {deck_slug}-WORKBOOK.pdf, {deck_slug}-WORKBOOK-FILLABLE.pdf
#   Producing phase:   P8.25-WORKBOOK (PIPELINE-MANIFEST.json, order 8.25)
#   Producing script:  scripts/workbook_builder.py (+ scripts/workbook_mapper.py),
#                       invoked via `presentation-canonical-entry.sh --resume`
#                       per the manifest's executor.cmd for P8.25-WORKBOOK.
#   Gate codes:         AF-WORKBOOK-PROMPT-NO-CONTENT, AF-WORKBOOK-EMPTY,
#                       AF-WORKBOOK-BOTH (workbook_builder.py's own dual-PDF
#                       verify path — a stricter, dedicated gate than this
#                       bundle's generic non-empty check).
#   SOP:                sops/WORKBOOK-BUILDER-SOP.md §0 ("TWO PDFs ship,
#                       always") and §2/§8 (both PDFs uploaded to the client's
#                       GHL media library).
#   Why gated separately: an always-shipped client deliverable with its own
#   dedicated, stricter dual-PDF gate (AF-WORKBOOK-BOTH) — folding it into
#   this generic bundle spec would duplicate, not strengthen, that gate, and
#   (per the evidence above) would desync REQUIRED_KEYS from the manifest's
#   build_bundle_files without the version lockstep.
#
# PRESENTER-AUDIO-WEBINAR.mp3 — the webinarized/host-framed speech audio
#   Producing phase:   P9-SPEECH-WEBINAR-INTRO (PIPELINE-MANIFEST.json, order 8.54)
#   Producing script:  scripts/synthesize_full_speech.py --webinar-intro-outro
#                       (manifest executor.cmd for P9-SPEECH-WEBINAR-INTRO)
#   Gate code:          AF-WEBINAR-INTRO
#   SOP:                sops/WEBINAR-BUILDER-SOP.md §1 (consumed as an input
#                       to P9.6-WEBINAR-VIDEO) and
#                       sops/audio-demonstration-specialist-sops.md SOP 9.2.
#   Why gated separately: a REQUIRED INTERMEDIATE, not a standalone client
#   handoff — it feeds P9.6-WEBINAR-VIDEO's `{deck_slug}-WEBINAR.mp4`, which
#   IS the canonical `webinar_mp4` key already in DELIVERABLE_AUDIT_SPEC above.
#   The rendered webinar mp4 is the client-facing artifact; the intro-framed
#   audio that fed it is not separately delivered, so it does not belong in a
#   *client deliverable* whitelist — but it IS produced and phase-gated (never
#   silently dropped), which is the fact this note exists to make discoverable.
#
# Pinned by tests/test_deliverables_gated_separately.py — that test fails if
# this constant, DELIVERABLE_COUNT, or REQUIRED_KEYS drifts from what B1 left
# them at.
# ---------------------------------------------------------------------------
DELIVERABLES_GATED_SEPARATELY = {
    "workbook_pdf": {
        "filenames": ["{deck_slug}-WORKBOOK.pdf", "{deck_slug}-WORKBOOK-FILLABLE.pdf"],
        "producing_phase": "P8.25-WORKBOOK",
        "producing_script": "scripts/workbook_builder.py",
        "gate_codes": ["AF-WORKBOOK-PROMPT-NO-CONTENT", "AF-WORKBOOK-EMPTY", "AF-WORKBOOK-BOTH"],
        "sop": "sops/WORKBOOK-BUILDER-SOP.md §0, §2, §8",
        "reason": (
            "always-ship client deliverable with its own dual-PDF gate "
            "(AF-WORKBOOK-BOTH); not folded into the 10-item bundle without "
            "the manifest version lockstep (see note above)"
        ),
    },
    "presenter_audio_webinar_mp3": {
        "filenames": ["PRESENTER-AUDIO-WEBINAR.mp3"],
        "producing_phase": "P9-SPEECH-WEBINAR-INTRO",
        "producing_script": "scripts/synthesize_full_speech.py --webinar-intro-outro",
        "gate_codes": ["AF-WEBINAR-INTRO"],
        "sop": (
            "sops/WEBINAR-BUILDER-SOP.md §1, "
            "sops/audio-demonstration-specialist-sops.md SOP 9.2"
        ),
        "reason": (
            "required intermediate feeding P9.6-WEBINAR-VIDEO's webinar_mp4 "
            "(the actual client deliverable); not itself a separate client handoff"
        ),
    },
}


def _expand_filename(template: str, deck_slug: str) -> str:
    """Expand a {deck_slug}-templated filename for a specific deck_slug."""
    return template.replace("{deck_slug}", deck_slug)


# ---------------------------------------------------------------------------
# W02-B4 (MASTER Part 8 FIX 3/4 wiring): deliverables.py imports BOTH sibling
# single-source modules so no consumer ever has to find them on its own:
#
#   * deliverable_floors.guide_floor(n)  — THE one scaled presenter-guide floor
#     (max(1600*n, 12000)). The guide_pdf entry above keeps its raw reference
#     min_bytes (51_200) only because tests/test_deliverables_single_source.py
#     pins DELIVERABLE_AUDIT_SPEC byte-for-byte against build_deck.py's
#     DELIVERABLES_REQUIRED and PIPELINE-MANIFEST.json; the RUNTIME floor for a
#     specific deck is guide_floor(slide_count), re-exported here.
#
#   * deliverable_paths.CANONICAL_PATHS  — THE one key -> canonical run-dir
#     relative path map (MASTER Part 8 FIX 4). Re-exported under the same names
#     the paths module defines, so `from presentation_job.deliverables import
#     deliverable_path` resolves without importing the sibling directly.
#
# Both are guarded imports: if a sibling module has not landed yet (a fresh
# box mid-fleet-roll), deliverables.py itself must still import — the gates it
# feeds degrade to their pre-FIX behavior rather than crashing every run.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring, exercised by tests
    from presentation_job.deliverable_floors import (  # noqa: F401
        BYTES_PER_SLIDE,
        MIN_BYTES_ABSOLUTE,
        guide_floor,
        guide_floor_min,
        # FIX 103 (MASTER Part 8): the remaining deck-size floors + the one
        # slide-count reader, re-exported here so every bundle/QC gate can
        # resolve the whole floor family from the module it already imports.
        PDF_BYTES_PER_SLIDE,
        PDF_FLOOR_ABSOLUTE,
        pdf_floor,
        qc_verdict_floor,
        slide_count,
    )
except ImportError:  # pragma: no cover - fresh-box fallback
    guide_floor = None
    guide_floor_min = None
    BYTES_PER_SLIDE = None
    MIN_BYTES_ABSOLUTE = None
    PDF_BYTES_PER_SLIDE = None
    PDF_FLOOR_ABSOLUTE = None
    pdf_floor = None
    qc_verdict_floor = None
    slide_count = None

try:  # pragma: no cover - import wiring, exercised by tests
    from presentation_job.deliverable_paths import (  # noqa: F401
        CANONICAL_PATHS,
        deliverable_path,
    )
except ImportError:  # pragma: no cover - fresh-box fallback
    CANONICAL_PATHS = None
    deliverable_path = None


def scaled_guide_floor(n_slides):
    """The runtime presenter-guide floor for an n-slide deck, from THE single
    source (deliverable_floors.guide_floor). Raises RuntimeError when the
    floors module is unavailable — a caller that cannot compute the real floor
    must not silently fall back to the raw reference value, because the
    51_200 reference is exactly what made 12-slide decks structurally
    unpassable (F36/F43d)."""
    if guide_floor is None:
        raise RuntimeError(
            "presentation_job.deliverable_floors is unavailable — the scaled "
            "guide floor cannot be computed. Restore the module (fleet roll "
            "incomplete); refusing to fall back to the raw 51_200 reference "
            "value that broke short decks.")
    return guide_floor(n_slides)


def scaled_pdf_floor(n_slides):
    """FIX 103: the runtime bundle-PDF floor for an n-slide deck, from THE
    single source (deliverable_floors.pdf_floor = max(1506*n, 8192)). Raises
    RuntimeError when the floors module is unavailable — the flat 51_200
    reference made every deck under ~34 slides structurally unpassable, so a
    caller that cannot scale must fail loud, not regress to it."""
    if pdf_floor is None:
        raise RuntimeError(
            "presentation_job.deliverable_floors is unavailable — the scaled "
            "PDF floor cannot be computed. Restore the module (fleet roll "
            "incomplete); refusing to fall back to the raw 51_200 reference "
            "value that broke short decks.")
    return pdf_floor(n_slides)


def scaled_qc_verdict_floor(n_slides):
    """FIX 103 / Fix 6: the runtime per-slide QC verdict floor for an n-slide
    deck, from THE single source (deliverable_floors.qc_verdict_floor =
    min(20, n)). A floor above the deck's slide count is unpassable without
    fabrication. Raises RuntimeError when the floors module is unavailable."""
    if qc_verdict_floor is None:
        raise RuntimeError(
            "presentation_job.deliverable_floors is unavailable — the scaled "
            "QC verdict floor cannot be computed. Restore the module (fleet "
            "roll incomplete); refusing to fall back to the flat 20-slide "
            "reference floor that demanded fabricated verdicts.")
    return qc_verdict_floor(n_slides)


def deck_slide_count(run_dir):
    """FIX 103: THIS deck's slide count, read by THE single source
    (deliverable_floors.slide_count) from the run dir's slides.json /
    arc_allocation.json — never a constant. Returns 0 when undeterminable
    (the caller decides its fallback; the helper never invents a number)."""
    if slide_count is None:
        raise RuntimeError(
            "presentation_job.deliverable_floors is unavailable — the deck "
            "slide count cannot be read. Restore the module (fleet roll "
            "incomplete); refusing to guess a slide count from a constant.")
    return slide_count(run_dir)


__all__ = [
    "DELIVERABLE_AUDIT_SPEC",
    "REQUIRED_DELIVERABLES",
    "REQUIRED_KEYS",
    "DELIVERABLE_COUNT",
    "BUNDLE_COMPLETE_FILENAME",
    "AF_BUNDLE_INCOMPLETE",
    "DELIVERABLES_GATED_SEPARATELY",
    "BYTES_PER_SLIDE",
    "MIN_BYTES_ABSOLUTE",
    "guide_floor",
    "guide_floor_min",
    "scaled_guide_floor",
    # FIX 103: the remaining floor family + the slide-count reader.
    "PDF_BYTES_PER_SLIDE",
    "PDF_FLOOR_ABSOLUTE",
    "pdf_floor",
    "qc_verdict_floor",
    "slide_count",
    "scaled_pdf_floor",
    "scaled_qc_verdict_floor",
    "deck_slide_count",
    "CANONICAL_PATHS",
    "deliverable_path",
]
