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
- DEL-14 (unit PKG-05-U1): every segment reaches the master canvas by
  CROP-IN -- scale up until the frame covers W x H, then cut the overhang
  off, anchored at the top so the plain top is the source's own. Never
  stretched, never letterboxed, never filled from a blurred copy of its
  own edge. The filter comes from scripts/video_still_fill/, the one
  path that owns full height.
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
- U-V03 (S75-055): this module's planning step also WRITES the timeline.
  plan_run_timeline(run_dir) composes edit/timeline.json from the run's
  own records (approved storyboard, shot plan, the picked song's
  measured word timings, the materialized clip rows with their lip-sync
  evidence) and writes it atomically -- it is the writing step no
  production module had. Every value comes from a record on disk; a
  value no record holds is the named refusal
  TIMELINE_INPUT_MISSING:<what>, never a default.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

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
# H12: receipt provenance stamp (same package).
try:
    from . import master_provenance
except ImportError:                     # direct-script fallback
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import master_provenance  # noqa: E402

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)
import master_length  # noqa: E402  (Part I I4)
import delivery_audio  # noqa: E402  (FU-AAC-FINAL-MUX)

# DEL-14 (unit PKG-05-U1): the still-fill path lives one level above core,
# at scripts/video_still_fill/. Every segment reaches full height by
# crop-in through it -- never stretched, never letterboxed, never filled
# from a blurred copy of its own edge. Fail closed: a master cannot render
# on a box where the path is missing.
_scripts = os.path.dirname(_CORE)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
try:
    import video_still_fill as _VSF  # noqa: E402
except ImportError as _vsf_exc:      # pragma: no cover - packaging defect
    raise ImportError(
        "STILL_FILL_PATH_MISSING: final_assembler needs "
        "scripts/video_still_fill/ (DEL-14 crop-in fill path); the skill "
        "package is incomplete (%s)" % (_vsf_exc,)) from _vsf_exc

# DEL-14: blur fill is never used. scripts/ on the path for the refusal gate.
_SCRIPTS = os.path.dirname(_CORE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from qc_no_blur import assembler_gate as no_blur  # noqa: E402  (DEL-14)

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
# H13: a cross-fade into a lip-sync clip ends at least this long before
# the clip's first word; a gap inside one line longer than LONG_GAP_S is
# held on the speaking face (no cut-away inside the line window).
FADE_WORD_MARGIN_S = 0.1
LONG_GAP_S = 0.5
FADE_COVERS_FIRST_WORD = "FADE_COVERS_FIRST_WORD"
LONG_GAP_CUTAWAY = "LONG_GAP_CUTAWAY"

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


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def _loud_attach(receipt):
    import loud_failure
    return loud_failure.attach(receipt)


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


def _run_bound_builder(run_dir):
    """(runtime, provider) the run itself bound for its builder (S75-024).

    Read from the run's own ``model-bindings.json`` (the store
    ai_models.bind_roles wrote), so lane sizing judges the route this run
    really dispatches on instead of the literals this used to pass. Returns
    (None, None) when the run bound nothing or the store cannot be read:
    lane_size then sizes from the machine alone, never from a made-up route.
    """
    if not run_dir:
        return None, None
    try:
        from choice_card.intake_card import ai_models as _AM
    except ImportError:                     # package not shipped on this box
        return None, None
    try:
        doc = _AM.load_bindings(run_dir)
    except (OSError, ValueError):           # unreadable store: no binding
        return None, None
    row = ((doc or {}).get("bindings") or {}).get(_AM.ROLE_BUILD) or {}
    runtime = (row.get("dispatch") or {}).get("runtime")
    provider = row.get("route")
    if not runtime or not provider:
        return None, None
    return runtime, provider


def _lane_size_threads(run_dir=None):
    """Prefer W2-A's scripts/core/lane_size.py; None when it is not shipped yet."""
    core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    try:
        import lane_size                    # noqa: F401  (guarded: W2-A unit)
    except ImportError:                     # absent: documented, not an error
        return None
    except Exception as exc:                # noqa: BLE001  broken module
        _loud("warn", "LANE_SIZE_BROKEN", "lane_size import failed: %r" % (exc,))
        return None
    for name in ("ffmpeg_threads", "threads"):   # tolerant of H4's final spelling
        val = getattr(lane_size, name, None)
        if callable(val):
            try:
                val = val()
            except TypeError:
                try:
                    val = val(output_seconds=0, height=DEFAULT_HEIGHT)
                except Exception as exc:    # noqa: BLE001
                    _loud("warn", "LANE_SIZE_BROKEN", "%s(): %r" % (name, exc))
                    continue
            except Exception as exc:        # noqa: BLE001
                _loud("warn", "LANE_SIZE_BROKEN", "%s(): %r" % (name, exc))
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
            # size() (W2-A) takes (runtime, provider, ...) positionally:
            # same documented call intake_preflight/factory.py makes, but with
            # the run's OWN bound builder (S75-024), not a literal pair.
            out = fn(*_run_bound_builder(run_dir), units=999) \
                if name == "size" else fn()
        except Exception as exc:            # noqa: BLE001
            _loud("warn", "LANE_SIZE_BROKEN", "%s(): %r" % (name, exc))
            continue
        if isinstance(out, dict):
            for key in ("ffmpeg_threads", "threads"):
                val = out.get(key)
                if isinstance(val, (int, float)) and not isinstance(val, bool) \
                        and val >= 1:
                    return int(val)
    return None


def size_ffmpeg(output_seconds, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
                run_dir=None):
    """(threads, nice, timeout_s) for one render.

    threads  from lane_size.py when shipped, else Part D fallback; lane_size
             is told the run's own bound runtime and provider (S75-024)
    nice     NICE_LEVEL (fixed: manual M7 says -n 10 on Linux and macOS)
    timeout  lane_size's ffmpeg_timeout_s when shipped, else
             max(600, 2 x output seconds x 1080p height factor)
    """
    threads = _lane_size_threads(run_dir) or _part_d_threads()[0]
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

def _h5_core():
    core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    import shot_planner.timestamp_plan as tp
    return tp


def _h5_stretch(seg):
    return _h5_core().stretch_of(seg)


def h5_gates(plan):
    """Part H H5: no slow motion above 1.15x (SLOWMO_OVER_LIMIT) and, when
    the timeline carries line windows and segments name the line they show,
    every picture matches the line heard in its window
    (PICTURE_LINE_MISMATCH). Returns (_fail or None, evidence rows)."""
    tp = _h5_core()
    segs = plan["segments"]
    rows = tp.check_stretch(segs)
    ev = {"stretch": rows}
    bad = [r for r in rows if not r["ok"]]
    if bad:
        return _fail(tp.SLOWMO, next_action=(
            "segment(s) %s are slowed above %.2fx; generate the picture at "
            "the shot window's length instead of stretching it"
            % (",".join(str(r["index"]) for r in bad), tp.MAX_SLOWMO)),
            evidence=ev), ev
    if plan.get("lines") and any(s.get("shows_line_ids") for s in segs):
        fps = plan["fps"]
        shots = [{"shot_id": "seg%d" % i,
                  "song_start": s["offset_frames"] / fps,
                  "song_end": (s["offset_frames"] + s["frames"]) / fps,
                  "shows_line_ids": s.get("shows_line_ids", [])}
                 for i, s in enumerate(segs)]
        try:
            gate = tp.pictures_match_gate(shots, [
                {"line_id": l["line_id"], "start": l["start_s"],
                 "end": l["end_s"], "text": l.get("text", "")}
                for l in plan["lines"]])
        except (KeyError, TypeError, AttributeError, tp.PlanError) as exc:
            return _fail("TIMELINE_BAD_LINES", next_action=str(exc),
                         evidence=ev), ev
        ev["pictures_match"] = gate
        if gate["outcome"] != "ok":
            return _fail(gate["reason_code"], next_action=(
                "pictures do not match the words in " + ",".join(gate["mismatches"])),
                evidence=ev), ev
    return None, ev


LIPSYNC_NOT_IN_PLAN = "LIPSYNC_NOT_IN_PLAN"
LIPSYNC_NOT_APPLICABLE = "NOT_APPLICABLE"

def lipsync_gate(plan):
    """E6 final edit QC: lip-sync coverage on the planned timeline.

    plan segments carry "lip_sync" markers from plan_timeline; the gate
    counts distinct marked LINES as segments (each whole line one segment,
    per E5's atomicity) and totals their snapped footage.

    Missing markers and speaker metadata are missing evidence, never an
    exemption. An applicable, plan-bound exception must be implemented through
    the existing approval mechanism before a no-lip-sync plan can advance.
    This guard does not choose or change the numeric coverage policy.
    """
    marked = [s for s in plan["segments"]
              if s.get("lip_sync") or s.get("lip_sync_line_ids")]
    speaker_lines = [l for l in (plan.get("lines") or [])
                     if isinstance(l, dict) and l.get("speaker")]
    lines = len(marked)
    total = sum(s["snapped_dur"] for s in marked)
    evidence = {"ad_length_s": plan["total_dur"],
                "lipsync_lines_count": lines,
                "lipsync_total_s": total,
                "speaker_lines": len(speaker_lines)}
    known_lines = {l.get("line_id"): l for l in speaker_lines
                   if l.get("line_id")}
    incomplete = not speaker_lines or any(
        not s.get("lip_sync_line_ids") or any(
            lid not in known_lines for lid in s.get("lip_sync_line_ids", []))
        for s in marked)
    if incomplete:
        return _fail("LIPSYNC_EVIDENCE_MISSING",
                     next_action="restore the approved lip-sync plan, line and "
                                 "speaker metadata; missing evidence is not "
                                 "an approved no-lip-sync exception",
                     evidence=evidence)
    res = check_lipsync_coverage(plan["total_dur"], lines, total)
    if res["pass"]:
        return None
    return _fail(res["reason_code"], next_action=res["detail"],
                 evidence=res["evidence"])

def face_speaks_gate(plan):
    """Part H H4 final edit QC: every shot where a face is visibly speaking
    is a lip-sync clip of that character's own line, and lip-sync coverage
    sits in the target band.

    Opt-in by data: runs only when the timeline "lines" carry "speaker"
    (otherwise None, nothing to judge). Then every segment must declare
    "faces_on_screen" (optional "speaking_faces"); a missing declaration
    fails closed FACE_DATA_MISSING. Returns the _fail receipt or None; the
    shot table (shot / time / line / lip-sync) rides in evidence.
    """
    lines = [l for l in (plan.get("lines") or []) if l.get("speaker")]
    if not lines:
        return None
    core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    from shot_planner import face_speaks as fs
    fps, shots = plan["fps"], []
    for i, s in enumerate(plan["segments"]):
        if not isinstance(s.get("faces_on_screen"), list):
            return _fail("FACE_DATA_MISSING",
                         next_action="segments[%d] must declare "
                         "faces_on_screen when lines carry speakers" % i,
                         evidence={})
        start = s["offset_frames"] / fps
        shots.append({"shot_id": s.get("shot_id") or "seg%d" % i,
                      "start": start, "end": start + s["frames"] / fps,
                      "faces_on_screen": s["faces_on_screen"],
                      "speaking_faces": s.get("speaking_faces"),
                      "lip_sync_line_ids": s.get("lip_sync_line_ids")})
    res = fs.check_face_speaks(shots, plan["lines"])
    if not res["pass"]:
        return _fail(res["reason_code"], next_action=res["detail"],
                     evidence={"speaking_face_rows": res["rows"]})
    marked = [s for s in plan["segments"] if s.get("lip_sync_line_ids")]
    band = fs.check_coverage_band(plan["total_dur"], sum(
        s["snapped_dur"] for s in marked), len(marked))
    if not band["pass"]:
        return _fail(band["reason_code"],
                     next_action="lip-sync coverage is below the target band "
                     "(manual Part H H4)", evidence=band["evidence"])
    return None

# F9 frame-text check: sampled frames per lip-sync clip, extractor stub
# default (OCR optional; register_extractor installs it). No ffmpeg needed
# on the stub path, so dry runs and tests run it too -- the done-when is
# "a frame check runs on every lip-sync clip and the receipt shows it".
try:                                    # F9 sibling module (this package)
    from . import frame_text as _frame_text
    from .frame_text import GARBLED_TEXT_FRAME, clip_rows as _frame_rows
except ImportError:                     # direct script run from this dir
    import frame_text as _frame_text  # type: ignore
    from frame_text import (            # type: ignore
        GARBLED_TEXT_FRAME, clip_rows as _frame_rows)

# S75-045: the on-screen text check's code words (frame_text owns them).
OCR_UNAVAILABLE = _frame_text.OCR_UNAVAILABLE


def _onscreen_extractor(ffmpeg):
    """The OCR reader's registered name, or None (S75-045).

    onscreen_text owns the ONE reader: it registers ``tesseract`` with
    frame_text at import (its line 187), so this never adds a second reader --
    it only asks whether one can run here. No real render and no tesseract
    binary means no reader, and the check reports UNAVAILABLE, never PASS.
    Amendment to S75-045: use onscreen_text's registered name, not a new one.
    """
    if not ffmpeg:
        return None
    try:
        from onscreen_text import onscreen_text as _OT
    except ImportError:                  # package not shipped on this box
        return None
    try:
        if not _OT.tesseract_bin():
            return None
        if _frame_text.EXTRACTORS.get(_OT.ENGINE) is None:
            _frame_text.register_extractor(_OT.ENGINE, _OT.tesseract_extractor)
        return _OT.ENGINE
    except Exception:                    # noqa: BLE001  advisory setup only
        return None


def frame_text_warnings(rows):
    """Receipt warnings for text-check rows that never really ran (S75-045).

    An UNAVAILABLE row means the on-screen text check did not happen (no
    reader, no frames, a failed read). The receipt says so by name; a check
    that never ran is never read as a clean one.
    """
    out = []
    for r in rows or []:
        if r.get("status") != _frame_text.UNAVAILABLE:
            continue
        out.append({"kind": "WARNING",
                    "code": r.get("reason_code") or OCR_UNAVAILABLE,
                    "detail": "on-screen text check did not run on %s: "
                              "no reader read the sampled frames"
                              % (r.get("clip"),)})
    return out


def frame_text_gate(plan, ffmpeg=None, dry_run=False, frame_count=3,
                    extractor=None):
    """F9: one frame-text row per lip-sync clip, plus the gate result.

    Returns (rows, fail): rows always carry every lip-sync clip (stub mode
    names the extractor, so a dry-run receipt still shows the check ran);
    fail is the _fail receipt when a sampled readable-text frame flags
    GARBLED_TEXT_FRAME (no render spend), else None.

    S75-045: rows also carry one named verdict per segment that plans to show
    words (``check`` = "onscreen_text"). A row whose words are not the planned
    words fails the gate; a row nobody could read is UNAVAILABLE, and the
    caller puts ``frame_text_warnings(rows)`` on the receipt.
    """
    real_ffmpeg = "ffmpeg" if (ffmpeg and not dry_run) else None
    marked = [s for s in plan["segments"]
              if s.get("lip_sync") or s.get("lip_sync_line_ids")]
    rows = _frame_rows(
        marked, ffmpeg=real_ffmpeg, frame_count=frame_count,
        extractor=extractor)
    text_extractor = extractor if extractor is not None \
        else _onscreen_extractor(real_ffmpeg)
    for r in _frame_text.text_check_rows(
            plan["segments"], ffmpeg=real_ffmpeg, extractor=text_extractor,
            frame_count=frame_count):
        r["check"] = "onscreen_text"
        rows.append(r)
    for r in rows:
        if r.get("status") == _frame_text.FAIL:
            fail = _fail(r.get("reason_code") or _frame_text.TEXT_CHANGED,
                         next_action=(
                             "the on-screen words in %s are not the planned "
                             "words (%r); regenerate that shot with exactly "
                             "the planned words or overlay them at assembly"
                             % (r["clip"], r.get("expected"))),
                         evidence={"frame_text": rows})
        elif r.get("check") != "onscreen_text" and r["text_frames"]:
            fail = _fail(GARBLED_TEXT_FRAME, next_action=(
                "lip-sync clip %s shows readable invented text in sampled "
                "frame(s) %s; regenerate that clip (no OCR text is allowed "
                "in lip-sync close-ups)"
                % (r["clip"], r["text_frames"])),
                evidence={"frame_text": rows})
        else:
            continue
        fail["warnings"] = frame_text_warnings(rows)
        return rows, fail
    return rows, None


def excerpt_overlay_stage(plan, dry_run=False):
    """FU-U11 -- U9 SEAM. The client excerpt overlay, as DATA, before render.

    THE ONE PLACE an excerpt overlay is handed to a render step. The burn
    itself is U9's artifact and does NOT exist in this tree:

        final_assembler/captions_burn.py :: overlay_excerpt

    Until U9 lands, this function RETURNS A PENDING ROW and burns nothing --
    it never draws text, never reads frame text, and never binds an OCR
    engine. There is exactly ONE caption-burn site in this codebase and it is
    U9's; this is a call site, not a second burn module.

    The excerpt NEVER goes to a video model: ``plan`` carries it under
    ``excerpt_overlay`` (data posted at assembly), while the H3 prompt is
    built from the plan's prompt blocks and never reads this key.

    Returns {"rows": [...], "pending": bool, "reason_code": str|None}.
    """
    overlay = (plan or {}).get("excerpt_overlay")
    if not overlay:
        return {"rows": [], "pending": False, "reason_code": None}
    lines = list(overlay.get("lines") or [])
    if not lines:
        return {"rows": [], "pending": False, "reason_code": None}
    burn = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "captions_burn.py")
    if os.path.isfile(burn):
        # U9 has landed: the burn is its call, not ours.
        import importlib
        mod = importlib.import_module("%s.captions_burn" % __package__
                                      if __package__ else "captions_burn")
        mod.overlay_excerpt(lines, provenance=overlay.get("provenance"))
        return {"rows": [{"hook": "captions_burn.overlay_excerpt",
                          "lines": len(lines), "burned": True}],
                "pending": False, "reason_code": None}
    return {"rows": [{"hook": "captions_burn.overlay_excerpt",
                      "lines": len(lines), "burned": False,
                      "pending": True, "artifact": burn,
                      "artifact_present": False}],
            "pending": True, "reason_code": "BOOK_OVERLAY_UNAVAILABLE"}


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
    # DEL-14: the canvas has to be a real frame the crop-in path can cover.
    # A malformed size would silently clamp the crop and ship a frame short
    # of full height, so it fails here, at load (same 1920x1080 fallback
    # plan_timeline has always applied).
    try:
        _VSF.geometry(tl.get("width", 1920), tl.get("height", 1080))
    except _VSF.StillFillError as _exc:
        raise ValueError(
            "TIMELINE_BAD_SIZE: %s" % (_exc,)) from _exc
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


def probe_stream_duration(path, stream, ffprobe="ffprobe", timeout=30):
    """One stream's own duration in seconds (S75-044).

    ffprobe asks the selected stream (``v:0``, ``a:0``) for its duration.
    A stream that reports none - common for some audio encoders and for
    streamed transport - is measured from its packet timestamps instead, so
    the audio and video are never both read from the container's single
    format duration. Raises RuntimeError when neither answers.
    """
    cmd = [ffprobe, "-v", "error", "-select_streams", stream,
           "-show_entries", "stream=duration", "-of", "json", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"PROBE_UNAVAILABLE: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"PROBE_FAILED: {(proc.stderr or '').strip()[:200]}")
    try:
        streams = json.loads(proc.stdout).get("streams") or []
    except (ValueError, TypeError):
        streams = []
    for s in streams:
        try:
            dur = float(s.get("duration"))
        except (TypeError, ValueError):
            continue
        if dur > 0:
            return dur
    dur = _packet_duration(path, stream, ffprobe, timeout)
    if dur is None or dur <= 0:
        raise RuntimeError(
            f"PROBE_NO_DURATION: stream {stream} reports no duration")
    return dur


def _packet_duration(path, stream, ffprobe="ffprobe", timeout=30):
    """Last packet end from a stream's packet timestamps (S75-044 fallback).

    Used only when the stream itself reports no duration. Returns None when
    no packet carries a usable timestamp.
    """
    cmd = [ffprobe, "-v", "error", "-select_streams", stream,
           "-show_entries", "packet=pts_time,duration_time", "-of", "json",
           str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"PROBE_UNAVAILABLE: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"PROBE_FAILED: {(proc.stderr or '').strip()[:200]}")
    try:
        packets = json.loads(proc.stdout).get("packets") or []
    except (ValueError, TypeError):
        packets = []
    end = None
    for p in packets:
        try:
            pts = float(p.get("pts_time"))
        except (TypeError, ValueError):
            continue
        try:
            dur = float(p.get("duration_time"))
        except (TypeError, ValueError):
            dur = 0.0
        stop = pts + (dur if dur > 0 else 0.0)
        if end is None or stop > end:
            end = stop
    return end


def check_av_drift(output, vdur, frame, ffprobe="ffprobe", timeout=30):
    """S75-044: the audio stream measured on its own, compared to the video.

    Returns (audio_duration, None) when the two streams agree to within one
    frame, or (audio_duration, "AV_DRIFT") when they do not. Raises
    RuntimeError when the audio stream cannot be measured - an unmeasured
    stream is never read as aligned.
    """
    adur = probe_stream_duration(output, "a:0", ffprobe, timeout)
    return adur, ("AV_DRIFT" if abs(adur - vdur) > frame + 1e-3 else None)


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
        # H13: optional first_word_s (seconds into the clip). The fade
        # shrinks (down to a cut) so it ends FADE_WORD_MARGIN_S before it.
        fw = s.get("first_word_s")
        if i > 0 and fw is not None and xd > 0:
            cap = math.floor(max(0.0, fw - FADE_WORD_MARGIN_S) * fps
                             + 1e-9) / fps
            if cap < xd:
                xd = cap
                if xd == 0:
                    trans = "none"
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
        if fw is not None:
            item["first_word_s"] = float(fw)
        # Part F F12: the timeline's per-segment motion_score (the
        # motion_score() dict written by the scoring step) rides the plan
        # so the pre-assembly gate and the receipt read the same row.
        if isinstance(s.get("motion_score"), dict):
            item["motion_score"] = s["motion_score"]
        if isinstance(lids, list) and lids:
            item["lip_sync_line_ids"] = list(lids)
            if isinstance(s.get("lip_lead_s"), (int, float)):
                item["lip_lead_s"] = float(s["lip_lead_s"])   # Part H H1
        # Part H H5: slow-motion factor (shown s / source s, or 1/speed) and
        # the line this picture shows ride the plan for the two gates below.
        item["stretch"] = round(_h5_stretch({**s, "dur": dur}), 3)
        if s.get("shows_line_ids"):
            item["shows_line_ids"] = list(s["shows_line_ids"])
        # Part H H4: who is on screen / visibly speaking, for the face gate.
        # S75-045: the planned on-screen words ride the plan so the text
        # check reads one record for the shots it judges.
        for k in ("shot_id", "faces_on_screen", "speaking_faces", "speaker",
                  "artifact", "on_screen_text"):
            if s.get(k) is not None:
                item[k] = s[k]
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
            "run_dir": tl.get("run_dir"), "run_id": tl.get("run_id"),
            "chosen_length_s": tl.get("chosen_length_s"),
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


# --- H13: cross-fades vs words ------------------------------------------------


def check_fade_before_first_word(plan):
    """H13 gate: the fade into a clip ends FADE_WORD_MARGIN_S before its
    first word. Returns [] or [FADE_COVERS_FIRST_WORD]."""
    eps = 1e-6
    for s in plan["segments"]:
        fw = s.get("first_word_s")
        if fw is not None and s.get("xfade_dur", 0) > 0 \
                and s["xfade_dur"] + FADE_WORD_MARGIN_S > fw + eps:
            return [FADE_COVERS_FIRST_WORD]
    return []


def check_long_gap_hold(plan):
    """H13 gate: a line with an internal word gap above LONG_GAP_S must sit
    wholly inside the fully-opaque span of ONE lip-sync segment (held on
    the speaking face). Lines carry optional words [{start_s, end_s}].
    Returns [] or [LONG_GAP_CUTAWAY]."""
    fps, segs = plan["fps"], plan["segments"]
    spans = []
    for i, s in enumerate(segs):
        nxt = segs[i + 1].get("xfade_frames", 0) if i + 1 < len(segs) else 0
        a = (s["offset_frames"] + s.get("xfade_frames", 0)) / fps
        b = (s["offset_frames"] + s["frames"] - nxt) / fps
        spans.append((a, b, s))
    for ln in plan.get("lines") or []:
        w = ln.get("words") or []
        if not any(w[k + 1]["start_s"] - w[k]["end_s"] > LONG_GAP_S
                   for k in range(len(w) - 1)):
            continue
        held = any(
            s.get("lip_sync") or s.get("lip_sync_line_ids")
            for a, b, s in spans
            if a - 1e-6 <= ln["start_s"] and ln["end_s"] <= b + 1e-6
            and (not s.get("lip_sync_line_ids")
                 or ln["line_id"] in s["lip_sync_line_ids"]))
        if not held:
            return [LONG_GAP_CUTAWAY]
    return []


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


def validate_lipsync_placement(plan, tl):
    """Part H H1 gate: a lip-sync clip sits at its line's real Suno start
    minus its lead-in (segment key "lip_lead_s", written by the lip stage),
    within one frame -- never re-timed. Segments without "lip_lead_s" are
    not checked (legacy timelines). Raises ValueError LIPSYNC_RETIMED.
    Returns the checked count."""
    fps, n = plan["fps"], 0
    starts = {ln["line_id"]: float(ln["start"])
              for sec in (tl.get("timing") or {}).get("sections", [])
              for ln in sec.get("lyrics", [])}
    for s in plan["segments"]:
        lids = s.get("lip_sync_line_ids")
        if not lids or "lip_lead_s" not in s:
            continue
        if lids[0] not in starts:
            raise ValueError("LIPSYNC_WINDOW_UNKNOWN: lip-sync line %r "
                             "missing from the timing map" % (lids[0],))
        want = starts[lids[0]] - s["lip_lead_s"]
        got = s["offset_frames"] / fps
        if abs(got - want) > 1 / fps + 1e-9:
            raise ValueError(
                "LIPSYNC_RETIMED: %r placed at %.3fs but line %r starts at "
                "%.3fs with %.2fs lead-in (want %.3fs); a lip-sync clip is "
                "placed at its real Suno timestamp, never re-timed (Part H "
                "H1)" % (s["src"], got, lids[0], starts[lids[0]],
                         s["lip_lead_s"], want))
        n += 1
    return n


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
        plan.get("total_dur", 0), w, h, run_dir=plan.get("run_dir"))
    segs = plan["segments"]
    fr = 1.0 / fps
    # Load governor: nice -n 10 + -threads min(4, size_ffmpeg) on every ffmpeg argv.
    cmd = _LG.ffmpeg_argv(["-y"], ffmpeg, threads)
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
        # RL1 hold-to-slot: a clip SHORTER than its planned slot is held
        # (last frame cloned via tpad) up to the slot, never trimmed to
        # EOF; a clip LONGER than its slot is trimmed to the slot. Both
        # end on the same second trim, so the master length is the
        # planned length regardless of which side the clip is on.
        # The end second trim + setpt re-assert the exact slot even on
        # the conform path, where minterpolate's boundary rounding can
        # leave a frame.
        pad_step = ""
        if s.get("source_dur"):
            # margin-of-error floor: inside one frame of slot, no pad
            if s["source_dur"] < s["snapped_dur"] - fr:
                pad_step = (f"tpad=stop_mode=clone:stop=-1,"
                            f"trim=duration={s['snapped_dur']:.6f},")
        if conform:
            # H3: minterpolate cannot extrapolate, so it loses ~2 frames at
            # the cut. Trim a margin in, conform, then trim to the exact
            # slot so the segment keeps its planned frame count.
            step = (f"trim=duration={s['snapped_dur'] + 0.25:.6f},"
                    f"setpts=PTS-STARTPTS,{conform},"
                    f"{pad_step}"
                    f"trim=duration={s['snapped_dur']:.6f},"
                    "setpts=PTS-STARTPTS,")
        else:
            step = (f"trim=duration={s['snapped_dur']:.6f},"
                    "setpts=PTS-STARTPTS,"
                    f"{pad_step}"
                    f"trim=duration={s['snapped_dur']:.6f},"
                    "setpts=PTS-STARTPTS,")
        # H3: a pass-through Kling clip (source timebase 1/15360) and an
        # interpolated H3 clip (timebase 1/30) cannot meet in xfade/concat
        # unless every chain ends on the same timebase.
        step += f"settb=1/{fps:g},"
        # DEL-14: full height by crop-in (cover, then cut the overhang off,
        # top anchored), never a bare `scale=W:H` stretch and never a
        # padded or filled backdrop.
        fc.append(f"[{i}:v]{step}{_VSF.cover_crop_filter(w, h)}[v{i}]")
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
        amap = ["-map", vlast, "-map", "[aout]", *delivery_audio.AUDIO_OUT_ARGS]
    else:
        amap = ["-map", vlast, "-an"]
    cmd += ["-filter_complex", ";".join(fc),
            *amap, "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", f"{fps:g}", *delivery_audio.FASTSTART_ARGS, str(output)]
    return cmd


def _run(cmd, timeout=600):
    try:
        return _LG.run_ffmpeg(cmd, "ffmpeg-render", capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"FFMPEG_UNAVAILABLE: {exc}") from exc


def _receipt_evidence():
    """G5: the honest-receipt module (singing_detector.receipt_evidence).

    ponytail: imported lazily so the assembler stays runnable before G3's
    package lands on main; when the train resolve merges G3 this is the
    only import site to flip to a top-level import.
    """
    global _RE
    if _RE is None:
        core_dir = os.path.dirname(os.path.abspath(__file__))
        core_dir = os.path.dirname(core_dir)
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        try:
            from singing_detector import receipt_evidence as _mod
        except ImportError:      # core/ imported as a top-level package
            from singing_detector import receipt_evidence as _mod
        _RE = _mod
    return _RE


_RE = None

def _attach_evidence(receipt, detector_result, target, takes, verdict,
                     planned):
    """G5 amend: put the measured block on ANY receipt this module emits.

    Dry-run receipts are receipts too -- they are what QC reads before a
    spend -- so they carry the same measured sung/spoken/rap/no-voice
    percent + seconds, target, gap and takes as the rendered receipt.
    Raises receipt_evidence.ReceiptEvidenceError (a ValueError) on a
    dishonest or incomplete detector record; the caller refuses it.
    """
    if detector_result is None:
        return receipt
    receipt.update(_receipt_evidence().receipt_block(
        detector_result, target=target, takes=takes, verdict=verdict,
        planned=planned))
    return receipt


def _native_audio_layering(tl):
    """-> None, or a DOUBLE_MUSIC refusal for a timeline that layers a song
    over a take still carrying its generated track.

    A segment opts into this audit by carrying ``native_audio`` (the block
    prompt_templates.native_audio_block wrote for that take). The rule lives
    in prompt_templates.layering_refusal -- one owner for the policy.
    """
    try:
        import prompt_templates as _PT
    except ImportError:                                  # pragma: no cover
        # The policy module is a sibling package of every real deployment; if
        # it is absent the timeline's audio evidence cannot be audited, so the
        # layer fails closed rather than mixing unseen.
        return {"reason_code": "NATIVE_AUDIO_UNAVAILABLE",
                "detail": "prompt_templates is not importable; the take's "
                          "native_audio evidence cannot be audited"}
    for seg in tl.get("segments") or []:
        if not isinstance(seg, dict) or seg.get("native_audio") is None:
            continue
        bad = _PT.layering_refusal(seg.get("native_audio"), soundtrack=True,
                                   audio_dropped=True)
        if bad:
            bad = dict(bad)
            bad["segment"] = seg.get("src")
            bad["native_audio"] = seg.get("native_audio")
            return bad
    return None


def assemble(timeline_path, output, ffmpeg="ffmpeg", ffprobe="ffprobe",
             timeout=None, base_dir=".", dry_run=False, chosen_length_s=None,
             detector_result=None, target=None, takes=None, verdict=None,
             planned=None):
    """RL1 wrapper: run the render, then write the receipt beside the
    output on EVERY outcome (errors included) except dry_run -- the
    headless run reads the file, not a terminal. Returns the receipt."""
    receipt = _assemble(timeline_path, output, ffmpeg=ffmpeg,
                        ffprobe=ffprobe, timeout=timeout, base_dir=base_dir,
                        dry_run=dry_run, chosen_length_s=chosen_length_s,
                        detector_result=detector_result, target=target,
                        takes=takes, verdict=verdict, planned=planned)
    if not dry_run and isinstance(receipt, dict):
        _write_receipt(output, receipt)
    return receipt

def _assemble(timeline_path, output, ffmpeg="ffmpeg", ffprobe="ffprobe",
              timeout=None, base_dir=".", dry_run=False, chosen_length_s=None,
              detector_result=None, target=None, takes=None, verdict=None,
              planned=None):
    """Full render: validate -> preflight -> plan -> ffmpeg -> verify.

    Returns the receipt dict; assemble() (the public wrapper above)
    writes it to <output>.receipt.json on every outcome except dry_run.
    Post-render ffprobe check: |A-V| and |out - planned|
    each within 1 frame; else outcome error with AV_DRIFT/PLAN_DRIFT.
    S75-044: the video and audio durations are each read from their own
    stream, never both from the container's single duration.

    G5 honest receipts (Trevor order 1135, Part G, AMENDED by order 1150
    part G / review G8): when a delivery % rides the receipt it MUST be
    the measured block from the G3 singing detector (``detector_result``)
    -- source=measured, detector name + confidence, the measured sung /
    spoken / rap / no-voice percent AND seconds -- plus ``target``,
    ``gap`` and every take tried. Label time is boxed under labelled_*
    / the ``planned`` heading and never reported as sung. A label-shaped
    sung % is refused (fail-closed), never written.

    ``target`` / ``takes`` / ``verdict`` / ``planned`` feed the amended
    receipt block (singing_detector.receipt_evidence.receipt_block): a
    target-engine ``verdict`` supplies its targets, rounds used and the
    selected take when the caller does not pass them.

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
    if tl.get("run_dir"):
        tl["run_dir"] = os.path.abspath(os.path.join(base, tl["run_dir"]))

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
        # RL1 hold-to-slot: every input is measured (ffprobe), so the
        # render chain knows whether the clip must be HELD to its slot
        # (shorter, tpad clone in build_argv) or TRIMMED to it (longer).
        try:
            s["source_dur"] = probe_duration(s["src"], ffprobe)
        except RuntimeError as exc:
            if not dry_run:
                # a REAL render of an unreadable clip can only die in
                # ffmpeg — refuse it before the spend instead.
                return _fail("INPUT_UNREADABLE", next_action=str(exc),
                             evidence={"src": s["src"]},
                             )
            # dry run stays media-free: no measurement -> no hold decision
            # (today's trim-to-EOF behavior) and the gap is LOUD on the
            # receipt, never silent.
            _loud("warn", "SOURCE_DUR_UNKNOWN",
                  "%s: %s" % (s["src"], exc))
            s["source_dur"] = None
        if not s.get("hold") and s["source_dur"] is not None \
                and s["source_dur"] + 1.0 / plan["fps"] < s["snapped_dur"]:
            s["hold"] = True   # held on its own last frame(s) to the slot
    if plan["song_path"]:
        plan["song_path"] = abspath(plan["song_path"])
    # H3 native audio: H3 returns a stereo track the provider cannot disable,
    # so a timeline that carries a take's native_audio evidence may not lay
    # the approved song over a take that still carries its own generated
    # track. Timelines with no such key assemble exactly as before (clip
    # audio is already dropped: only the song is mapped).
    if plan["song_path"]:
        na_bad = _native_audio_layering(tl)
        if na_bad:
            return _fail(na_bad["reason_code"], next_action=na_bad["detail"],
                         evidence={"segment": na_bad.get("segment"),
                                   "native_audio": na_bad.get("native_audio")})
    # Part E E5: lip-sync clips stay whole — same gate the shot-planner QC
    # path runs, at assembly validation. Render only a plan that passes.
    try:
        validate_lipsync_atomic(plan, tl)
        validate_lipsync_placement(plan, tl)
    except ValueError as exc:
        msg = str(exc)
        return _fail(msg.split(":")[0], next_action=msg, evidence={})
    # Part H H5: slow motion cap + pictures-match-words, before any spend.
    h5_fail, _h5_ev = h5_gates(plan)
    if h5_fail:
        return h5_fail
    # Part I I4: the master (and its end card) ends by chosen length - 2 s.
    # chosen_length_s comes from the caller or the timeline; absent = not
    # checked here (qc_gate still demands it at final_edit).
    chosen = chosen_length_s if chosen_length_s is not None \
        else tl.get("chosen_length_s")
    plan["chosen_length_s"] = chosen
    if chosen is not None:
        try:
            mp = master_length.plan(chosen)
        except ValueError as exc:
            return _fail("MASTER_LENGTH_BAD", next_action=str(exc), evidence={})
        mc = master_length.check_master(chosen, plan["total_dur"])
        ec = plan.get("endcard_start_s")
        if mc.get("warning"):
            # Order 2026-10-21: an overshoot is a FLAG, never a stop; the
            # client decides whether to redo. The named code reaches the receipt.
            _loud("warn", mc["warning"].get("code"), mc["warning"].get("detail"))
        if mc["outcome"] != "ok" or (
                ec is not None and ec >= mp["end_card_end_s"]):
            return _fail(mc["reason_code"] if mc["outcome"] != "ok"
                         else "MASTER_TOO_LONG",
                         next_action=mc["detail"] + "; shorten the timeline "
                         "so the end card finishes by %gs" % mp["end_card_end_s"],
                         evidence=mc)
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
    # H13: fades finish before the first word; long in-line gaps are held.
    for gate, why in (
            (check_fade_before_first_word, "shorten the fade or add "
             "pre-roll so it ends 0.1 s before the first word (H13)"),
            (check_long_gap_hold, "hold the speaking face through the "
             "gap; do not cut away inside one line (H13)")):
        bad = gate(plan)
        if bad:
            return _fail(bad[0], next_action=why, evidence={})
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
            plan.get("height", DEFAULT_HEIGHT), run_dir=plan.get("run_dir"))
    argv = build_argv(plan, output, ffmpeg)
    # DEL-14: refuse an attempted blur fill BEFORE any render spend. The
    # timeline (a renderer asking for a fill), the plan it built and the
    # command (blur, edge-sampled backdrop, duplicated blurred strip,
    # blurred mask, letterbox pad) are all scanned; the only path to full
    # height is crop-in re-lip-sync.
    nb = no_blur.check_render(plan={"timeline": tl, "plan": plan},
                              argv=argv, frame_scan=False)
    if not nb["ok"]:
        return _fail(nb["reason_code"], next_action=nb["reason"],
                     evidence={"qc_no_blur": nb})
    # E6 lip-sync coverage result rides in every receipt; only a FAIL
    # blocks the render. The dry-run receipt exists for exactly this.
    cov = lipsync_gate(plan)
    from lipsync_evidence import check_plan
    export_check = check_plan(plan, require_measured=not dry_run)
    export_fail = None if export_check["pass"] else _fail(
        export_check["reason_code"], next_action="restore the approved storyboard, "
        "matching generation receipts and included materialized clips",
        evidence=export_check["evidence"])
    face = face_speaks_gate(plan)        # Part H H4
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
        # FU-U11: the excerpt overlay row rides the DRY-RUN evidence too, so
        # the pending U9 seam is visible before any render spend.
        _excerpt = excerpt_overlay_stage(plan, dry_run=True)
        out = {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
               "tool_version": TOOL_VERSION, "command": "assemble",
               "outcome": "ok", "reason_code": "DRY_RUN",
               "next_action": "rerun without dry_run to render",
               "evidence": {"argv": argv, "plan": plan,
                            "timeout_s": timeout, "lipsync": cov,
                            "lipsync_export": export_check,
                            "frame_text": frows,
                            "excerpt_overlay": _excerpt,
                            "motion": motion, "h5": _h5_ev,
                            "qc_no_blur": nb},
               # S75-045: a text check nobody could run is named on the
               # receipt, never passed over in silence.
               "warnings": frame_text_warnings(frows),
               "state_version": 0}
        blocked = next((b for b in (cov, face, ffail, export_fail) if b is not None
                        and b.get("outcome") == "error"), None)
        if blocked is not None:  # blocked before spend, but evidence stays
            out["outcome"] = "error"
            out["reason_code"] = blocked["reason_code"]
            out["next_action"] = blocked["next_action"]
            out.setdefault("evidence", {}).setdefault("gate_evidence", {})
            out["evidence"]["gate_evidence"] = blocked["evidence"]
        try:
            _attach_evidence(out, detector_result, target, takes, verdict,
                             planned)
        except ValueError as exc:
            return _fail("DISHONEST_SUNG_PCT", next_action=str(exc),
                         evidence={"detector_result": detector_result})
        return out
    for blocked in (cov, face, ffail, export_fail):   # gate FAILs: no render spend (17.5)
        # Missing lip-sync evidence is a failure and blocks before rendering.
        if blocked is not None and blocked.get("outcome") == "error":
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
    # S75-044: the video duration is the video stream's own, so the audio
    # stream is measured and compared against it separately below.
    try:
        vdur = probe_stream_duration(output, "v:0", ffprobe)
    except RuntimeError as exc:
        return _fail("VERIFY_UNAVAILABLE", next_action=str(exc),
                     evidence={"output": str(output)})
    frame = 1.0 / plan["fps"]
    evid = {"planned_dur": plan["total_dur"], "output_dur": vdur,
            "total_frames": plan["total_frames"], "argv": argv,
            "timeout_s": timeout,
            # F12: every clip's motion score rides in the receipt
            # (scored before the render; flagged clips never reached here).
            "motion": motion, "h5": _h5_ev}
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
    # RL1 hold-to-slot accounting: a held (tpad-cloned) span IS a
    # deliberate still — its own frozen frames are the hold, and the whole
    # mpdecimate run over the master would otherwise count them (and an
    # xfade boundary into the next clip) against the conform gate. The
    # per-segment report polices every NON-held window at the SAME cap,
    # so only the pure (all-trim/non-held) master path runs the
    # master-level assert. Same cap, honest accounting, nothing loosened.
    holds = [s for s in plan["segments"] if s.get("hold")]
    if holds:
        evid["dup_frame_gate"] = "PASS_VIA_HOLD" if not seg_bad else "SEGMENTS_FAIL"
    else:
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
    if chosen is not None:  # I4: the measured file, not only the plan
        mc = master_length.check_master(chosen, vdur)
        if mc.get("warning"):
            _loud("warn", mc["warning"].get("code"), mc["warning"].get("detail"))
        if mc["outcome"] != "ok":
            return _fail(mc["reason_code"], next_action=mc["detail"],
                         evidence=dict(evid, master=mc))
    if abs(vdur - plan["total_dur"]) > frame + 1e-3:
        return _fail("PLAN_DRIFT",
                     next_action="output duration off plan by >1 frame",
                     evidence=evid)
    if plan["song_path"]:
        # S75-044: the audio stream's own duration, never the container's
        # format duration (which is the video's, and made this check pass
        # by construction). An unmeasurable stream fails closed.
        try:
            adur, av_code = check_av_drift(output, vdur, frame, ffprobe)
        except RuntimeError as exc:
            return _fail("VERIFY_UNAVAILABLE", next_action=str(exc),
                         evidence=evid)
        evid["audio_dur"] = adur
        if av_code:
            return _fail("AV_DRIFT",
                         next_action="audio/video differ by >1 frame",
                         evidence=evid)
    if plan["song_path"]:  # FU-AAC-FINAL-MUX delivery gate: AAC, not silent
        ag = delivery_audio.check_delivery_audio(output, ffprobe, ffmpeg)
        evid["delivery_audio"] = ag
        if not ag["ok"]:
            return _fail(ag["reason_code"], next_action=ag["reason"],
                         evidence=evid)
    # DEL-14: the produced frame itself. A fill that landed anyway is refused
    # here, before anything is delivered: a frame short of full height
    # because of a fill, an edge-sampled backdrop, a gaussian-filled
    # background, a duplicated blurred strip, a blurred mask or letterbox
    # bars. The repair is crop-in re-lip-sync, never a fill.
    nf = no_blur.check_render(
        output=output, expect_width=plan.get("width"),
        expect_height=plan.get("height"), ffmpeg=ffmpeg, ffprobe=ffprobe)
    evid["qc_no_blur"] = nf
    if not nf["ok"]:
        return _fail(nf["reason_code"], next_action=nf["reason"],
                     evidence=evid)
    # Load governor: the master is verified; delete the stage intermediates the
    # timeline lists (never deliverables), log each deletion, record heavy-job waits.
    reg = _LG.StageRegistry()
    reg.register("assemble", [abspath(p) for p in tl.get("intermediates", [])])
    evid["cleanup"] = reg.consumed("assemble", output)
    evid["load_governor"] = _LG.receipt()
    # Preserve the lip-sync gate evidence on the rendered receipt.
    evid["lipsync"] = cov
    evid["lipsync_export"] = export_check
    evid["lipsync_plan"] = plan
    receipt = {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
               "tool_version": TOOL_VERSION, "command": "assemble",
               "outcome": "ok", "reason_code": "ASSEMBLED",
               "next_action": "QC per directive 17.5 (independent reviewer)",
               "evidence": evid, "state_version": 0,
               # H12: QC fails any master this receipt does not vouch for.
               "produced_by": master_provenance.producer_stamp(),
               "master_sha256": master_provenance.sha256_file(output)}
    # G5 (amended): a delivery % on the receipt only via the measured
    # detector block, and it arrives with target, gap and every take tried.
    if detector_result is not None:
        try:
            receipt.update(_receipt_evidence().receipt_block(
                detector_result, target=target, takes=takes,
                verdict=verdict, planned=planned))
        except ValueError as exc:
            return _fail("DISHONEST_SUNG_PCT", next_action=str(exc),
                         evidence={"detector_result": detector_result})
    # No silent failure: every recorded FAILURE/WARNING rides the receipt.
    _loud_attach(receipt)
    # S75-045: the text check's own UNAVAILABLE warnings ride beside them.
    receipt["warnings"] = list(receipt.get("warnings") or []) \
        + frame_text_warnings(evid.get("frame_text") or [])
    return receipt


def _write_receipt(output, receipt):
    """RL1: every assemble() outcome writes its receipt beside the output
    (headless QC reads files, not a terminal). One shared writer."""
    try:
        with open(str(output) + ".receipt.json", "w",
                  encoding="utf-8") as fh:
            json.dump(receipt, fh, indent=2)
        return True
    except OSError as exc:
        _loud("fail", "RECEIPT_WRITE_FAILED",
              "%s.receipt.json: %s" % (output, exc))
        _loud_attach(receipt)
        return False


# --- U-V03 (S75-055): the planning step writes edit/timeline.json ------------
#
# edit/timeline.json is the one file this assembler, the clip cutter
# (delivery_clips) and the trailer cutter read, and factory.py's `assembly`
# stage command names it -- but no production module wrote it. Only the proof
# run and tests built one by hand (S75-055). plan_run_timeline() is that
# writer: the run-level planning step, beside plan_timeline() which stays the
# pure frame plan over a timeline that already exists.
#
# Every value comes from a record on disk; a value that no record holds is the
# named refusal TIMELINE_INPUT_MISSING:<what>, never a default.

TIMELINE_INPUT_MISSING = "TIMELINE_INPUT_MISSING"

#: the run's own records, exactly where its stage commands keep them.
RECORD_SHOT_LIST = "storyboard/shot-list.json"
RECORD_APPROVAL = "storyboard/approval.json"
RECORD_CLIPS = "video/clips.json"
RECORD_TIMINGS = "music/word-timings.json"
RECORD_SESSION = "control/intake-session.json"
RECORD_METHOD = "control/method.json"
RECORD_SONGS = ("music/picked-song.mp3", "music/mix.mp3")


class TimelineInputMissing(ValueError):
    """A timeline value no record on disk holds (named, never defaulted)."""

    def __init__(self, what, detail=""):
        self.what = what
        self.code = TIMELINE_INPUT_MISSING
        super().__init__("%s:%s%s" % (TIMELINE_INPUT_MISSING, what,
                                      (" (%s)" % detail) if detail else ""))


def _run_json(root, rel):
    """One record from the run folder, or the named refusal when it is absent."""
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise TimelineInputMissing(rel, str(exc)) from exc


def _run_rel(root, path):
    """A record's file path as the timeline writes it: run-relative."""
    if not isinstance(path, str) or not path.strip():
        raise TimelineInputMissing("clip path", RECORD_CLIPS)
    full = os.path.abspath(path if os.path.isabs(path)
                           else os.path.join(root, path))
    try:
        rel = os.path.relpath(full, root)
    except ValueError:                       # another drive (Windows)
        return path
    return path if rel.startswith("..") else rel


def _measured_words(root):
    """The picked song's measured word timings (music/word-timings.json).

    Accepts the DEL-13 receipt shape (``{"words": [...], "source": ...}``)
    and the ``provide_word_timings`` envelope (``{"ok": true, "timings":
    {...}}``). The ``source`` must be one timestamp_plan calls a REAL timing
    of the finished song: planned or packet timings are refused, never used
    as if they were measured.
    """
    doc = _run_json(root, RECORD_TIMINGS)
    timings = doc.get("timings") if isinstance(doc, dict) \
        and isinstance(doc.get("timings"), dict) else doc
    if not isinstance(timings, dict):
        raise TimelineInputMissing(RECORD_TIMINGS, "not a timing record")
    core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    from shot_planner import timestamp_plan as _tp
    source = timings.get("source")
    if source not in _tp.REAL_TIMING_SOURCES:
        raise TimelineInputMissing(
            "measured word timings",
            "%s carries source %r, which is not a measured timing of the "
            "finished song" % (RECORD_TIMINGS, source))
    words = []
    for w in timings.get("words") or []:
        if not isinstance(w, dict):
            raise TimelineInputMissing("word timing", RECORD_TIMINGS)
        st = w.get("start", w.get("startS"))
        en = w.get("end", w.get("endS"))
        if isinstance(st, bool) or isinstance(en, bool) \
                or not isinstance(st, (int, float)) \
                or not isinstance(en, (int, float)) or en <= st:
            raise TimelineInputMissing("word timing", repr(w))
        words.append({"word": str(w.get("word") or ""),
                      "start": float(st), "end": float(en)})
    if not words:
        raise TimelineInputMissing("measured word timings",
                                   "%s carries no words" % RECORD_TIMINGS)
    return sorted(words, key=lambda w: w["start"])


def _clip_rows(root):
    """The materialized clip rows (video/clips.json), keyed by shot id.

    Each row is the run's own record of one materialized clip: its path, its
    recorded sha256, the dispatch receipt it came from and the task id -- the
    lip-sync evidence lipsync_evidence.check_plan joins at assembly. A row
    may also carry the measured ``motion_score`` (F12).
    """
    doc = _run_json(root, RECORD_CLIPS)
    rows = doc.get("clips") if isinstance(doc, dict) else doc
    if not isinstance(rows, list) or not rows:
        raise TimelineInputMissing(RECORD_CLIPS, "no clip rows")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("shot_id") or "").strip():
            raise TimelineInputMissing(RECORD_CLIPS, "a clip row carries no shot_id")
        out[str(row["shot_id"])] = row
    return out


def _run_id_of(root):
    """The run's own id (control/intake-session.json) -- never the folder name."""
    session = _run_json(root, RECORD_SESSION)
    run_id = session.get("run_id") if isinstance(session, dict) else None
    if not isinstance(run_id, str) or not run_id.strip():
        raise TimelineInputMissing("run_id", RECORD_SESSION)
    return run_id


def _song_record(root):
    """The run's soundtrack file, first one its records name that exists."""
    for rel in RECORD_SONGS:
        if os.path.isfile(os.path.join(root, rel)):
            return rel
    raise TimelineInputMissing(RECORD_SONGS[0], "no picked song or mix on disk")


def _motion_of(sid, row, src_abs, scorer):
    """A clip's F12 motion score: the record's, else MEASURED from the clip.

    Read from the clip row when the row carries it; otherwise measured from
    the materialized clip file (a record on disk) by the scoring owner
    (shot_planner.motion_score). Never defaulted: a score nobody could read
    is TIMELINE_INPUT_MISSING:motion_score:<shot>.
    """
    ms = row.get("motion_score")
    if isinstance(ms, dict) and isinstance(ms.get("score"), (int, float)) \
            and not isinstance(ms.get("score"), bool):
        return ms
    try:
        got = scorer(clip_path=src_abs)
    except Exception as exc:                    # noqa: BLE001 - named refusal
        raise TimelineInputMissing("motion_score:" + sid, str(exc)) from exc
    if not isinstance(got, dict) or not isinstance(got.get("score"), (int, float)) \
            or isinstance(got.get("score"), bool):
        raise TimelineInputMissing("motion_score:" + sid,
                                   "the scorer returned no score")
    return got


def _default_motion_scorer(clip_path):
    core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    import shot_planner.motion_score as _ms
    return _ms.motion_score(clip_path=clip_path)


def plan_run_timeline(run_dir, out_path=None, width=None, height=None,
                      motion_scorer=None):
    """The run-level planning step: write <run>/edit/timeline.json atomically.

    Composes the timeline from the run's OWN records, one value at a time:

    * the approved storyboard -- storyboard/shot-list.json (the approved shot
      plan) plus storyboard/approval.json (state "approved", one approved
      entry per shot, and the same shot identities);
    * the picked song's measured word timings -- music/word-timings.json:
      each line's window is the measured word run inside its approved shot
      window, so a line time is never invented;
    * the lip-sync evidence -- video/clips.json: each shot's materialized
      clip path, recorded sha256, dispatch receipt and task id;
    * the soundtrack (music/picked-song.mp3, else music/mix.mp3), the run id
      (control/intake-session.json) and, when recorded, the chosen length
      (control/method.json).

    The candidate file is written to a temporary name in the same folder and
    validated with load_timeline() BEFORE it replaces the old one, so a bad
    plan never lands as edit/timeline.json. Returns the written path. Raises
    TimelineInputMissing naming the record that is absent; nothing is
    defaulted.
    """
    root = os.path.abspath(str(run_dir))
    if not os.path.isdir(root):
        raise TimelineInputMissing("run_dir", root)
    path = out_path or os.path.join(root, "edit", "timeline.json")
    fps = fps_conform.MASTER_FPS
    width = int(width if width is not None else DEFAULT_WIDTH)
    height = int(height if height is not None else DEFAULT_HEIGHT)
    scorer = motion_scorer or _default_motion_scorer

    shot_doc = _run_json(root, RECORD_SHOT_LIST)
    shots = shot_doc.get("shots") if isinstance(shot_doc, dict) else shot_doc
    if not isinstance(shots, list) or not shots:
        raise TimelineInputMissing(RECORD_SHOT_LIST, "no shots")
    approval = _run_json(root, RECORD_APPROVAL)
    if not isinstance(approval, dict) or approval.get("state") != "approved":
        raise TimelineInputMissing("approved storyboard",
                                   "%s does not record state 'approved'"
                                   % RECORD_APPROVAL)
    approved = approval.get("shots")
    if not isinstance(approved, dict) or not approved:
        raise TimelineInputMissing("approved storyboard",
                                   "%s carries no per-shot approvals"
                                   % RECORD_APPROVAL)
    words = _measured_words(root)
    clips = _clip_rows(root)
    run_id = _run_id_of(root)
    song_path = _song_record(root)
    chosen = None
    if os.path.isfile(os.path.join(root, RECORD_METHOD)):
        method = _run_json(root, RECORD_METHOD)
        value = method.get("chosen_length_s") if isinstance(method, dict) else None
        if type(value) is int and value > 0:
            chosen = value

    lines, sections, segments = [], [], []
    seen_lines, seen_shots = set(), set()
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise TimelineInputMissing("shot record", "%s[%d]" % (RECORD_SHOT_LIST, index))
        sid = shot.get("shot_id")
        if not isinstance(sid, str) or not sid.strip():
            raise TimelineInputMissing("shot_id", "%s[%d]" % (RECORD_SHOT_LIST, index))
        if sid in seen_shots:
            raise TimelineInputMissing("duplicate shot_id", sid)
        seen_shots.add(sid)
        entry = approved.get(sid)
        if not isinstance(entry, dict) or entry.get("status") != "approved":
            raise TimelineInputMissing("storyboard approval for " + sid,
                                       "%s records no approved entry" % RECORD_APPROVAL)
        start, end = shot.get("song_start"), shot.get("song_end")
        if isinstance(start, bool) or isinstance(end, bool) \
                or not isinstance(start, (int, float)) \
                or not isinstance(end, (int, float)) or not start < end:
            raise TimelineInputMissing("shot window", sid)
        lids = shot.get("lyric_line_ids")
        if not isinstance(lids, list) or len(lids) != 1 \
                or not isinstance(lids[0], str) or not lids[0].strip():
            # One approved shot carries one line: a multi-line shot has no
            # recorded per-line window, and splitting it would be invented.
            raise TimelineInputMissing(
                "one line per shot",
                "%s lyric_line_ids=%r; a multi-line shot's per-line windows "
                "are in no record" % (sid, lids))
        lid = lids[0]
        if lid in seen_lines:
            raise TimelineInputMissing("duplicate line_id", lid)
        seen_lines.add(lid)
        inside = [w for w in words
                  if w["start"] >= start - 1e-6 and w["end"] <= end + 1e-6]
        if not inside:
            raise TimelineInputMissing(
                "measured words for " + lid,
                "shot %s window %.3f-%.3f holds no measured word of the "
                "picked song" % (sid, start, end))
        line_start = inside[0]["start"]
        line_end = inside[-1]["end"]
        text = " ".join(w["word"] for w in inside).strip()
        speaker = shot.get("speaker")
        lips = bool(shot.get("lip_sync") or shot.get("lip_sync_line_ids"))
        if lips:
            recorded = shot.get("lip_sync_line_ids")
            if not isinstance(recorded, list) or lid not in recorded:
                raise TimelineInputMissing("lip_sync_line_ids", sid)
            if not isinstance(speaker, str) or not speaker.strip():
                raise TimelineInputMissing("speaker", sid)
        faces = shot.get("character_ids")
        if not isinstance(faces, list) or not all(isinstance(f, str) and f.strip()
                                                  for f in faces):
            raise TimelineInputMissing("character_ids", sid)

        row = clips.get(sid)
        if row is None:
            raise TimelineInputMissing("clip row for " + sid, RECORD_CLIPS)
        src = _run_rel(root, row.get("path"))
        sha = row.get("sha256")
        if not isinstance(sha, str) or not sha.strip():
            raise TimelineInputMissing("clip sha256 for " + sid, RECORD_CLIPS)
        artifact = {"schema_version": "1.0.0", "kind": "video",
                    "run_id": run_id,
                    "artifact_id": str(row.get("artifact_id") or sid),
                    "stage": "generation",
                    "stale": bool(row.get("stale", False)),
                    "path": src, "sha256": sha}
        if lips:
            receipt = row.get("receipt_path")
            task = row.get("task_id")
            if not isinstance(receipt, str) or not receipt.strip():
                raise TimelineInputMissing("receipt_path for " + sid,
                                           RECORD_CLIPS)
            if not isinstance(task, str) or not task.strip():
                raise TimelineInputMissing("task_id for " + sid, RECORD_CLIPS)
            artifact["provenance"] = {"task_id": task,
                                      "receipt_path": _run_rel(root, receipt)}
        src_abs = os.path.join(root, src)
        segment = {"src": src, "dur": round(float(end) - float(start), 6),
                   "shot_id": sid, "lip_sync": lips,
                   "faces_on_screen": list(faces),
                   "motion_score": _motion_of(sid, row, src_abs, scorer),
                   "artifact": artifact, "scene_index": index}
        if lips:
            segment["lip_sync_line_ids"] = list(shot["lip_sync_line_ids"])
            segment["speaking_faces"] = [speaker]
        if isinstance(speaker, str) and speaker.strip():
            segment["speaker"] = speaker
        for key in ("transition", "beat_cut", "shows_line_ids", "on_screen_text"):
            if shot.get(key) is not None:
                segment[key] = shot[key]
        segments.append(segment)
        line = {"line_id": lid, "start_s": line_start, "end_s": line_end,
                "text": text}
        line["speaker"] = speaker if isinstance(speaker, str) else None
        if not (isinstance(line["speaker"], str) and line["speaker"].strip()):
            line.pop("speaker")
        lines.append(line)
        sections.append({"section_id": sid, "lyrics": [
            {"line_id": lid, "start": line_start, "end": line_end,
             "text": text}]})

    if seen_shots != set(approved):
        raise TimelineInputMissing(
            "storyboard approval scope",
            "the approved shot ids differ from the current shot list")

    timeline = {"schema_version": TIMELINE_SCHEMA, "fps": fps,
                "width": width, "height": height,
                "song_path": song_path, "run_dir": "..", "run_id": run_id,
                "segments": segments, "lines": lines,
                "timing": {"sections": sections}}
    if chosen is not None:
        timeline["chosen_length_s"] = chosen
    return _write_timeline_atomic(path, timeline)


def _write_timeline_atomic(path, timeline):
    """Write the candidate, validate it with load_timeline(), then replace."""
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".timeline-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(timeline, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        load_timeline(tmp)          # the plan is validated before it lands
        os.replace(tmp, path)
        return path
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(prog="final_assembler",
                                 description="timeline.json -> ffmpeg render")
    ap.add_argument("timeline", help="timeline.json path")
    ap.add_argument("output", help="output mp4 path")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chosen-length-s", type=float, default=None,
                    help="I4: chosen video length; master must be <= this - 2")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--timeout", type=int, default=None,
                    help="render cap in seconds; default: lane_size.py "
                         "or Part D max(600, 2 x output s x 1080p factor)")
    ap.add_argument("--detector-result", default=None,
                    help="path to the G3 singing-detector result JSON; "
                         "the only legal source of a receipt sung %% (G5)")
    ap.add_argument("--target", default=None,
                    help="inline JSON target set (e.g. "
                         "'{\"sung_share\":0.55}') for the receipt's "
                         "target/gap fields (G5 amend)")
    ap.add_argument("--takes", default=None,
                    help="path to the JSON list of every take tried, each "
                         "measured or carrying its reason (G5 amend)")
    ap.add_argument("--verdict", default=None,
                    help="path to a target_engine verdict JSON; supplies "
                         "target, rounds used and the selected take")
    ap.add_argument("--run-dir", default=None,
                    help="U-V03: the run folder. When TIMELINE does not exist "
                         "yet, the planning step writes it from the run's own "
                         "records (plan_run_timeline) before assembling")
    args = ap.parse_args(argv)
    if args.run_dir and not os.path.isfile(args.timeline):
        # U-V03 (S75-055): the planning step writes edit/timeline.json; an
        # existing timeline is never rewritten behind a run.
        try:
            path = plan_run_timeline(args.run_dir, args.timeline)
        except (TimelineInputMissing, ValueError) as exc:
            msg = str(exc)
            print(json.dumps(_fail(msg.split(":")[0], next_action=msg)))
            return EXIT["error"]
        print(json.dumps({"timeline": path, "outcome": "ok",
                          "reason_code": "TIMELINE_WRITTEN"}))
    if not shutil.which(args.ffmpeg) or not shutil.which(args.ffprobe):
        print(json.dumps(_fail("PREREQ_MISSING",
                               next_action="install ffmpeg+ffprobe")))
        return 3

    def _load_json(path, what):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps(_fail("%s_UNREADABLE" % what.upper(),
                                   next_action=str(exc))))
            return None

    det = None
    if args.detector_result:
        det = _load_json(args.detector_result, "detector_result")
        if det is None:
            return 1
    tgt = None
    if args.target:
        try:
            tgt = json.loads(args.target)
        except json.JSONDecodeError as exc:
            print(json.dumps(_fail("TARGET_UNREADABLE",
                                   next_action=str(exc))))
            return 1
    tks = None
    if args.takes:
        tks = _load_json(args.takes, "takes")
        if tks is None:
            return 1
    ver = None
    if args.verdict:
        ver = _load_json(args.verdict, "verdict")
        if ver is None:
            return 1
    receipt = assemble(args.timeline, args.output, ffmpeg=args.ffmpeg,
                       chosen_length_s=args.chosen_length_s,
                       ffprobe=args.ffprobe, timeout=args.timeout,
                       dry_run=args.dry_run, detector_result=det,
                       target=tgt, takes=tks, verdict=ver)
    receipt = _loud_attach(receipt)
    print(json.dumps(receipt, indent=2))
    for ln in (receipt.get("warnings") or []) + (receipt.get("failures") or []):
        print("%s %s: %s" % (ln["kind"], ln["code"], ln["detail"]),
              file=sys.stderr)
    return EXIT["ok"] if receipt["outcome"] == "ok" else EXIT["error"]


if __name__ == "__main__":
    sys.exit(main())
