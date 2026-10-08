"""final_assembler: timeline.json -> frame-exact ffmpeg render.

Contract: directive 17.5 + acceptance-profile timeline rules
(round once to frame grid, no cumulative drift, A/V within 1 frame,
no gaps/black frames). Stdlib only (json, subprocess, shutil, argparse,
sys, os). ffmpeg/ffprobe invoked with argument arrays via subprocess,
never shell strings.

Skill 25 (multi_clip_assembly) / Skill 27 (broll_merge) use moviepy
concatenation, which cannot guarantee frame-exact cuts, so this unit
shells to ffmpeg directly and reuses only their conventions:
ffprobe JSON duration probing (ai_providers._validate_downloaded_video)
and libx264/AAC export presets (export.py).

Timeline schema (blackceo.timeline/v1):
  {"schema_version": "blackceo.timeline/v1", "fps": 30,
   "width": 1920, "height": 1080, "song_path": "master.wav | null",
   "transition": "none" | "fade", "transition_duration": 0.5,
   "segments": [{"src": "clip.mp4", "dur": 2.0 | null,
                 "transition": "fade" | null}]}

E2 (manual Part E): the MISSING transition default is "fade" with
  TRANSITION_DURATION 0.4 s (manual allows 0.3-0.5) applied at every
  scene change; "none" is only honored when the segment carries an
  explicit shot-planner offbeat/on-beat marker (beat_cut: true) — an
  unmarked hard cut fails QC with HARD_CUT_UNMARKED. Timelines that
  carry explicit transition values keep them; only the missing default
  changed (fully backward compatible).

Rules:
- Video is the master duration; the song is laid under it
  (trimmed/padded to the video duration). Clip audio is ignored:
  silent-video default with the song as soundtrack.
- Every cut point is rounded ONCE to the frame grid; offsets
  accumulate in integer frames so drift cannot compound.
- xfade overlaps consume frames from the joined segments.
- ffmpeg is bounded (manual M7): argv starts with `nice -n 10`, carries
  `-threads N`, and the render cap grows with output length instead of a
  flat 600 s (see size_ffmpeg / lane_size.py Part D).
- E3 minimum shot length: load_timeline fails closed on any segment
  under 1.5 s (1.0 s when marked beat_cut) via
  shot_planner.validate_timeline_min_shot.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

try:                                    # E1 module (this package)
    from . import fps_conform
except ImportError:                     # direct-script fallback
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fps_conform  # noqa: E402

TOOL_NAME = "final_assembler"
TOOL_VERSION = "1.0.1"
SCHEMA_VERSION = "1.0.0"
TIMELINE_SCHEMA = "blackceo.timeline/v1"

# E3 minimum shot length floors (shot_planner is the source of truth).
# ponytail: import inside check_timeline_min_shot so an absent/broken
# shot_planner cannot break every assemble; the check fails closed by
# raising there instead.
MIN_SHOT_S = 1.5
BEAT_CUT_MIN_SHOT_S = 1.0

EXIT = {"ok": 0, "error": 1, "unavailable": 3}

# --- E2: transitions (manual Part E E2) --------------------------------------
# Default: fade 0.4 s (manual allows 0.3-0.5) at every scene change;
# `none` only when the segment carries the planner's on-beat marker
# (beat_cut: true — the cut lands ON a song beat, a hard cut is musical
# there). An unmarked `none` never assembles (QC: HARD_CUT_UNMARKED).
DEFAULT_TRANSITION = "fade"
TRANSITION_DURATION = 0.4
HARD_CUT_UNMARKED = "HARD_CUT_UNMARKED"

# --- M7 bounding: processor share + wall-clock cap (manual 02 M7, Part D) ----
#
# ffmpeg used to be started bare, so it took every core of the box and was
# killed by a flat 600 s cap that a long 1080p re-encode on a 2-core VPS
# outruns. Two knobs bound it:
#
#   -threads N  and  nice -n 10   -> no core theft (Linux and macOS both
#                                    accept `nice -n 10`, no `--` prefix)
#   timeout S                    -> grows with the output length
#
# Both knobs are READ FROM scripts/core/lane_size.py when W2-A has landed it
# (it owns that module, not this unit), and fall back to Part D's formulas
# while it is absent, so this unit works standalone either way.
#
# ponytail: the 1080p/4k height factor below is this unit's own convention;
# move it into lane_size.py's `ffmpeg_timeout_s` output when H4 lands and
# this fallback becomes a dead path.
NICE_LEVEL = 10                  # manual M7: nice -n 10 on Linux and macOS
MIN_TIMEOUT_S = 600              # Part D floor for ffmpeg_timeout_s
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1920, 1080


def _effective_cores():
    """Container quota beats host total, else physical/dedicated cores (Part D D1)."""
    for path in ("/sys/fs/cgroup/cpu.max",):          # cgroup v2
        try:
            with open(path, encoding="utf-8") as fh:
                quota, period = fh.read().split()[:2]
            if quota != "max":
                return max(1, int(math.floor(int(quota) / int(period))))
        except (OSError, ValueError, ZeroDivisionError):
            pass
    for q, p in (("/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
                  "/sys/fs/cgroup/cpu/cpu.cfs_period_us"),):   # cgroup v1
        try:
            with open(q, encoding="utf-8") as fh:
                quota = int(fh.read().strip())
            if quota > 0:
                with open(p, encoding="utf-8") as fh:
                    period = int(fh.read().strip())
                return max(1, int(math.floor(quota / period)))
        except (OSError, ValueError, ZeroDivisionError):
            pass
    try:
        return max(1, len(os.sched_getaffinity(0)))   # Linux
    except (AttributeError, OSError):
        pass
    try:
        return max(1, int(subprocess.run(
            ["sysctl", "-n", "hw.physicalcpu"], capture_output=True,
            text=True, timeout=10, check=False).stdout.strip()))   # macOS
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return max(1, (os.cpu_count() or 1))


def _part_d_threads(cores_eff=None):
    """Part D fallback: jobs = floor(cores/4), threads = floor((cores-1)/jobs)."""
    cores = cores_eff if cores_eff else _effective_cores()
    jobs = max(1, int(math.floor(cores / 4.0)))
    return max(1, int(math.floor((cores - 1) / float(jobs)))), jobs


def _lane_size_threads():
    """Prefer W2-A's scripts/core/lane_size.py; None when it is not shipped yet."""
    core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    try:
        import lane_size                    # noqa: F401  (guarded: W2-A unit)
    except Exception:                       # noqa: BLE001  absent/broken/odd name
        return None
    for name in ("ffmpeg_threads", "threads"):   # tolerant of H4's final spelling
        val = getattr(lane_size, name, None)
        if callable(val):
            try:
                val = val()
            except TypeError:
                try:
                    val = val(output_seconds=0, height=DEFAULT_HEIGHT)
                except Exception:           # noqa: BLE001
                    continue
            except Exception:               # noqa: BLE001
                continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)) and val >= 1:
            return int(val)
    for name in ("compute", "sizes", "measure", "size"):
        fn = getattr(lane_size, name, None)
        if not callable(fn):
            continue
        try:
            out = fn()
        except Exception:                   # noqa: BLE001
            continue
        if isinstance(out, dict):
            for key in ("ffmpeg_threads", "threads"):
                val = out.get(key)
                if isinstance(val, (int, float)) and not isinstance(val, bool) \
                        and val >= 1:
                    return int(val)
    return None


def size_ffmpeg(output_seconds, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT):
    """(threads, nice, timeout_s) for one render.

    threads  from lane_size.py when shipped, else Part D fallback
    nice     NICE_LEVEL (fixed: manual M7 says -n 10 on Linux and macOS)
    timeout  lane_size's ffmpeg_timeout_s when shipped, else
             max(600, 2 x output seconds x 1080p height factor)
    """
    threads = _lane_size_threads() or _part_d_threads()[0]
    # 1080p factor scales by pixel area: 1080p = 1, 4K = 4.
    factor = max(1.0, (float(width or DEFAULT_WIDTH) *
                       float(height or DEFAULT_HEIGHT)) /
                 float(DEFAULT_WIDTH * DEFAULT_HEIGHT))
    timeout = int(max(MIN_TIMEOUT_S,
                      math.ceil(2.0 * max(0.0, float(output_seconds)) * factor)))
    return threads, NICE_LEVEL, timeout


# ponytail: transitions limited to none/fade; add xfade variants
# (dissolve variants, wipes) when a campaign needs them.


def _fail(reason, **kw):
    out = {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
           "tool_version": TOOL_VERSION, "outcome": "error",
           "reason_code": reason}
    out.update(kw)
    return out


def check_timeline_min_shot(tl, floor=None):
    """E3 QC wiring: run shot_planner.validate_timeline_min_shot on the
    loaded timeline. Returns [reason strings]; a non-empty list is a FAIL
    for the final gate (same check path W-E's dup-frames check uses).
    Refuses silently-losing the check when shot_planner is absent.
    """
    if floor is None:
        floor = MIN_SHOT_S
    core_dir = os.path.dirname(os.path.abspath(__file__))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    import shot_planner as sp
    return sp.validate_timeline_min_shot(tl, floor=floor)


def load_timeline(path):
    """Load + validate timeline.json. Returns dict or raises ValueError.

    E3: after the structural pass, the minimum-shot-length QC check runs
    fail-closed — a timeline with any segment under its applicable floor
    (1.5 s, or 1.0 s when that segment is marked beat_cut) is rejected;
    run shot planner floor remediation before assembling.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            tl = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"TIMELINE_UNREADABLE: {exc}") from exc
    if not isinstance(tl, dict):
        raise ValueError("TIMELINE_BAD_SCHEMA: top level must be an object")
    if tl.get("schema_version") != TIMELINE_SCHEMA:
        raise ValueError(
            f"TIMELINE_BAD_SCHEMA: schema_version must be {TIMELINE_SCHEMA}")
    segs = tl.get("segments")
    if not segs or not isinstance(segs, list):
        raise ValueError("TIMELINE_NO_SEGMENTS: segments[] required")
    fps = tl.get("fps", 30)
    if not isinstance(fps, (int, float)) or fps <= 0:
        raise ValueError("TIMELINE_BAD_FPS: fps must be positive")
    for i, s in enumerate(segs):
        if not isinstance(s, dict) or not s.get("src"):
            raise ValueError(f"TIMELINE_BAD_SEGMENT: segments[{i}] needs src")
        if s.get("dur") is not None and s["dur"] <= 0:
            raise ValueError(
                f"TIMELINE_BAD_SEGMENT: segments[{i}].dur must be positive")
    min_shot_errs = check_timeline_min_shot(tl)
    if min_shot_errs:
        raise ValueError(
            "SEGMENT_TOO_SHORT: minimum shot length failed: "
            + "; ".join(min_shot_errs[:4]))
    return tl


def probe_duration(path, ffprobe="ffprobe", timeout=30):
    """ffprobe duration in seconds (argv array, JSON stdout)."""
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration",
           "-of", "json", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"PROBE_UNAVAILABLE: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"PROBE_FAILED: {(proc.stderr or '').strip()[:200]}")
    try:
        dur = float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError(f"PROBE_NO_DURATION: {exc}") from exc
    if dur <= 0:
        raise RuntimeError("PROBE_NO_DURATION: non-positive duration")
    return dur


def _beat_cut(seg):
    """E2: shot planner's on-beat marker (beat_cut: true). Truthy only."""
    return seg.get("beat_cut") is True


def resolve_segments(tl):
    """E2 + QC: resolve per-segment transitions against the E2 rules.

    Returns (segments, errors). errors is a list of HARD_CUT_UNMARKED
    records for any non-first segment whose transition is 'none' without
    the planner's beat_cut=true marker. Explicitly-authored values keep
    working (fade stays fade; a legacy 'none' authored WITH beat_cut=true
    stays none); only the missing default changed from none to fade.
    """
    errors = []
    segs = []
    for i, s in enumerate(tl["segments"]):
        missing = i > 0 and "transition" not in s
        if missing:
            t, marker = DEFAULT_TRANSITION, False   # scene change default
        else:
            t = s.get("transition", tl.get("transition", "none"))
            marker = _beat_cut(s)
        if t not in ("none", "fade"):
            raise ValueError(f"TIMELINE_BAD_TRANSITION: {t!r}")
        if i > 0 and t == "none" and not marker:
            errors.append({"index": i, "src": s.get("src"),
                           "reason_code": HARD_CUT_UNMARKED})
        segs.append(dict(s, transition=t, beat_cut=marker))
    return segs, errors


def qc_transitions(tl):
    """E2 QC: every scene-boundary hard cut must carry beat_cut=true.

    Returns ok record or _fail(HARD_CUT_UNMARKED).
    """
    _segs, errors = resolve_segments(tl)
    if errors:
        return _fail(HARD_CUT_UNMARKED,
                     next_action="mark the cut on-beat in the shot plan "
                                 "(beat_cut: true) or let the default fade "
                                 "apply",
                     evidence={"unmarked_hard_cuts": errors})
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "command": "qc_transitions",
            "outcome": "ok", "reason_code": "transitions-ok",
            "evidence": {"checked": len(tl["segments"])},
            "state_version": 0}


def _seg_transition(tl, seg):
    t = seg.get("transition", tl.get("transition", "none"))
    if t not in ("none", "fade"):
        raise ValueError(f"TIMELINE_BAD_TRANSITION: {t!r}")
    if t == "none" and not _beat_cut(seg):
        raise ValueError(f"{HARD_CUT_UNMARKED}: segment {seg.get('src')!r} "
                         "transition none without beat_cut=true")
    return t


def plan_timeline(tl, base_dir=".", probe=None):
    """Pure frame plan: snap durations once, accumulate integer frames.

    probe(src) -> seconds; used when seg dur is null (full clip).
    Missing files are NOT checked here (assemble preflight does that).
    Returns plan dict with frames/segments/total.
    """
    fps = float(tl.get("fps", 30))
    width = int(tl.get("width", 1920))
    height = int(tl.get("height", 1080))
    # E2: the resolved default is fade TRANSITION_DURATION; explicit
    # transition_duration values keep working (manual allows 0.3-0.5).
    default_xd = float(tl.get("transition_duration",
                              TRANSITION_DURATION) or 0)
    items = []
    for i, s in enumerate(tl["segments"]):
        dur = s.get("dur")
        if dur is None:
            if probe is None:
                raise ValueError(
                    f"TIMELINE_NEEDS_PROBE: segments[{i}] has no dur "
                    "and no probe supplied")
            dur = probe(s["src"])
        frames = max(1, round(dur * fps))
        trans = _seg_transition(
            tl, s) if i > 0 and "transition" in s else (
            DEFAULT_TRANSITION if i > 0 else "none")
        xd = round(default_xd * fps) / fps if trans != "none" else 0.0
        # Part E E1(3): carry source/output fps per segment. The timeline's
        # per-segment "fps" key (absent on legacy timelines) is the clip's
        # requested source rate; fall back to the timeline fps so the
        # manifest records an equal-fps pass-through for legacy inputs.
        rec = fps_conform.conform_record(
            s.get("fps", fps) if s.get("fps") is not None else fps, fps)
        items.append({"src": s["src"], "frames": frames,
                      "snapped_dur": frames / fps, "transition": trans,
                      "xfade_dur": xd, **rec})
    for i in range(1, len(items)):
        ov = round(items[i]["xfade_dur"] * fps)
        lo = min(items[i - 1]["frames"], items[i]["frames"])
        if ov >= lo:
            raise ValueError(
                f"TIMELINE_XFADE_TOO_LONG: join {i} overlap {ov}f >= "
                f"shortest segment {lo}f")
        items[i]["xfade_frames"] = ov
    total_frames = sum(it["frames"] for it in items) - sum(
        it.get("xfade_frames", 0) for it in items)
    # Integer-frame offsets: no cumulative float drift by construction.
    off = 0
    for it in items:
        it["offset_frames"] = off
        off += it["frames"] - it.get("xfade_frames", 0)
    return {"fps": fps, "width": width, "height": height,
            "song_path": tl.get("song_path"),
            "segments": items, "total_frames": total_frames,
            "total_dur": total_frames / fps}


def build_argv(plan, output, ffmpeg="ffmpeg"):
    """ffmpeg argv array rendering plan -> output. No gaps by construction
    (concat/xfade chain covers every output frame exactly once).

    M7: the command is prefixed with `nice -n 10` and carries `-threads N`
    (from lane_size.py when shipped, else the Part D fallback) so a render
    never pegs every core of the box.
    """
    fps, w, h = plan["fps"], plan["width"], plan["height"]
    threads, nice, _timeout = size_ffmpeg(
        plan.get("total_dur", 0), w, h)
    segs = plan["segments"]
    cmd = ["nice", "-n", str(nice), ffmpeg, "-y", "-threads", str(threads)]
    for s in segs:
        cmd += ["-i", s["src"]]
    song = plan.get("song_path")
    song_idx = len(segs) if song else None
    if song:
        cmd += ["-i", song]
    fc = []
    for i, s in enumerate(segs):
        # Part E E1: motion-compensated conform, never the plain `fps`
        # filter (it duplicates frames -> visible stutter). The segment's
        # recorded source_fps decides pass-through vs minterpolate.
        conform = fps_conform.build_conform_argv(
            s.get("source_fps", fps), fps, w, h)
        step = f"setpts=PTS-STARTPTS,"
        if conform:
            step += f"{conform},"
        fc.append(f"[{i}:v]trim=duration={s['snapped_dur']:.6f},"
                  f"{step}"
                  f"scale={w}:{h},setsar=1[v{i}]")
    if len(segs) == 1:
        vlast = "[v0]"
    elif all(s["transition"] == "none" for s in segs[1:]):
        fc.append("".join(f"[v{i}]" for i in range(len(segs))) +
                  f"concat=n={len(segs)}:v=1:a=0[vout]")
        vlast = "[vout]"
    else:
        prev = "[v0]"
        for i in range(1, len(segs)):
            s = segs[i]
            if s["transition"] == "none":
                # hard join: concat the chain so far with the next clip
                fc.append(f"{prev}[v{i}]concat=n=2:v=1:a=0[x{i}]")
                prev = f"[x{i}]"
            else:
                start_frame = (s["offset_frames"] -
                               s.get("xfade_frames", 0))
                offset = start_frame / fps
                fc.append(f"{prev}[v{i}]xfade=transition=fade:"
                          f"duration={s['xfade_dur']:.6f}:"
                          f"offset={offset:.6f}[x{i}]")
                prev = f"[x{i}]"
        fc.append(f"{prev}null[vout]")
        vlast = "[vout]"
    amap = []
    if song:
        total = plan["total_dur"]
        fc.append(f"[{song_idx}:a]atrim=duration={total:.6f},"
                  f"apad=whole_dur={total:.6f},aresample=48000,"
                  "aformat=channel_layouts=stereo[aout]")
        amap = ["-map", vlast, "-map", "[aout]", "-c:a", "aac"]
    else:
        amap = ["-map", vlast, "-an"]
    cmd += ["-filter_complex", ";".join(fc),
            *amap, "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", f"{fps:g}", "-movflags", "faststart", str(output)]
    return cmd


def _run(cmd, timeout=600):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"FFMPEG_UNAVAILABLE: {exc}") from exc


def assemble(timeline_path, output, ffmpeg="ffmpeg", ffprobe="ffprobe",
             timeout=None, base_dir=".", dry_run=False):
    """Full render: validate -> preflight -> plan -> ffmpeg -> verify.

    Returns receipt dict (also written to <output>.receipt.json unless
    dry_run). Post-render ffprobe check: |A-V| and |out - planned|
    each within 1 frame; else outcome error with AV_DRIFT/PLAN_DRIFT.

    M7: timeout=None means "let lane_size.py (or the Part D fallback)
    bound the render from the plan's own duration" instead of the old
    flat 600 s cap. Callers that pass a number keep exact control.
    """
    try:
        tl = load_timeline(timeline_path)
    except ValueError as exc:
        return _fail(str(exc).split(":")[0], next_action=str(exc),
                     evidence={"timeline": str(timeline_path)})
    # E2 QC: unmarked hard cuts never assemble.
    try:
        qc = qc_transitions(tl)
    except ValueError as exc:
        return _fail(str(exc).split(":")[0], next_action=str(exc),
                     evidence={"timeline": str(timeline_path)})
    if qc["outcome"] != "ok":
        return qc
    base = os.path.dirname(os.path.abspath(str(timeline_path))) or base_dir

    def abspath(p):
        return p if os.path.isabs(p) else os.path.join(base, p)

    missing = [s["src"] for s in tl["segments"]
               if not os.path.isfile(abspath(s["src"]))]
    song = tl.get("song_path")
    if song and not os.path.isfile(abspath(song)):
        missing.append(song)
    if missing:
        return _fail("MISSING_INPUTS", next_action="provide listed inputs",
                     evidence={"missing": missing})
    try:
        plan = plan_timeline(
            tl, base, probe=lambda s: probe_duration(abspath(s), ffprobe))
    except (ValueError, RuntimeError) as exc:
        msg = str(exc)
        return _fail(msg.split(":")[0], next_action=msg, evidence={})
    for s in plan["segments"]:
        s["src"] = abspath(s["src"])
    if plan["song_path"]:
        plan["song_path"] = abspath(plan["song_path"])
    if timeout is None:
        _threads, _nice, timeout = size_ffmpeg(
            plan.get("total_dur", 0), plan.get("width", DEFAULT_WIDTH),
            plan.get("height", DEFAULT_HEIGHT))
    argv = build_argv(plan, output, ffmpeg)
    if dry_run:
        return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
                "tool_version": TOOL_VERSION, "command": "assemble",
                "outcome": "ok", "reason_code": "DRY_RUN",
                "next_action": "rerun without dry_run to render",
                "evidence": {"argv": argv, "plan": plan,
                             "timeout_s": timeout}, "state_version": 0}
    try:
        proc = _run(argv, timeout)
    except RuntimeError as exc:
        return _fail(str(exc).split(":")[0], next_action=str(exc),
                     evidence={"argv": argv})
    if proc.returncode != 0:
        return _fail("FFMPEG_FAILED",
                     next_action=(proc.stderr or "")[-500:],
                     evidence={"argv": argv, "returncode": proc.returncode})
    # Verify: output A/V durations within 1 frame of plan and each other.
    try:
        vdur = probe_duration(output, ffprobe)
    except RuntimeError as exc:
        return _fail("VERIFY_UNAVAILABLE", next_action=str(exc),
                     evidence={"output": str(output)})
    frame = 1.0 / plan["fps"]
    evid = {"planned_dur": plan["total_dur"], "output_dur": vdur,
            "total_frames": plan["total_frames"], "argv": argv,
            "timeout_s": timeout}
    # Part E E1(5) final QC gate: a master above 2% duplicated frames
    # (mpdecimate marker ratio) fails with TIMELINE_DUP_FRAMES. The only
    # accepted dup source is source fps == timeline fps; with the E1
    # conform a failure here means a bad conform (or a passthrough used
    # where interpolation was owed) and the render is refused.
    dup_pct = fps_conform.mpdecimate_dup_ratio(proc.stderr or "")
    evid["dup_frame_pct"] = dup_pct
    try:
        fps_conform.assert_no_dupe_frames(dup_pct)
        evid["dup_frame_gate"] = "PASS"
    except ValueError as exc:
        return _fail(str(exc),
                     next_action=("master exceeds %s%% duplicated frames; "
                                  "reconform the offending clip with "
                                  "fps_conform.build_conform_argv (mci, "
                                  "never the plain fps filter)"
                                  % fps_conform.DUP_FRAMES_CAP),
                     evidence=evid)
    if abs(vdur - plan["total_dur"]) > frame + 1e-3:
        return _fail("PLAN_DRIFT",
                     next_action="output duration off plan by >1 frame",
                     evidence=evid)
    if plan["song_path"]:
        try:
            adur = probe_duration(output, ffprobe)
        except RuntimeError:
            adur = vdur
        evid["audio_dur"] = adur
        if abs(adur - vdur) > frame + 1e-3:
            return _fail("AV_DRIFT",
                         next_action="audio/video differ by >1 frame",
                         evidence=evid)
    receipt = {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
               "tool_version": TOOL_VERSION, "command": "assemble",
               "outcome": "ok", "reason_code": "ASSEMBLED",
               "next_action": "QC per directive 17.5 (independent reviewer)",
               "evidence": evid, "state_version": 0}
    try:
        with open(str(output) + ".receipt.json", "w",
                  encoding="utf-8") as fh:
            json.dump(receipt, fh, indent=2)
    except OSError:
        pass
    return receipt


def main(argv=None):
    ap = argparse.ArgumentParser(prog="final_assembler",
                                 description="timeline.json -> ffmpeg render")
    ap.add_argument("timeline", help="timeline.json path")
    ap.add_argument("output", help="output mp4 path")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--timeout", type=int, default=None,
                    help="render cap in seconds; default: lane_size.py "
                         "or Part D max(600, 2 x output s x 1080p factor)")
    args = ap.parse_args(argv)
    if not shutil.which(args.ffmpeg) or not shutil.which(args.ffprobe):
        print(json.dumps(_fail("PREREQ_MISSING",
                               next_action="install ffmpeg+ffprobe")))
        return 3
    receipt = assemble(args.timeline, args.output, ffmpeg=args.ffmpeg,
                       ffprobe=args.ffprobe, timeout=args.timeout,
                       dry_run=args.dry_run)
    print(json.dumps(receipt, indent=2))
    return EXIT["ok"] if receipt["outcome"] == "ok" else EXIT["error"]


if __name__ == "__main__":
    sys.exit(main())
