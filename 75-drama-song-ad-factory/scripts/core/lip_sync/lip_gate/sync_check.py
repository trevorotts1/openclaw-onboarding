"""sync_check.py: the measured lip-sync sync test (LSL002). Pure stdlib, $0.

Faithful port of the fixer window's lipsync_check_v2 (validated, SELFTEST PASS).
The mouth opening (outer-lip height / face height, one value per frame) is
correlated with the voice loudness envelope; then:

  * lag search +-10 frames (the best lag is reported, never a reason to fail);
  * the clip is CUT to the audio length first (Kling pads the video tail);
  * chance test: the same audio ROLLED by 15+ frames (step 3) is scored the same
    way; `pct` = share of rolls scoring at least as high as the real audio;
  * margin = own corr minus the best OTHER line's corr, other lines whose
    envelope matches this audio (a repeated hook, corr >= 0.85 at a similar
    length) are dropped from the controls;
  * raw grade: NOT_SYNCED when corr < 0.40, or pct > 0.20, or margin < 0;
    WEAK when margin is 0 to 0.05; SYNCED when margin >= 0.05;
  * UNMEASURABLE (never a pass): face found in under 95 percent of frames, mouth
    not at human proportions, silent audio, mouth barely moves (range < 0.015),
    fewer than 2 other lines supplied, no distinct other line left, under 45 frames.

verdict(m, sung) maps the raw grade to the skill verdicts (Trevor, 2026-10-08,
"loosen the checks so it's not as strict"):
  SYNCED -> PASS;  WEAK -> ACCEPT_WITH_FLAG (used, note in the receipt);
  NOT_SYNCED -> FAIL on a SPOKEN line;
  on a SUNG line WEAK and NOT_SYNCED -> UNDETERMINED: held for a person to look
  at a mouth strip, NO automatic paid redo (an amplitude envelope has little to
  lock to on continuous singing; 1 of 99 redos ever passed);
  UNMEASURABLE -> reported, never a pass.
"""
from __future__ import annotations

import math

# ---- constants (the same block in both repos; do not drift) -----------------
MAX_LAG_FRAMES = 10          # lag search window (+-10 frames)
CORR_FLOOR = 0.40            # NOT_SYNCED below this
MARGIN_FLOOR = 0.0           # NOT_SYNCED below this lead over the best other line
SYNCED_MARGIN = 0.05         # SYNCED at margin >= this; WEAK from the floor to here
CHANCE_PCT_MAX = 0.20        # NOT_SYNCED when more than this share of rolls score as high
ROLL_MIN_FRAMES = 15         # chance test rolls the audio by at least this many frames
ROLL_STEP_FRAMES = 3
LOOKALIKE_CORR = 0.85        # an other line this close to the audio is a repeated hook: dropped
LOOKALIKE_LEN_RATIO = 0.25   # "similar length": lengths within this share of each other
MIN_FRAMES = 45              # shorter (after the cut to the audio length) = UNMEASURABLE
MIN_FACE_FOUND = 0.95        # share of frames with a face
MOUTH_POS = (0.55, 0.85)     # where the mouth sits inside the face box (human proportions)
MIN_MOUTH_RANGE = 0.015      # p95-p5 of mouth opening / face height
MIN_OTHER_LINES = 2          # other lines of the chapter needed for the control

SYNCED, WEAK, NOT_SYNCED, UNMEASURABLE = "SYNCED", "WEAK", "NOT_SYNCED", "UNMEASURABLE"
PASS, FLAG, FAIL, UNDETERMINED = "PASS", "ACCEPT_WITH_FLAG", "FAIL", "UNDETERMINED"

R_CORR = "corr"
R_CHANCE = "chance"
R_MARGIN = "margin"


def _pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a) / n
    vb = sum((y - mb) ** 2 for y in b) / n
    if va <= 1e-18 or vb <= 1e-18:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / n / math.sqrt(va * vb)


def smooth(x, w=3):
    """3-tap [.25 .5 .25] moving average, edges held (the same as the tool's hanning(5)[1:-1])."""
    n = len(x)
    return [.25 * x[max(i - 1, 0)] + .5 * x[i] + .25 * x[min(i + 1, n - 1)]
            for i in range(n)]


def prep_env(e):
    """Log-compress a loudness series (quiet syllables count), smooth 3 frames."""
    top = max(e) if e else 0.0
    return smooth([math.log(v + 0.02 * top) for v in e])


def best(m, e, max_lag=MAX_LAG_FRAMES):
    """-> (lag, corr). corr(m[t], e[t-L]) over lags -max..+max; L>0 = mouth LATE."""
    res = {}
    for L in range(-max_lag, max_lag + 1):
        a, b = (m[L:], e[:len(e) - L]) if L >= 0 else (m[:L], e[-L:])
        k = min(len(a), len(b))
        if k >= 8:
            c = _pearson(a[:k], b[:k])
            if c is not None:
                res[L] = c
    if not res:
        return 0, 0.0
    L = max(res, key=res.get)
    return L, res[L]


def _fit(x, n):
    """Cut to n frames; a shorter series is padded with silence (0) at the end."""
    return (list(x) + [0.0] * n)[:n]


def _roll(x, k):
    n = len(x)
    return [x[(i - k) % n] for i in range(n)]


def unmeasurable(why, **extra):
    return dict(extra, grade=UNMEASURABLE, unmeasurable=why, corr=0.0, lag_frames=0,
                offset_s=0.0, pct=1.0, margin=0.0, control_corr=0.0)


def measure_sync(mouth, voice, others, fps, face_found=1.0, mouth_pos=0.7):
    """Measure one clip.
    mouth: per-frame mouth opening (gaps filled); voice: this line's audio loudness
    at the same frame rate (natural length); others: loudness series of the chapter's
    OTHER lines (a list of series). Returns the measurement dict (grade included)."""
    if not mouth or not voice or fps <= 0:
        raise ValueError("LIP_UNMEASURED: empty mouth or voice series")
    n = min(len(mouth), len(voice) + 1)            # cut to the audio length (Kling pads the tail)
    base = dict(fps=fps, frames_video=len(mouth), frames_used=n,
                face_found=round(face_found, 3), mouth_pos=round(mouth_pos, 3))
    s = sorted(mouth[:n])
    rng = s[int(.95 * (n - 1))] - s[int(.05 * (n - 1))]
    base["mouth_range"] = round(rng, 4)
    if face_found < MIN_FACE_FOUND:
        return unmeasurable("face found in %.0f%% of frames (< %.0f%%)" % (
            100 * face_found, 100 * MIN_FACE_FOUND), **base)
    if not MOUTH_POS[0] <= mouth_pos <= MOUTH_POS[1]:
        return unmeasurable("landmarks implausible (mouth at %.2f of face height): "
                            "not a human-proportioned face" % mouth_pos, **base)
    if n < MIN_FRAMES:
        return unmeasurable("clip too short (%d frames < %d)" % (n, MIN_FRAMES), **base)
    e = _fit(voice, n)
    if max(e) < 1e-4:
        return unmeasurable("audio silent", **base)
    if rng < MIN_MOUTH_RANGE:
        return unmeasurable("mouth barely moves (range %.4f < %s)" % (rng, MIN_MOUTH_RANGE), **base)
    if len(others) < MIN_OTHER_LINES:
        return unmeasurable("need >= %d other lines for the control" % MIN_OTHER_LINES, **base)
    ms, pe = smooth(mouth[:n]), prep_env(e)
    lag, corr = best(ms, pe)
    pe_nat = prep_env(list(voice))
    distinct, dropped = [], 0
    for o in others:
        k = min(len(o), len(voice))
        similar = abs(len(o) - len(voice)) <= LOOKALIKE_LEN_RATIO * len(voice)
        c = _pearson(pe_nat[:k], prep_env(list(o))[:k]) if similar and k >= 8 else None
        if c is not None and c >= LOOKALIKE_CORR:
            dropped += 1
        else:
            distinct.append(o)
    if not distinct:
        return unmeasurable("every other line is a lookalike of this audio: no control", **base)
    oc = [best(ms, prep_env(_fit(o, n)))[1] for o in distinct]
    rolls = [best(ms, prep_env(_roll(e, k)))[1]
             for k in range(ROLL_MIN_FRAMES, n - ROLL_MIN_FRAMES, ROLL_STEP_FRAMES)]
    pct = sum(r >= corr for r in rolls) / len(rolls) if rolls else 1.0
    m = dict(base, corr=round(corr, 4), lag_frames=lag, offset_s=round(lag / fps, 4),
             pct=round(pct, 3), control_corr=round(max(oc), 4),
             margin=round(corr - max(oc), 4), others_dropped=dropped,
             others_used=len(distinct), unmeasurable=None)
    m["grade"] = grade(m)
    m["fail_tests"] = fail_tests(m)
    return m


def fail_tests(m):
    t = []
    if m["corr"] < CORR_FLOOR:
        t.append(R_CORR)
    if m["pct"] > CHANCE_PCT_MAX:
        t.append(R_CHANCE)
    if m["margin"] < MARGIN_FLOOR:
        t.append(R_MARGIN)
    return t


def grade(m):
    """Raw grade of a measurement: SYNCED / WEAK / NOT_SYNCED / UNMEASURABLE."""
    if m.get("unmeasurable"):
        return UNMEASURABLE
    if fail_tests(m):
        return NOT_SYNCED
    return SYNCED if m["margin"] >= SYNCED_MARGIN else WEAK


def verdict(m, sung=False):
    """Skill verdict for a measurement. See the module docstring for the map."""
    g = grade(m)
    if g == UNMEASURABLE:
        return UNMEASURABLE
    if g == SYNCED:
        return PASS
    if sung:
        return UNDETERMINED
    return FLAG if g == WEAK else FAIL
