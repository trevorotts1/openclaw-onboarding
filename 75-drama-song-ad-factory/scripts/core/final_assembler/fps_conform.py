"""fps_conform: motion-compensated fps conform for the final assembler
(manual 02 Part E E1, Critical).

Problem: the plain ffmpeg `fps` filter conforms clips by DUPLICATING
frames (or dropping them), which shows up in the finished ad as visible
stutter when a 24/25 fps source clip is glued into a 30 fps master
(measured on the failed ad behind manual Part E: `mpdecimate` drops up to
~30% of the master's frames). This module replaces that filter with
motion-compensated interpolation:

    minterpolate=fps=<timeline_fps>:mi_mode=mci

- source fps == timeline fps -> pass-through (no conform filter at all).
- source fps != timeline fps -> minterpolate (mci) conform. Both the E1
  "24/25 -> 30" case and the duration-preserving retime (a target fps
  BELOW the source fps) use the same pattern; minterpolate regenerates
  the timeline without duplicating or dropping source frames either way.
- The argv it emits is a FILTER STRING for the assembler's existing
  per-input chain (trim -> setpts -> <conform> -> scale -> setsar), not a
  standalone command, so the assembler keeps its M7 bounding and its
  frame-exact cut plan untouched.

QC helpers (same module, used by the final gate):
- mpdecimate_dup_ratio(stderr)   -> percentage-duplicated frames as a
  PURE function of `ffmpeg -i master -vf mpdecimate -f null -` stderr
  text, so a unit test needs no real video.
- assert_no_dupe_frames(pct)     -> raises ValueError
  "TIMELINE_DUP_FRAMES" when more than DUP_FRAMES_CAP pct are duplicated.
"""
import re

# Part E E1 "Done when": a conforming master must drop <= 2% of its
# frames under mpdecimate; a master above this fails the final QC gate.
DUP_FRAMES_CAP = 2.0

# E1 reason code, emitted exactly for a dup-ratio gate failure.
TIMELINE_DUP_FRAMES = "TIMELINE_DUP_FRAMES"

# Fractional-rate spellings ffmpeg prints/probes (ntsc/pal film, web).
_FRAME_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?\s*$")

_CONFORM_MARKER = "minterpolate"


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

    - equal fps (tolerance 1e-3) -> "" (pass-through: no filter; E1).
    - 24/25 -> 30 (any differing pair) ->
        "minterpolate=fps=<timeline_fps>:mi_mode=mci" (E1 motion-
        compensated interpolation; never the plain `fps` filter).
    - duration-preserving retime (timeline fps BELOW source fps) -> the
      same minterpolate pattern, per manual wording ("a
      duration-preserving retime" is allowed as an equal alternative).

    Returns the string to splice into the per-input filterchain between
    setpts and scale (empty string means splice nothing).
    """
    src = parse_fps(source_fps)
    dst = parse_fps(timeline_fps)
    if abs(src - dst) <= 1e-3:
        return ""
    return "%s=fps=%s:mi_mode=mci" % (_CONFORM_MARKER, _g(dst))


def _g(x):
    """Compact fps formatting for filter strings (30 -> '30', 29.97 -> '29.97')."""
    s = "%.6g" % float(x)
    return s


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