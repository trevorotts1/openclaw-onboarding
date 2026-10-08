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
- F8 (manual Part F): the final sung/spoken line must end before the
  end card starts. The end card is marked by an optional top-level
  "endcard_start_s" (validated in load_timeline when present; no key =
  not checked — old timelines assemble unchanged). Sung/spoken line
  windows come from the optional "lines" list ({line_id, start_s,
  end_s}, the same absolute-window shape other checks read). When the
  end card key is present, check_last_line_before_endcard(plan) runs
  at assembly and a line ending after the card fails with
  LAST_LINE_OVER_ENDCARD.
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
# E6 sibling checker (same package): the lip-sync coverage rule in code.
try:
    from .lipsync_coverage import check_lipsync_coverage
except ImportError:  # direct script run from inside this directory
    from lipsync_coverage import check_lipsync_coverage  # type: ignore

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

# --- F8: last line before the end card (manual Part F F8) --------------------
# The ad's final sung/spoken line must end before the end card begins.
# The card is marked with the optional timeline key "endcard_start_s"
# (validated in load_timeline when present; no key = not checked).
# Sung/spoken line windows come from the optional "lines" list.
LAST_LINE_OVER_ENDCARD = "LAST_LINE_OVER_ENDCARD"

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

def motion_f12_gate(plan):
    """F12 QC wiring: run shot_planner.motion_score.gate_clips on the plan.

    Segments scored by the scoring step carry "motion_score" (the
    motion_score() dict). Every planned segment must be scored: an
    unscored clip raises ValueError CLIP_UNSCORED (fail closed — the
    near-still check may not silently pass); a flagged clip is returned as
    a non-ok result the caller turns into a CLIP_LOW_MOTION failure BEFORE
    any render spend.
    """
    core_dir = os.path.dirname(os.path.abspath(__file__))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    import shot_planner.motion_score as ms
    return ms.gate_clips(plan["segments"])

def lipsync_gate(plan):
    """E6 final edit QC: lip-sync coverage on the planned timeline.

    plan segments carry "lip_sync" markers from plan_timeline; the gate
    counts distinct marked LINES as segments (each whole line one segment,
    per E5's atomicity) and totals their snapped footage. Returns the
    _fail receipt on a short ad, or None when coverage holds (or the plan
    declares no lip-sync markers at all, which the QC review layer reads
    as a FAIL via the emitted coverage report — never silently as none).
    """
    marked = [s for s in plan["segments"]
              if s.get("lip_sync") or s.get("lip_sync_line_ids")]
    lines = len(marked)
    total = sum(s["snapped_dur"] for s in marked)
    res = check_lipsync_coverage(plan["total_dur"], lines, total)
    if res["pass"]:
        return None
    return _fail(res["reason_code"], next_action=res["detail"],
                 evidence=res["evidence"])

# F9 frame-text check: sampled frames per lip-sync clip, extractor stub
# default (OCR optional; register_extractor installs it). No ffmpeg needed
# on the stub path, so dry runs and tests run it too -- the done-when is
# "a frame check runs on every lip-sync clip and the receipt shows it".
try:                                    # F9 sibling module (this package)
    from .frame_text import GARBLED_TEXT_FRAME, clip_rows as _frame_rows
except ImportError:                     # direct script run from this dir
    from frame_text import (            # type: ignore
        GARBLED_TEXT_FRAME, clip_rows as _frame_rows)

def frame_text_gate(plan, ffmpeg=None, dry_run=False, frame_count=3,
                    extractor=None):
    """F9: one frame-text row per lip-sync clip, plus the gate result.

    Returns (rows, fail): rows always carry every lip-sync clip (stub mode
    names the extractor, so a dry-run receipt still shows the check ran);
    fail is the _fail receipt when a sampled readable-text frame flags
    GARBLED_TEXT_FRAME (no render spend), else None.
    """
    marked = [s for s in plan["segments"]
              if s.get("lip_sync") or s.get("lip_sync_line_ids")]
    rows = _frame_rows(
        marked, ffmpeg=("ffmpeg" if (ffmpeg and not dry_run) else None),
        frame_count=frame_count, extractor=extractor)
    for r in rows:
        if r["text_frames"]:
            return rows, _fail(GARBLED_TEXT_FRAME, next_action=(
                "lip-sync clip %s shows readable invented text in sampled "
                "frame(s) %s; regenerate that clip (no OCR text is allowed "
                "in lip-sync close-ups)"
                % (r["clip"], r["text_frames"])),
                evidence={"frame_text": rows})
    return rows, None


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
    # Part H H3: the master is 30 fps. Another rate needs the choice card
    # to set it explicitly (top-level "fps_set_by_choice_card": true).
    if (abs(fps - fps_conform.MASTER_FPS) > 1e-3
            and tl.get("fps_set_by_choice_card") is not True):
        raise ValueError(
            "TIMELINE_FPS_NOT_30: master fps must be %d (got %g); only the "
            "choice card may set another rate" % (fps_conform.MASTER_FPS, fps))
    for i, s in enumerate(segs):
        if not isinstance(s, dict) or not s.get("src"):
            raise ValueError(f"TIMELINE_BAD_SEGMENT: segments[{i}] needs src")
        if s.get("dur") is not None and s["dur"] <= 0:
            raise ValueError(
                f"TIMELINE_BAD_SEGMENT: segments[{i}].dur must be positive")
        # E6: an optional per-segment lip-sync marker must be a boolean, so
        # the coverage gate below counts exactly what the planner intended.
        if not isinstance(s.get("lip_sync", False), bool):
            raise ValueError(
                f"TIMELINE_BAD_SEGMENT: segments[{i}].lip_sync must be "
                "boolean")
    # F8: optional end card marker (and sung/spoken line windows) are
    # validated here, at load, when present — fail closed on bad shape.
    if tl.get("endcard_start_s") is not None:
        ec = tl["endcard_start_s"]
        if (isinstance(ec, bool) or not isinstance(ec, (int, float))
                or ec != ec or ec <= 0):
            raise ValueError(
                "TIMELINE_BAD_ENDCARD: endcard_start_s must be a positive "
                "number of seconds")
    if tl.get("lines") is not None:
        ls = tl["lines"]
        if not isinstance(ls, list):
            raise ValueError("TIMELINE_BAD_LINES: lines must be a list")
        for i, ln in enumerate(ls):
            if not isinstance(ln, dict) \
                    or not str(ln.get("line_id") or "").strip():
                raise ValueError(
                    f"TIMELINE_BAD_LINES: lines[{i}] needs line_id")
            st, en = ln.get("start_s"), ln.get("end_s")
            for name, v in (("start_s", st), ("end_s", en)):
                if (isinstance(v, bool) or not isinstance(v, (int, float))
                        or v != v):
                    raise ValueError(
                        f"TIMELINE_BAD_LINES: lines[{i}].{name} must be a "
                        "number")
            if en <= st:
                raise ValueError(
                    f"TIMELINE_BAD_LINES: lines[{i}] end must be after "
                    "start")
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
        lids = s.get("lip_sync_line_ids")
        # Part E E5: a lip-sync clip is atomic. Snap UP to the frame grid
        # (ceil, never the plain round) so conforming a lip-sync segment
        # can never trim it below its aligned line duration; the remaining
        # trim side stays policed by validate_lipsync_atomic.
        if isinstance(lids, list) and lids:
            frames = max(1, math.ceil(dur * fps))
        else:
            frames = max(1, round(dur * fps))
        trans = _seg_transition(
            tl, s) if i > 0 and "transition" in s else (
            DEFAULT_TRANSITION if i > 0 else "none")
        xd = round(default_xd * fps) / fps if trans != "none" else 0.0
        # Part E E1(3): carry source/output fps per segment. The timeline's
        # per-segment "fps" key (absent on legacy timelines) is the clip's
        # requested source rate; fall back to the timeline fps so the
        # manifest records an equal-fps pass-through for legacy inputs.
        # Part H H3: explicit per-segment fps wins, then the model's known
        # native rate (Kling 30 pass-through, MiniMax H3 24 interpolated).
        src_fps = s.get("fps")
        if src_fps is None:
            src_fps = fps_conform.native_fps(s.get("model"))
        rec = fps_conform.conform_record(
            src_fps if src_fps is not None else fps, fps)
        item = {"src": s["src"], "frames": frames,
                "snapped_dur": frames / fps, "transition": trans,
                "xfade_dur": xd, "lip_sync": bool(s.get("lip_sync")),
                "hold": bool(s.get("hold")), **rec}
        # Part F F12: the timeline's per-segment motion_score (the
        # motion_score() dict written by the scoring step) rides the plan
        # so the pre-assembly gate and the receipt read the same row.
        if isinstance(s.get("motion_score"), dict):
            item["motion_score"] = s["motion_score"]
        if isinstance(lids, list) and lids:
            item["lip_sync_line_ids"] = list(lids)
        items.append(item)
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
            "total_dur": total_frames / fps,
            # F8: card marker + line windows ride the plan so
            # check_last_line_before_endcard(plan) runs off the plan.
            "endcard_start_s": tl.get("endcard_start_s"),
            "lines": tl.get("lines")}


# --- F8: last line before the end card (manual Part F F8) --------------------
#
# The failed 2026-10-08 ad let its last sung line run INTO the end card:
# the words were still playing when the CTA card appeared and the whole
# close was cut off. The check is timeline-based, needs no media:
#   * line windows come from the optional timeline key "lines"
#     ([{line_id, start_s, end_s}], absolute seconds, the same shape
#     other timing checks read);
#   * the card's start is the optional timeline key "endcard_start_s"
#     (validated in load_timeline when present; no key = not checked);
#   * plan_timeline copies both onto the plan so the gate runs off the
#     plan, like every other assembler gate.
# Reason code: LAST_LINE_OVER_ENDCARD — a line whose END lands after the
# card's start on the timeline. Any gate error raises ValueError with a
# reason code (fail closed), never silently passes.


def check_last_line_before_endcard(plan):
    """F8 gate: final sung/spoken line ends before the end card starts.

    plan: plan_timeline() output (must carry "endcard_start_s" and
    "lines" copied from the timeline, or neither — the check is a no-op
    without the card marker).

    Returns [] on pass or when not checked; else a list of reason
    strings — ["LAST_LINE_OVER_ENDCARD"] when any final sung/spoken
    line's end time lands after the end card's start time on the
    timeline. Malformed plan shapes raise ValueError (fail closed,
    never a silent pass).
    """
    ec = plan.get("endcard_start_s")
    if ec is None:
        return []                              # no card key = not checked
    ls = plan.get("lines")
    if ls is None:
        raise ValueError(
            "LAST_LINE_WINDOW_UNKNOWN: endcard_start_s present but the "
            "timeline carries no lines to check against")
    if not isinstance(ec, (int, float)) or isinstance(ec, bool) \
            or not isinstance(ls, list):
        raise ValueError(
            "LAST_LINE_INPUT_BAD: endcard_start_s must be a number and "
            "lines a list")
    for i, ln in enumerate(ls):
        if not isinstance(ln, dict):
            raise ValueError(
                "LAST_LINE_INPUT_BAD: lines[%d] must be an object" % i)
        end = ln.get("end_s")
        if isinstance(end, bool) or not isinstance(end, (int, float)):
            raise ValueError(
                "LAST_LINE_INPUT_BAD: lines[%d].end_s must be a number"
                % i)
    if all(float(ln["end_s"]) <= float(ec) for ln in ls):
        return []
    return [LAST_LINE_OVER_ENDCARD]


def _last_line_over_detail(plan):
    """Evidence for a LAST_LINE_OVER_ENDCARD failure: the offending lines."""
    ec = float(plan["endcard_start_s"])
    return [{"line_id": str(ln.get("line_id") or i),
             "end_s": float(ln["end_s"]), "endcard_start_s": ec}
            for i, ln in enumerate(plan["lines"])
            if float(ln["end_s"]) > ec]


# --- Part E E5: lip-sync clips stay whole (atomic) --------------------------
#
# A lip-sync clip carries one sung line's mouth motion, aligned to that
# line's window in the timing map (directive 12.4 shape, the map the
# planner binds via load_timing_map/bind_plan). The old assembler was free
# to split one lip-sync clip across two timeline segments (the failed 2026
# ad split one in two) or trim it below its line. Both are now gate
# failures at planning AND assembly validation:
#
#   LIPSYNC_SPLIT     - one lip-sync source clip used in two segments
#                       (planning side also raises PlanError LIPSYNC_SPLIT
#                       via shot_planner.bind_plan for shot lists)
#   LIPSYNC_TRIMMED   - a segment carrying a lip-sync clip is shorter than
#                       that clip's aligned line duration
#
# Timing data: segments carry "lip_sync_line_ids" (directive 12.3/12.4
# names, the same ids the planner's bind_plan resolves) and the timeline
# carries a directive-12.4 timing map under a "timing" key ({"sections":
# [{"section_id", "lyrics": [{"line_id", "start", "end", ...}]}]}) — the
# same shape load_timing_map() accepts. A declared lip-sync segment whose
# ids cannot resolve in the map fails closed (LIPSYNC_WINDOW_UNKNOWN).


def _timing_lines(tl):
    """Directive-12.4 timing map (timeline 'timing' key) -> {line_id: seconds}.

    Same shape shot_planner.load_timing_map accepts. Bad shape raises
    ValueError LIPSYNC_TIMING_BAD; absent/no map raises None and the caller
    fails closed for any declared lip-sync segment.
    """
    t = tl.get("timing")
    if t is None:
        return None
    if not isinstance(t, dict) or not isinstance(t.get("sections"), list):
        raise ValueError(
            "LIPSYNC_TIMING_BAD: timeline 'timing' must be a directive-"
            "12.4 map ({'sections': [{'lyrics': ...}, ...]})")
    lines = {}
    for sec in t["sections"]:
        if not isinstance(sec, dict) or not isinstance(sec.get("lyrics"),
                                                       list):
            raise ValueError(
                "LIPSYNC_TIMING_BAD: each section needs a lyrics list")
        for ln in sec["lyrics"]:
            if not isinstance(ln, dict) or not isinstance(ln.get("line_id"),
                                                          str) or not ln["line_id"].strip():
                raise ValueError(
                    "LIPSYNC_TIMING_BAD: lyric line needs line_id")
            st, en = ln.get("start"), ln.get("end")
            if (not isinstance(st, (int, float)) or isinstance(st, bool)
                    or not isinstance(en, (int, float))
                    or isinstance(en, bool) or not st < en):
                raise ValueError(
                    "LIPSYNC_TIMING_BAD: line %r window unordered"
                    % ln["line_id"])
            lines[ln["line_id"]] = float(en) - float(st)
    return lines


def validate_lipsync_atomic(plan, tl=None):
    """Part E E5 gate: lip-sync clips may not be split or trimmed.

    plan: plan_timeline() output; tl: the loaded timeline dict (for the
    timing map). Raises ValueError with reason LIPSYNC_SPLIT (one lip-sync
    source in two segments), LIPSYNC_TRIMMED (segment shorter than its
    clip's aligned line duration; both declared ids checked) or
    LIPSYNC_WINDOW_UNKNOWN (declared ids unresolvable — fail closed).
    Returns the checked count of lip-sync segments.
    """
    segs = plan["segments"]
    seen = {}
    for i, s in enumerate(segs):
        lids = s.get("lip_sync_line_ids")
        if not lids:
            continue
        if s["src"] in seen:
            raise ValueError(
                "LIPSYNC_SPLIT: lip-sync source %r appears in segments "
                "%d and %d; a lip-sync clip is atomic (manual Part E E5)"
                % (s["src"], seen[s["src"]], i))
        seen[s["src"]] = i
    if tl is not None:
        lines = _timing_lines(tl)
        for s in segs:
            lids = s.get("lip_sync_line_ids")
            if not lids:
                continue
            if not lines:
                raise ValueError(
                    "LIPSYNC_WINDOW_UNKNOWN: segment carries "
                    "lip_sync_line_ids %s but the timeline carries no "
                    "timing map to align against" % (lids,))
            for lid in lids:
                if lid not in lines:
                    raise ValueError(
                        "LIPSYNC_WINDOW_UNKNOWN: lip-sync line %r missing "
                        "from the timing map" % (lid,))
            if s["snapped_dur"] < min(lines[lid] for lid in lids) - 1e-9:
                raise ValueError(
                    "LIPSYNC_TRIMMED: segment %r %.3fs is below its "
                    "lip-sync line duration(s) %s; a lip-sync clip may "
                    "not be trimmed below its aligned line (manual Part "
                    "E E5)" % (s["src"], s["snapped_dur"], sorted(lids)))
    checked = sum(1 for s in segs if s.get("lip_sync_line_ids"))
    return checked


def build_argv(plan, output, ffmpeg="ffmpeg"):
    """ffmpeg argv array rendering plan -> output. No gaps by construction
    (concat/xfade chain covers every output frame exactly once).

    M7: the command is prefixed with `nice -n 10` and carries `-threads N`
    (from lane_size.py when shipped, else the Part D fallback) so a render
    never pegs every core of the box.

    Part E E5: lip-sync segments conform at their snapped (ceil-rounded,
    never-below-line) duration, so the trim in the filter chain cannot cut
    into a lip-sync clip; everything else is unchanged.
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
        if conform:
            # H3: minterpolate cannot extrapolate, so it loses ~2 frames at
            # the cut. Trim a margin in, conform, then trim to the exact
            # slot so the segment keeps its planned frame count.
            step = (f"trim=duration={s['snapped_dur'] + 0.25:.6f},"
                    f"setpts=PTS-STARTPTS,{conform},"
                    f"trim=duration={s['snapped_dur']:.6f},"
                    "setpts=PTS-STARTPTS,")
        else:
            step = (f"trim=duration={s['snapped_dur']:.6f},"
                    "setpts=PTS-STARTPTS,")
        # H3: a pass-through Kling clip (source timebase 1/15360) and an
        # interpolated H3 clip (timebase 1/30) cannot meet in xfade/concat
        # unless every chain ends on the same timebase.
        step += f"settb=1/{fps:g},"
        fc.append(f"[{i}:v]{step}"
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
    # Part E E5: lip-sync clips stay whole — same gate the shot-planner QC
    # path runs, at assembly validation. Render only a plan that passes.
    try:
        validate_lipsync_atomic(plan, tl)
    except ValueError as exc:
        msg = str(exc)
        return _fail(msg.split(":")[0], next_action=msg, evidence={})
    # F8: the final sung/spoken line must end before the end card starts.
    # No endcard_start_s key on the timeline = not checked (backward
    # compatible); a bad line window already failed in load_timeline.
    try:
        over = check_last_line_before_endcard(plan)
    except ValueError as exc:
        msg = str(exc)
        return _fail(msg.split(":")[0], next_action=msg, evidence={})
    if over:
        return _fail(over[0],
                     next_action=("move the final sung/spoken line's end "
                                  "before the end card starts (manual "
                                  "Part F F8)"),
                     evidence={"over": _last_line_over_detail(plan)})
    # Part F F12: clips must move. Every planned clip carries its motion
    # score in the receipt; a near-still clip fails before any render spend
    # (CLIP_LOW_MOTION). Scored rows come from the timeline segments
    # (motion_score key, written by the scoring step); anything unscored
    # fails closed — the check may not silently pass.
    try:
        motion = motion_f12_gate(plan)
    except ValueError as exc:
        msg = str(exc)
        return _fail(msg.split(":")[0], next_action=msg, evidence={})
    if motion["outcome"] != "ok":
        return _fail(
            motion["reason_code"],
            next_action="regenerate the flagged clips (prompt carries the "
                        "F12 motion line) before assembling",
            evidence=motion)
    if timeout is None:
        _threads, _nice, timeout = size_ffmpeg(
            plan.get("total_dur", 0), plan.get("width", DEFAULT_WIDTH),
            plan.get("height", DEFAULT_HEIGHT))
    argv = build_argv(plan, output, ffmpeg)
    # E6 lip-sync coverage result rides in every receipt; only a FAIL
    # blocks the render. The dry-run receipt exists for exactly this.
    cov = lipsync_gate(plan)
    # F9 frame-text check runs on EVERY lip-sync clip (stub mode when
    # there is no real ffmpeg or on dry runs; extract mode on real
    # renders). Rows ride the receipt either way; only a flagged row
    # blocks, with no render spend.
    try:
        frows, ffail = frame_text_gate(plan, ffmpeg=ffmpeg, dry_run=dry_run)
    except Exception as exc:            # fail closed on extractor/setup
        msg = str(exc)
        return _fail(getattr(exc, "code", "FRAME_EXTRACT_UNAVAILABLE"),
                     next_action=msg, evidence={})
    if dry_run:
        out = {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
               "tool_version": TOOL_VERSION, "command": "assemble",
               "outcome": "ok", "reason_code": "DRY_RUN",
               "next_action": "rerun without dry_run to render",
               "evidence": {"argv": argv, "plan": plan,
                            "timeout_s": timeout, "lipsync": cov,
                            "frame_text": frows,
                            "motion": motion},
               "state_version": 0}
        blocked = cov if cov is not None else ffail
        if blocked is not None:  # blocked before spend, but evidence stays
            out["outcome"] = "error"
            out["reason_code"] = blocked["reason_code"]
            out["next_action"] = blocked["next_action"]
            out.setdefault("evidence", {}).setdefault("gate_evidence", {})
            out["evidence"]["gate_evidence"] = blocked["evidence"]
        return out
    for blocked in (cov, ffail):   # gate FAILs: no render spend (17.5)
        if blocked is not None:
            return blocked
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
            "timeout_s": timeout,
            # F12: every clip's motion score rides in the receipt
            # (scored before the render; flagged clips never reached here).
            "motion": motion}
    # Part E E1(5) final QC gate: a master above 2% duplicated frames
    # (mpdecimate marker ratio) fails with TIMELINE_DUP_FRAMES. The only
    # accepted dup source is source fps == timeline fps; with the E1
    # conform a failure here means a bad conform (or a passthrough used
    # where interpolation was owed) and the render is refused.
    # H3: measure the rendered master with mpdecimate (the render's own
    # stderr carries no mpdecimate markers, so it can never measure this).
    try:
        dup_pct = fps_conform.measure_dup_pct(output, ffmpeg)
        seg_rows, seg_bad = fps_conform.segment_dup_report(
            output, plan, ffmpeg)
    except RuntimeError as exc:
        return _fail("DUP_MEASURE_FAILED", next_action=str(exc),
                     evidence=evid)
    evid["dup_frame_pct"] = dup_pct
    evid["segment_dups"] = seg_rows
    evid["frame_text"] = frows   # F9: one row per lip-sync clip, in receipt
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
    if seg_bad:
        return _fail(fps_conform.TIMELINE_SEGMENT_DUP_FRAMES,
                     next_action=("segments above %s%% duplicated frames: "
                                  "%s; regenerate the clip or mark a "
                                  "deliberate still hold"
                                  % (fps_conform.SEGMENT_DUP_CAP,
                                     [r["index"] for r in seg_bad])),
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
