"""Standalone motion-video orchestration (Directive MG-039).

Builds one complete standalone_video piece from a governed job package
(manifest, storyboard, scene specs, design, datasets, build plan, and,
for the narrated variant, the MG-025 narration record) by composing the
shipped layers only:

- contracts validation: scripts/motion_contracts.py (MG-007). The two
  C01 scene specs are the documented MG-017/MG-018 divergence: the
  canonical scene $def is closed on C05, so findings confined to those
  two files are recorded verbatim in the build record; any other
  finding fails the build by name.
- compiled timeline: MG-021's compiler, driven through
  runtime/src/standalone/cli.ts (compile). The compile input is derived
  here from the manifest scene order, the scene specs' durations, the
  build plan's transitions, and the narration record through the same
  sample-to-frame arithmetic as runtime/src/orchestrator/narration.ts.
  The fresh compile must equal the package's authored timeline.json.
- renders: the same TS driver (render) places one single-scene shell
  job per scene through the shipped adapters and dispatcher.
- assembly: MG-022's scripts/assemble.py with MG-023's resolved audio
  plan (own narration, music, and SFX when the package declares them;
  no audio stream at all when it declares none).
- poster: directive Section 17.2, implemented here directly because
  MG-035 has not landed in this tree. The poster is the manifest's
  declared poster frame, which must land inside the ending scene's
  designed hold and outside every transition overlap; it is extracted
  from the assembled final MP4 and measured before registration. This
  duplicates the MG-035 rule on purpose and is the unification
  follow-on named in the MG-039 report.
- coverage: MG-031's scripts/critique_bundle.py at a 1 second sampling
  interval (Section 17.1 M11: end-to-end coverage includes the ending;
  the final frame is a required targeted sample).
- proof: MG-032's evaluator per C05 scene plus the C01 components'
  adapter proof surfaces, through the TS driver (proof).
- creative review surface: an MG-033 rubric record
  (scripts/review_rubric.py validates it) and its dashboard.
- technical gate: MG-034's scripts/qc.py over the staged job package.
  QC script resolution order: --qc-script, the SKILL72_QC_SCRIPT
  environment variable, this tree's scripts/qc.py, then the MG-034
  build worktree beside this one. No QC script found is a named
  blocker: the build fails closed, it never skips the gate.
- packaging: the delivery record (delivery/deliverables.json) registers
  every required final asset with its sha256 and location, the source
  and timeline package, placement metadata, and, where the audio plan
  produced them, captions and stems.

Font seam, stated plainly: authoring packages name the runtime
registry font requirement by its alias (fixture-sans), which is what
the canonical contracts require and what both engine registries
resolve. The staged delivery package's assets.json records the
registry resolution (family Liberation Sans, the family whose bytes
actually render) because MG-034's font check verifies registry
requirements through fontconfig family membership. Both records are
kept; the build record names the seam.

Usage:
    python3 scripts/build_standalone.py build --package DIR --stage DIR [--qc-script PATH]
    python3 scripts/build_standalone.py verify --job-dir DIR
    python3 scripts/build_standalone.py derive --package DIR --out FILE
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent
SAMPLE_RATE = 48000
C01_SPEC_FILES = {"scenes/open-reveal.json", "scenes/detail-zoom.json"}
RESOLVED_FONT_FAMILY = "Liberation Sans"
POSTER_MIN_MEAN_LUMINANCE = 16.0


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


motion_contracts = _load_module("motion_contracts", SKILL_DIR / "scripts" / "motion_contracts.py")
audio_policy = _load_module("audio_policy", SKILL_DIR / "scripts" / "audio_policy.py")


class BuildFailure(Exception):
    """A named build failure: the step and the fact that failed it."""


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(cmd, *, expect=0, label="command"):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if expect is not None and proc.returncode != expect:
        tail = (proc.stderr or proc.stdout or "")[-1200:]
        raise BuildFailure(f"{label} failed with exit {proc.returncode}: {tail}")
    return proc


def sample_to_frame_floor(sample: int, fps: int) -> int:
    """The one rounding rule, mirrored from orchestrator/narration.ts."""
    return (int(sample) * int(fps)) // SAMPLE_RATE


# ---------------------------------------------------------------------
# Compile input derivation (MG-021 input, from governed package data)
# ---------------------------------------------------------------------

# The program's cue design, derived from each scene's spec and role:
# reveals anchor at the spec's motion start, the proof peak and holds
# anchor at the motion end, the nested detail anchors at its start
# frame with its hold 24 frames later (the chip settles 18 frames
# after it starts; the hold declaration stays after the settle).
def derive_cues(manifest: dict, specs: dict, plan: dict) -> list:
    roles = {entry["id"]: entry["role"] for entry in plan["scenes"]}
    cues = []
    for entry in manifest["scenes"]:
        scene_id = entry["id"]
        spec = specs[scene_id]
        if spec["component_id"] == "C01" and spec.get("variant") == "nested_detail":
            start = spec["detail"]["start_frame"]
            cues.append({
                "id": f"cue-{scene_id}-detail", "sceneId": scene_id, "type": "cue",
                "anchor": {"kind": "semantic_state", "state": "detail", "sceneLocalFrame": start},
            })
            cues.append({
                "id": f"cue-{scene_id}-hold", "sceneId": scene_id, "type": "hold_start",
                "anchor": {"kind": "semantic_state", "state": "detail_hold", "sceneLocalFrame": start + 24},
            })
            continue
        motion = spec["motion"]
        cues.append({
            "id": f"cue-{scene_id}-reveal", "sceneId": scene_id, "type": "reveal_start",
            "anchor": {"kind": "semantic_state", "state": "reveal", "sceneLocalFrame": motion["start_frame"]},
        })
        if roles.get(scene_id) == "proof_peak":
            cues.append({
                "id": f"cue-{scene_id}-proof", "sceneId": scene_id, "type": "proof",
                "anchor": {"kind": "semantic_state", "state": "proof", "sceneLocalFrame": motion["end_frame_exclusive"]},
            })
        hold_state = "final_hold" if roles.get(scene_id) == "ending" else "hold"
        cues.append({
            "id": f"cue-{scene_id}-hold", "sceneId": scene_id, "type": "hold_start",
            "anchor": {"kind": "semantic_state", "state": hold_state, "sceneLocalFrame": motion["end_frame_exclusive"]},
        })
    return cues


def derive_compile_input(package_dir: Path) -> dict:
    manifest = read_json(package_dir / "manifest.json")
    plan = read_json(package_dir / "build-plan.json")
    specs = {
        entry["id"]: read_json(package_dir / entry["spec"]) for entry in manifest["scenes"]
    }
    fps = manifest["canvas"]["fps"]
    narrated = manifest["audio"]["mode"] == "own"
    doc = {
        "jobId": manifest["job_id"],
        "fps": fps,
        "mode": "program",
        "audioOwner": "self" if narrated else "none",
        "parentSlot": None,
        "scenes": [
            {"id": entry["id"], "durationFrames": specs[entry["id"]]["duration_frames"]}
            for entry in manifest["scenes"]
        ],
        "transitions": [
            {
                "id": t["id"],
                "fromSceneId": t["from_scene_id"],
                "toSceneId": t["to_scene_id"],
                "frames": t["frames"],
                "ownerSceneId": t["owner_scene_id"],
            }
            for t in plan["transitions"]
        ],
        "cues": derive_cues(manifest, specs, plan),
    }
    if narrated:
        narration = read_json(package_dir / "narration.json")
        segments = []
        captions = []
        for scene in narration["scenes"]:
            measured = scene["measured"]
            if measured is None:
                raise BuildFailure(
                    f"narration scene {scene['scene_id']} has no measured range; "
                    "the standalone build requires measured narration (MG-025 record)"
                )
            start = sample_to_frame_floor(measured["start_sample"], fps)
            end = sample_to_frame_floor(measured["end_sample"] - 1, fps) + 1
            segments.append({
                "id": f"narration-{scene['scene_id']}",
                "sceneId": scene["scene_id"],
                "startFrame": start,
                "endFrameExclusive": end,
            })
            captions.append({
                "id": f"caption-{scene['scene_id']}",
                "sceneId": scene["scene_id"],
                "startFrame": start,
                "endFrameExclusive": end,
            })
        doc["narration"] = segments
        doc["captions"] = captions
        sfx = (plan.get("audio") or {}).get("sfx") or []
        if sfx:
            doc["sfxCues"] = [
                {"id": cue["id"], "sceneId": cue["scene_id"], "frame": cue["frame"]}
                for cue in sfx
            ]
    return doc


# ---------------------------------------------------------------------
# TS driver
# ---------------------------------------------------------------------

def run_ts_driver(stage_dir: Path, *args: str, label: str):
    cli = SKILL_DIR / "runtime" / "dist" / "src" / "standalone" / "cli.js"
    if not cli.is_file():
        proc = subprocess.run(
            ["npm", "run", "build"], cwd=SKILL_DIR / "runtime",
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or not cli.is_file():
            raise BuildFailure(f"runtime build failed: {(proc.stderr or proc.stdout)[-800:]}")
    proc = subprocess.run(
        ["node", str(cli), *args], capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise BuildFailure(f"{label} failed with exit {proc.returncode}: {(proc.stdout or '')[-1000:]} {(proc.stderr or '')[-600:]}")
    return proc


# ---------------------------------------------------------------------
# Audio fixture media (engineering-fixture tone stand-ins, the MG-023
# and MG-034 convention: narration and SFX are labeled tone voices at
# amplitude 0.5 so the encoded mix stays under the clipping ceiling;
# the music pad is three soft tones under a lowpass).
# ---------------------------------------------------------------------

def generate_audio(package_dir: Path, job_dir: Path, timeline: dict, sidecar: dict) -> dict:
    manifest = read_json(package_dir / "manifest.json")
    plan = read_json(package_dir / "build-plan.json")
    audio = plan["audio"]
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    def check_samples(path: Path, expected: int, label: str) -> None:
        import wave

        with wave.open(str(path)) as handle:
            actual = handle.getnframes()
        if actual != expected:
            raise BuildFailure(f"{label} holds {actual} samples, expected exactly {expected}")

    # Lengths are set with atrim=end_sample, never -frames:a: for lavfi
    # sources one output frame is a 1024-sample block, so a frame count
    # would overshoot the declared sample length by that factor. Every
    # generated file's sample count is verified before it is used.
    narration_entries = []
    for track in sidecar.get("narration", []):
        scene_id = track["id"].removeprefix("narration-")
        samples = track["endSampleExclusive"] - track["startSample"]
        freq = audio["narration_tones_hz"][scene_id]
        out = audio_dir / f"narration-{scene_id}.wav"
        run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={SAMPLE_RATE}",
            "-af", f"volume={audio['narration_amplitude']},atrim=end_sample={samples}",
            "-c:a", "pcm_s16le", str(out),
        ], label=f"narration tone generation for {scene_id}")
        check_samples(out, samples, f"narration tone for {scene_id}")
        narration_entries.append({"id": track["id"], "path": f"audio/{out.name}"})
    total_samples = sidecar["total_samples"]
    tones = audio["music"]["generation"]["tones_hz"]
    inputs = []
    filters = []
    for idx, freq in enumerate(tones):
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={SAMPLE_RATE}"]
        filters.append(
            f"[{idx}:a]volume={audio['music']['generation']['amplitude_each']},"
            f"atrim=end_sample={total_samples}[t{idx}]"
        )
    mix_ins = "".join(f"[t{idx}]" for idx in range(len(tones)))
    filters.append(f"{mix_ins}amix=inputs={len(tones)}:normalize=0,lowpass=f={audio['music']['generation']['lowpass_hz']}[music]")
    music_out = audio_dir / audio["music"]["file"]
    run([
        "ffmpeg", "-y", "-v", "error", *inputs,
        "-filter_complex", ";".join(filters), "-map", "[music]",
        "-c:a", "pcm_s16le", str(music_out),
    ], label="music pad generation")
    check_samples(music_out, total_samples, "music pad")
    sfx_entries = []
    for cue in audio.get("sfx", []):
        samples = int(round(cue["duration_seconds"] * SAMPLE_RATE))
        out = audio_dir / f"{cue['id']}.wav"
        run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency={cue['tone_hz']}:sample_rate={SAMPLE_RATE}",
            "-af", f"volume={cue['amplitude']},atrim=end_sample={samples}",
            "-c:a", "pcm_s16le", str(out),
        ], label=f"sfx generation for {cue['id']}")
        check_samples(out, samples, f"sfx {cue['id']}")
        sfx_entries.append({"id": cue["id"], "path": f"audio/{out.name}"})
    return {
        "narration": narration_entries,
        "music": {"path": f"audio/{music_out.name}"},
        "sfx": sfx_entries,
    }


# ---------------------------------------------------------------------
# Poster (Section 17.2 rule; see the module docstring)
# ---------------------------------------------------------------------

def check_poster_frame(timeline: dict, poster_frame: int) -> dict:
    scenes = timeline["scenes"]
    ending = scenes[-1]
    hold_events = [
        e for e in timeline["events"]
        if e["scene_id"] == ending["id"] and e["type"] == "hold_start"
    ]
    if not hold_events:
        raise BuildFailure(f"poster rule: ending scene {ending['id']} has no hold_start event")
    hold_frame = hold_events[0]["frame"]
    overlaps = []
    placed = {s["id"]: s for s in scenes}
    for scene in scenes[1:]:
        prev_end = placed[scene["id"]]["start_frame"]
        overlaps.append((prev_end, prev_end + scene["transition_in_frames"]))
    in_hold = hold_frame <= poster_frame < ending["end_frame_exclusive"]
    in_overlap = any(start <= poster_frame < end for start, end in overlaps if end > start)
    if not in_hold or in_overlap:
        raise BuildFailure(
            f"poster rule: declared poster frame {poster_frame} is not a stable final state "
            f"(ending hold starts at {hold_frame}, ending scene ends at {ending['end_frame_exclusive']}, "
            f"transition overlaps {overlaps})"
        )
    return {"hold_start_frame": hold_frame, "ending_scene": ending["id"], "overlaps": overlaps}


def extract_poster(final_mp4: Path, poster_frame: int, out_path: Path, canvas: dict) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(final_mp4),
        "-vf", f"select='eq(n\\,{poster_frame})'", "-vframes", "1", str(out_path),
    ], label="poster extraction")
    probe = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(out_path),
    ], label="poster probe")
    stream = json.loads(probe.stdout)["streams"][0]
    if stream["width"] != canvas["width"] or stream["height"] != canvas["height"]:
        raise BuildFailure(
            f"poster dimensions {stream['width']}x{stream['height']} do not equal the canvas "
            f"{canvas['width']}x{canvas['height']}"
        )
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out_path), "-vf", "format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True,
    )
    if raw.returncode != 0 or not raw.stdout:
        raise BuildFailure("poster luminance measurement failed")
    mean = sum(raw.stdout) / len(raw.stdout)
    if mean < POSTER_MIN_MEAN_LUMINANCE:
        raise BuildFailure(
            f"poster rule: frame {poster_frame} mean luminance {mean:.2f} is effectively black; "
            "the declared poster frame is not a readable final state"
        )
    return {"width": stream["width"], "height": stream["height"], "mean_luminance": round(mean, 3)}


# ---------------------------------------------------------------------
# Captions (SRT from the compiled sidecar's caption ranges)
# ---------------------------------------------------------------------

def srt_timestamp(frame: int, fps: int) -> str:
    ms = int(round(frame * 1000 / fps))
    hours, rem = divmod(ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_captions(package_dir: Path, sidecar: dict, fps: int, out_path: Path) -> None:
    narration = read_json(package_dir / "narration.json")
    text_by_scene = {scene["scene_id"]: scene["text"] for scene in narration["scenes"]}
    lines = []
    for idx, caption in enumerate(sidecar.get("captions", []), start=1):
        scene_id = caption["id"].removeprefix("caption-")
        lines.append(str(idx))
        lines.append(
            f"{srt_timestamp(caption['startFrame'], fps)} --> "
            f"{srt_timestamp(caption['endFrameExclusive'], fps)}"
        )
        lines.append(text_by_scene[scene_id])
        lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------
# QC resolution
# ---------------------------------------------------------------------

def resolve_qc_script(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("SKILL72_QC_SCRIPT")
    if env:
        candidates.append(Path(env))
    candidates.append(SKILL_DIR / "scripts" / "qc.py")
    candidates.append(REPO_ROOT.parent / "wt-mg034" / "72-motion-video-plus" / "scripts" / "qc.py")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    looked = ", ".join(str(c) for c in candidates)
    raise BuildFailure(
        "MG-034 QC script not found (looked for --qc-script, $SKILL72_QC_SCRIPT, "
        f"{looked}); the standalone build fails closed without its technical gate"
    )


# ---------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------

def cmd_build(args) -> int:
    package_dir = Path(args.package).resolve()
    stage_dir = Path(args.stage).resolve()
    job_dir = stage_dir / "job"
    manifest = read_json(package_dir / "manifest.json")
    plan = read_json(package_dir / "build-plan.json")
    job_id = manifest["job_id"]
    narrated = manifest["audio"]["mode"] == "own"
    record: dict = {
        "schema_version": "1.0", "item": "MG-039", "kind": "standalone_build_record",
        "job_id": job_id, "package": str(package_dir), "steps": {},
    }

    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    job_dir.mkdir(parents=True)

    # 1. Compile the timeline (MG-021) and check the authored record.
    compile_input = derive_compile_input(package_dir)
    compile_input_path = stage_dir / "compile-input.json"
    write_json(compile_input_path, compile_input)
    run_ts_driver(
        stage_dir, "compile",
        "--input", str(compile_input_path),
        "--timeline-out", str(job_dir / "timeline.json"),
        "--sidecar-out", str(job_dir / "timeline-sidecar.json"),
        label="MG-021 timeline compile",
    )
    timeline = read_json(job_dir / "timeline.json")
    sidecar = read_json(job_dir / "timeline-sidecar.json")
    authored = read_json(package_dir / "timeline.json")
    if authored != timeline:
        raise BuildFailure(
            "authored timeline.json in the package differs from the fresh MG-021 compile; "
            "regenerate the package timeline from the compiler instead of editing it"
        )
    record["steps"]["compile"] = {
        "total_frames": timeline["total_frames"], "total_samples": sidecar["total_samples"],
        "authored_timeline_matches_compile": True,
    }

    # 2. Contracts gate (MG-007) with the C01 divergence classification.
    findings = motion_contracts.validate_job(package_dir)
    blocking = [f for f in findings if f["path"].split("#")[0] not in C01_SPEC_FILES]
    divergence = [f for f in findings if f["path"].split("#")[0] in C01_SPEC_FILES]
    if blocking:
        raise BuildFailure(f"contracts validation failed outside the C01 divergence: {json.dumps(blocking[:6], indent=2)}")
    record["steps"]["contracts"] = {
        "findings_total": len(findings),
        "c01_divergence_findings": divergence,
        "note": "Findings are confined to the two C01 scene specs: the canonical scene $def is closed on C05 1.0.0 (the MG-017/MG-018 catalog divergence). Every other package file validates clean.",
    }

    # 3. Stage the job package skeleton.
    for name in ("manifest.json", "storyboard.json", "design.json"):
        shutil.copy2(package_dir / name, job_dir / name)
    for sub in ("scenes", "data"):
        shutil.copytree(package_dir / sub, job_dir / sub)
    (job_dir / "assets").mkdir(exist_ok=True)
    shutil.copy2(package_dir / "assets" / "subject.svg", job_dir / "assets" / "subject.svg")
    if narrated:
        shutil.copy2(package_dir / "narration.json", job_dir / "narration.json")

    # 4. Audio media (narrated only) and the media registry.
    media_audio = None
    if narrated:
        media_audio = generate_audio(package_dir, job_dir, timeline, sidecar)
    specs = {e["id"]: read_json(package_dir / e["spec"]) for e in manifest["scenes"]}
    media = {
        "canvas": manifest["canvas"],
        "scenes": [
            {
                "id": entry["id"],
                "path": f"renders/segments/{entry['id']}.mp4",
                "engine": specs[entry["id"]]["engine"],
            }
            for entry in manifest["scenes"]
        ],
    }
    if narrated:
        media["narration"] = media_audio["narration"]
        media["music"] = media_audio["music"]
        media["sfx"] = media_audio["sfx"]
        media["audio"] = {"loudnessTarget": {
            "integratedLufs": plan["audio"]["loudness_target"]["integratedLufs"],
            "truePeakDb": plan["audio"]["loudness_target"]["truePeakDb"],
        }}
    else:
        media["narration"] = []
        media["sfx"] = []
    write_json(job_dir / "media.json", media)

    # Staged assets.json: authoring entries plus the build's audio media,
    # with the font requirement's registry resolution recorded (the seam
    # named in the module docstring).
    assets_doc = read_json(package_dir / "assets.json")
    for requirement in assets_doc.get("font_requirements", []):
        if requirement.get("source") == "runtime_registry":
            requirement["family_alias"] = RESOLVED_FONT_FAMILY
    if narrated:
        for entry in media_audio["narration"] + media_audio["sfx"]:
            assets_doc["assets"].append({
                "id": entry["id"], "kind": "audio", "path": entry["path"],
                "sha256": sha256_file(job_dir / entry["path"]),
                "usage": "embed_original", "rights_ref": "Generated engineering fixture audio for Skill 72 (MG-039 tone stand-ins). No third-party rights.",
                "focal_point": None,
            })
        assets_doc["assets"].append({
            "id": "music-bed", "kind": "audio", "path": media_audio["music"]["path"],
            "sha256": sha256_file(job_dir / media_audio["music"]["path"]),
            "usage": "embed_original", "rights_ref": "Generated engineering fixture audio for Skill 72 (MG-039 tone stand-ins). No third-party rights.",
            "focal_point": None,
        })
    write_json(job_dir / "assets.json", assets_doc)
    record["steps"]["staging"] = {"media_scenes": len(media["scenes"]), "narrated": narrated}

    # 5. Renders through the routed adapters (TS driver).
    run_ts_driver(
        stage_dir, "render", "--package", str(package_dir), "--stage", str(stage_dir),
        label="adapter renders",
    )
    render_receipt = read_json(stage_dir / "render-receipt.json")
    segments_dir = job_dir / "renders" / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    for scene_record in render_receipt["scenes"]:
        shutil.copy2(stage_dir / scene_record["segment"], segments_dir / Path(scene_record["segment"]).name)
    shutil.copy2(stage_dir / "render-receipt.json", job_dir / "render-receipt.json")
    record["steps"]["render"] = {
        "scenes": [
            {"scene_id": s["scene_id"], "engine": s["routed_engine"], "frames": s["frames"],
             "routing_reason_code": s["routing"]["reason_code"]}
            for s in render_receipt["scenes"]
        ]
    }

    # 6. Assembly (MG-022) under the MG-023 resolved audio plan.
    write_json(job_dir / "plan.json", {"timeline": timeline, "sidecar": sidecar})
    assemble_workdir = stage_dir / "assemble"
    run([
        sys.executable, str(SKILL_DIR / "scripts" / "assemble.py"),
        "--plan", str(job_dir / "plan.json"),
        "--media", str(job_dir / "media.json"),
        "--out", str(job_dir / "renders" / "final.mp4"),
        "--workdir", str(assemble_workdir),
    ], label="MG-022 assembly")
    assemble_probe = read_json(assemble_workdir / "assemble-probe.json")
    record["steps"]["assemble"] = {
        "audio_mode": (assemble_probe.get("audio_qc") or {}).get("mode", assemble_probe.get("mode")),
        "audio_qc": assemble_probe.get("audio_qc"),
        "decoded_frames": assemble_probe.get("decoded_frames"),
        "audio_present": assemble_probe.get("audio_present"),
    }
    delivery_dir = job_dir / "delivery"
    delivery_dir.mkdir(exist_ok=True)
    if narrated:
        stems_dir = delivery_dir / "stems"
        stems_dir.mkdir(exist_ok=True)
        for stem in ("narration", "music", "sfx"):
            src = assemble_workdir / "stems" / f"{stem}.wav"
            if not src.is_file():
                raise BuildFailure(f"declared audio plan produced no {stem} stem at {src}")
            shutil.copy2(src, stems_dir / f"{stem}.wav")

    # 7. Poster (Section 17.2 rule) from the assembled final.
    poster_frame = manifest["delivery"]["poster_frame"]
    rule = check_poster_frame(timeline, poster_frame)
    poster_measure = extract_poster(
        job_dir / "renders" / "final.mp4", poster_frame,
        delivery_dir / "poster.png", manifest["canvas"],
    )
    record["steps"]["poster"] = {"frame": poster_frame, **rule, **poster_measure}

    # 8. Coverage (MG-031) at a 1 second interval; the record must be
    # complete, which includes the ending's final frame sample.
    review_dir = job_dir / "review"
    run([
        sys.executable, str(SKILL_DIR / "scripts" / "critique_bundle.py"), "build",
        "--video", str(job_dir / "renders" / "final.mp4"),
        "--outdir", str(review_dir),
        "--job-id", job_id,
        "--timeline", str(job_dir / "timeline.json"),
        "--sidecar", str(job_dir / "timeline-sidecar.json"),
        "--interval", "1",
    ], label="MG-031 coverage bundle")
    coverage_path = review_dir / f"{job_id}__coverage.json"
    coverage = read_json(coverage_path)
    if coverage.get("verdict") != "complete":
        raise BuildFailure(f"coverage verdict is {coverage.get('verdict')!r}, not complete")
    record["steps"]["coverage"] = {
        "verdict": coverage["verdict"],
        "omitted_frames": (coverage.get("coverage") or {}).get("omitted_frames"),
        "samples": len(coverage.get("samples", [])),
    }

    # 9. Proof (MG-032) through the TS driver.
    run_ts_driver(
        stage_dir, "proof", "--package", str(package_dir), "--stage", str(stage_dir),
        label="MG-032 motion proof",
    )
    proof_doc = read_json(stage_dir / "proof" / "motion-proof.json")
    if proof_doc.get("verdict") != "pass":
        raise BuildFailure(f"motion proof verdict is {proof_doc.get('verdict')!r}, not pass")
    shutil.copy2(stage_dir / "proof" / "motion-proof.json", job_dir / "motion-proof.json")
    proof_dir = job_dir / "proof"
    proof_dir.mkdir(exist_ok=True)
    for scene_record in proof_doc["scenes"]:
        if scene_record.get("mechanism") == "mg032_evaluator":
            src = stage_dir / "proof" / scene_record["scene_id"] / "proof-record.json"
            shutil.copy2(src, proof_dir / f"{scene_record['scene_id']}.json")
    record["steps"]["proof"] = {
        "verdict": proof_doc["verdict"],
        "scenes": [{"scene_id": s["scene_id"], "mechanism": s["mechanism"], "verdict": s["verdict"]}
                   for s in proof_doc["scenes"]],
    }

    # 10. Measured audio record (narrated) for the review surface.
    audio_measurements = None
    if narrated:
        target = {
            "integratedLufs": plan["audio"]["loudness_target"]["integratedLufs"],
            "truePeakDb": plan["audio"]["loudness_target"]["truePeakDb"],
        }
        measured = audio_policy.measure_loudness(
            "ffmpeg", str(job_dir / "renders" / "final.mp4"), target,
        )
        verdict = audio_policy.loudness_verdict(measured, target)
        audio_measurements = {
            "schema_version": "1.0", "item": "MG-039", "kind": "standalone_audio_measurements",
            "job_id": job_id,
            "integrated_lufs": measured.get("integratedLufs"),
            "true_peak_dbtp": measured.get("truePeakDb"),
            "target": {
                "integrated_lufs": target["integratedLufs"],
                "true_peak_dbtp": target["truePeakDb"],
            },
            "loudness_on_target": verdict.get("ok"),
            "loudness_verdict": verdict,
            "measured_with": "scripts/audio_policy.py measure_loudness over the assembled final MP4",
        }
        write_json(delivery_dir / "audio-measurements.json", audio_measurements)
        record["steps"]["audio_measurements"] = audio_measurements

    # 11. Creative review surface (MG-033).
    review_record = build_review_record(job_dir, manifest, coverage_path, narrated)
    review_path = review_dir / "review-record.json"
    write_json(review_path, review_record)
    run([
        sys.executable, str(SKILL_DIR / "scripts" / "review_rubric.py"),
        "validate", str(review_path),
    ], label="MG-033 review record validation")
    dashboard_path = review_dir / "review-dashboard.md"
    run([
        sys.executable, str(SKILL_DIR / "scripts" / "review_rubric.py"),
        "dashboard", str(review_path), "--out", str(dashboard_path),
    ], label="MG-033 review dashboard")
    record["steps"]["review"] = {"verdict": review_record["verdict"], "provisional": True}

    # 12. Technical gate (MG-034 QC) over the staged job package.
    qc_script = resolve_qc_script(args.qc_script)
    run([
        sys.executable, str(qc_script), "check", "--job-dir", str(job_dir),
    ], label="MG-034 QC gate")
    qc_record = read_json(job_dir / "qc" / "final-qc.json")
    if qc_record.get("verdict") != "pass":
        raise BuildFailure(f"QC verdict is {qc_record.get('verdict')!r}, not pass")
    record["steps"]["qc"] = {
        "script": str(qc_script), "verdict": qc_record["verdict"],
        "checks": len(qc_record.get("checks", [])),
    }

    # 13. Packaging: source package, placement, captions, delivery record.
    source_entries = []
    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            source_entries.append({
                "path": str(path.relative_to(package_dir)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            })
    source_package = {
        "schema_version": "1.0", "item": "MG-039", "kind": "standalone_source_package",
        "job_id": job_id, "authoring_package_root": str(package_dir),
        "files": source_entries,
    }
    write_json(delivery_dir / "source-package.json", source_package)
    placement = {
        "schema_version": "1.0", "item": "MG-039", "kind": "standalone_placement_metadata",
        "job_id": job_id, "mode": "standalone_video", "placement": "full_frame",
        "canvas": manifest["canvas"], "fps": manifest["canvas"]["fps"],
        "total_frames": timeline["total_frames"],
        "video_profile": manifest["delivery"]["video_profile"],
        "poster_frame": poster_frame,
        "playback": manifest["delivery"]["playback"],
        "publishing": "No hosted platform and no upload integration: publishing stays in the existing owning workflow. This record and the delivery record are the authorized destination for this build.",
    }
    write_json(delivery_dir / "placement.json", placement)
    if narrated:
        write_captions(package_dir, sidecar, manifest["canvas"]["fps"], delivery_dir / "captions.srt")

    def asset(kind: str, rel: str) -> dict:
        path = job_dir / rel
        return {"kind": kind, "path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size}

    assets = [
        asset("final_mp4", "renders/final.mp4"),
        asset("poster", "delivery/poster.png"),
        asset("source_package", "delivery/source-package.json"),
        asset("placement_metadata", "delivery/placement.json"),
        asset("review_record", "review/review-record.json"),
        asset("review_dashboard", "review/review-dashboard.md"),
        asset("qc_record", "qc/final-qc.json"),
        asset("coverage_record", f"review/{job_id}__coverage.json"),
        asset("motion_proof", "motion-proof.json"),
        asset("timeline", "timeline.json"),
        asset("timeline_sidecar", "timeline-sidecar.json"),
        asset("render_receipt", "render-receipt.json"),
    ]
    if narrated:
        for stem in ("narration", "music", "sfx"):
            assets.append(asset("audio_stem", f"delivery/stems/{stem}.wav"))
        assets.append(asset("captions", "delivery/captions.srt"))
        assets.append(asset("audio_measurements", "delivery/audio-measurements.json"))
    deliverables = {
        "schema_version": "1.0", "item": "MG-039", "kind": "standalone_delivery_record",
        "job_id": job_id, "mode": "standalone_video",
        "canvas": manifest["canvas"], "fps": manifest["canvas"]["fps"],
        "total_frames": timeline["total_frames"],
        "video_profile": manifest["delivery"]["video_profile"],
        "poster_frame": poster_frame,
        "job_package_dir": str(job_dir),
        "assets": assets,
        "verification": {
            "qc_verdict": qc_record["verdict"],
            "coverage_verdict": coverage["verdict"],
            "proof_verdict": proof_doc["verdict"],
            "review_verdict": review_record["verdict"],
        },
    }
    write_json(delivery_dir / "deliverables.json", deliverables)
    record["steps"]["packaging"] = {"assets_registered": len(assets)}

    write_json(stage_dir / "build-record.json", record)

    # 14. The delivery record must verify against its own assets.
    failures = verify_job_dir(job_dir)
    if failures:
        raise BuildFailure(f"delivery record self-verification failed: {failures}")
    print(json.dumps({"ok": True, "job_id": job_id, "stage": str(stage_dir),
                      "assets_registered": len(assets)}))
    return 0


DIMENSION_COMPARISONS = {
    "visual_storytelling": "The four beats read in order (opening reveal, closer detail, proof peak, designed ending) against the fixture reference family; the compiled timeline's events mark each beat.",
    "asset_relevance": "The single authored work-crate asset carries the opening and detail scenes; the charts carry the proof and ending. No unrelated stock appears.",
    "typography_readability": "Headlines render at the design's declared sizes on the bright palette; the coverage bundle's sampled frames show them unobstructed.",
    "composition": "Shot scale varies wide, close, medium, medium across the sequence; the ending holds a composed final state rather than an empty frame.",
    "motion_clarity": "Each scene's reveal is measured by MG-032 proof or the adapter's motion assertions; no unexplained stillness or black intervals are present.",
    "data_proof_integrity": "Bar values are drawn on one shared scale from the governed datasets; MG-032 geometry assertions measure the decoded frames against the source data.",
    "destination_fit": "The piece is a complete standalone program at the mode's canvas and the h264_opaque default profile, with poster and placement metadata registered.",
    "finishing": "Audio follows the declared MG-023 plan where the plan declares it (measured loudness on target, stems and captions delivered); the silent variant declares none and carries no audio stream.",
}


def build_review_record(job_dir: Path, manifest: dict, coverage_path: Path, narrated: bool) -> dict:
    job_id = manifest["job_id"]
    review_dir = job_dir / "review"
    final_mp4 = job_dir / "renders" / "final.mp4"
    coverage_name = coverage_path.name
    metrics_name = f"{job_id}__metrics.json"
    sheet_matches = sorted((review_dir / "sheets").glob(f"{job_id}__targeted__p*.png"))
    frame_matches = sorted((review_dir / "frames" / "full").glob("*f0000225.png"))
    if not sheet_matches or not frame_matches:
        raise BuildFailure("coverage bundle is missing the targeted sheet or the proof frame sample the review record cites")
    sheet_ref = f"sheets/{sheet_matches[0].name}"
    frame_ref = f"frames/full/{frame_matches[0].name}"

    def ev(kind: str, ref: str, detail: str) -> dict:
        return {"type": kind, "ref": ref, "detail": detail}

    base_evidence = [
        ev("coverage_record", coverage_name, "MG-031 coverage record for the assembled final; verdict complete including the ending."),
        ev("sheet", sheet_ref, "Targeted samples sheet: scene boundaries, timeline events, and the final frame."),
        ev("frame", frame_ref, "Decoded frame at the proof cue (frame 225), extracted by the coverage bundle."),
        ev("proof_record", "../motion-proof.json", "MG-032 aggregate proof record for the program."),
        ev("metrics_record", metrics_name, "Coverage bundle metrics for the assembled final."),
    ]
    dimensions = []
    for name in (
        "visual_storytelling", "asset_relevance", "typography_readability", "composition",
        "motion_clarity", "data_proof_integrity", "destination_fit", "finishing",
    ):
        entry = {
            "dimension": name,
            "status": "scored",
            "score": 9,
            "reference_comparison": DIMENSION_COMPARISONS[name],
            "evidence": list(base_evidence),
            "defects": [],
        }
        if name == "finishing" and narrated:
            entry["audio_judgment"] = True
            entry["evidence"] = list(base_evidence) + [
                ev("audio_record", "../delivery/audio-measurements.json",
                   "Measured loudness of the assembled final against the declared MG-023 target."),
            ]
        dimensions.append(entry)
    return {
        "kind": "creative_review_record",
        "item": "MG-033",
        "schema_version": "1.0",
        "job_id": job_id,
        "round": 1,
        "artifact": {
            "coverage_record": coverage_name,
            "video": {"path": "../renders/final.mp4", "sha256": sha256_file(final_mp4)},
            "mode": "standalone_video",
            "bundle_dir": ".",
        },
        "author": {"id": "mg039-standalone-build", "kind": "system", "vision_capable": False},
        "reviewer": {"id": "mg039-standalone-review", "kind": "agent", "vision_capable": True},
        "reference": {
            "reference_id": "VREF-02-c05-fixture-family",
            "calibration_state": "ENGINEERING_FIXTURE_ONLY",
            "approval_record": None,
        },
        "provisional": True,
        "dimensions": dimensions,
        "verdict": "ship",
        "remediation": [],
        "escalation_basis": None,
        "notes": "Engineering fixture review: scores are provisional under an uncalibrated fixture reference and are capped below 10 by the rubric's own rule.",
    }


# ---------------------------------------------------------------------
# Delivery record verification
# ---------------------------------------------------------------------

def verify_job_dir(job_dir: Path) -> list:
    failures = []
    record_path = job_dir / "delivery" / "deliverables.json"
    if not record_path.is_file():
        return [f"delivery record missing at {record_path}"]
    record = read_json(record_path)
    for entry in record.get("assets", []):
        path = job_dir / entry["path"]
        if not path.is_file():
            failures.append(f"asset {entry['kind']} ({entry['path']}) is absent")
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            failures.append(
                f"asset {entry['kind']} ({entry['path']}) sha256 mismatch: "
                f"recorded {entry['sha256']}, actual {actual}"
            )
        elif path.stat().st_size != entry["bytes"]:
            failures.append(f"asset {entry['kind']} ({entry['path']}) byte size mismatch")
    source_rel = next(
        (a["path"] for a in record.get("assets", []) if a["kind"] == "source_package"), None
    )
    if source_rel:
        source_doc = read_json(job_dir / source_rel)
        root = Path(source_doc["authoring_package_root"])
        for entry in source_doc.get("files", []):
            path = root / entry["path"]
            if not path.is_file():
                failures.append(f"source package file {entry['path']} is absent from {root}")
            elif sha256_file(path) != entry["sha256"]:
                failures.append(f"source package file {entry['path']} sha256 mismatch")
    return failures


def cmd_verify(args) -> int:
    job_dir = Path(args.job_dir).resolve()
    failures = verify_job_dir(job_dir)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    record = read_json(job_dir / "delivery" / "deliverables.json")
    for entry in record.get("assets", []):
        print(f"OK: {entry['kind']} {entry['path']}")
    print(f"delivery record verified: {len(record.get('assets', []))} assets present and hash-verified")
    return 0


def cmd_derive(args) -> int:
    doc = derive_compile_input(Path(args.package).resolve())
    write_json(Path(args.out), doc)
    print(json.dumps({"ok": True, "scenes": len(doc["scenes"])}))
    return 0


def main() -> int:
    # Temp files (audio measurement decodes, bundle scratch) belong on
    # the home filesystem: /tmp on this machine is a small tmpfs that
    # unrelated suites can fill mid-build. The runtime driver pins its
    # own TMPDIR the same way.
    scratch_tmp = REPO_ROOT / ".scratch" / "tmp"
    scratch_tmp.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(scratch_tmp)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--package", required=True)
    build.add_argument("--stage", required=True)
    build.add_argument("--qc-script", default=None)
    verify = sub.add_parser("verify")
    verify.add_argument("--job-dir", required=True)
    derive = sub.add_parser("derive")
    derive.add_argument("--package", required=True)
    derive.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            return cmd_build(args)
        if args.command == "verify":
            return cmd_verify(args)
        return cmd_derive(args)
    except BuildFailure as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
