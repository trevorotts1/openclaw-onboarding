#!/usr/bin/env python3
"""Skill 72 assembly (MG-022): the tested assembly implementation.

assemble.sh is a thin compatibility wrapper around this module. The
pre-repair shell implementation is reproduced defect by defect in
tests/evidence/mg022/repro/; this module is its replacement.

Design rules (directive MG-022, consuming the MG-021 compiled plan):

- Placement comes from the compiled timeline (timeline.json plus its
  sidecar), never from duration arithmetic here. Scene order, placed
  ranges and source ranges are read from the plan; overlap lengths
  come from the sidecar handles. A mismatch between media and plan is
  an assembly failure with the plan as the reference.
- Every ffmpeg input is registered once in an InputRegistry, which
  assigns the actual input index. Filter graphs reference streams
  only through registry indexes, so the audio-index defect of the old
  script (audio addressed by position in an audio-only list while
  segment inputs occupied the low indexes) cannot recur.
- Every filter chain terminates in a valid filter with an explicit
  output label, including the single-scene case.
- Streams reused across branches (the narration stem feeding both
  the mix and the sidechain key) are split explicitly with asplit.
- Durations are enforced by construction (trims and apad to the
  plan's frame and sample totals) and then verified by probing the
  output. -shortest is never used: it derives the output length from
  the shortest stream instead of from the plan, which is how the old
  script concealed its drift.
- ffmpeg runs as an argument array with a checked return code; its
  stderr is retained in the workdir log. Failures are reported as a
  structured JSON finding on stderr, never as a traceback.

Mixing POLICY is MG-023's layer (scripts/audio_policy.py, documented
in references/audio-policy.md). Audio sources are resolved ONCE in
job_from_plan by audio_policy.resolve_audio_plan, from the compiled
timeline's audio_owner (none / parent / self, named none /
inherited / own as policy modes) plus the media registry; the
resolved plan (job["audio_plan"]) is the only audio input the graph
builder, the loudness finish, and output verification consume.
Nothing re-reads the registry or a manifest for audio after
resolution. Own-mode mixes (the only independent final mixes) are
finished with measured loudnorm and verified on the encoded output:
loudness on target, no clipping, final narration present at its
planned end, the chosen score audible in narration-free sections;
own-mode stems are preserved as WAVs in the workdir. One signal-path
rule predates the policy layer and stays fixed: when ducking
applies, the sidechain key is the narration stem, not the whole mix
(the old script ducked from voiceover plus SFX together).

Modes:

  Plan mode (the production path):
    assemble.py --plan PLAN.json [--sidecar SIDECAR.json]
                --media MEDIA.json --out OUT.mp4 [--workdir DIR]
    PLAN.json is the canonical MG-021 timeline, or a combined
    document {"timeline": ..., "sidecar": ...}. Media paths in
    MEDIA.json resolve relative to the media file's directory.

  Legacy bridge mode (what assemble.sh invokes):
    assemble.py --legacy --manifest M --workdir W --voiceover V
                --out O [--score S] [--beats B] [--sfx-dir D]
    Accepts the pre-V2 manifest shape and builds the plan-shaped job
    in memory (fixed 0.5s fades, the historical bridge rule),
    resolving music and SFX exactly once. Two deliberate corrections
    over the old script, both directive-mandated and documented in
    references/assembly.md: a voiceover longer than the compiled
    picture fails instead of being cut by -shortest, and the
    synthesized score is actually mixed (the old script re-read the
    manifest after synthesis and silently discarded it). The legacy
    loudnorm finish (-14 LUFS) is preserved in this mode only.

Exit codes: 0 ok; 1 internal error; 2 usage; 3 input missing;
4 plan invalid or media/plan mismatch; 5 ffmpeg failed;
6 output verification failed.
"""

import argparse
import fractions
import hashlib
import importlib.util
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
import traceback

SAMPLE_RATE = 48000

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_PLAN = 4
EXIT_FFMPEG = 5
EXIT_VERIFY = 6


class AssembleError(Exception):
    """A structured assembly failure: JSON finding, no traceback."""

    def __init__(self, code, message, exit_code=EXIT_INTERNAL,
                 mg_category=None, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.mg_category = mg_category
        self.details = details

    def finding(self):
        out = {"status": "error", "code": self.code, "message": self.message}
        if self.mg_category:
            out["mg_category"] = self.mg_category
        if self.details:
            out["details"] = self.details
        return out


def _load_audio_policy():
    """MG-023's policy layer lives beside this module. Load it by
    path so assemble.py works both as a script (its own directory is
    then on sys.path) and when a test loads this file by path."""
    try:
        import audio_policy
        return audio_policy
    except ImportError:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "audio_policy.py")
        spec = importlib.util.spec_from_file_location("audio_policy", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


audio_policy = _load_audio_policy()


def call_policy(fn, *args, **kwargs):
    """Run an audio_policy function, translating its errors into
    this module's structured finding type (same code, same exit,
    Section 16.9 category preserved)."""
    try:
        return fn(*args, **kwargs)
    except audio_policy.AudioPolicyError as exc:
        raise AssembleError(exc.code, exc.message, exc.exit_code,
                            mg_category=exc.mg_category, **exc.details)


def round_half_up(x):
    return int(math.floor(x + 0.5))


# --------------------------------------------------------------------
# Subprocess helpers
# --------------------------------------------------------------------

def run_checked(argv, log_path=None, label="subprocess"):
    """Run an argument array; on failure raise a structured error and
    keep the child's stderr in log_path (when given)."""
    if log_path:
        with open(log_path, "a") as log:
            log.write("\n=== %s ===\n%s\n" % (label, shlex.join(argv)))
            log.flush()
            proc = subprocess.run(argv, stdout=log, stderr=log)
    else:
        proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = ""
        if log_path and os.path.exists(log_path):
            with open(log_path, errors="replace") as f:
                tail = f.read()[-2000:]
        elif proc.stderr:
            tail = proc.stderr[-2000:]
        raise AssembleError(
            "ASSEMBLE_FFMPEG_FAILED",
            "%s failed with exit code %d" % (label, proc.returncode),
            EXIT_FFMPEG, log=log_path, stderr_tail=tail)
    return proc


def ffprobe_json(ffprobe, path, extra=()):
    argv = [ffprobe, "-v", "error", "-show_streams", "-show_format",
            "-of", "json"] + list(extra) + [path]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssembleError("ASSEMBLE_PROBE_FAILED",
                            "ffprobe failed on %s" % path, EXIT_INPUT,
                            stderr=proc.stderr[-1000:])
    return json.loads(proc.stdout)


def probe_media(ffprobe, path):
    """Facts about one media file: video geometry/rate/frames, audio
    sample length at the plan rate."""
    info = ffprobe_json(ffprobe, path)
    out = {"path": path}
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fmt_dur = float(info.get("format", {}).get("duration", 0.0))
    if v:
        rate = fractions.Fraction(v.get("avg_frame_rate", "0/1"))
        out["width"] = v["width"]
        out["height"] = v["height"]
        out["fps"] = float(rate) if rate else 0.0
        if v.get("nb_frames"):
            out["frames"] = int(v["nb_frames"])
        else:
            out["frames"] = round_half_up(fmt_dur * out["fps"])
    if a:
        dur = float(a.get("duration", fmt_dur))
        out["audio_samples"] = round_half_up(dur * SAMPLE_RATE)
        out["audio_rate"] = int(a.get("sample_rate", 0))
    return out


# --------------------------------------------------------------------
# Input registry: the single authority on ffmpeg input indexes
# --------------------------------------------------------------------

class InputRegistry:
    """Registers every ffmpeg input in order and hands out the actual
    input index. Filter graphs are built exclusively from these
    indexes, so a stream can never be addressed by a position in some
    other list (the old script's audio-index defect)."""

    def __init__(self):
        self.entries = []

    def add(self, kind, ident, path, pre_args=()):
        idx = len(self.entries)
        self.entries.append({"index": idx, "kind": kind, "id": ident,
                             "path": path, "pre_args": list(pre_args)})
        return idx

    def argv(self):
        out = []
        for e in self.entries:
            out += e["pre_args"] + ["-i", e["path"]]
        return out

    def record(self):
        return [dict(e) for e in self.entries]


# --------------------------------------------------------------------
# Job model: the normalized shape both front-ends produce and the
# graph builder consumes. Times are integer frames and integer
# samples at SAMPLE_RATE throughout.
# --------------------------------------------------------------------

def empty_job(job_id):
    return {
        "job_id": job_id,
        "fps": 30,
        "total_frames": 0,
        "total_samples": 0,
        "canvas": {"width": 0, "height": 0},
        "scenes": [],      # {id, path, placed_start, placed_end, source_start, source_end}
        "handles": [],     # {from, to, frames}
        "narration": [],   # {id, path, start_sample, end_sample}
        "music": None,     # {path}
        "sfx": [],         # {id, path, sample, file_samples}
        "mix": {"musicVolume": 1.0, "ducking": None},
        "audio_plan": None,  # MG-023 resolved audio plan (plan mode)
        "audio_expected": False,
        "mode": "plan",
    }


def handle_frames(job, from_id, to_id):
    for h in job["handles"]:
        if h["from"] == from_id and h["to"] == to_id:
            return h["frames"]
    return 0


# --------------------------------------------------------------------
# Plan mode: load and validate the compiled plan plus media registry
# --------------------------------------------------------------------

def load_json_file(path, what):
    if not os.path.exists(path):
        raise AssembleError("ASSEMBLE_INPUT_MISSING",
                            "%s not found: %s" % (what, path), EXIT_INPUT)
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise AssembleError("ASSEMBLE_PLAN_INVALID",
                            "%s is not valid JSON: %s" % (what, exc), EXIT_PLAN)


def synthesize_score_once(media_dir, entry, total_samples, ffprobe):
    """Execute the resolved plan's synthesized-score decision
    exactly once. Synthesis is deterministic (seeded), so an
    identical prior synthesis already in the media package is
    reused, never rewritten and never silently replaced."""
    gen_dir = os.path.join(media_dir, "generated")
    os.makedirs(gen_dir, exist_ok=True)
    score_path = os.path.join(gen_dir, "score.wav")
    params_path = os.path.join(gen_dir, "score-params.json")
    total_seconds = total_samples / SAMPLE_RATE
    if os.path.exists(score_path) and os.path.exists(params_path):
        try:
            params = load_json_file(params_path, "score params")
        except AssembleError:
            params = {}
        probe = probe_media(ffprobe, score_path)
        if (params.get("bpm") == entry["bpm"]
                and params.get("seed") == entry["seed"]
                and abs(probe.get("audio_samples", -1) / SAMPLE_RATE
                        - total_seconds) < 0.05):
            return score_path
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    run_checked([sys.executable, os.path.join(scripts_dir, "synth-score.py"),
                 "--bpm", str(entry["bpm"]),
                 "--duration", str(total_seconds),
                 "--seed", str(entry["seed"]),
                 "--outdir", gen_dir],
                label="synth-score")
    return score_path


def job_from_plan(plan_path, sidecar_path, media_path, ffprobe):
    plan_doc = load_json_file(plan_path, "plan")
    if "timeline" in plan_doc:
        timeline, sidecar = plan_doc["timeline"], plan_doc.get("sidecar")
        if sidecar is None and sidecar_path:
            sidecar = load_json_file(sidecar_path, "sidecar")
    else:
        timeline = plan_doc
        sidecar = load_json_file(sidecar_path, "sidecar") if sidecar_path else None
    if sidecar is None:
        raise AssembleError("ASSEMBLE_PLAN_INVALID",
                            "no sidecar: pass a combined plan document or --sidecar",
                            EXIT_PLAN)
    media = load_json_file(media_path, "media registry")
    media_dir = os.path.dirname(os.path.abspath(media_path))

    def media_file(rel):
        p = rel if os.path.isabs(rel) else os.path.join(media_dir, rel)
        if not os.path.exists(p):
            raise AssembleError("ASSEMBLE_INPUT_MISSING",
                                "media file not found: %s" % p, EXIT_INPUT)
        return p

    fps = timeline["fps"]
    if sidecar["fps"] != fps or sidecar["total_frames"] != timeline["total_frames"]:
        raise AssembleError("ASSEMBLE_PLAN_INCONSISTENT",
                            "timeline and sidecar disagree on fps or total_frames",
                            EXIT_PLAN)
    total_frames = timeline["total_frames"]
    total_samples = sidecar["total_samples"]
    if total_samples != total_frames * SAMPLE_RATE // fps:
        raise AssembleError("ASSEMBLE_PLAN_INCONSISTENT",
                            "sidecar total_samples does not match total_frames at %d Hz"
                            % SAMPLE_RATE, EXIT_PLAN)

    job = empty_job(timeline["job_id"])
    job["fps"] = fps
    job["total_frames"] = total_frames
    job["total_samples"] = total_samples
    job["canvas"] = media["canvas"]

    side_scenes = {s["id"]: s for s in sidecar["scenes"]}
    media_scenes = {s["id"]: s for s in media.get("scenes", [])}
    for ts in timeline["scenes"]:
        sid = ts["id"]
        if sid not in media_scenes:
            raise AssembleError("ASSEMBLE_PLAN_INCONSISTENT",
                                "scene %s has no media registry entry" % sid, EXIT_PLAN)
        if sid not in side_scenes:
            raise AssembleError("ASSEMBLE_PLAN_INCONSISTENT",
                                "scene %s missing from sidecar" % sid, EXIT_PLAN)
        ss = side_scenes[sid]
        if (ss["placedRange"]["startFrame"] != ts["start_frame"]
                or ss["placedRange"]["endFrameExclusive"] != ts["end_frame_exclusive"]
                or ss["sourceRange"]["startFrame"] != ts["source_start_frame"]):
            raise AssembleError("ASSEMBLE_PLAN_INCONSISTENT",
                                "scene %s placed/source ranges disagree between "
                                "timeline and sidecar" % sid, EXIT_PLAN)
        path = media_file(media_scenes[sid]["path"])
        probe = probe_media(ffprobe, path)
        src_start = ss["sourceRange"]["startFrame"]
        src_end = ss["sourceRange"]["endFrameExclusive"]
        if probe["frames"] - src_start < src_end - src_start:
            raise AssembleError(
                "ASSEMBLE_MEDIA_SHORTER_THAN_PLAN",
                "segment %s holds %d frames from its start; the plan consumes "
                "source frames [%d, %d)" % (sid, probe["frames"], src_start, src_end),
                EXIT_PLAN)
        job["scenes"].append({
            "id": sid, "path": path,
            "placed_start": ts["start_frame"],
            "placed_end": ts["end_frame_exclusive"],
            "source_start": src_start, "source_end": src_end,
            "probe": probe,
        })

    job["handles"] = [{"from": h["fromSceneId"], "to": h["toSceneId"],
                       "frames": h["frames"]} for h in sidecar["handles"]]

    media_narr = {n["id"]: n for n in media.get("narration", [])}
    job["warnings"] = []
    for seg in sidecar["narration"]:
        if seg["id"] not in media_narr:
            raise AssembleError("ASSEMBLE_PLAN_INCONSISTENT",
                                "narration %s has no media registry entry" % seg["id"],
                                EXIT_PLAN)
        path = media_file(media_narr[seg["id"]]["path"])
        probe = probe_media(ffprobe, path)
        want = seg["endSampleExclusive"] - seg["startSample"]
        have = probe.get("audio_samples", 0)
        if have < want - 512:
            raise AssembleError(
                "ASSEMBLE_NARRATION_SHORTER_THAN_PLAN",
                "narration %s file holds about %d samples; the plan places "
                "%d" % (seg["id"], have, want), EXIT_PLAN)
        if have < want:
            job["warnings"].append(
                "narration %s is %d samples short of its placed range; "
                "the tail is silence" % (seg["id"], want - have))
        job["narration"].append({
            "id": seg["id"], "path": path,
            "start_sample": seg["startSample"],
            "end_sample": seg["endSampleExclusive"],
        })

    media_sfx = {x["id"]: x for x in media.get("sfx", [])}
    for cue in sidecar["sfx"]:
        if cue["id"] not in media_sfx:
            raise AssembleError("ASSEMBLE_PLAN_INCONSISTENT",
                                "sfx %s has no media registry entry" % cue["id"],
                                EXIT_PLAN)
        path = media_file(media_sfx[cue["id"]]["path"])
        probe = probe_media(ffprobe, path)
        job["sfx"].append({
            "id": cue["id"], "path": path, "sample": cue["sample"],
            "file_samples": probe.get("audio_samples", 0),
        })

    # MG-023: resolve the audio ONCE, here, through the policy
    # layer, from the compiled plan's ownership declaration plus the
    # media registry. The resolved plan below is the only audio
    # input the graph builder, the loudness finish, and output
    # verification consume; nothing re-reads the registry or a
    # manifest for audio after this point. (The old shell script's
    # D-ASSEMBLE-MUSIC-RESET was exactly such a re-read, discarding
    # the resolved score; the legacy bridge below already resolves
    # once, and this is the plan-mode resolution it was missing.)
    audio_plan = call_policy(
        audio_policy.resolve_audio_plan,
        timeline.get("audio_owner"),
        [n["id"] for n in job["narration"]],
        [x["id"] for x in job["sfx"]],
        media)
    job["audio_plan"] = audio_plan
    for excl in audio_plan["exclusions"]:
        job["warnings"].append(
            "%s: %s" % (excl["code"], excl["reason"]))
    if audio_plan["music"]:
        entry = audio_plan["music"]
        if entry["kind"] == "supplied":
            job["music"] = {"path": media_file(entry["path"])}
        else:  # synthesized: an option, executed exactly once, here
            entry["path"] = synthesize_score_once(
                media_dir, entry, total_samples, ffprobe)
            job["music"] = {"path": entry["path"]}
    job["mix"] = {"musicVolume": audio_plan["mix"]["musicVolume"],
                  "ducking": audio_plan["mix"]["ducking"]}
    job["audio_expected"] = bool(job["narration"] or job["sfx"] or job["music"])

    # Own mode only: a clipped source fails by name at load instead
    # of being laundered through loudness normalization later.
    if audio_plan["mode"] == audio_policy.MODE_OWN:
        sources = ([("narration", n["id"], n["path"]) for n in job["narration"]]
                   + [("sfx", x["id"], x["path"]) for x in job["sfx"]]
                   + ([("music", "music", job["music"]["path"])]
                      if job["music"] else []))
        job["audio_sources_qc"] = {}
        for kind, ident, path in sources:
            samples = call_policy(audio_policy.decode_pcm, "ffmpeg", path)
            report = audio_policy.clipping_report(samples)
            job["audio_sources_qc"]["%s:%s" % (kind, ident)] = report
            if report["clipped"]:
                raise AssembleError(
                    "ASSEMBLE_AUDIO_CLIPPING",
                    "%s source %s is clipped (peak %.2f dBFS, fraction "
                    "%.4f of samples at full scale); refusing to "
                    "normalize a clipped source into the mix"
                    % (kind, ident, report["peakDbfs"],
                       report["fullScaleRatio"]),
                    EXIT_VERIFY, mg_category="MG_QC_FAILED",
                    source=path, **report)
    job["media_provenance"] = {
        "syntheticSegments": bool(media.get("syntheticSegments")),
        "engines": {s["id"]: s.get("engine") for s in media.get("scenes", [])},
    }
    return job


# --------------------------------------------------------------------
# Filter graph construction
#
# The builder is a pure function of the job plus the registry: it
# reads registry indexes but never touches the filesystem, so unit
# tests can assert on the exact graph. Inputs are registered by the
# caller (run_assembly) in the same deterministic order the builder
# expects: scenes in plan order, narration, music, SFX, silence
# canvas last; register_inputs() below is the single place that
# order lives.
# --------------------------------------------------------------------

def sec(frames, fps):
    return "%.6f" % (frames / fps)


def register_inputs(job, registry):
    idx = {}
    for s in job["scenes"]:
        idx[("scene", s["id"])] = registry.add("scene", s["id"], s["path"])
    for n in job["narration"]:
        idx[("narration", n["id"])] = registry.add("narration", n["id"], n["path"])
    if job["music"]:
        idx[("music", "music")] = registry.add("music", "music", job["music"]["path"])
    for x in job["sfx"]:
        idx[("sfx", x["id"])] = registry.add("sfx", x["id"], x["path"])
    placements = ([n for n in job["narration"] if n["start_sample"] > 0]
                  + [x for x in job["sfx"] if x["sample"] > 0])
    if placements:
        total_sec = job["total_samples"] / SAMPLE_RATE
        idx[("canvas", "silence")] = registry.add(
            # anullsrc accepts only the short option names cl/r.
            "canvas", "silence", "anullsrc=cl=stereo:r=%d" % SAMPLE_RATE,
            pre_args=["-f", "lavfi", "-t", "%.6f" % total_sec])
        idx["canvas_parts"] = len(placements)
    return idx


def build_filter_complex(job, idx):
    parts = []
    W, H, fps = job["canvas"]["width"], job["canvas"]["height"], job["fps"]

    # Video: normalize each segment (trim to the plan's source range,
    # dimensions, fps, timebase, pixel format), then join per plan.
    for i, s in enumerate(job["scenes"]):
        k = idx[("scene", s["id"])]
        dur = s["source_end"] - s["source_start"]
        parts.append(
            "[%d:v]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS,"
            "scale=%d:%d,fps=%d,settb=AVTB,format=yuv420p[vs%d]"
            % (k, s["source_start"], s["source_end"], W, H, fps, i))
        assert dur == s["placed_end"] - s["placed_start"], "compiler invariant"

    current = "[vs0]"
    cursor = job["scenes"][0]["placed_end"] - job["scenes"][0]["placed_start"]
    for j in range(1, len(job["scenes"])):
        prev, nxt = job["scenes"][j - 1], job["scenes"][j]
        overlap = handle_frames(job, prev["id"], nxt["id"])
        label = "[vx%d]" % j
        if overlap > 0:
            offset = (cursor - overlap) / fps
            parts.append("%s[vs%d]xfade=transition=fade:duration=%s:offset=%.6f%s"
                         % (current, j, sec(overlap, fps), offset, label))
            cursor = cursor - overlap + (nxt["placed_end"] - nxt["placed_start"])
        else:
            parts.append("%s[vs%d]concat=n=2:v=1:a=0%s" % (current, j, label))
            cursor = cursor + (nxt["placed_end"] - nxt["placed_start"])
        current = label
    parts.append("%strim=end_frame=%d,setpts=PTS-STARTPTS,format=yuv420p[vout]"
                 % (current, job["total_frames"]))

    if not job["audio_expected"]:
        return ";".join(parts), False

    # Audio: build placed stems at sample accuracy, then mix.
    total = job["total_samples"]

    def place(src_label, start, length, tmp, out):
        """Trim a source to length samples, place it at start on the
        plan's sample grid over the silence canvas."""
        chain = ("%saresample=%d,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 "atrim=start_sample=0:end_sample=%d,apad=whole_dur=%.6f[%s]"
                 % (src_label, SAMPLE_RATE, length, total / SAMPLE_RATE, tmp))
        if start > 0:
            cv = "[%d:a]" % idx[("canvas", "silence")]
            return [chain,
                    "%satrim=start_sample=0:end_sample=%d[cvp_%s]" % (cv, start, out),
                    "[cvp_%s][%s]concat=n=2:v=0:a=1,"
                    "atrim=start_sample=0:end_sample=%d[%s]" % (out, tmp, total, out)]
        return [chain,
                "[%s]atrim=start_sample=0:end_sample=%d[%s]" % (tmp, total, out)]

    stems = []  # (role, label) in mix order: narration, music, sfx

    if job["narration"]:
        seg_labels = []
        for j, n in enumerate(job["narration"]):
            k = idx[("narration", n["id"])]
            length = n["end_sample"] - n["start_sample"]
            parts += place("[%d:a]" % k, n["start_sample"], length,
                           "nt%d" % j, "np%d" % j)
            seg_labels.append("[np%d]" % j)
        if len(seg_labels) == 1:
            parts.append("%sanull[narr]" % seg_labels[0])
        else:
            parts.append("%samix=inputs=%d:normalize=0[narr]"
                         % ("".join(seg_labels), len(seg_labels)))
        stems.append(("narration", "[narr]"))

    if job["music"]:
        k = idx[("music", "music")]
        vol = job["mix"]["musicVolume"]
        chain = ("[%d:a]aresample=%d,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 "apad=whole_dur=%.6f,atrim=start_sample=0:end_sample=%d"
                 % (k, SAMPLE_RATE, total / SAMPLE_RATE, total))
        if vol != 1.0:
            chain += ",volume=%.6f" % vol
        parts.append(chain + "[mus]")
        stems.append(("music", "[mus]"))

    if job["sfx"]:
        cue_labels = []
        for j, x in enumerate(job["sfx"]):
            k = idx[("sfx", x["id"])]
            length = min(x["file_samples"], total - x["sample"])
            parts += place("[%d:a]" % k, x["sample"], length,
                           "st%d" % j, "sp%d" % j)
            cue_labels.append("[sp%d]" % j)
        if len(cue_labels) == 1:
            parts.append("%sanull[sfxm]" % cue_labels[0])
        else:
            parts.append("%samix=inputs=%d:normalize=0[sfxm]"
                         % ("".join(cue_labels), len(cue_labels)))
        stems.append(("sfx", "[sfxm]"))

    # Ducking: split the narration stem explicitly so the same stream
    # feeds the mix branch and the sidechain branch; the key is the
    # narration stem only (see module docstring).
    duck = job["mix"].get("ducking")
    if duck and job["music"] and job["narration"]:
        parts.append("[narr]asplit=2[narr_mix][narr_key]")
        parts.append("[mus][narr_key]sidechaincompress=threshold=%s:ratio=%s:"
                     "attack=%s:release=%s[mus_d]"
                     % (duck["threshold"], duck["ratio"],
                        duck["attack"], duck["release"]))
        stems = [(role, "[narr_mix]" if role == "narration"
                  else "[mus_d]" if role == "music" else label)
                 for role, label in stems]

    labels = [label for _, label in stems]
    # MG-023: own-mode assembly preserves stems. Each stem is split
    # once more so the identical signal feeds the mix and its own
    # output; stems are the pre-loudnorm mix ingredients (the music
    # stem is post-ducking, as mixed). Opt-in via job["emit_stems"]
    # so the graph contract for other callers is unchanged; the
    # resulting labels are recorded on job["stem_labels"].
    job["stem_labels"] = {}
    if job.get("emit_stems"):
        tapped = []
        for role, label in stems:
            parts.append("%sasplit=2[%s_stm][stem_%s]"
                         % (label, role, role))
            parts.append("[stem_%s]atrim=start_sample=0:end_sample=%d,"
                         "aresample=%d[stemout_%s]"
                         % (role, total, SAMPLE_RATE, role))
            tapped.append("[%s_stm]" % role)
            job["stem_labels"][role] = "[stemout_%s]" % role
        labels = tapped
    if len(labels) == 1:
        parts.append("%sanull,atrim=start_sample=0:end_sample=%d,"
                     "aresample=%d[aout]" % (labels[0], total, SAMPLE_RATE))
    else:
        parts.append("%samix=inputs=%d:normalize=0,"
                     "atrim=start_sample=0:end_sample=%d,aresample=%d[aout]"
                     % ("".join(labels), len(labels), total, SAMPLE_RATE))
    # Filter labels are single-use: when the caller needs the mix
    # itself as PCM (the measured-loudnorm finish), split [aout]
    # once and record which label is the deliverable's.
    job["aout_label"] = "[aout]"
    job["mix_label"] = None
    if job.get("emit_mix"):
        parts.append("[aout]asplit=2[aout_mp4][aout_mix]")
        job["aout_label"] = "[aout_mp4]"
        job["mix_label"] = "[aout_mix]"
    return ";".join(parts), True


# --------------------------------------------------------------------
# Output verification: the probe record every acceptance rests on
# --------------------------------------------------------------------

def last_frame_sha256(ffmpeg, path, total_frames):
    filt = "select='eq(n\\,%d)'" % (total_frames - 1)
    proc = subprocess.run([ffmpeg, "-v", "error", "-i", path, "-vf", filt,
                           "-frames:v", "1", "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"],
                          capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise AssembleError("ASSEMBLE_VERIFY_FAILED",
                            "could not decode the last frame of %s" % path,
                            EXIT_VERIFY, stderr=proc.stderr.decode(errors="replace")[-500:])
    return hashlib.sha256(proc.stdout).hexdigest(), len(proc.stdout)


def verify_output(ffmpeg, ffprobe, out_path, job):
    info = ffprobe_json(ffprobe, out_path, extra=["-count_frames"])
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise AssembleError("ASSEMBLE_VERIFY_FAILED", "output has no video stream",
                            EXIT_VERIFY)
    frames = int(v.get("nb_read_frames") or v.get("nb_frames") or 0)
    stream_map = [{"index": s["index"], "codec_type": s["codec_type"],
                   "codec_name": s["codec_name"],
                   "width": s.get("width"), "height": s.get("height"),
                   "sample_rate": s.get("sample_rate")}
                  for s in info["streams"]]
    record = {
        "output": out_path,
        "expected_frames": job["total_frames"],
        "decoded_frames": frames,
        "duration_seconds": float(info["format"]["duration"]),
        "expected_duration_seconds": job["total_frames"] / job["fps"],
        "stream_map": stream_map,
        "audio_present": a is not None,
    }
    problems = []
    if frames != job["total_frames"]:
        problems.append("decoded %d frames, plan total is %d"
                        % (frames, job["total_frames"]))
    if abs(record["duration_seconds"] - record["expected_duration_seconds"]) > 0.12:
        problems.append("duration %.3fs differs from plan %.3fs by more than 0.12s"
                        % (record["duration_seconds"],
                           record["expected_duration_seconds"]))
    if job["audio_expected"] and a is None:
        problems.append("plan carries audio but the output has no audio stream")
    if not job["audio_expected"] and a is not None:
        problems.append("plan carries no audio but the output has an audio stream")
    sha, nbytes = last_frame_sha256(ffmpeg, out_path, job["total_frames"])
    record["last_frame_sha256"] = sha
    record["last_frame_bytes"] = nbytes
    if problems:
        raise AssembleError("ASSEMBLE_VERIFY_FAILED", "; ".join(problems),
                            EXIT_VERIFY, record=record)
    return record


# --------------------------------------------------------------------
# MG-023 measured audio verification of the ENCODED output. Every
# check measures the file that will actually ship, never the
# requested filter settings. Failures are named QC findings
# (exit 6, Section 16.9 category MG_QC_FAILED).
# --------------------------------------------------------------------

def verify_audio(ffmpeg, out_path, job):
    plan = job["audio_plan"]
    qc = {"mode": plan["mode"]}
    samples = call_policy(audio_policy.decode_pcm, ffmpeg, out_path)

    clip = audio_policy.clipping_report(samples)
    qc["outputClipping"] = clip
    if clip["peakDbfs"] > audio_policy.OUTPUT_CLIP_CEILING_DBFS:
        raise AssembleError(
            "ASSEMBLE_AUDIO_CLIPPING",
            "encoded output peaks at %.2f dBFS, above the %.2f dBFS "
            "ceiling" % (clip["peakDbfs"],
                         audio_policy.OUTPUT_CLIP_CEILING_DBFS),
            EXIT_VERIFY, mg_category="MG_QC_FAILED", **clip)

    if plan.get("loudnessTarget"):
        measured = call_policy(audio_policy.measure_loudness,
                               ffmpeg, out_path, plan["loudnessTarget"])
        verdict = audio_policy.loudness_verdict(measured,
                                                plan["loudnessTarget"])
        qc["loudness"] = verdict
        if not verdict["ok"]:
            raise AssembleError(
                "ASSEMBLE_AUDIO_LOUDNESS_OFF_TARGET",
                "encoded output measures %.2f LUFS integrated and "
                "%.2f dBTP true peak against a target of %.2f LUFS "
                "/ %.2f dBTP (tolerance %.1f LU / %.1f dB)"
                % (measured["integratedLufs"], measured["truePeakDb"],
                   plan["loudnessTarget"]["integratedLufs"],
                   plan["loudnessTarget"]["truePeakDb"],
                   audio_policy.LOUDNESS_TOLERANCE_LU,
                   audio_policy.TRUE_PEAK_TOLERANCE_DB),
                EXIT_VERIFY, mg_category="MG_QC_FAILED", **verdict)

    if job["narration"]:
        spans = {}
        for n in job["narration"]:
            src = call_policy(audio_policy.decode_pcm, ffmpeg, n["path"])
            rep = audio_policy.segment_presence_report(
                samples, src, n["start_sample"], n["end_sample"])
            spans[n["id"]] = rep
            if not rep["present"]:
                raise AssembleError(
                    "ASSEMBLE_AUDIO_NARRATION_MISSING",
                    "narration segment %s is not present in the "
                    "encoded output at its dominant bands (band "
                    "ratio %.3f)" % (n["id"], rep["bandRatio"]),
                    EXIT_VERIFY, mg_category="MG_QC_FAILED",
                    segment=n["id"], **rep)
        qc["narrationSpans"] = spans
        last = max(job["narration"], key=lambda n: n["end_sample"])
        src = call_policy(audio_policy.decode_pcm, ffmpeg, last["path"])
        tail = audio_policy.narration_tail_report(
            samples, src, last["start_sample"], last["end_sample"])
        qc["finalWords"] = {"segment": last["id"], **tail}
        if not tail["presentAtPlannedEnd"]:
            raise AssembleError(
                "ASSEMBLE_AUDIO_FINAL_WORDS_MISSING",
                "the final narration segment %s is missing at its "
                "planned end in the encoded output (source tail "
                "%.2f dBFS, band ratio %.3f)"
                % (last["id"], tail["sourceTailRmsDbfs"],
                   tail["bandRatio"]),
                EXIT_VERIFY, mg_category="MG_QC_FAILED",
                segment=last["id"], **tail)

    if job["music"]:
        src = call_policy(audio_policy.decode_pcm, ffmpeg,
                          job["music"]["path"])
        rep = audio_policy.score_audibility_report(
            samples,
            [(n["start_sample"], n["end_sample"]) for n in job["narration"]],
            job["total_samples"],
            audio_policy.rms_dbfs(src), job["mix"]["musicVolume"])
        qc["scoreAudible"] = rep
        if rep["applicable"] and not rep["audible"]:
            raise AssembleError(
                "ASSEMBLE_AUDIO_SCORE_NOT_AUDIBLE",
                "the chosen score is not audible in the "
                "narration-free window %s (measured %.2f dBFS, "
                "expected about %.2f dBFS)"
                % (rep["windowSeconds"], rep["windowRmsDbfs"],
                   rep["expectedRmsDbfs"]),
                EXIT_VERIFY, mg_category="MG_QC_FAILED", **rep)
    return qc


# --------------------------------------------------------------------
# Assembly driver
# --------------------------------------------------------------------

def run_assembly(job, out_path, workdir, ffmpeg="ffmpeg", ffprobe="ffprobe",
                 finish_loudnorm=False):
    os.makedirs(workdir, exist_ok=True)
    registry = InputRegistry()
    idx = register_inputs(job, registry)
    audio_plan = job.get("audio_plan") or {}
    # MG-023: own-mode plan assembly preserves stems (see
    # build_filter_complex). The legacy bridge keeps its historical
    # single-output shape.
    if audio_plan.get("mode") == audio_policy.MODE_OWN:
        job["emit_stems"] = True
    if audio_plan.get("loudnessTarget"):
        job["emit_mix"] = True
    graph, has_audio = build_filter_complex(job, idx)
    log_path = os.path.join(workdir, "ffmpeg.log")
    with open(os.path.join(workdir, "assemble-graph.txt"), "w") as f:
        f.write(graph + "\n")
    staged = os.path.join(workdir, "assembled.mp4")
    argv = [ffmpeg, "-y"] + registry.argv() + [
        "-filter_complex", graph, "-map", "[vout]"]
    if has_audio:
        argv += ["-map", job.get("aout_label", "[aout]")]
    argv += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(job["fps"])]
    if has_audio:
        argv += ["-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE)]
    argv += [staged]
    stem_paths = {}
    if has_audio and job.get("stem_labels"):
        stems_dir = os.path.join(workdir, "stems")
        os.makedirs(stems_dir, exist_ok=True)
        for role, label in sorted(job["stem_labels"].items()):
            stem_path = os.path.join(stems_dir, role + ".wav")
            argv += ["-map", label, "-c:a", "pcm_s16le", stem_path]
            stem_paths[role] = stem_path
    # When the measured-loudnorm finish will run, also write the
    # mix itself as PCM in the same invocation: loudness is then
    # measured on the mix (not on an AAC decode of it), and the
    # finished audio is encoded to AAC exactly once, from the
    # filtered PCM, so the deliverable keeps the single-encode
    # duration the plan's verification expects.
    mix_wav = None
    if has_audio and audio_plan.get("loudnessTarget"):
        mix_wav = os.path.join(workdir, "mix.wav")
        argv += ["-map", job["mix_label"], "-c:a", "pcm_s16le", mix_wav]
    run_checked(argv, log_path=log_path, label="ffmpeg assemble")
    final = staged
    loudness_input = None
    if finish_loudnorm and has_audio:
        # Legacy bridge only: the historical single-pass finish,
        # preserved as-is (see references/audio-policy.md for the
        # scope judgment).
        normalized = os.path.join(workdir, "normalized.mp4")
        run_checked([ffmpeg, "-y", "-i", staged, "-af",
                     "loudnorm=I=-14:TP=-1:LRA=11", "-c:v", "copy",
                     "-c:a", "aac", "-b:a", "192k", normalized],
                    log_path=log_path, label="ffmpeg loudnorm")
        final = normalized
    elif audio_plan.get("loudnessTarget") and has_audio:
        # MG-023 own mode: MEASURED loudnorm. Measure the mix (the
        # PCM written by the assemble invocation), apply with the
        # measured values, then verify the encoded output in
        # verify_audio; the target is never trusted from the
        # requested settings alone. The sample rate is set
        # explicitly (the legacy pass above leaves loudnorm's
        # resample in place; that quirk is legacy-only now).
        loudness_input = call_policy(audio_policy.measure_loudness,
                                     ffmpeg, mix_wav,
                                     audio_plan["loudnessTarget"])
        normalized = os.path.join(workdir, "normalized.mp4")
        run_checked([ffmpeg, "-y", "-i", staged, "-i", mix_wav,
                     "-map", "0:v:0", "-map", "1:a:0", "-af",
                     audio_policy.loudnorm_apply_filter(
                         loudness_input, audio_plan["loudnessTarget"]),
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                     "-ar", str(SAMPLE_RATE), normalized],
                    log_path=log_path, label="ffmpeg loudnorm (measured)")
        final = normalized
    record = verify_output(ffmpeg, ffprobe, final, job)
    if has_audio and job.get("audio_plan"):
        record["audio_qc"] = verify_audio(ffmpeg, final, job)
        if loudness_input is not None:
            record["audio_qc"]["loudnessInput"] = loudness_input
    if os.path.abspath(final) != os.path.abspath(out_path):
        os.replace(final, out_path)
    record["output"] = out_path
    record["inputs"] = registry.record()
    record["mode"] = job["mode"]
    record["job_id"] = job["job_id"]
    if job.get("audio_plan"):
        record["audio_plan"] = job["audio_plan"]
    if job.get("audio_sources_qc"):
        record["audio_sources_qc"] = job["audio_sources_qc"]
    if stem_paths:
        record["stems"] = stem_paths
    if job.get("warnings"):
        record["warnings"] = job["warnings"]
    if job.get("media_provenance"):
        record["media_provenance"] = job["media_provenance"]
    with open(os.path.join(workdir, "assemble-probe.json"), "w") as f:
        json.dump(record, f, indent=2)
    return record


# --------------------------------------------------------------------
# Legacy bridge: the pre-V2 manifest shape, compiled to the same job
# model. The wrapper (assemble.sh) invokes this mode.
# --------------------------------------------------------------------

LEGACY_FADE_SECONDS = 0.5          # the old script's fixed crossfade
LEGACY_DUCKING = {"threshold": 0.02, "ratio": 8, "attack": 20, "release": 400}
LEGACY_MUSIC_VOLUME = 0.35


def job_from_legacy(manifest_path, workdir, voiceover, out_score, out_beats,
                    sfx_dir, ffmpeg, ffprobe):
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(manifest_path):
        raise AssembleError("ASSEMBLE_INPUT_MISSING",
                            "manifest not found: %s" % manifest_path, EXIT_INPUT)
    if not os.path.exists(voiceover):
        raise AssembleError("ASSEMBLE_INPUT_MISSING",
                            "voiceover not found: %s" % voiceover, EXIT_INPUT)
    manifest = load_json_file(manifest_path, "manifest")
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    tmp = os.path.join(workdir, "legacy-plan")
    os.makedirs(tmp, exist_ok=True)

    # Segments: explicit (scene_id, path, duration) unpacking. The old
    # script passed the tuple itself to ffmpeg; here each field is
    # used for what it is.
    seg_rows = []
    for scene in manifest.get("scenes", []):
        scene_id = scene["id"]
        path = os.path.join(workdir, "scenes", scene_id, scene_id + ".mp4")
        if not os.path.exists(path):
            raise AssembleError("ASSEMBLE_INPUT_MISSING",
                                "segment not found: %s" % path, EXIT_INPUT)
        probe = probe_media(ffprobe, path)
        seg_rows.append((scene_id, path, probe))
    if not seg_rows:
        raise AssembleError("ASSEMBLE_PLAN_INVALID", "manifest names no scenes",
                            EXIT_PLAN)
    fps = int(round(seg_rows[0][2]["fps"])) or 30
    fade_frames = round_half_up(LEGACY_FADE_SECONDS * fps)

    job = empty_job(manifest.get("id", "legacy"))
    job["mode"] = "legacy"
    job["fps"] = fps
    job["canvas"] = {"width": seg_rows[0][2]["width"],
                     "height": seg_rows[0][2]["height"]}

    cursor_end = 0
    for i, (scene_id, path, probe) in enumerate(seg_rows):
        dur_frames = probe["frames"]
        if i == 0:
            start = 0
        else:
            start = cursor_end - fade_frames
            job["handles"].append({"from": seg_rows[i - 1][0], "to": scene_id,
                                    "frames": fade_frames})
        need = (fade_frames if i > 0 else 0) + (fade_frames
                                                if i < len(seg_rows) - 1 else 0)
        if dur_frames <= need:
            raise AssembleError(
                "ASSEMBLE_PLAN_INVALID",
                "segment %s is %d frames; the 0.5s bridge fades need more "
                "than %d" % (scene_id, dur_frames, need), EXIT_PLAN)
        job["scenes"].append({
            "id": scene_id, "path": path, "placed_start": start,
            "placed_end": start + dur_frames, "source_start": 0,
            "source_end": dur_frames, "probe": probe})
        cursor_end = start + dur_frames
    job["total_frames"] = cursor_end
    job["total_samples"] = round_half_up(cursor_end * SAMPLE_RATE / fps)
    spf = SAMPLE_RATE / fps

    # Voiceover: one narration segment starting at frame 0. It must
    # fit the compiled picture; the old script let -shortest cut it.
    vo_probe = probe_media(ffprobe, voiceover)
    vo_samples = vo_probe.get("audio_samples", 0)
    if vo_samples > job["total_samples"]:
        raise AssembleError(
            "ASSEMBLE_NARRATION_EXCEEDS_PICTURE",
            "voiceover is %.2fs but the compiled picture is %.2fs; refusing "
            "to truncate (the old pipeline cut it with -shortest)"
            % (vo_samples / SAMPLE_RATE, job["total_samples"] / SAMPLE_RATE),
            EXIT_PLAN)
    job["narration"].append({"id": "voiceover", "path": voiceover,
                             "start_sample": 0, "end_sample": vo_samples})

    # Music resolution, exactly once (the old script resolved or
    # synthesized a score, then re-read the manifest and threw the
    # synthesized path away).
    music_path = None
    if manifest.get("music_bed"):
        music_path = manifest["music_bed"]
        if not os.path.isabs(music_path):
            music_path = os.path.join(manifest_dir, music_path)
    elif out_score:
        music_path = out_score
    else:
        audio_dir = os.path.join(workdir, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        total_seconds = sum(p["frames"] / fps for _, _, p in seg_rows)
        run_checked([sys.executable, os.path.join(scripts_dir, "synth-score.py"),
                     "--bpm", str(manifest.get("music_bpm", 84)),
                     "--duration", str(total_seconds),
                     "--seed", str(manifest.get("music_seed", 42)),
                     "--outdir", audio_dir],
                    log_path=os.path.join(tmp, "synth.log"), label="synth-score")
        run_checked([sys.executable, os.path.join(scripts_dir, "beat-grid.py"),
                     "--params", os.path.join(audio_dir, "score-params.json"),
                     "--out", out_beats or os.path.join(audio_dir, "beats.json")],
                    log_path=os.path.join(tmp, "synth.log"), label="beat-grid")
        music_path = os.path.join(audio_dir, "score.wav")
    if music_path:
        if not os.path.exists(music_path):
            raise AssembleError("ASSEMBLE_INPUT_MISSING",
                                "music bed not found: %s" % music_path, EXIT_INPUT)
        job["music"] = {"path": music_path}
        job["mix"] = {"musicVolume": LEGACY_MUSIC_VOLUME,
                      "ducking": dict(LEGACY_DUCKING)}

    # SFX: resolve the sound map once, then place each event on the
    # compiled timeline (placed scene start plus the event offset),
    # never on raw accumulated durations.
    synth_sfx = manifest.get("synth_sfx", True)
    if sfx_dir:
        sfx_map = {n: os.path.join(sfx_dir, n + ".wav")
                   for n in ("pop", "click", "whoosh", "thump")
                   if os.path.exists(os.path.join(sfx_dir, n + ".wav"))}
    elif synth_sfx:
        sfx_out = os.path.join(tmp, "sfx")
        run_checked([sys.executable, os.path.join(scripts_dir, "synth-sfx.py"),
                     "--outdir", sfx_out],
                    log_path=os.path.join(tmp, "synth.log"), label="synth-sfx")
        sfx_map = {n: os.path.join(sfx_out, n + ".wav")
                   for n in ("pop", "click", "whoosh", "thump")}
    else:
        sfx_map = {}
        for name, p in manifest.get("sfx", {}).items():
            sfx_map[name] = p if os.path.isabs(p) else os.path.join(manifest_dir, p)
    placed_start = {s["id"]: s["placed_start"] for s in job["scenes"]}
    count = 0
    for scene in manifest.get("scenes", []):
        for ev in scene.get("sfx_events", []):
            name = ev.get("sound", "pop")
            if name not in sfx_map:
                raise AssembleError("ASSEMBLE_INPUT_MISSING",
                                    "sfx sound %r is not in the resolved sfx map"
                                    % name, EXIT_INPUT)
            count += 1
            frame = placed_start[scene["id"]] + round_half_up(
                float(ev.get("at_seconds", 0.0)) * fps)
            probe = probe_media(ffprobe, sfx_map[name])
            job["sfx"].append({
                "id": "sfx%d" % count, "path": sfx_map[name],
                "sample": round_half_up(frame * spf),
                "file_samples": probe.get("audio_samples", 0)})
    job["audio_expected"] = True
    with open(os.path.join(tmp, "job.json"), "w") as f:
        json.dump({k: v for k, v in job.items() if k != "scenes"} |
                  {"scenes": [{k: v for k, v in s.items() if k != "probe"}
                              for s in job["scenes"]]}, f, indent=2)
    return job


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="assemble.py",
        description="Skill 72 assembly (MG-022). See references/assembly.md.")
    p.add_argument("--plan", help="compiled timeline JSON (plan mode)")
    p.add_argument("--sidecar", help="timeline sidecar JSON (plan mode, "
                                     "if the plan file is not combined)")
    p.add_argument("--media", help="media registry JSON (plan mode)")
    p.add_argument("--legacy", action="store_true",
                   help="legacy manifest bridge mode (used by assemble.sh)")
    p.add_argument("--manifest")
    p.add_argument("--voiceover")
    p.add_argument("--score")
    p.add_argument("--beats")
    p.add_argument("--sfx-dir", dest="sfx_dir")
    p.add_argument("--workdir", help="logs, graph and probe record go here")
    p.add_argument("--out", required=True)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    try:
        if args.legacy:
            if not args.manifest or not args.workdir or not args.voiceover:
                raise AssembleError("ASSEMBLE_USAGE",
                                    "--legacy needs --manifest, --workdir and "
                                    "--voiceover", EXIT_USAGE)
            job = job_from_legacy(args.manifest, args.workdir, args.voiceover,
                                  args.score, args.beats, args.sfx_dir,
                                  "ffmpeg", "ffprobe")
            record = run_assembly(job, args.out, args.workdir,
                                  finish_loudnorm=True)
            print("assembled: %s (-14 LUFS)" % args.out)
        else:
            if not args.plan or not args.media:
                raise AssembleError("ASSEMBLE_USAGE",
                                    "plan mode needs --plan and --media "
                                    "(or use --legacy)", EXIT_USAGE)
            workdir = args.workdir or tempfile.mkdtemp(prefix="mg022-assemble-")
            job = job_from_plan(args.plan, args.sidecar, args.media, "ffprobe")
            record = run_assembly(job, args.out, workdir)
            record["workdir"] = workdir
        print(json.dumps({"status": "ok", **record}, indent=2))
        return EXIT_OK
    except AssembleError as exc:
        print(json.dumps(exc.finding(), indent=2), file=sys.stderr)
        return exc.exit_code
    except Exception:  # last resort: still structured, still no traceback dump
        print(json.dumps({"status": "error", "code": "ASSEMBLE_INTERNAL",
                          "message": traceback.format_exc(limit=3)},
                         indent=2), file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
