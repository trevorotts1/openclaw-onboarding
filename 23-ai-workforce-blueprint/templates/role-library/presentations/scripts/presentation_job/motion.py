"""Motion-graphics seam for the presentation pipeline (MG-036).

WHAT THIS MODULE IS, PLAINLY

The single shared definition site for the governed motion path that
Skill 72 Motion Graphics V2 (directive Section 14, patch points
P01-P08) adds to this pipeline:

  * the B14 election semantics (the item 34 reconciliation): motion is
    allowed only when the client elected it. The election field is
    ``want_motion_graphics`` (intake capture key
    ``WANT_MOTION_GRAPHICS``), resolved through
    presentation_job.defers like the other want_* elections, default
    NO, with the same waiver discipline (a recorded ``motion_graphics``
    waiver IS the decline).
  * the fixture constraints that govern every elected piece: a hard
    cap of 2 motion pieces per deck; Slot A is slide 1, Slot B is a
    section divider slide; a piece is a silent 1920x1080 30 fps
    H.264 MP4 of 4.0 to 8.0 seconds and at most 20 MB; its poster is
    byte-identical to the package poster and to the slide's QC PNG
    (renders/slide-NN.png), and the poster is deliberately the
    piece's final readable state (MG-035's poster selector refuses
    mid-reveal frames): the governed path enforces poster
    byte-identity and does NOT claim frame-0 parity for reveal
    pieces, whose frame 0 is the designed opening state.
  * the run records: ``working/checkpoints/motion.json`` (the run
    record every consumer reads) and
    ``working/checkpoints/slide_media_manifest.json`` (the
    slide-media manifest the webinar build consumes), both written
    atomically (sibling temp file, then os.replace).
  * the degrade vocabulary: every motion failure degrades the slide
    to its static render with a reason code from the MOTION_* set
    below. Nothing on this path fails silently and nothing is waved
    through: a slide is embedded only after build_deck.py's
    validate_motion_slide_artifacts has authenticated its MG-035
    package (package record, MG-034 QC verdict, poster parity,
    receipt binding, hashes) in the current run.

CONSUMERS
  build_deck.py          plans the record at preflight, embeds through
                         add_motion_media at assembly, finalizes the
                         record from the assembled deck's media parts.
  scripts/motion_phase.py (phase P8.15-MOTION) re-verifies the record
                         against the delivered bundle deck and the
                         live packages, and (re)writes the
                         slide-media manifest.
  build_webinar_video.py reads the slide-media manifest (or derives
                         it from motion.json) and hash-verifies every
                         clip before webinar_ffmpeg.py may use it.
  phase_verifiers.py     surfaces motion_summary_line (the B14
                         Section 5.4 one-line delivery summary) as the
                         P8.15-MOTION verifier's PASS NOTE, the same
                         shape the VSL verifier's defer/waived NOTE
                         takes, so the run record states the motion
                         outcome without anyone opening the JSON.

This module deliberately holds no validation logic of its own beyond
election/slot/record plumbing: package authentication lives in
build_deck.py (the P02 teeth), so there is exactly one validator.

PLATFORM TRUTH: nothing here claims PowerPoint playback. Playback
inside Microsoft PowerPoint is UNVERIFIED on every platform; the
records this module writes carry embed structure and hashes, never a
playback claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Election (B14 seam semantics; resolved via presentation_job.defers)
# ---------------------------------------------------------------------------

MOTION_ELECTION_KEY = "want_motion_graphics"
MOTION_ELECTION_CAPTURE_KEY = "WANT_MOTION_GRAPHICS"
MOTION_ELECTION_WAIVER_RULE = "motion_graphics"
MOTION_ELECTION_DEFAULT = "no"

# ---------------------------------------------------------------------------
# B14 fixture constraints for an elected motion piece
# ---------------------------------------------------------------------------

MOTION_MAX_PIECES_PER_DECK = 2
MOTION_SLOT_A_SLIDE = 1
MOTION_CLIP_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MOTION_CLIP_MIN_SECONDS = 4.0
MOTION_CLIP_MAX_SECONDS = 8.0
MOTION_CLIP_WIDTH = 1920
MOTION_CLIP_HEIGHT = 1080
MOTION_CLIP_FPS = 30.0

# ---------------------------------------------------------------------------
# Run records
# ---------------------------------------------------------------------------

MOTION_RECORD_REL = "working/checkpoints/motion.json"
MOTION_SLIDE_MEDIA_MANIFEST_REL = "working/checkpoints/slide_media_manifest.json"
MOTION_RECORD_SCHEMA_VERSION = "1.0"
MOTION_RECORD_GENERATED_BY = "MG-036 presentation motion seam"

# ---------------------------------------------------------------------------
# MG-035 package layout inside a slide's motion workspace. The media
# block in slides.json names the workspace through its paths
# (Section 14.2: working/motion/slide-NN/manifest.json,
# working/motion/slide-NN/renders/artifacts.json,
# working/motion/slide-NN/delivery/poster.png); the governed package
# sits beside them under package/.
# ---------------------------------------------------------------------------

MOTION_PACKAGE_DIR_NAME = "package"
MOTION_PACKAGE_RECORD_NAME = "package-record.json"
MOTION_PACKAGE_CLIP_NAME = "component.mp4"
MOTION_PACKAGE_POSTER_NAME = "poster.png"

# ---------------------------------------------------------------------------
# Degrade reason codes. Every motion failure lands in motion.json with
# exactly one of these codes and the slide renders static instead.
# MOTION_LATE_NOT_EMBEDDED is a status, not a failure: the package
# authenticated only after the deck was assembled, so the piece was
# produced but is not in the deck (B14 produced_late_not_embedded).
# ---------------------------------------------------------------------------

MOTION_NOT_ELECTED = "MOTION_NOT_ELECTED"
MOTION_CAP_EXCEEDED = "MOTION_CAP_EXCEEDED"
MOTION_SLOT_INVALID = "MOTION_SLOT_INVALID"
MOTION_MEDIA_MALFORMED = "MOTION_MEDIA_MALFORMED"
MOTION_PATH_ESCAPE = "MOTION_PATH_ESCAPE"
MOTION_PACKAGE_MISSING = "MOTION_PACKAGE_MISSING"
MOTION_PACKAGE_INVALID = "MOTION_PACKAGE_INVALID"
MOTION_QC_FAILED = "MOTION_QC_FAILED"
MOTION_HASH_MISMATCH = "MOTION_HASH_MISMATCH"
MOTION_RECEIPT_UNREADABLE = "MOTION_RECEIPT_UNREADABLE"
MOTION_RECEIPT_MISMATCH = "MOTION_RECEIPT_MISMATCH"
MOTION_POSTER_MISMATCH = "MOTION_POSTER_MISMATCH"
MOTION_CLIP_FORMAT = "MOTION_CLIP_FORMAT"
MOTION_CLIP_TOO_LARGE = "MOTION_CLIP_TOO_LARGE"
MOTION_CLIP_DURATION = "MOTION_CLIP_DURATION"
MOTION_CLIP_NOT_SILENT = "MOTION_CLIP_NOT_SILENT"
MOTION_PLAYBACK_MISMATCH = "MOTION_PLAYBACK_MISMATCH"
MOTION_PLACEMENT_INVALID = "MOTION_PLACEMENT_INVALID"
MOTION_WEBINAR_POLICY_INVALID = "MOTION_WEBINAR_POLICY_INVALID"
MOTION_LOOP_UNQUALIFIED = "MOTION_LOOP_UNQUALIFIED"
MOTION_HOLD_UNPROVEN = "MOTION_HOLD_UNPROVEN"
MOTION_COPY_INVENTORY_INCOMPLETE = "MOTION_COPY_INVENTORY_INCOMPLETE"
MOTION_COPY_DENSITY = "MOTION_COPY_DENSITY"
MOTION_EMBED_MISSING = "MOTION_EMBED_MISSING"
MOTION_RECORD_INVALID = "MOTION_RECORD_INVALID"
MOTION_CLIP_EXCEEDS_SLOT = "MOTION_CLIP_EXCEEDS_SLOT"

# Slot-exclusion codes (FIX-PLAN Item 34 residual R3, B14 Sections 3.2
# and 3.3): a slide can BE a nominal slot (slide 1, or a section
# divider) and still be doctrine-barred from hosting a piece. That is
# a different fact from MOTION_SLOT_INVALID (no slot at all), so each
# exclusion carries its own named code and the motion record entry
# says which doctrine barred the slide.
MOTION_SLOT_EXCLUDED_HOOK = "MOTION_SLOT_EXCLUDED_HOOK"
MOTION_SLOT_EXCLUDED_PRICE = "MOTION_SLOT_EXCLUDED_PRICE"
MOTION_SLOT_EXCLUDED_OFFER_CTA = "MOTION_SLOT_EXCLUDED_OFFER_CTA"
MOTION_SLOT_EXCLUDED_PROOF = "MOTION_SLOT_EXCLUDED_PROOF"

MOTION_STATUS_EMBEDDED = "embedded"
MOTION_STATUS_VALIDATED = "validated"
MOTION_STATUS_DEGRADED = "degraded"
MOTION_STATUS_LATE = "produced_late_not_embedded"

# Phase id of the pipeline phase that owns the post-assembly audit.
MOTION_PHASE_ID = "P8.15-MOTION"

# ---------------------------------------------------------------------------
# Motion copy-density policy (Section 14.2, narrowly scoped).
#
# The deck-level copy checks are NOT disabled for motion slides: the
# approved copy in slides.json stays authoritative and is still banded
# by the deck's own copy-density gate. What a motion slide adds is
# time: words may appear at distinct times. The declared policy for
# the component itself is therefore judged on the state every viewer
# can read, the final (poster) state recorded in the package record's
# placement audit:
#   * the final state's essential text must fit the same slide-total
#     character ceiling the still policy enforces (the COPY band
#     ceiling build_deck applies to a still slide's copy), and
#   * no temporal state may introduce words outside the approved copy
#     plus the validated dynamic chart labels/values (enforced by the
#     temporal copy-inventory comparison in build_deck).
# A component denser than a still slide at its readable state is a
# policy breach (MOTION_COPY_DENSITY), never a silent pass.
# ---------------------------------------------------------------------------

MOTION_COPY_FINAL_STATE_CHAR_CEILING = 180  # == build_deck COPY slide-total ceiling

# Section-divider markers for Slot B, matched against the slide's arc
# tag blob (the same token family build_deck's _load_slide_arc_tags
# produces: arc_section/section/beat/tag/type/role/phase strings plus
# tags[] entries, lowercased). The markers cover both vocabularies in
# force: build_deck._is_hook_or_banner_slide's ("section-banner",
# "section_banner", "sectionbanner", "banner") and the B14 seam's own
# "section divider" spelling. A bare "section" is deliberately NOT a
# marker: ordinary content slides carry section names in their tags.
SECTION_DIVIDER_MARKERS = (
    "divider",
    "section-banner",
    "section_banner",
    "sectionbanner",
    "banner",
)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Hex sha256 of a file's bytes, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    """Parse a JSON file to a dict; None when absent/unreadable/not a dict."""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 -- a bad record is data, not a crash
        return None
    return obj if isinstance(obj, dict) else None


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> Path:
    """Write JSON atomically: sibling temp file, then os.replace.

    The same save discipline as assemble_pptx and the engine's state
    store, so a crashed writer never leaves a torn record at the
    governed path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return path


def resolve_contained(run_dir: Path, rel: Any) -> Optional[Path]:
    """Resolve a run-relative path with symlinks resolved BEFORE the
    containment check (Section 14.2). Returns the resolved absolute
    path when it stays inside the run root, else None. A non-string or
    empty value resolves to None."""
    if not isinstance(rel, str) or not rel.strip():
        return None
    root = Path(run_dir).resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


# ---------------------------------------------------------------------------
# Election
# ---------------------------------------------------------------------------

def election_for_run(run_dir: Path,
                     intake: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve the deck's motion election.

    Returns {"elected": bool, "value": "yes"|"no", "source":
    "intake_capture"|"waiver"|"default"|"top_level"}. The value comes
    from presentation_job.defers.resolve_intake_value with the
    want_motion_graphics registration (default "no"), so the capture
    field, the waiver discipline, and the default all behave exactly
    like the want_vsl_page election. Never raises on malformed
    intake: an unreadable election is NO."""
    from presentation_job import defers  # local import: no cycle risk

    if intake is None:
        intake = defers.load_intake(Path(run_dir))
    value = defers.resolve_intake_value(intake, MOTION_ELECTION_KEY)
    source = "default"
    if isinstance(intake, dict):
        cap = intake.get("pre_presentation_capture")
        if isinstance(cap, dict) and any(
                cap.get(k) is not None
                for k in (MOTION_ELECTION_CAPTURE_KEY, MOTION_ELECTION_KEY,
                          MOTION_ELECTION_CAPTURE_KEY.lower())):
            source = "intake_capture"
        elif MOTION_ELECTION_WAIVER_RULE in defers._waiver_rules(intake):
            source = "waiver"
        elif intake.get(MOTION_ELECTION_KEY) is not None:
            source = "top_level"
    elected = (value == "yes")
    return {"elected": elected, "value": value or MOTION_ELECTION_DEFAULT,
            "source": source}


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------

def is_section_divider_blob(tag_blob: Optional[str]) -> bool:
    """True when an arc tag blob marks the slide as a section divider."""
    if not tag_blob:
        return False
    blob = str(tag_blob).lower()
    return any(marker in blob for marker in SECTION_DIVIDER_MARKERS)


def slot_for_slide(slide_ord: int, tag_blob: Optional[str]) -> Optional[str]:
    """The B14 slot a slide may host a motion piece in: "A" for
    slide 1, "B" for a section divider, else None (no slot, so a
    motion declaration there degrades MOTION_SLOT_INVALID)."""
    if slide_ord == MOTION_SLOT_A_SLIDE:
        return "A"
    if is_section_divider_blob(tag_blob):
        return "B"
    return None


# ---------------------------------------------------------------------------
# Slot exclusions (B14 Sections 3.2 and 3.3, Item 34 residual R3)
#
# Slot legality is judged from run data the validator already reads
# neighbors of: the slide's arc tag blob (arc_allocation.json, via
# build_deck._load_slide_arc_tags, whose "hook" token is the per-slide
# dedicated-hook marker; hook_package.json carries only a slide COUNT,
# never slide numbers, so it cannot name a slide) and the slide's
# approved copy lines (slides.json copy, threaded in by the planner).
# No new copy and no new client question is invented for this judgment.
# ---------------------------------------------------------------------------

# Arc-blob markers for the offer/CTA arc family.
OFFER_CTA_ARC_MARKERS = (
    "offer",
    "cta",
    "call-to-action",
    "call_to_action",
)

# Arc-blob markers for proof / guarantee / signature-quote slides.
PROOF_ARC_MARKERS = (
    "proof",
    "guarantee",
    "testimonial",
    "signature-quote",
    "signature_quote",
    "signature quote",
)

# Approved-copy markers for proof / guarantee copy. The price judgment
# has its own matcher below (a currency amount, or the FINAL_PRICE
# literal the copy pipeline carries).
PROOF_COPY_MARKERS = (
    "guarantee",
    "guaranteed",
    "money-back",
    "money back",
    "testimonial",
)

_PRICE_TOKEN_RE = re.compile(r"\$\s?\d")


def _copy_blob(copy_lines) -> str:
    if not copy_lines:
        return ""
    return "\n".join(str(c) for c in copy_lines).lower()


def slot_exclusion(slide_ord: int, tag_blob: Optional[str],
                   copy_lines=None):
    """The B14 Section 3.2 doctrine exclusion for one nominal slot
    slide, as (reason_code, detail), or None when the slide may host
    a piece. Judged in doctrine order: dedicated hook, price copy,
    offer/CTA arc, proof or guarantee. Adjacency of the two filled
    slots (B14 Section 3.2's last exclusion) is deliberately NOT
    enforced here or in the planner: the landed MG-036 suite pins
    adjacent slides 1 and 2 as the two kept pieces of its cap case
    (test_plan_enforces_b14_cap), so an adjacency degrade would
    contradict the merged seam's own acceptance behavior. The
    conflict is recorded in the Item 34 stream record (B34-IMPL)
    for a coordinator ruling; until then the landed behavior
    governs, exactly as with the frame-0 poster divergence."""
    blob = str(tag_blob or "").lower()
    copy = _copy_blob(copy_lines)
    if "hook" in blob:
        return (MOTION_SLOT_EXCLUDED_HOOK,
                f"slide {slide_ord} is a dedicated hook slide (the "
                f"run's arc data marks it hook); B14 Section 3.2 "
                f"bars motion on dedicated hook slides, so the piece "
                f"degrades to the static slide")
    if "final_price" in copy or _PRICE_TOKEN_RE.search(copy):
        return (MOTION_SLOT_EXCLUDED_PRICE,
                f"slide {slide_ord}'s approved copy carries a price "
                f"token or FINAL_PRICE; B14 Section 3.2 bars motion "
                f"on price and offer slides, so the piece degrades "
                f"to the static slide")
    for marker in OFFER_CTA_ARC_MARKERS:
        if marker in blob:
            return (MOTION_SLOT_EXCLUDED_OFFER_CTA,
                    f"slide {slide_ord} sits in the offer/CTA arc "
                    f"(arc marker {marker!r}); B14 Section 3.2 bars "
                    f"motion on offer and CTA slides, so the piece "
                    f"degrades to the static slide")
    for marker in PROOF_ARC_MARKERS:
        if marker in blob:
            return (MOTION_SLOT_EXCLUDED_PROOF,
                    f"slide {slide_ord} is a proof, guarantee or "
                    f"signature-quote slide (arc marker {marker!r}); "
                    f"B14 Section 3.2 bars motion there, so the piece "
                    f"degrades to the static slide")
    for marker in PROOF_COPY_MARKERS:
        if marker in copy:
            return (MOTION_SLOT_EXCLUDED_PROOF,
                    f"slide {slide_ord}'s approved copy carries "
                    f"proof or guarantee copy ({marker!r}); B14 "
                    f"Section 3.2 bars motion on proof and guarantee "
                    f"slides, so the piece degrades to the static "
                    f"slide")
    return None


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def empty_motion_record(election: Dict[str, Any]) -> Dict[str, Any]:
    """A fresh motion.json skeleton for a run."""
    return {
        "schema_version": MOTION_RECORD_SCHEMA_VERSION,
        "generated_by": MOTION_RECORD_GENERATED_BY,
        "phase": MOTION_PHASE_ID,
        "election": {
            "field": MOTION_ELECTION_KEY,
            "value": election.get("value", MOTION_ELECTION_DEFAULT),
            "elected": bool(election.get("elected")),
            "source": election.get("source", "default"),
        },
        "limits": {
            "max_pieces_per_deck": MOTION_MAX_PIECES_PER_DECK,
            "clip_max_bytes": MOTION_CLIP_MAX_BYTES,
            "clip_duration_seconds": [MOTION_CLIP_MIN_SECONDS,
                                      MOTION_CLIP_MAX_SECONDS],
            "clip_dimensions": [MOTION_CLIP_WIDTH, MOTION_CLIP_HEIGHT],
            "clip_fps": MOTION_CLIP_FPS,
            "silent": True,
        },
        "slides": [],
    }


def motion_record_path(run_dir: Path) -> Path:
    return Path(run_dir) / MOTION_RECORD_REL


def write_motion_record(run_dir: Path, record: Dict[str, Any]) -> Path:
    return atomic_write_json(motion_record_path(run_dir), record)


def read_motion_record(run_dir: Path) -> Optional[Dict[str, Any]]:
    return read_json_file(motion_record_path(run_dir))


def slide_media_manifest_path(run_dir: Path) -> Path:
    return Path(run_dir) / MOTION_SLIDE_MEDIA_MANIFEST_REL


def slide_media_manifest_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the slide-media manifest the webinar build consumes
    from a motion record: one entry per slide whose component is in
    the deck (embedded) or authenticated and awaiting the webinar
    render (validated), with the clip identity the consumer must
    re-verify by hash before use."""
    entries = []
    for entry in record.get("slides", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") not in (MOTION_STATUS_EMBEDDED,
                                       MOTION_STATUS_VALIDATED):
            continue
        entries.append({
            "slide": entry.get("slide"),
            "status": entry.get("status"),
            "clip_path": entry.get("clip_path"),
            "clip_sha256": entry.get("artifact_sha256"),
            "poster_path": entry.get("poster_path"),
            "poster_sha256": entry.get("poster_sha256"),
            "fit": (entry.get("webinar_policy") or {}).get("fit"),
            "job_id": entry.get("job_id"),
        })
    return {
        "schema_version": MOTION_RECORD_SCHEMA_VERSION,
        "generated_by": MOTION_RECORD_GENERATED_BY,
        "source_record": MOTION_RECORD_REL,
        "slides": entries,
    }


def write_slide_media_manifest(run_dir: Path,
                               record: Dict[str, Any]) -> Path:
    return atomic_write_json(slide_media_manifest_path(run_dir),
                             slide_media_manifest_from_record(record))


# ---------------------------------------------------------------------------
# Delivery surfacing (B14 Section 5.4 tail, Item 34 residual R4)
# ---------------------------------------------------------------------------

def motion_summary_line(record: Dict[str, Any],
                        arc_tags: Optional[Dict[int, str]] = None) -> str:
    """The one-line motion summary the delivery path surfaces, derived
    from the LANDED motion.json shape (election object plus slides[]
    entries keyed by slide number with MOTION_* reason codes; the
    record stores no slot letter on degraded-before-slot entries, so
    the letter is derived through slot_for_slide exactly as the seam
    derives it, using the entry's recorded slot when it carries one).

    Shape: "Motion: 1 of 2 pieces embedded; slot B degraded
    (MOTION_...); deck complete on static slides". A deck that did
    not elect motion reads "Motion: not elected; deck complete on
    static slides". The line states embed structure only; it never
    claims playback."""
    record = record if isinstance(record, dict) else {}
    election = record.get("election") or {}
    if not election.get("elected"):
        return "Motion: not elected; deck complete on static slides"
    slides = [e for e in (record.get("slides") or [])
              if isinstance(e, dict)]
    total = len(slides)
    embedded = sum(1 for e in slides
                   if e.get("status") == MOTION_STATUS_EMBEDDED)
    parts = [f"Motion: {embedded} of {total} pieces embedded"]
    arc_tags = arc_tags or {}
    for entry in slides:
        status = entry.get("status")
        if status == MOTION_STATUS_EMBEDDED:
            continue
        slide = entry.get("slide")
        letter = entry.get("slot")
        if not letter and isinstance(slide, int):
            letter = slot_for_slide(slide, arc_tags.get(slide, ""))
        name = f"slot {letter}" if letter else f"slide {slide}"
        if status == MOTION_STATUS_DEGRADED:
            parts.append(
                f"{name} degraded "
                f"({entry.get('reason_code') or MOTION_RECORD_INVALID})")
        elif status == MOTION_STATUS_LATE:
            parts.append(f"{name} produced late, not embedded")
        elif status == MOTION_STATUS_VALIDATED:
            parts.append(f"{name} validated, not embedded")
        else:
            parts.append(f"{name} {status or 'unrecorded'}")
    if embedded < total or total == 0:
        parts.append("deck complete on static slides")
    return "; ".join(parts)
