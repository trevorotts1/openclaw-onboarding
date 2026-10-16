"""Delivery packager for the powerpoint_graphic mode (MG-035).

Given a rendered motion component in a job package (the MP4 from the
existing render path, at renders/final.mp4), produce the slide-ready
delivery package:

    component.mp4        the 16:9 H.264 artifact, byte-identical
    poster.png           the deliberately selected poster frame
    fallback.png         the static fallback image (the poster's
                         readable final state) for PDF export and
                         nonplaying environments
    deck.pptx            the embedded-video test deck, built by
                         scripts/powerpoint_adapter.py
    package-record.json  the governed package record (validated
                         against references/powerpoint-package-
                         schema.json): hashes for every file, the
                         poster selection and its reason, playback
                         metadata, the placement text audit, and
                         the MG-034 QC binding
    final-qc.json        the consumed MG-034 final QC record
    export-record.json   the MG-040 export record, when the render
                         produced one
    source/              the job package records the deck was built
                         from (the manifest's source_package)

Gates, in order, each refused by name:

1. The manifest must validate against the canonical contracts and
   declare mode powerpoint_graphic with delivery profile
   h264_opaque (the MG-040 PowerPoint path).
2. The MG-034 final QC record (qc/final-qc.json) must exist, name
   this job, carry verdict pass, and bind the exact artifact bytes
   by sha256. Packaging is a post-FINAL_QC_PASSED lifecycle step
   (directive Section 16.8); this packager consumes the record and
   never re-runs or imports the QC layer.
3. The artifact itself is re-probed: H.264, yuv420p (opaque), the
   manifest's canvas, the compiled timeline's frame count and fps.
4. Audio follows the MG-023 plan resolved once from the compiled
   timeline (scripts/audio_policy.py): mode none means the artifact
   carries no audio stream.
5. The poster is selected by scripts/poster_select.py from the
   compiled plan and measured against the artifact; a declared
   poster frame in a partial state refuses the package.
6. Essential text is audited at the package's actual placement
   size (directive Section 17.1 M07, MG-013 role floors, MG-014
   placement rules): authored size times placement scale must meet
   the role floor, or the component is refused by name rather than
   shipped small.
7. Loop packages carry the M13 seam check; hold-final packages
   must end on the poster's state.

PLATFORM TRUTH: the package record states powerpoint_playback
UNVERIFIED. The deck's embed is proven structurally by the adapter;
no playback in Microsoft PowerPoint is claimed from this Linux
build box.

CLI:
    python3 scripts/powerpoint_package.py package --job-dir DIR \
        --out DIR [--final PATH] [--display-width 960|169.3mm] \
        [--force]
    python3 scripts/powerpoint_package.py verify --package-dir DIR

One JSON result on stdout; refusals exit with the Section 16.9
class of the failure category.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_policy
import poster_select
import powerpoint_adapter
from poster_select import PosterSelectionError
from powerpoint_adapter import AdapterError

from jsonschema import Draft202012Validator

SKILL_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_PATH = SKILL_ROOT / "references" / "contracts-v2.schema.json"
PACKAGE_SCHEMA_PATH = (SKILL_ROOT / "references"
                       / "powerpoint-package-schema.json")
TYPOGRAPHY_PATH = SKILL_ROOT / "references" / "typography-tokens.json"

SLIDE_WIDTH_IN = 10.0    # build_deck.py SLIDE_WIDTH_IN
SLIDE_HEIGHT_IN = 5.625  # build_deck.py SLIDE_HEIGHT_IN
SLIDE_WIDTH_MM = 254.0

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
    "MG_COVERAGE_INCOMPLETE": 6,
    "MG_DELIVERY_FAILED": 7,
    "MG_PARENT_HANDOFF_REJECTED": 7,
    "MG_HASH_MISMATCH": 9,
    "MG_FOREIGN_JOB": 9,
    "MG_SECURITY_VIOLATION": 9,
}


class PackageError(Exception):
    """A named packaging refusal with a Section 16.9 category."""

    def __init__(self, code: str, category: str, message: str,
                 details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.category = category
        self.message = message
        self.details = details or {}


def _sha256_file(path: Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path: Path, code: str = "PPTX_INPUT_MISSING") -> dict:
    if not path.exists():
        raise PackageError(
            code, "MG_INPUT_MISSING",
            "the job package lacks %s" % path.name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:
        raise PackageError(
            "PPTX_RECORD_INVALID", "MG_SCHEMA_INVALID",
            "%s is not valid JSON: %s" % (path.name, err))


def _validator_for(schema_doc: dict, def_name: str | None):
    if def_name is None:
        return Draft202012Validator(schema_doc)
    wrapper = {
        "$schema": schema_doc["$schema"],
        "$ref": "#/$defs/%s" % def_name,
        "$defs": schema_doc["$defs"],
    }
    return Draft202012Validator(wrapper)


def _probe(mp4: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_streams",
         "-show_format", "-of", "json", str(mp4)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise PackageError(
            "PPTX_PROBE_FAILED", "MG_DELIVERY_FAILED",
            "ffprobe cannot parse %s: %s"
            % (mp4, proc.stderr.strip()[-300:]))
    doc = json.loads(proc.stdout)
    streams = doc.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"),
                 None)
    if video is None:
        raise PackageError(
            "PPTX_PROBE_FAILED", "MG_DELIVERY_FAILED",
            "%s carries no video stream" % mp4)
    num, _, den = (video.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    frames = video.get("nb_read_frames") or video.get("nb_frames")
    return {
        "codec": video.get("codec_name"),
        "pixel_format": video.get("pix_fmt"),
        "width": video.get("width"),
        "height": video.get("height"),
        "frames": int(frames) if frames else 0,
        "fps": fps,
        "duration_seconds": float(doc["format"]["duration"]),
        "audio_streams": sum(
            1 for s in streams if s.get("codec_type") == "audio"),
    }


def _png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise PackageError(
            "PPTX_POSTER_INVALID", "MG_DELIVERY_FAILED",
            "%s is not a PNG file" % path)
    width, height = struct.unpack(">II", head[16:24])
    return width, height


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def _check_qc_gate(job_dir: Path, manifest: dict, artifact: Path) -> dict:
    record_path = job_dir / "qc" / "final-qc.json"
    if not record_path.exists():
        raise PackageError(
            "PPTX_QC_RECORD_MISSING", "MG_INPUT_MISSING",
            "no MG-034 final QC record at qc/final-qc.json; packaging "
            "is a post-FINAL_QC_PASSED step (directive Section 16.8) "
            "and refuses to proceed without the gate's record")
    record = _load_json(record_path)
    if record.get("job_id") not in (None, manifest["job_id"]):
        raise PackageError(
            "PPTX_QC_FOREIGN_JOB", "MG_FOREIGN_JOB",
            "the QC record names job %r, not this job %r"
            % (record.get("job_id"), manifest["job_id"]))
    artifact_sha = _sha256_file(artifact)
    if record.get("artifact_sha256") != artifact_sha:
        raise PackageError(
            "PPTX_QC_HASH_MISMATCH", "MG_HASH_MISMATCH",
            "the QC record binds artifact %s but renders/final.mp4 "
            "hashes to %s; the bytes QC passed are not the bytes "
            "being packaged"
            % (record.get("artifact_sha256"), artifact_sha))
    if record.get("verdict") != "pass":
        failed = (record.get("summary") or {}).get("failed_checks", [])
        raise PackageError(
            "PPTX_QC_NOT_PASSED", "MG_QC_FAILED",
            "the MG-034 final QC verdict is %r, not pass; failed "
            "checks: %s" % (record.get("verdict"),
                            ", ".join(failed) or "unspecified"),
            details={"qc_summary": record.get("summary")})
    summary = record.get("summary") or {}
    return {
        "record_file": "final-qc.json",
        "record_sha256": _sha256_file(record_path),
        "verdict": "pass",
        "artifact_sha256": artifact_sha,
        "checks_passed": int(summary.get("pass", 0)),
        "checks_failed": int(summary.get("fail", 0)),
    }


def _check_media(manifest: dict, timeline: dict, probe: dict) -> None:
    canvas = manifest["canvas"]
    problems = []
    if probe["codec"] != "h264":
        problems.append("codec is %r, not h264" % probe["codec"])
    if probe["pixel_format"] != "yuv420p":
        problems.append(
            "pixel format is %r, not yuv420p (the h264_opaque "
            "profile is opaque)" % probe["pixel_format"])
    if (probe["width"], probe["height"]) != (canvas["width"],
                                              canvas["height"]):
        problems.append(
            "dimensions are %dx%d, not the manifest canvas %dx%d"
            % (probe["width"], probe["height"],
               canvas["width"], canvas["height"]))
    if probe["frames"] != timeline["total_frames"]:
        problems.append(
            "decoded frame count is %d, not the compiled timeline's "
            "%d (M01)" % (probe["frames"], timeline["total_frames"]))
    if abs(probe["fps"] - canvas["fps"]) > 0.01:
        problems.append(
            "frame rate is %s, not the manifest canvas fps %s"
            % (probe["fps"], canvas["fps"]))
    expected_duration = timeline["total_frames"] / canvas["fps"]
    if abs(probe["duration_seconds"] - expected_duration) > (
            1.0 / canvas["fps"] + 0.05):
        problems.append(
            "duration is %.3fs, not %.3fs within one frame (M01)"
            % (probe["duration_seconds"], expected_duration))
    if problems:
        raise PackageError(
            "PPTX_MEDIA_NONCONFORMANT", "MG_DELIVERY_FAILED",
            "the rendered artifact does not match the package it "
            "would ship in: " + "; ".join(problems),
            details={"probe": probe})


def _resolve_audio(job_dir: Path, timeline: dict, sidecar: dict,
                   probe: dict) -> dict:
    media_path = job_dir / "media.json"
    media = (_load_json(media_path)
             if media_path.exists() else {})
    narration_ids = [n.get("id") for n in sidecar.get("narration", [])]
    sfx_ids = [s.get("id") for s in sidecar.get("sfx", [])]
    try:
        plan = audio_policy.resolve_audio_plan(
            timeline.get("audio_owner"), narration_ids, sfx_ids, media)
    except audio_policy.AudioPolicyError as err:
        raise PackageError(
            err.code, "MG_MODE_MISMATCH", err.message)
    if plan["mode"] == "none" and probe["audio_streams"] > 0:
        raise PackageError(
            "PPTX_AUDIO_MODE_VIOLATION", "MG_MODE_MISMATCH",
            "the MG-023 plan resolves this job to audio mode none "
            "(powerpoint_graphic components are silent; the presenter "
            "narrates live), but the artifact carries %d audio "
            "stream(s)" % probe["audio_streams"])
    return {
        "resolved_mode": plan["mode"],
        "policy_version": plan["policyVersion"],
        "artifact_audio_streams": probe["audio_streams"],
    }


# Design field to typography role (MG-014's field mapping for chart
# scenes; floors come from references/typography-tokens.json, MG-013).
ROLE_FIELDS = {
    "headline_px": "headline",
    "hero_number_px": "hero_number",
    "support_px": "essential_support",
    "cta_px": "cta",
    "label_px": "chart_category_label",
    "value_px": "chart_value",
    "disclosure_px": "disclosure",
}


def _parse_display_width(raw: str | None,
                          placement_kind: str,
                          canvas: dict) -> tuple[float, str]:
    """Resolve the actual placement display width in canvas pixels.

    full_frame places at the canvas size. An inset's display width
    is declared in px, or in mm converted through the slide's own
    px-per-mm ratio (MG-014); no display DPI is ever assumed.
    """
    if raw is None:
        if placement_kind == "inset":
            raise PackageError(
                "PPTX_PLACEMENT_UNPROVABLE", "MG_INPUT_MISSING",
                "the manifest declares an inset placement but no "
                "display width was given (--display-width); text "
                "cannot be audited at an undeclared actual size")
        return float(canvas["width"]), "full_frame"
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(px|mm)?", raw.strip())
    if not match:
        raise PackageError(
            "PPTX_PLACEMENT_INVALID", "MG_SCHEMA_INVALID",
            "display width %r is not a number of px or mm" % raw)
    value = float(match.group(1))
    if match.group(2) == "mm":
        px_per_mm = canvas["width"] / SLIDE_WIDTH_MM
        return value * px_per_mm, "inset"
    return value, "inset"


def _placement_audit(job_dir: Path, manifest: dict, design: dict,
                     storyboard: dict, scene_specs: list[dict],
                     display_width_arg: str | None) -> dict:
    canvas = manifest["canvas"]
    kind = manifest["delivery"]["placement"]
    display_width, kind = _parse_display_width(
        display_width_arg, kind, canvas)
    scale = display_width / canvas["width"]
    display_height = display_width * canvas["height"] / canvas["width"]
    tokens = _load_json(TYPOGRAPHY_PATH)
    floors = {r["role"]: r["floor_px"] for r in tokens["roles"]}
    rows = []
    failures = []
    for spec in scene_specs:
        variant = spec.get("layout_variant")
        layout = (design.get("layouts") or {}).get(variant)
        if layout is None:
            raise PackageError(
                "PPTX_PLACEMENT_UNPROVABLE", "MG_INPUT_MISSING",
                "the design record carries no layout for variant "
                "%r (scene %s); placement legibility cannot be "
                "proven" % (variant, spec["id"]))
        for field, role in ROLE_FIELDS.items():
            if field not in layout:
                continue
            authored = float(layout[field])
            floor = float(floors[role])
            effective = authored * scale
            rows.append({
                "scene_id": spec["id"],
                "layout_variant": variant,
                "role": role,
                "design_field": field,
                "authored_px": authored,
                "floor_px": floor,
                "effective_px": round(effective, 3),
                "verdict": "pass",
            })
            if effective < floor:
                failures.append(
                    "scene %s role %s: authored %g px at placement "
                    "scale %.3f is %g px effective, below the %g px "
                    "floor" % (spec["id"], role, authored, scale,
                               effective, floor))
    if failures:
        raise PackageError(
            "PPTX_TEXT_BELOW_FLOOR", "MG_QC_FAILED",
            "essential text would ship below its floor at the "
            "actual placement size: " + "; ".join(failures),
            details={"scale": scale,
                     "display_width_px": display_width})
    essential_text = []
    for beat in storyboard.get("beats", []):
        essential_text.extend(beat.get("essential_text", []))
    return {
        "kind": kind,
        "display_width_px": round(display_width, 3),
        "display_height_px": round(display_height, 3),
        "slide_width_in": SLIDE_WIDTH_IN,
        "slide_height_in": SLIDE_HEIGHT_IN,
        "scale": round(scale, 6),
        "roles": rows,
        "essential_text": essential_text,
        "caveat": (
            "Font size against the MG-013 role floors is necessary "
            "evidence, not a complete legibility guarantee (M07): "
            "glyph size, weight, contrast, and viewing distance also "
            "govern whether the placed component reads."),
    }


def _loop_seam_check(mp4: Path, timeline: dict, canvas: dict,
                     playback: dict) -> dict:
    if playback.get("repeat") != "loop":
        return {
            "status": "not_applicable",
            "reason": "playback repeat is %r; the seam check governs "
                      "loop packages only" % playback.get("repeat"),
            "seam_mean_abs_diff": None,
            "typical_step_mean_abs_diff": None,
            "ratio": None,
        }
    total = timeline["total_frames"]
    width, height = canvas["width"], canvas["height"]
    first = poster_select._decode_frame_rgb(mp4, 0, width, height)
    second = poster_select._decode_frame_rgb(mp4, 1, width, height)
    last = poster_select._decode_frame_rgb(
        mp4, total - 1, width, height)
    seam = poster_select._diff_stats(last, first)["mean_abs_diff"]
    step = poster_select._diff_stats(second, first)["mean_abs_diff"]
    ratio = (seam / step) if step > 0 else None
    if seam > max(4.0 * step, 2.0):
        raise PackageError(
            "PPTX_LOOP_SEAM", "MG_QC_FAILED",
            "the loop seam is visible: the last-to-first frame step "
            "measures mean abs diff %.3f against the piece's own "
            "typical step %.3f (M13 judges the state at one full "
            "period against the state at zero; a reveal that ends "
            "away from its start cannot loop seamlessly)"
            % (seam, step),
            details={"seam_mean_abs_diff": seam,
                     "typical_step_mean_abs_diff": step})
    return {
        "status": "pass",
        "reason": None,
        "seam_mean_abs_diff": seam,
        "typical_step_mean_abs_diff": step,
        "ratio": round(ratio, 4) if ratio is not None else None,
    }


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

def package(job_dir: Path, out_dir: Path, final: Path | None = None,
            display_width: str | None = None,
            force: bool = False) -> dict:
    job_dir = Path(job_dir)
    out_dir = Path(out_dir)
    manifest = _load_json(job_dir / "manifest.json")
    contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        _validator_for(contracts, "manifest").iter_errors(manifest),
        key=lambda e: list(e.absolute_path))
    if errors:
        raise PackageError(
            "PPTX_MANIFEST_INVALID", "MG_SCHEMA_INVALID",
            "the job manifest fails the canonical contracts: "
            + "; ".join(
                "%s: %s" % ("/".join(str(p) for p in e.absolute_path),
                            e.message) for e in errors[:3]))
    if manifest.get("mode") != "powerpoint_graphic":
        raise PackageError(
            "PPTX_MODE_MISMATCH", "MG_MODE_MISMATCH",
            "this packager packages the powerpoint_graphic mode; "
            "the job declares mode %r" % manifest.get("mode"))
    delivery = manifest["delivery"]
    if delivery.get("video_profile") != "h264_opaque":
        raise PackageError(
            "PPTX_DELIVERY_PROFILE", "MG_MODE_MISMATCH",
            "the PowerPoint package requires the h264_opaque "
            "profile (the MG-040 default and PowerPoint path); the "
            "job declares %r" % delivery.get("video_profile"))

    artifact = Path(final) if final else job_dir / "renders" / "final.mp4"
    if not artifact.exists():
        raise PackageError(
            "PPTX_INPUT_MISSING", "MG_INPUT_MISSING",
            "no rendered artifact at %s" % artifact)
    timeline = _load_json(
        job_dir / (manifest.get("timeline") or "timeline.json"))
    sidecar = _load(("timeline-sidecar.json"), job_dir)
    storyboard = _load_json(
        job_dir / (manifest.get("storyboard") or "storyboard.json"))
    design = _load_json(
        job_dir / (manifest.get("design") or "design.json"))
    scene_specs = []
    for entry in manifest.get("scenes", []):
        scene_specs.append(_load_json(job_dir / entry["spec"]))

    qc = _check_qc_gate(job_dir, manifest, artifact)
    probe = _probe(artifact)
    _check_media(manifest, timeline, probe)
    audio = _resolve_audio(job_dir, timeline, sidecar, probe)
    playback = delivery["playback"]

    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise PackageError(
            "PPTX_PACKAGE_EXISTS", "MG_DELIVERY_FAILED",
            "the output directory %s is not empty; refusing to "
            "overwrite a package (pass --force to replace it)"
            % out_dir)
    staging = out_dir.parent / (".%s.staging-%d"
                                % (out_dir.name, os.getpid()))
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        selection = poster_select.select_poster(job_dir, artifact)
        poster_path = staging / "poster.png"
        poster_select.extract_poster_png(
            artifact, selection["frame"], poster_path)
        poster_w, poster_h = _png_size(poster_path)
        fallback_path = staging / "fallback.png"
        shutil.copy(poster_path, fallback_path)

        loop_check = _loop_seam_check(
            artifact, timeline, manifest["canvas"], playback)
        if (playback.get("end") == "hold_final"
                and selection["state"] != "final_hold"):
            raise PackageError(
                "PPTX_HOLD_STATE_MISMATCH", "MG_QC_FAILED",
                "playback declares end hold_final, but the compiled "
                "plan never reaches a stable final state for the "
                "poster to hold (poster state %r)"
                % selection["state"])
        if playback.get("end") == "hold_final":
            hold_check = {
                "status": "pass",
                "poster_equals_final_state": bool(
                    (selection.get("measured") or {})
                    .get("equals_final_state")),
                "reason": None,
            }
        else:
            hold_check = {
                "status": "not_applicable",
                "poster_equals_final_state": None,
                "reason": "playback end is %r; the hold-final check "
                          "governs reveal-and-hold packages"
                          % playback.get("end"),
            }

        placement = _placement_audit(
            job_dir, manifest, design, storyboard, scene_specs,
            display_width)

        component_path = staging / "component.mp4"
        shutil.copy(artifact, component_path)
        shutil.copy(job_dir / "qc" / "final-qc.json",
                    staging / "final-qc.json")
        export_record_sha = None
        export_src = Path(str(artifact) + ".export-record.json")
        if export_src.exists():
            export_doc = _load_json(export_src)
            if export_doc.get("profile") not in (
                    None, delivery["video_profile"]):
                raise PackageError(
                    "PPTX_EXPORT_PROFILE_MISMATCH",
                    "MG_DELIVERY_FAILED",
                    "the render's export record names profile %r "
                    "but the job declares %r"
                    % (export_doc.get("profile"),
                       delivery["video_profile"]))
            if export_doc.get("artifactSha256") not in (
                    None, _sha256_file(artifact)):
                raise PackageError(
                    "PPTX_EXPORT_HASH_MISMATCH", "MG_HASH_MISMATCH",
                    "the render's export record binds a different "
                    "artifact than renders/final.mp4")
            shutil.copy(export_src, staging / "export-record.json")
            export_record_sha = _sha256_file(export_src)

        source_dir = staging / "source"
        source_dir.mkdir()
        for name in ("manifest.json", "timeline.json",
                     "timeline-sidecar.json", "storyboard.json",
                     "design.json", "assets.json", "media.json",
                     "intake-assets.json"):
            src = job_dir / name
            if src.exists():
                shutil.copy(src, source_dir / name)
        for sub in ("scenes", "data"):
            if (job_dir / sub).exists():
                shutil.copytree(job_dir / sub, source_dir / sub)

        deck_record = powerpoint_adapter.build_deck(
            component_path, poster_path, fallback_path, playback,
            staging / "deck.pptx",
            title="Motion component: %s" % manifest["job_id"])
        deck_verify = powerpoint_adapter.verify_deck(
            staging / "deck.pptx",
            expect_mp4_sha256=_sha256_file(component_path),
            expect_fallback_sha256=_sha256_file(fallback_path))

        total = timeline["total_frames"]
        fps = manifest["canvas"]["fps"]
        record = {
            "schema_version": "1.0",
            "item": "MG-035",
            "job_id": manifest["job_id"],
            "mode": "powerpoint_graphic",
            "generated_by": "scripts/powerpoint_package.py",
            "source_job": {
                "manifest_sha256": _sha256_file(
                    job_dir / "manifest.json"),
                "timeline_sha256": _sha256_file(
                    job_dir / (manifest.get("timeline")
                               or "timeline.json")),
                "sidecar_sha256": _sha256_file(
                    job_dir / "timeline-sidecar.json"),
                "storyboard_sha256": _sha256_file(
                    job_dir / (manifest.get("storyboard")
                               or "storyboard.json")),
                "design_sha256": _sha256_file(
                    job_dir / (manifest.get("design")
                               or "design.json")),
            },
            "artifact": {
                "file": "component.mp4",
                "sha256": _sha256_file(component_path),
                "bytes": component_path.stat().st_size,
                "probe": probe,
            },
            "export": {
                "profile": delivery["video_profile"],
                "export_record_sha256": export_record_sha,
            },
            "audio": audio,
            "poster": {
                "file": "poster.png",
                "sha256": _sha256_file(poster_path),
                "bytes": poster_path.stat().st_size,
                "width": poster_w,
                "height": poster_h,
                "frame": selection["frame"],
                "state": selection["state"],
                "rule": selection["rule"],
                "reason": selection["reason"],
                "stable_interval": selection["stable_interval"],
                "motion_complete_frame":
                    selection["motion_complete_frame"],
                "declared_poster_frame":
                    selection["declared_poster_frame"],
                "per_scene": selection["per_scene"],
                "measured": selection.get("measured"),
            },
            "fallback": {
                "file": "fallback.png",
                "sha256": _sha256_file(fallback_path),
                "bytes": fallback_path.stat().st_size,
                "source_frame": selection["frame"],
                "carries": (
                    "the poster's readable final state: every "
                    "scene's motion complete, all essential text at "
                    "its final value, held still for reading"),
            },
            "playback": {
                "start": playback["start"],
                "repeat": playback["repeat"],
                "end": playback["end"],
                "intended_duration_frames": total,
                "intended_duration_seconds": total / fps,
                "final_hold_state": (
                    "the piece ends on frame %d and holds it: the "
                    "final readable state the poster shows"
                    % (total - 1) if playback.get("end") == "hold_final"
                    else "playback end behavior is %s"
                    % playback.get("end")),
            },
            "placement": placement,
            "checks": {
                "loop_seam": loop_check,
                "hold_final": hold_check,
            },
            "qc": qc,
            "deck": {
                "file": "deck.pptx",
                "sha256": deck_record["sha256"],
                "bytes": deck_record["bytes"],
                "slides": deck_record["slides"],
                "media_part": deck_record["media_part"],
                "embed_verified": bool(
                    deck_verify["media_matches_packaged_artifact"]
                    and deck_verify["all_relationships_internal"]),
            },
            "platform": {
                "powerpoint_playback": "UNVERIFIED",
                "statement": (
                    "Playback inside Microsoft PowerPoint is "
                    "UNVERIFIED on every platform: this package was "
                    "built and structurally verified on Linux, where "
                    "PowerPoint is not available. The deck's embed "
                    "is proven from the file itself (the media part "
                    "is inside the deck, byte-identical to "
                    "component.mp4, and parses); whether PowerPoint "
                    "plays it is a separate claim this build does "
                    "not make."),
            },
        }
        schema = json.loads(
            PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema).iter_errors(record),
            key=lambda e: list(e.absolute_path))
        if errors:
            raise PackageError(
                "PPTX_RECORD_INVALID", "MG_DELIVERY_FAILED",
                "the package record fails its own schema "
                "(references/powerpoint-package-schema.json): "
                + "; ".join(
                    "%s: %s" % ("/".join(str(p) for p in e.absolute_path),
                                e.message) for e in errors[:3]))
        (staging / "package-record.json").write_text(
            json.dumps(record, indent=1) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if out_dir.exists():
        shutil.rmtree(out_dir)
    os.replace(staging, out_dir)
    return {
        "status": "packaged",
        "package_dir": str(out_dir),
        "job_id": record["job_id"],
        "record": record,
    }


def _load(name: str, job_dir: Path) -> dict:
    return _load_json(job_dir / name)


def verify(package_dir: Path) -> dict:
    package_dir = Path(package_dir)
    record_path = package_dir / "package-record.json"
    record = _load_json(record_path)
    schema = json.loads(PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(record),
        key=lambda e: list(e.absolute_path))
    if errors:
        raise PackageError(
            "PPTX_RECORD_INVALID", "MG_SCHEMA_INVALID",
            "package-record.json fails its schema: "
            + "; ".join(e.message for e in errors[:3]))
    for block in ("artifact", "poster", "fallback", "deck"):
        entry = record[block]
        path = package_dir / entry["file"]
        if not path.exists():
            raise PackageError(
                "PPTX_PACKAGE_INCOMPLETE", "MG_INPUT_MISSING",
                "the package is missing %s" % entry["file"])
        actual = _sha256_file(path)
        if actual != entry["sha256"]:
            raise PackageError(
                "PPTX_PACKAGE_HASH_MISMATCH", "MG_HASH_MISMATCH",
                "%s hashes to %s, not the recorded %s"
                % (entry["file"], actual, entry["sha256"]))
    qc_copy = package_dir / record["qc"]["record_file"]
    if not qc_copy.exists():
        raise PackageError(
            "PPTX_PACKAGE_INCOMPLETE", "MG_INPUT_MISSING",
            "the package is missing its consumed QC record %s"
            % record["qc"]["record_file"])
    if _sha256_file(qc_copy) != record["qc"]["record_sha256"]:
        raise PackageError(
            "PPTX_PACKAGE_HASH_MISMATCH", "MG_HASH_MISMATCH",
            "the packaged QC record does not hash to the value the "
            "package record binds")
    deck = powerpoint_adapter.verify_deck(
        package_dir / record["deck"]["file"],
        expect_mp4_sha256=record["artifact"]["sha256"],
        expect_fallback_sha256=record["fallback"]["sha256"])
    return {
        "status": "verified",
        "package_dir": str(package_dir),
        "job_id": record["job_id"],
        "deck_embed": deck,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package a powerpoint_graphic motion component "
                    "for slide delivery (MG-035).")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("package")
    p.add_argument("--job-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--final")
    p.add_argument("--display-width",
                   help="actual placement display width for an "
                        "inset package, in px (960) or mm (169.3mm)")
    p.add_argument("--force", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("--package-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "package":
            result = package(
                Path(args.job_dir), Path(args.out),
                final=Path(args.final) if args.final else None,
                display_width=args.display_width, force=args.force)
        else:
            result = verify(Path(args.package_dir))
    except PackageError as err:
        print(json.dumps({
            "status": "error", "code": err.code,
            "category": err.category, "message": err.message,
            "details": err.details}, indent=1))
        return EXIT_BY_CATEGORY.get(err.category, 7)
    except (PosterSelectionError, AdapterError) as err:
        print(json.dumps({
            "status": "error", "code": err.code,
            "category": err.category, "message": err.message,
            "details": err.details}, indent=1))
        return EXIT_BY_CATEGORY.get(err.category, 7)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
