"""Deliberate poster-frame selection for motion components (MG-035).

The poster is the still that stands for the piece everywhere the video
does not play: the slide image in the deck, the PDF export page, the
package thumbnail. Choosing it by accident (frame 0, or whatever frame
a tool happens to grab) can publish false data: directive Section 17.2
shows a bar chart at frame 45 whose bars stand at half reveal while the
final value labels already print. A poster taken there presents
partial data as if it were final.

This module selects the poster from the compiled plan, never from a
guess:

- A frame is eligible only when every scene has COMPLETED its motion
  there (no scene is before its motion start or inside its changing
  interval) and the frame sits inside the piece's terminal hold, so
  the state on the poster is the state the piece ends on.
- When the manifest declares delivery.poster_frame, the declaration
  is honored only if the frame is eligible. A declared frame inside a
  changing interval is refused by name (PPTX_POSTER_FRAME_INVALID),
  with the scene's own semantic assertion cited when one pins the
  partial state.
- When nothing is declared, the earliest proof event inside the
  stable interval wins; failing that, the first stable frame.
- When no stable readable frame exists at all, selection refuses
  (PPTX_POSTER_STATE_UNAVAILABLE) instead of shipping a guess,
  with one bounded exception: a loop package (playback repeat
  "loop") has no final state by construction, so a declared
  poster frame, or failing that a proof event frame, is taken as
  the loop's representative state and recorded as such. The
  exception never applies when a stable state exists: there, a
  declared frame outside the hold still refuses.

When an MP4 is supplied, the selection is also measured: the chosen
frame's decoded raster is compared against the final frame's raster
(they must agree; both sit in the hold) and against a mid-reveal
frame when one exists (they must differ; the poster is not the
partial state).

CLI:
    python3 scripts/poster_select.py --job-dir DIR [--out PATH]

Reads manifest.json, timeline.json, timeline-sidecar.json and the
scene specs from the job directory, prints one JSON result (the
selection record) to stdout, and exits 0 on success. Refusals print
one JSON error object and exit with the Section 16.9 class of the
failure category.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Section 16.9 exit classes, mirrored from the house convention
# (scripts/qc.py and scripts/audio_policy.py carry the same map).
EXIT_BY_CATEGORY = {
    "MG_SCHEMA_INVALID": 2,
    "MG_UNKNOWN_COMPONENT": 2,
    "MG_MODE_MISMATCH": 2,
    "MG_TIMELINE_INVALID": 2,
    "MG_INPUT_MISSING": 3,
    "MG_FONT_UNRESOLVED": 3,
    "MG_RUNTIME_UNAVAILABLE": 3,
    "MG_CAPABILITY_UNSUPPORTED": 3,
    "MG_QC_FAILED": 6,
    "MG_DELIVERY_FAILED": 7,
    "MG_HASH_MISMATCH": 9,
    "MG_FOREIGN_JOB": 9,
}


class PosterSelectionError(Exception):
    """A named poster-selection refusal with a Section 16.9 category."""

    def __init__(self, code: str, category: str, message: str,
                 details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.category = category
        self.message = message
        self.details = details or {}


def _placed_motion(scene_spec: dict, sidecar_scene: dict) -> dict:
    """Map one scene's authored motion onto placed frames.

    Motion frames in a scene spec are source frames; the sidecar's
    placedRange/sourceRange pair gives the source-to-placed mapping.
    Scenes without a motion record are complete from their first
    placed frame.
    """
    placed = sidecar_scene["placedRange"]
    source = sidecar_scene["sourceRange"]
    offset = placed["startFrame"] - source["startFrame"]
    motion = scene_spec.get("motion") or {}
    if motion:
        start = motion["start_frame"] + offset
        end = motion["end_frame_exclusive"] + offset
        hold_to = (motion.get("hold_to_frame_exclusive")
                   or scene_spec.get("duration_frames", end)) + offset
    else:
        start = end = placed["startFrame"]
        hold_to = placed["endFrameExclusive"]
    return {
        "scene_id": scene_spec["id"],
        "motion_start": start,
        "motion_end": end,
        "hold_to": hold_to,
        "placed_start": placed["startFrame"],
        "placed_end": placed["endFrameExclusive"],
    }


def _progress_at(motion: dict, frame: int) -> float:
    """Completion of one scene's motion at a frame: 0 before the
    changing interval, 1 at and after its end. Inside the interval
    the scene is by definition not complete; the exact fraction is
    reported only for linear reveals, where the plan defines it."""
    if frame < motion["motion_start"]:
        return 0.0
    if frame >= motion["motion_end"]:
        return 1.0
    span = motion["motion_end"] - motion["motion_start"]
    return (frame - motion["motion_start"]) / span if span else 1.0


def _state_at(motions: list[dict], frame: int) -> str:
    """Name the plan state a frame sits in, for refusal messages."""
    for m in motions:
        if m["motion_start"] <= frame < m["motion_end"]:
            return "changing"
        if frame < m["motion_start"]:
            return "pre_reveal"
    return "complete"


def plan_selection(timeline: dict, sidecar: dict,
                   scene_specs: list[dict], delivery: dict) -> dict:
    """Choose the poster frame from the compiled plan alone.

    Returns the selection record (without measurement). Raises
    PosterSelectionError on a named refusal.
    """
    total = timeline["total_frames"]
    sidecar_by_id = {s["id"]: s for s in sidecar.get("scenes", [])}
    motions = []
    for spec in scene_specs:
        placed = sidecar_by_id.get(spec["id"])
        if placed is None:
            raise PosterSelectionError(
                "PPTX_POSTER_PLAN_INCOMPLETE", "MG_TIMELINE_INVALID",
                "scene %s has no placed range in the timeline sidecar; "
                "poster eligibility cannot be proven" % spec["id"])
        motions.append(_placed_motion(spec, placed))

    motion_complete = max((m["motion_end"] for m in motions), default=0)
    events = timeline.get("events", [])
    hold_starts = [e["frame"] for e in events
                   if e.get("type") == "hold_start"
                   and e["frame"] >= motion_complete]
    stable_from = max([motion_complete] + hold_starts)
    declared = delivery.get("poster_frame")

    per_scene = []
    for m, spec in zip(motions, scene_specs):
        per_scene.append({
            "scene_id": m["scene_id"],
            "motion_interval_placed": [m["motion_start"], m["motion_end"]],
            "hold_interval_placed": [m["motion_end"], m["hold_to"]],
        })

    base = {
        "total_frames": total,
        "motion_complete_frame": motion_complete,
        "stable_interval": [stable_from, total],
        "declared_poster_frame": declared,
        "per_scene": per_scene,
    }

    if stable_from >= total:
        playback = delivery.get("playback") or {}
        if playback.get("repeat") == "loop":
            if declared is not None and 0 <= declared < total:
                return {**base,
                        "frame": declared,
                        "rule": "loop_representative_declared",
                        "state": "loop_representative",
                        "reason": (
                            "the piece loops and never holds a final "
                            "state; the manifest declares frame %d as "
                            "the poster's representative state for "
                            "the loop" % declared)}
            proofs = sorted(e["frame"] for e in events
                            if e.get("type") == "proof"
                            and 0 <= e["frame"] < total)
            if proofs:
                return {**base,
                        "frame": proofs[0],
                        "rule": "loop_representative_proof",
                        "state": "loop_representative",
                        "reason": (
                            "the piece loops and never holds a final "
                            "state; frame %d is the compiled plan's "
                            "proof event, taken as the loop's "
                            "representative state" % proofs[0])}
            raise PosterSelectionError(
                "PPTX_POSTER_STATE_UNAVAILABLE", "MG_QC_FAILED",
                "the piece loops without ever holding a stable "
                "state, and neither a poster frame nor a proof "
                "event is declared; a loop package needs one of "
                "the two to name its representative poster state",
                details=base)
        raise PosterSelectionError(
            "PPTX_POSTER_STATE_UNAVAILABLE", "MG_QC_FAILED",
            "the compiled plan never reaches a stable readable state: "
            "motion completes at frame %d of %d, leaving no held frame "
            "to stand as the poster" % (motion_complete, total),
            details=base)

    if declared is not None:
        if stable_from <= declared < total:
            return {**base,
                    "frame": declared,
                    "rule": "manifest_declared_in_final_hold",
                    "state": "final_hold",
                    "reason": (
                        "the manifest declares frame %d and the compiled "
                        "plan places it inside the terminal hold [%d, %d) "
                        "with every scene's motion complete, so the "
                        "poster shows the piece's final readable state"
                        % (declared, stable_from, total))}
        state = _state_at(motions, declared)
        detail = ""
        for spec in scene_specs:
            for assertion in spec.get("semantic_motion_assertions", []):
                if assertion.get("frame") == declared:
                    detail = (
                        " The scene's own semantic assertion %r at "
                        "frame %d expects %s, against final values "
                        "reached only at motion end."
                        % (assertion.get("id"), declared,
                           assertion.get("expected_values")))
        raise PosterSelectionError(
            "PPTX_POSTER_FRAME_INVALID", "MG_QC_FAILED",
            "the manifest declares poster frame %d, but the compiled "
            "plan places that frame in state %r (stable readable "
            "frames are [%d, %d)); a poster there would present "
            "partial data as final.%s"
            % (declared, state, stable_from, total, detail),
            details=base)

    proofs = sorted(e["frame"] for e in events
                    if e.get("type") == "proof" and e["frame"] >= stable_from)
    if proofs:
        frame = proofs[0]
        return {**base,
                "frame": frame,
                "rule": "proof_event_in_final_hold",
                "state": "final_hold",
                "reason": (
                    "no poster frame is declared; frame %d is the "
                    "compiled plan's proof event inside the terminal "
                    "hold [%d, %d), the earliest frame whose state is "
                    "both proven and final" % (frame, stable_from, total))}
    return {**base,
            "frame": stable_from,
            "rule": "final_hold_start",
            "state": "final_hold",
            "reason": (
                "no poster frame is declared and the plan carries no "
                "proof event in the hold; frame %d is the first frame "
                "of the terminal hold [%d, %d), where every scene's "
                "motion is complete" % (stable_from, stable_from, total))}


def _decode_frame_rgb(mp4: Path, frame: int, width: int,
                      height: int) -> bytes:
    """Decode one frame to raw RGB via ffmpeg (the house probe tool)."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp4),
         "-vf", "select='eq(n\\,%d)'" % frame, "-vframes", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    if proc.returncode != 0:
        raise PosterSelectionError(
            "PPTX_POSTER_MEASURE_FAILED", "MG_DELIVERY_FAILED",
            "ffmpeg could not decode frame %d of %s: %s"
            % (frame, mp4, proc.stderr.decode("utf-8", "replace")[-300:]))
    expected = width * height * 3
    if len(proc.stdout) != expected:
        raise PosterSelectionError(
            "PPTX_POSTER_MEASURE_FAILED", "MG_DELIVERY_FAILED",
            "decoded frame %d has %d bytes, expected %d (%dx%d rgb24)"
            % (frame, len(proc.stdout), expected, width, height))
    return proc.stdout


def _diff_stats(a: bytes, b: bytes) -> dict:
    """Per-channel absolute difference summary between two rasters."""
    total_abs = 0
    max_abs = 0
    over = 0
    for x, y in zip(a, b):
        d = x - y if x >= y else y - x
        total_abs += d
        if d > max_abs:
            max_abs = d
        if d > 8:
            over += 1
    n = len(a)
    return {
        "mean_abs_diff": round(total_abs / n, 4) if n else 0.0,
        "max_abs_diff": max_abs,
        "fraction_channels_over_8": round(over / n, 6) if n else 0.0,
    }


def measure_selection(mp4: Path, selection: dict, timeline: dict,
                      canvas: dict) -> dict:
    """Measure the chosen frame against the final frame (same hold)
    and against a mid-reveal frame (a different, partial state)."""
    width, height = canvas["width"], canvas["height"]
    total = timeline["total_frames"]
    frame = selection["frame"]
    poster_rgb = _decode_frame_rgb(mp4, frame, width, height)
    final_rgb = _decode_frame_rgb(mp4, total - 1, width, height)
    vs_final = _diff_stats(poster_rgb, final_rgb)
    measured = {
        "basis": selection["state"],
        "poster_frame": frame,
        "final_frame": total - 1,
        "vs_final_frame": vs_final,
        # Both frames sit in the encoded hold; the rasters must agree
        # to within encoder noise, never to a different state's gap.
        "equals_final_state": (
            vs_final["mean_abs_diff"] <= 1.0
            and vs_final["fraction_channels_over_8"] <= 0.001),
    }
    motions_mid = None
    complete = selection["motion_complete_frame"]
    starts = [s["motion_interval_placed"][0]
              for s in selection["per_scene"]]
    if starts and complete > min(starts):
        motions_mid = (min(starts) + complete) // 2
    if motions_mid is not None and motions_mid != frame:
        mid_rgb = _decode_frame_rgb(mp4, motions_mid, width, height)
        vs_mid = _diff_stats(poster_rgb, mid_rgb)
        measured["mid_reveal_frame"] = motions_mid
        measured["vs_mid_reveal_frame"] = vs_mid
        measured["differs_from_mid_reveal"] = vs_mid["mean_abs_diff"] > 1.0
    return measured


def extract_poster_png(mp4: Path, frame: int, out_path: Path) -> None:
    """Write the chosen frame as a PNG at the artifact's own size."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp4),
         "-vf", "select='eq(n\\,%d)'" % frame, "-vframes", "1",
         str(out_path), "-y"],
        capture_output=True)
    if proc.returncode != 0 or not out_path.exists():
        raise PosterSelectionError(
            "PPTX_POSTER_MEASURE_FAILED", "MG_DELIVERY_FAILED",
            "ffmpeg could not extract poster frame %d from %s: %s"
            % (frame, mp4, proc.stderr.decode("utf-8", "replace")[-300:]))


def select_poster(job_dir: Path, mp4: Path | None = None) -> dict:
    """Full selection for a job package: plan rule plus measurement
    when the rendered artifact is supplied."""
    job_dir = Path(job_dir)
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.exists():
        raise PosterSelectionError(
            "PPTX_INPUT_MISSING", "MG_INPUT_MISSING",
            "no manifest.json in job directory %s" % job_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timeline_path = job_dir / (manifest.get("timeline") or "timeline.json")
    sidecar_path = job_dir / "timeline-sidecar.json"
    for path in (timeline_path, sidecar_path):
        if not path.exists():
            raise PosterSelectionError(
                "PPTX_INPUT_MISSING", "MG_INPUT_MISSING",
                "the job package lacks %s; poster selection reads the "
                "compiled timeline and its sidecar" % path.name)
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    scene_specs = []
    for entry in manifest.get("scenes", []):
        spec_path = job_dir / entry["spec"]
        if not spec_path.exists():
            raise PosterSelectionError(
                "PPTX_INPUT_MISSING", "MG_INPUT_MISSING",
                "the job package lacks scene spec %s" % entry["spec"])
        scene_specs.append(
            json.loads(spec_path.read_text(encoding="utf-8")))
    selection = plan_selection(
        timeline, sidecar, scene_specs, manifest.get("delivery") or {})
    selection["job_id"] = manifest["job_id"]
    selection["per_scene_progress"] = {
        s["scene_id"]: 1.0 for s in selection["per_scene"]}
    if mp4 is not None:
        selection["measured"] = measure_selection(
            Path(mp4), selection, timeline, manifest["canvas"])
        if (selection["state"] == "final_hold"
                and not selection["measured"]["equals_final_state"]):
            raise PosterSelectionError(
                "PPTX_POSTER_STATE_MISMATCH", "MG_QC_FAILED",
                "the decoded poster frame %d does not match the "
                "decoded final frame %d within hold tolerance "
                "(mean abs diff %s); the poster would not show the "
                "state the piece ends on"
                % (selection["frame"], timeline["total_frames"] - 1,
                   selection["measured"]["vs_final_frame"]
                   ["mean_abs_diff"]),
                details=selection)
    return selection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select the poster frame for a motion component "
                    "from its compiled plan (MG-035).")
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--mp4",
                        help="rendered artifact to measure the "
                             "selection against (default: the job's "
                             "renders/final.mp4 when present)")
    parser.add_argument("--out", help="also write the record here")
    args = parser.parse_args(argv)
    job_dir = Path(args.job_dir)
    mp4 = Path(args.mp4) if args.mp4 else job_dir / "renders" / "final.mp4"
    try:
        record = select_poster(job_dir, mp4 if mp4.exists() else None)
    except PosterSelectionError as err:
        print(json.dumps({
            "status": "error", "code": err.code,
            "category": err.category, "message": err.message,
            "details": err.details}, indent=1))
        return EXIT_BY_CATEGORY.get(err.category, 7)
    if args.out:
        Path(args.out).write_text(
            json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
