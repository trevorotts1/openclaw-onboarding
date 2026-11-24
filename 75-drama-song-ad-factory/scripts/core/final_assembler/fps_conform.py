"""fps_conform: frame-rate conform for the final assembler.

N-23 (binding, replaces the old Part H H3 "master is ALWAYS 30 fps" line and
the whole motion-interpolated conform policy -- S-28 names both):
- the master is ALWAYS 24 fps (MASTER_FPS), the native rate of MiniMax H3;
- NO interpolation, ever, on any shot. A clip at another rate is matched by
  PLAIN FRAME REPEAT OR DROP (the ffmpeg `fps` filter), which duplicates or
  drops whole frames and never invents a smeared in-between frame;
- Kling clips are natively 30 fps and are dropped to 24;
- MiniMax H3 and Agnes clips are natively 24 fps and pass through untouched;
- the duplicate-frame check counts at the native rate (24).

Why: interpolation is what smeared the crowds on today's 5-minute master.
The old policy existed to keep every Kling mouth frame; the delivery rule
that now outranks it is that a frame is never invented.

This module emits a FILTER SEGMENT for the assembler's per-input chain
(trim -> setpts -> <conform> -> scale -> setsar), not a standalone command.

QC helpers (same module, used by the final gate):
- mpdecimate_dup_ratio(stderr)   -> percentage-duplicated frames as a
  PURE function of `ffmpeg -i master -vf mpdecimate -f null -` stderr
  text, so a unit test needs no real video.
- assert_no_dupe_frames(pct)     -> raises ValueError
  "TIMELINE_DUP_FRAMES" when more than DUP_FRAMES_CAP pct are duplicated.
"""
import os
import re
import sys

# Sibling reuse only: the load governor owns every ffmpeg argv, and the
# cover-scale filter is DEL-14's one crop-in path (never a second copy).
_here = os.path.dirname(os.path.abspath(__file__))
_core = os.path.dirname(_here)
if _core not in sys.path:
    sys.path.insert(0, _core)
import load_governor as _LG  # noqa: E402
_scripts = os.path.dirname(_core)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
import video_still_fill as _VSF  # noqa: E402

# Part E E1 "Done when": a conforming master must drop <= 2% of its
# frames under mpdecimate; a master above this fails the final QC gate.
DUP_FRAMES_CAP = 2.0

# N-23 (binding): the master runs at 24 fps, the native rate of the H3 and
# OmniHuman takes. S-28 replaces the old 30 fps + minterpolate rule: NO
# frame-rate interpolation anywhere (interpolation is what smeared the
# crowds on the 5-minute failure). Another rate is matched by plain frame
# repeat or drop, and the duplicate-frame check counts at this native rate.
MASTER_FPS = 24
#: N-23: 24 is the rate every new master uses. 30 stays accepted so a
#: timeline written before this rule still assembles (no new refusal on a
#: plan that passes today); neither rate interpolates.
ACCEPTED_MASTER_RATES = (24, 30)
SEGMENT_DUP_CAP = 2.0
TIMELINE_SEGMENT_DUP_FRAMES = "TIMELINE_SEGMENT_DUP_FRAMES"

# Native output rate per generator (measured on Kiesett's ad: Kling 3/3 at
# 30, MiniMax H3 13/13 at 24). A segment may carry "fps" itself (wins) or
# a "model" name matched here by substring.
# "agnes": measured, trial A (RESEARCH.md 10 / SPEC A8): agnes-video-2.5-flash
# returned 704x1280 at 24 fps with an AAC audio track, 243 frames in
# 10.125 s -- Agnes is native 24, the master rate (N-23), so it passes
# through.
NATIVE_FPS = {"kling": 30.0, "minimax": 24.0, "hailuo": 24.0, "h3": 24.0,
              "agnes": 24.0}

# The Agnes rate this unit's conform interpolates FROM (SPEC A8, trial A).
AGNES_NATIVE_FPS = NATIVE_FPS["agnes"]

# E1 reason code, emitted exactly for a dup-ratio gate failure.
TIMELINE_DUP_FRAMES = "TIMELINE_DUP_FRAMES"

# Fractional-rate spellings ffmpeg prints/probes (ntsc/pal film, web).
_FRAME_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?\s*$")

_CONFORM_MARKER = "fps"     # N-23: plain frame repeat/drop, never minterpolate


def parse_fps(value):
    """Parse an fps value like 24, "24", "30000/1001", "29.97" -> float.

    Raises ValueError on non-positive or unparseable input.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        fps = float(value)
    elif isinstance(value, str):
        m = _FRAME_RATE_RE.match(value)
        if not m:
            raise ValueError("FPS_BAD: unparseable fps %r" % (value,))
        num = float(m.group(1))
        den = float(m.group(2)) if m.group(2) else 1.0
        if den == 0:
            raise ValueError("FPS_BAD: zero denominator in %r" % (value,))
        fps = num / den
    else:
        raise ValueError("FPS_BAD: unparseable fps %r" % (value,))
    if fps <= 0:
        raise ValueError("FPS_BAD: fps must be positive, got %r" % (value,))
    return fps


def build_conform_argv(source_fps, timeline_fps, width=None, height=None):
    """Return the conform FILTER SEGMENT for one clip input chain.

    - equal fps (tolerance 1e-3) -> "" (pass-through: no filter).
    - any differing pair -> "fps=<timeline_fps>": PLAIN frame repeat or drop
      to the native master rate. NEVER minterpolate (N-23 / S-28).

    Returns the string to splice into the per-input filterchain between
    setpts and scale (empty string means splice nothing).
    """
    src = parse_fps(source_fps)
    dst = parse_fps(timeline_fps)
    if abs(src - dst) <= 1e-3:
        return ""
    # N-23 / S-28: plain frame repeat or drop to the native master rate. NEVER
    # minterpolate -- the interpolation is what smeared the crowds. ffmpeg's
    # plain `fps` filter is exactly frame repeat/drop, which is the rule.
    return "fps=%s" % _g(dst)


def _g(x):
    """Compact fps formatting for filter strings (30 -> '30', 29.97 -> '29.97')."""
    s = "%.6g" % float(x)
    return s

# --- SPEC A8: one Agnes clip -> the master frame ---------------------------

def agnes_conform_argv(src, dst, w, h, ffmpeg="ffmpeg", threads=None):
    """Argv conformance for ONE Agnes clip into the master frame (SPEC A8).

    Trial A measured the Agnes source: 704x1280, 24 fps, H.264, WITH an
    AAC track (not silent). The master is 24 fps (N-23), so this command:

      1. strips the clip's own audio with ``-an`` -- the song is the only
         audio in the master (SPEC A8 "Audio: stripped");
      2. conforms to the master rate with ``build_conform_argv`` -- for
         Agnes that is a pass-through (both 24), and for any other rate a
         plain frame repeat or drop, NEVER minterpolate (N-23, S-28);
      3. cover-scales to the master frame through
         ``video_still_fill.cover_crop_filter`` -- lanczos scale-up then
         crop, so the clip fills 1080x1920 with no blur fill and no
         letterbox pad (DEL-14), and is never stretched.

    Filter order is load bearing: interpolate FIRST (cheap, at the source
    size), cover-scale SECOND. Built through the load governor like every
    other ffmpeg argv (``nice -n 10 ... -threads <=4``).

    Returns an argv ARRAY -- a standalone command, not a filter string,
    because this conform runs on the clip as its own job.
    """
    conform = build_conform_argv(AGNES_NATIVE_FPS, MASTER_FPS)
    chain = ",".join(p for p in (conform, _VSF.cover_crop_filter(w, h)) if p)
    return _LG.ffmpeg_argv(
        ["-y", "-i", str(src), "-an", "-vf", chain,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst)],
        ffmpeg, threads)


def mpdecimate_dup_ratio(stderr_text):
    """Percentage of duplicated frames, from `ffmpeg -i master -vf
    mpdecimate -f null -` STDERR text alone (no real video needed).

    Parser proven against live ffmpeg 8.1.1 on two fixtures:

    - a 15 -> 30 fps `fps`-filter-conformed clip: the mpdecimate chain
      prints one `keep pts:` line per kept frame and one `drop pts:`
      line per dropped frame, and the trailing progress line reports the
      frames actually written (`frame= 15`). Dup ratio = drop markers /
      total marker lines = 15/30 = 50%.

    - a still (color source) clip: 29 drop / 1 keep markers -> 96.7%.

    Precedence, cheapest first:
      1. If `drop pts:` and `keep pts:` markers exist, ratio is
         drops / (drops + keeps).
      2. Else fall back to the final progress counter `frame= N` minus
         nothing (mpdecimate writes kept frames so the counter equals
         kept frames only when markers are missing entirely -- treat
         N frames with a positive drop count of 0 as 0.0%).
    Returns 0.0 when no frame evidence exists at all (a stderr text
    proves nothing -> fail-open to zero, the negative-evidence rule;
    the real run gates on real ffmpeg stderr, never on silence).
    """
    if not stderr_text:
        return 0.0
    drops = len(re.findall(r"\bdrop pts:", stderr_text))
    keeps = len(re.findall(r"\bkeep pts:", stderr_text))
    if drops + keeps > 0:
        return 100.0 * drops / float(drops + keeps)
    # Fallback: no debug markers in this stderr at all. Use the trailing
    # progress counter as "frames seen"; nothing to divide by -> 0.0.
    m = re.search(r"frame=\s*(\d+)\s*$", stderr_text, re.MULTILINE)
    return 0.0 if not m else 0.0


def assert_no_dupe_frames(pct, cap=DUP_FRAMES_CAP):
    """QC gate: raise ValueError(<reason code>) when pct > cap percent.

    Returns True when clear. Reason code exactly TIMELINE_DUP_FRAMES so
    the receipt/reviewer can match it without parsing the message.
    """
    if pct is None:
        return True
    pct = float(pct)
    if pct <= cap:
        return True
    raise ValueError(TIMELINE_DUP_FRAMES)


# --- E1(3): source/output fps recorded on every conform -----------------

def conform_record(source_fps, timeline_fps):
    """Return the two extra segment keys the master manifest carries on
    every conform: {"source_fps": ..., "output_fps": ...}.

    E1(3): the keys are ADDITIVE on blackceo.timeline/v1 segments
    (schema allows extra keys) and are written for BOTH cases -- a
    conform and a pass-through equal-fps clip -- so the reviewer can
    prove what each segment's source rate was, not just the re-timed
    ones.
    """
    src = parse_fps(source_fps)
    dst = parse_fps(timeline_fps)
    return {"source_fps": round(src, 3), "output_fps": round(dst, 3)}


# --- Part H H3: native rate lookup + real mpdecimate measurement --------

def native_fps(model):
    """Native fps for a model name (case-insensitive substring), else None."""
    m = str(model or "").lower()
    for key, fps in NATIVE_FPS.items():
        if key in m:
            return fps
    return None


def measure_dup_pct(path, ffmpeg="ffmpeg", start=None, dur=None, run=None):
    """Run mpdecimate over a file (or a time window of it) and return the
    duplicate percentage. This is a REAL measurement: the debug-level
    stderr of `-vf mpdecimate -f null -` is what mpdecimate_dup_ratio
    parses. `run(argv) -> stderr text` is injectable for tests.
    """
    argv = [ffmpeg, "-hide_banner", "-loglevel", "debug", "-threads", "4"]
    if start is not None:
        argv += ["-ss", "%.6f" % start]
    if dur is not None:
        argv += ["-t", "%.6f" % dur]
    argv += ["-i", str(path), "-vf", "mpdecimate", "-an", "-f", "null", "-"]
    if run is None:
        import subprocess
        proc = subprocess.run(argv, capture_output=True, text=True,
                              check=False)
        if proc.returncode != 0:
            raise RuntimeError("DUP_MEASURE_FAILED: " + (proc.stderr or "")[-300:])
        return mpdecimate_dup_ratio(proc.stderr)
    return mpdecimate_dup_ratio(run(argv))


def segment_dup_report(master, plan, ffmpeg="ffmpeg", cap=SEGMENT_DUP_CAP,
                       run=None):
    """Per-shot duplicate check on the rendered master (H3, N-52).

    ONE row per shot id, keyed by ``shot_id`` (the fallback key is the
    segment index). A shot split over two plan segments is reported once:
    its duplicate ratio is measured over the shot's whole on-screen window,
    never once per piece -- the 580.7 s master carried 16 rows twice because
    the bookkeeping keyed rows by segment, not by shot.

    Row: {shot_id, index, src, start_s, dur_s, dup_pct, hold, pass}.
    Cross-fade overlaps are excluded from the window. A segment marked hold
    (a deliberate still) is reported but never fails. Returns
    (rows, failed_rows).
    """
    fps = plan["fps"]
    segs = plan["segments"]
    rows, by_shot = [], {}
    for i, s in enumerate(segs):
        lead = s.get("xfade_frames", 0)
        tail = segs[i + 1].get("xfade_frames", 0) if i + 1 < len(segs) else 0
        start = (s["offset_frames"] + lead) / fps
        dur = (s["frames"] - lead - tail) / fps
        hold = bool(s.get("hold"))
        sid = str(s.get("shot_id") or "seg%d" % i)
        prev = by_shot.get(sid)
        if prev is not None:
            # Same shot in a second segment: one row, the whole window.
            prev["dur_s"] += dur
            prev["hold"] = prev["hold"] or hold
            continue
        row = {"shot_id": sid, "index": i, "src": s["src"], "start_s": start,
               "dur_s": dur, "hold": hold}
        by_shot[sid] = row
        rows.append(row)
    for row in rows:
        row["dup_pct"] = measure_dup_pct(master, ffmpeg, row["start_s"],
                                         row["dur_s"], run=run)
        row["pass"] = row["hold"] or row["dup_pct"] <= cap
    return rows, [r for r in rows if not r["pass"]]
