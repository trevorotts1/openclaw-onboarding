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
        "min_bytes": 50000,
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
        "min_bytes": 50000,
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
        "min_bytes": 20000,
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
        "min_bytes": 5000,
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
        "min_bytes": 20000,
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
        "min_bytes": 5000,
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
        "min_bytes": 100000,
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
        "min_bytes": 5000,
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
        "min_bytes": 500000,
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


def _expand_filename(template: str, deck_slug: str) -> str:
    """Expand a {deck_slug}-templated filename for a specific deck_slug."""
    return template.replace("{deck_slug}", deck_slug)
