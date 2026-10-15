"""Non-destructive V1 to V2 manifest migration for Skill 72 (MG-007).

Reads a V1 run manifest (shape: references/legacy-manifest-schema.json) and
writes a NEW V2 job scaffold into a separate output directory:

    manifest.json                 V2 manifest, validated against the
                                  contracts-v2 manifest definition before exit
    scenes/<scene-id>.legacy.json each V1 scene record preserved verbatim,
                                  plus a top-level legacy_schema_version marker
    migration-receipt.json        full accounting of the migration

The input file is never modified. Destination (mode) and owning company are
operator decisions: without --mode or --company-id the tool writes only a
needs_input receipt and exits 2. A VSL mode also refuses with needs_input,
because a VSL insert requires a parent handoff and a V1 manifest carries no
parent; inventing one would fabricate an approval-grade relationship.

Values the V2 manifest cannot honestly hold (the V1 animation_model string,
the music bed path, TTS voice settings, the brand bible path, the storage
root, legacy segmentation) are preserved verbatim in the receipt instead of
being dropped or stuffed into fields with different meanings. Inferred
values are listed explicitly in the receipt's inferred_fields.

Exit codes: 0 migrated; 2 needs_input, failed_validation, or input error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motion_contracts  # noqa: E402

VSL_MODES = ("vsl_desktop", "vsl_mobile")
ALL_MODES = ("powerpoint_graphic", "vsl_desktop", "vsl_mobile", "standalone_video")
PRODUCTION_APPROVAL_POLICY = "owner_or_existing_authorized_reviewer"
COMPANION_ARTIFACTS = ("storyboard.json", "assets.json", "design.json", "timeline.json")
SCENE_COMPATIBILITY = (
    "Scene specs remain on the declared V1 legacy compatibility path: each "
    "scenes/<scene-id>.legacy.json file holds the V1 scene record verbatim "
    "plus a legacy_schema_version marker. They are not native V2 component "
    "scenes and must not be rendered as one; the legacy renderer path owns "
    "them until each scene is re-authored against a registered component."
)
COMPANION_NOTE = (
    "The migrated V2 manifest references storyboard.json, assets.json, "
    "design.json and timeline.json under their standard job artifact names. "
    "Those V2 companion artifacts do not exist yet for the migrated job and "
    "must be authored before the job can reach INPUTS_READY."
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _receipt_base(source: Path, source_sha256: str) -> dict:
    return {
        "source_path": str(source),
        "source_sha256": source_sha256,
        "status": "needs_input",
        "mapped_fields": {},
        "inferred_fields": [],
        "preserved_unmapped": [],
        "adjustments": [],
        "missing_inputs": [],
        "operator_choices": {},
        "scene_compatibility": SCENE_COMPATIBILITY,
        "companion_artifacts_missing": list(COMPANION_ARTIFACTS),
        "companion_artifacts_note": COMPANION_NOTE,
        "created_files": [],
    }


def _finish(out_dir: Path, receipt: dict, exit_code: int) -> int:
    _write_json(out_dir / "migration-receipt.json", receipt)
    if "migration-receipt.json" not in receipt["created_files"]:
        receipt["created_files"].append("migration-receipt.json")
        _write_json(out_dir / "migration-receipt.json", receipt)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "out_dir": str(out_dir),
                "receipt": str(out_dir / "migration-receipt.json"),
                "created_files": receipt["created_files"],
            },
            indent=2,
        )
    )
    return exit_code


def migrate(source: Path, *, mode, company_id, job_id, engine, out_dir) -> int:
    try:
        raw = source.read_bytes()
    except OSError as exc:
        print(f"cannot read V1 manifest {source}: {exc}", file=sys.stderr)
        return 2
    source_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        v1 = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"V1 manifest {source} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(v1, dict):
        print(f"V1 manifest {source} is not a JSON object", file=sys.stderr)
        return 2

    video_name = v1.get("video_name") if isinstance(v1.get("video_name"), str) else "migrated-job"
    if out_dir is None:
        out_dir = source.parent / f"{video_name}.v2"
    out_dir = Path(out_dir)
    receipt = _receipt_base(source, source_sha256)
    receipt["operator_choices"] = {
        "mode": mode,
        "company_id": company_id,
        "job_id": job_id or video_name,
        "default_engine": engine,
    }

    # Refuse to invent destination, owner, or parent.
    missing: list[str] = []
    if mode is None:
        missing.append("--mode: the delivery destination is an operator decision and is never guessed")
    if not company_id:
        missing.append("--company-id: the owning company is an operator decision and is never guessed")
    if mode in VSL_MODES:
        missing.append(
            "parent: VSL modes require a parent handoff (parent job, task, slot, narration cue); "
            "a V1 manifest carries no parent and one is never invented"
        )
    if missing:
        receipt["status"] = "needs_input"
        receipt["missing_inputs"] = missing
        return _finish(out_dir, receipt, 2)

    scenes_v1 = v1.get("scenes")
    if not isinstance(scenes_v1, list) or not scenes_v1:
        receipt["status"] = "failed_validation"
        receipt["missing_inputs"] = ["the V1 manifest has no scenes array to migrate"]
        return _finish(out_dir, receipt, 2)
    fps = v1.get("fps")
    if not isinstance(fps, int) or isinstance(fps, bool) or fps < 1:
        receipt["status"] = "failed_validation"
        receipt["missing_inputs"] = ["the V1 manifest has no usable integer fps"]
        return _finish(out_dir, receipt, 2)

    duration_frames = 0
    scene_entries: list[dict] = []
    legacy_scenes: list[tuple[str, dict]] = []
    for scene in scenes_v1:
        if not isinstance(scene, dict) or not isinstance(scene.get("id"), str):
            receipt["status"] = "failed_validation"
            receipt["missing_inputs"] = ["a V1 scene has no id and cannot be given a stable spec name"]
            return _finish(out_dir, receipt, 2)
        seconds = scene.get("duration_seconds")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            receipt["status"] = "failed_validation"
            receipt["missing_inputs"] = [
                f"V1 scene {scene['id']} has no numeric duration_seconds; its frame duration is never invented"
            ]
            return _finish(out_dir, receipt, 2)
        duration_frames += int(math.floor(seconds * fps + 0.5))
        legacy = dict(scene)
        legacy["legacy_schema_version"] = "1.0"
        legacy_scenes.append((scene["id"], legacy))
        scene_entries.append({"id": scene["id"], "spec": f"scenes/{scene['id']}.legacy.json"})

    has_voiceover = any(
        isinstance(s, dict) and isinstance(s.get("voiceover_text"), str) and s["voiceover_text"].strip()
        for s in scenes_v1
    )
    music_bed = v1.get("music_bed") if isinstance(v1.get("music_bed"), str) else None
    sfx_map = v1.get("sfx") if isinstance(v1.get("sfx"), dict) else {}
    sfx_keys = sorted(str(k) for k in sfx_map.keys())

    adjustments: list[dict] = []
    inferred: list[str] = []
    inferred.append(
        f"duration_frames = {duration_frames}: computed as the sum over {len(scenes_v1)} scenes "
        f"of round(duration_seconds * fps) at fps {fps}; V1 stores seconds, V2 stores frames"
    )

    # Audio derivation.
    if mode == "powerpoint_graphic":
        audio = {
            "mode": "none",
            "parent_audio_ref": None,
            "create_voiceover": False,
            "create_music": False,
            "source_assets": [],
        }
        adjustments.append(
            {
                "field": "audio",
                "wanted": "carry the V1 narration and music into the manifest",
                "used": "audio.mode none with no created or attached audio",
                "reason": "powerpoint_graphic graphics are silent inserts and the V2 manifest "
                "schema forces audio.mode none for this mode; the V1 voiceover text and music "
                "bed are preserved verbatim in the legacy scene files and in this receipt",
            }
        )
        inferred.append(
            "audio.mode = none: forced by the powerpoint_graphic mode, not derived from the V1 audio content"
        )
    else:
        if has_voiceover or music_bed or sfx_keys:
            audio_mode = "own"
        else:
            audio_mode = "none"
        audio = {
            "mode": audio_mode,
            "parent_audio_ref": None,
            "create_voiceover": bool(has_voiceover),
            "create_music": bool(music_bed),
            "source_assets": sfx_keys if audio_mode == "own" else [],
        }
        inferred.append(
            f"audio.mode = {audio_mode}: derived from the V1 manifest "
            f"(voiceover_text present: {bool(has_voiceover)}, music_bed present: {bool(music_bed)}, "
            f"sfx entries: {len(sfx_keys)})"
        )

    if music_bed:
        adjustments.append(
            {
                "field": "audio.source_assets",
                "wanted": "list the music bed alongside the sfx keys",
                "used": "sfx keys only; the music bed path is held in audio_legacy_refs",
                "reason": "V2 audio.source_assets holds asset IDs matching an identifier pattern; "
                "the V1 music bed is a file path, not an asset ID, and is never rewritten into one",
            }
        )

    content_scope = "insert" if mode == "powerpoint_graphic" else "full_program"
    if mode == "standalone_video":
        inferred.append(
            "content_scope = full_program: a V1 run manifest describes a complete standalone "
            "program (the schema forces insert for the other supported migration mode)"
        )

    adjustments.append(
        {
            "field": "approval_policy",
            "wanted": "required",
            "used": PRODUCTION_APPROVAL_POLICY,
            "reason": "the contracts-v2 manifest definition admits only fixture_only and "
            "owner_or_existing_authorized_reviewer, and its production branch requires "
            "owner_or_existing_authorized_reviewer for execution_context production",
        }
    )
    inferred.append(
        "authoring: selection inherit_config with null provider, model and harness; the V1 "
        "animation_model string is preserved in this receipt under mapped_fields and is not "
        "resolved into a V2 authoring identity"
    )
    inferred.append(
        f"delivery.poster_frame = {duration_frames - 1}: the last frame index of the migrated duration"
    )

    manifest = {
        "schema_version": "2.0",
        "job_id": job_id or video_name,
        "company_id": company_id,
        "execution_context": "production",
        "parent": None,
        "mode": mode,
        "content_scope": content_scope,
        "canvas": {"width": v1.get("width"), "height": v1.get("height"), "fps": fps},
        "duration_frames": duration_frames,
        "authoring": {"selection": "inherit_config", "provider": None, "model": None, "harness": None},
        "rendering": {
            "default_engine": engine,
            "allow_legacy_fallback": False,
            "runtime_lock": "runtime-lock.json",
        },
        "storyboard": "storyboard.json",
        "assets": "assets.json",
        "design": "design.json",
        "timeline": "timeline.json",
        "audio": audio,
        "approval_policy": PRODUCTION_APPROVAL_POLICY,
        "variants": [],
        "scenes": scene_entries,
        "delivery": {
            "video_profile": "h264_opaque",
            "poster_frame": duration_frames - 1,
            "placement": "full_frame",
            "playback": {"start": "automatic", "repeat": "once", "end": "hold_final"},
            "required": ["mp4", "poster", "source_package"],
        },
    }

    validation_errors = motion_contracts.validate_document(manifest, "manifest")
    # validate_document drops root allOf branch failures by design; run the
    # full validator here because a migrated production manifest must satisfy
    # the conditional branches too.
    full_errors = motion_contracts._raw_errors(manifest, "manifest")
    if full_errors:
        receipt["status"] = "failed_validation"
        receipt["validation_errors"] = [
            {"path": motion_contracts._error_path(e), "message": e.message} for e in full_errors
        ]
        receipt["missing_inputs"] = [
            "the migrated manifest does not validate against the contracts-v2 manifest "
            "definition; no manifest was written"
        ]
        return _finish(out_dir, receipt, 2)
    _ = validation_errors  # shape stage already covered by the full pass

    mapped: dict[str, object] = {
        "video_name": "manifest job_id (unless --job-id overrides it) and the default output directory name",
        "fps": "manifest canvas.fps",
        "width": "manifest canvas.width",
        "height": "manifest canvas.height",
        "scenes": "manifest scenes entries pointing at scenes/<scene-id>.legacy.json; each V1 scene "
        "record is preserved verbatim in its legacy spec file",
        "animation_model": "preserved verbatim in mapped_fields.animation_model_note; never resolved "
        "into the V2 authoring block",
        "animation_model_note": v1.get("animation_model"),
    }
    if music_bed:
        mapped["music_bed"] = (
            "sets audio.create_music true; the bed path itself is a legacy reference held in "
            "audio_legacy_refs.music_bed because V2 audio.source_assets holds asset IDs, not paths"
        )
    if sfx_map:
        mapped["sfx"] = (
            "sfx keys are listed in manifest audio.source_assets (when the derived audio mode is "
            "own); the key-to-path map is held verbatim in audio_legacy_refs.sfx"
        )
    preserved: list[dict] = []
    preserved_reasons = {
        "brand_bible": "authoring input for the V2 design.json, which must still be authored; "
        "the V2 manifest holds no brand bible path",
        "storage_root": "runtime placement for the legacy pipeline; the V2 manifest does not "
        "carry machine-specific storage roots",
        "segment_minutes": "legacy render segmentation; V2 compiles one timeline and does not "
        "segment by minutes",
        "music_bpm": "legacy synthesized-score tempo; a V2 score decision is declared with the "
        "audio source decisions, not reverse-engineered from V1",
        "music_seed": "legacy synthesized-score seed; see music_bpm",
        "synth_sfx": "legacy SFX synthesis toggle; V2 resolves SFX as declared audio source assets",
        "tts": "V1 voice settings (model, reference_id, temperature) are an audio source "
        "decision that must be re-declared and approved for the V2 job; the values are preserved "
        "here so nothing is lost, and are never copied into the manifest",
    }
    handled = set(mapped) | {"animation_model_note"}
    for key, value in v1.items():
        if key in handled:
            continue
        preserved.append(
            {
                "field": key,
                "value": value,
                "reason": preserved_reasons.get(
                    key, "no honest V2 manifest home; preserved verbatim in this receipt"
                ),
            }
        )

    receipt["status"] = "migrated"
    receipt["mapped_fields"] = mapped
    receipt["inferred_fields"] = inferred
    receipt["preserved_unmapped"] = preserved
    receipt["adjustments"] = adjustments
    receipt["audio_legacy_refs"] = {"music_bed": music_bed, "sfx": sfx_map}

    created: list[str] = []
    for scene_id, legacy in legacy_scenes:
        name = f"scenes/{scene_id}.legacy.json"
        _write_json(out_dir / name, legacy)
        created.append(name)
    _write_json(out_dir / "manifest.json", manifest)
    created.append("manifest.json")
    receipt["created_files"] = created
    return _finish(out_dir, receipt, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate a Skill 72 V1 manifest to a V2 job scaffold, non-destructively."
    )
    parser.add_argument("source", help="Path to the V1 manifest JSON file. Never modified.")
    parser.add_argument("--mode", choices=ALL_MODES, default=None,
                        help="V2 delivery mode. Required; never guessed.")
    parser.add_argument("--company-id", default=None,
                        help="Owning company ID for the V2 job. Required; never guessed.")
    parser.add_argument("--job-id", default=None,
                        help="V2 job ID. Defaults to the V1 video_name.")
    parser.add_argument("--engine", choices=("remotion", "hyperframes"), default="remotion",
                        help="Default engine recorded in the V2 manifest (operator choice).")
    parser.add_argument("--out-dir", default=None,
                        help="Output directory. Defaults to a sibling named <video_name>.v2.")
    args = parser.parse_args(argv)
    return migrate(
        Path(args.source),
        mode=args.mode,
        company_id=args.company_id,
        job_id=args.job_id,
        engine=args.engine,
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )


if __name__ == "__main__":
    sys.exit(main())
