#!/usr/bin/env python3
"""P8.15-MOTION — the governed motion audit phase (MG-036).

Executor for the pipeline phase P8.15-MOTION (PIPELINE-MANIFEST.json,
executor_kind "script", dispatched by presentation_job.phases
Engine.run_phase like every other script phase; there is no handler
registry and this script is not one).

WHAT IT PROVES, PLAINLY

build_deck.py plans the deck's motion path at render time (election,
package authentication, embed through add_motion_media) and writes
working/checkpoints/motion.json. This phase is the post-assembly
audit of that record against the DELIVERED artifacts, run after
P8-ASSEMBLE has attested the bundle deck:

  * every slide the record claims as embedded is proven against the
    delivered deck itself: the deck's media parts are hashed and the
    authenticated component bytes must be inside the file. A record
    claiming an embed the delivered deck does not carry FAILS this
    phase (MOTION_EMBED_MISSING). This is the wiring proof: a
    component counts only when the deck actually plays it.
  * every degraded slide must carry its MOTION_* reason code; a
    degrade without a reason is a record defect and fails the phase.
  * a component whose package authenticates NOW but was never
    embedded (it landed after assembly) is recorded
    produced_late_not_embedded: an honest state, not a failure. The
    delivered deck is static for that slide and the piece is ready
    for a re-assembly.
  * the B14 limits are re-asserted from the live package records
    (cap, slots, clip size and duration), so a package swapped after
    the render is caught here even if the render-time record was
    honest when written.

The phase ALWAYS writes both run records (motion.json refreshed,
working/checkpoints/slide_media_manifest.json for the P9.6 webinar
build), including on decks that elected no motion: the records then
carry the election outcome and zero motion slides, and the phase
passes. Exit codes: 0 pass, 3 a required input is absent (no
slides.json and no motion.json to audit), 6 audit failure.

PLATFORM TRUTH: this audit proves embed structure and byte identity.
Playback inside Microsoft PowerPoint is UNVERIFIED on every platform
and is never claimed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from presentation_job import motion as _motion  # noqa: E402

EXIT_OK = 0
EXIT_INPUT_MISSING = 3
EXIT_AUDIT_FAILED = 6


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_delivered_deck(run_dir: Path):
    """The assembled bundle deck: *-FINAL.pptx under the run (newest
    wins), else the render output out.pptx. None when no deck exists."""
    candidates = [p for p in run_dir.rglob("*-FINAL.pptx")
                  if p.is_file() and not p.name.startswith(".")]
    if not candidates:
        out = run_dir / "out.pptx"
        return out if out.is_file() else None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _deck_media_hashes(deck: Path) -> dict:
    """{sha256: part_name} for every video media part inside a deck."""
    hashes = {}
    with zipfile.ZipFile(deck) as zf:
        for name in zf.namelist():
            if name.startswith("ppt/media/") and name.lower().endswith(
                    (".mp4", ".mov", ".m4v", ".webm")):
                hashes[hashlib.sha256(zf.read(name)).hexdigest()] = name
    return hashes


def run(run_dir: Path) -> int:
    run_dir = Path(run_dir).resolve()
    record = _motion.read_motion_record(run_dir)
    slides = None
    slides_path = run_dir / "working" / "copy" / "slides.json"
    if slides_path.is_file():
        try:
            obj = json.loads(slides_path.read_text(encoding="utf-8"))
            slides = obj.get("slides") if isinstance(obj, dict) else obj
        except Exception:  # noqa: BLE001
            slides = None
    if record is None and not slides:
        print("MOTION PHASE: no motion.json and no slides.json under "
              f"{run_dir}; nothing can be audited (input missing).",
              file=sys.stderr)
        return EXIT_INPUT_MISSING

    # The one validator lives in build_deck (P02). Import it lazily:
    # without it nothing can be authenticated, and the phase fails
    # closed rather than guessing.
    try:
        import build_deck
    except Exception as exc:  # noqa: BLE001
        print(f"MOTION PHASE: build_deck is not importable ({exc!r}); "
              "the motion validator is unavailable, failing closed.",
              file=sys.stderr)
        return EXIT_INPUT_MISSING

    if record is None:
        # build_deck's canonical path always plans; a missing record
        # means assembly ran outside it. Rebuild the plan from the
        # declared slides so the audit still has a governed record.
        record, _media = build_deck.plan_motion_media(run_dir, slides)
        rebuilt = True
    else:
        rebuilt = False

    election = record.get("election") or {}
    deck = _find_delivered_deck(run_dir)
    media_hashes = {}
    if deck is not None:
        try:
            media_hashes = _deck_media_hashes(deck)
        except Exception as exc:  # noqa: BLE001
            print(f"MOTION PHASE: delivered deck {deck} is unreadable "
                  f"({exc!r}); no embed can be proven.", file=sys.stderr)
            media_hashes = {}

    # Live truth: which declared slides authenticate RIGHT NOW.
    live = build_deck._authenticated_motion_outcomes(run_dir)

    failures = []
    late = []
    embedded_verified = 0
    entries = record.get("slides") or []
    by_slide = {e.get("slide"): e for e in entries if isinstance(e, dict)}

    # Slides that authenticate now but the record does not carry as
    # embedded: they were produced after assembly (or the record was
    # never finalized). Record the late state honestly.
    for ord_, outcome in sorted(live.items()):
        entry = by_slide.get(ord_)
        if entry is not None and entry.get("status") == \
                _motion.MOTION_STATUS_EMBEDDED:
            continue
        if entry is None:
            entry = {k: v for k, v in outcome.items()
                     if not k.startswith("_")}
            entries.append(entry)
            by_slide[ord_] = entry
        if (entry.get("artifact_sha256") or "") in media_hashes:
            entry["status"] = _motion.MOTION_STATUS_EMBEDDED
            entry["embed"] = {
                "media_part": media_hashes[entry["artifact_sha256"]],
                "deck": str(deck), "proven_by": _motion.MOTION_PHASE_ID}
            entry.pop("reason_code", None)
            entry.pop("detail", None)
            # embedded_verified is counted once, in the sweep below.
        else:
            entry["status"] = _motion.MOTION_STATUS_LATE
            entry["reason_code"] = None
            entry["detail"] = (
                "the component's package authenticates but the piece "
                "is not in the delivered deck; it was produced after "
                "assembly (produced_late_not_embedded)")
            late.append(ord_)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status == _motion.MOTION_STATUS_EMBEDDED:
            sha = entry.get("artifact_sha256") or ""
            if sha in media_hashes:
                embedded_verified += 1
            else:
                failures.append({
                    "slide": entry.get("slide"),
                    "code": _motion.MOTION_EMBED_MISSING,
                    "detail": "motion.json claims this slide embedded "
                              "but the delivered deck carries no media "
                              "part byte-identical to the authenticated "
                              "component"})
        elif status == _motion.MOTION_STATUS_DEGRADED:
            if not entry.get("reason_code"):
                failures.append({
                    "slide": entry.get("slide"),
                    "code": _motion.MOTION_RECORD_INVALID,
                    "detail": "a degraded motion slide carries no "
                              "reason code; every degrade must be named"})
        elif status == _motion.MOTION_STATUS_VALIDATED:
            # Planned but never finalized and not provable in the deck:
            # it was produced, not embedded.
            entry["status"] = _motion.MOTION_STATUS_LATE
            entry["detail"] = (
                "the component was validated at plan time but is not "
                "in the delivered deck (produced_late_not_embedded)")
            late.append(entry.get("slide"))

    # B14 re-assertion from the live records: the cap counts pieces
    # the deck actually carries or could carry.
    live_validated = len(live)
    if live_validated > _motion.MOTION_MAX_PIECES_PER_DECK:
        failures.append({
            "slide": None,
            "code": _motion.MOTION_CAP_EXCEEDED,
            "detail": f"{live_validated} motion packages authenticate "
                      f"for this deck, over the B14 hard cap of "
                      f"{_motion.MOTION_MAX_PIECES_PER_DECK}"})

    record["slides"] = entries
    record["phase_audit"] = {
        "phase": _motion.MOTION_PHASE_ID,
        "audited_at": _now_iso(),
        "record_rebuilt": rebuilt,
        "election": election,
        "deck": str(deck) if deck else None,
        "embedded_verified": embedded_verified,
        "produced_late_not_embedded": late,
        "failures": failures,
    }
    _motion.write_motion_record(run_dir, record)
    _motion.write_slide_media_manifest(run_dir, record)

    summary = {
        "phase": _motion.MOTION_PHASE_ID,
        "elected": bool(election.get("elected")),
        "deck": str(deck) if deck else None,
        "embedded_verified": embedded_verified,
        "produced_late_not_embedded": late,
        "failures": failures,
        "motion_record": _motion.MOTION_RECORD_REL,
        "slide_media_manifest": _motion.MOTION_SLIDE_MEDIA_MANIFEST_REL,
    }
    print(json.dumps(summary, indent=2))
    if failures:
        for f in failures:
            print(f"MOTION PHASE FAIL slide={f['slide']}: {f['code']}: "
                  f"{f['detail']}", file=sys.stderr)
        return EXIT_AUDIT_FAILED
    return EXIT_OK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="P8.15-MOTION: audit the governed motion record "
                    "against the delivered deck (MG-036).")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    return run(Path(args.run_dir))


if __name__ == "__main__":
    sys.exit(main())
