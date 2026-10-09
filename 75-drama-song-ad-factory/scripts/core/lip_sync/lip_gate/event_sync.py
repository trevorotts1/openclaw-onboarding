#!/usr/bin/env python3
"""event_sync.py: ADVISORY lip-sync measure (from LSR001). It NEVER gates.

The gate is sync_check.py (calibrated on real controls; see calibrate_sync.py).
event_sync checks the mouth against EVENTS taken from the lead-vocal span and
the Suno word timestamps, +/-0.2 s: a voiced-run ONSET after a rest (mouth
opens), an OFFSET before a rest (mouth closes below p35), every p/b/m word (a
lip-closure dip). `lip_gate.run_gate` records the result in the receipt row as
`advisory_event_sync` and takes no decision from it. Its thresholds are
UNVERIFIED on real clips (synthetic controls only); `calibrate_events.py`
prints the real-control table that decides whether it may ever gate.

Verdicts: SYNCED, WEAK, UNMEASURABLE, NOT_SYNCED (hard defects only).
`python3 event_sync.py selftest` runs the synthetic control battery.
Pure stdlib, $0.
"""
from __future__ import annotations

import math

LIP_UNMEASURED = "LIP_UNMEASURED"

# --- event_sync numbers (design doc 13, 2e; calibrate on the human-scored set)
TOL_S = 0.2                  # +/-0.2 s: not detectable by people
MIN_EVENTS = 4
MIN_FACE_FRAC = 0.90
REST_S = 0.12                # a real rest between voiced runs
RISE_FRAC = 0.30             # onset: mouth rises >= 30% of its range
LOW_PCT = 35                 # offset / bilabial: mouth below its p35
CLOSED_PCT = 20
SYNCED_HIT = 0.70
SYNCED_MARGIN = 0.20
HARD_HIT = 0.40
HARD_HIT_MIN_EVENTS = 6
STILL_RANGE = 0.015
MAX_CLOSED_VOICED_S = 0.5
MAX_MOVING_REST_S = 0.5
SHIFTS_S = (-1.0, -0.5, 0.5, 1.0)

SYNCED, WEAK, UNMEASURABLE, NOT_SYNCED = "SYNCED", "WEAK", "UNMEASURABLE", "NOT_SYNCED"
TIER = {SYNCED: 3, WEAK: 2, UNMEASURABLE: 1, NOT_SYNCED: 0}

LIP_STILL = "LIP_STILL_MOUTH"
LIP_CLOSED_VOICED = "LIP_CLOSED_THROUGH_VOICE"
LIP_MOVING_REST = "LIP_MOVING_THROUGH_REST"
LIP_HIT_LOW = "LIP_HIT_LOW"


# ------------------------------------------------------------ small maths ----

def _pct(x, p):
    s = sorted(x)
    if not s:
        return 0.0
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _smooth(x, w=3):
    h = w // 2
    return [sum(x[max(0, i - h):i + h + 1]) / len(x[max(0, i - h):i + h + 1])
            for i in range(len(x))]


def _fill(m):
    """Forward/back fill NaN (no face) frames; returns (series, face_fraction)."""
    ok = [v for v in m if v == v]
    if not ok:
        return [], 0.0
    out, last = [], next(v for v in m if v == v)
    for v in m:
        last = v if v == v else last
        out.append(last)
    return out, len(ok) / float(len(m))


def _win(m, fps, a, b):
    i, j = max(0, int(math.floor(a * fps))), min(len(m), int(math.ceil(b * fps)) + 1)
    return m[i:j]


# ------------------------------------------------------- events from audio ----

def voiced_runs(env, fps, thr_frac=0.2, rest_s=REST_S, min_s=0.1):
    """Voiced runs (start_s, end_s) from a loudness envelope of the lead-vocal
    STEM: frames above thr_frac x max, gaps shorter than rest_s merged."""
    if not env:
        return []
    thr = thr_frac * max(env)
    runs, s = [], None
    for i, v in enumerate(env + [0.0]):
        if v > thr and s is None:
            s = i
        elif v <= thr and s is not None:
            runs.append([s / float(fps), i / float(fps)])
            s = None
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < rest_s:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [tuple(r) for r in merged if r[1] - r[0] >= min_s]


def events(voiced, words=(), dur=None, rest_s=REST_S):
    """Build the event set for one span. voiced: [(s, e)] from voiced_runs;
    words: [{"word","start","end"}] Suno stamps relative to the span start."""
    onsets = [s for s, _ in voiced]
    offsets = [e for _, e in voiced]
    bil = [(w["start"], w["end"]) for w in words
           if any(c in "pbm" for c in str(w.get("word", "")).lower())]
    rests = [(voiced[i][1], voiced[i + 1][0]) for i in range(len(voiced) - 1)
             if voiced[i + 1][0] - voiced[i][1] >= rest_s]
    end = dur if dur else (voiced[-1][1] if voiced else 0.0)
    return {"onsets": onsets, "offsets": offsets, "bilabial": bil,
            "voiced": list(voiced), "rests": rests, "dur": end}


def _n_events(ev):
    return len(ev["onsets"]) + len(ev["offsets"]) + len(ev["bilabial"])


def _shift(ev, d, scale=1.0):
    f = lambda t: t * scale + d
    return {"onsets": [f(t) for t in ev["onsets"]],
            "offsets": [f(t) for t in ev["offsets"]],
            "bilabial": [(f(a), f(b)) for a, b in ev["bilabial"]],
            "voiced": [(f(a), f(b)) for a, b in ev["voiced"]],
            "rests": [(f(a), f(b)) for a, b in ev["rests"]],
            "dur": ev["dur"] * scale}


def _hits(m, fps, ev, lo_thr, rng, tol=TOL_S):
    """(matched, total) for one event set against one mouth series."""
    hit = tot = 0
    n = len(m) / float(fps)
    for t in ev["onsets"]:
        tot += 1
        if t - tol < 0 or t + tol > n + tol:
            continue
        before, after = _win(m, fps, t - tol, t), _win(m, fps, t, t + tol)
        if before and after and max(after) - min(before) >= RISE_FRAC * rng:
            hit += 1
    for t in ev["offsets"]:
        tot += 1
        w = _win(m, fps, t - tol, t + tol) if 0 <= t <= n + tol else []
        if w and min(w) <= lo_thr:
            hit += 1
    for a, b in ev["bilabial"]:
        tot += 1
        w = _win(m, fps, a, b) if 0 <= a <= n else []
        if w and min(w) <= lo_thr:
            hit += 1
    return hit, tot


def _rate(m, fps, ev, lo_thr, rng):
    h, t = _hits(m, fps, ev, lo_thr, rng)
    return h / float(t) if t else 0.0


def _defects(m, fps, ev, rng, p20):
    d = []
    voiced_total = sum(b - a for a, b in ev["voiced"])
    if rng < STILL_RANGE and voiced_total > 0:
        d.append(LIP_STILL)
    run_max = 0
    for a, b in ev["voiced"]:
        run = 0
        for v in _win(m, fps, a, b):
            run = run + 1 if v <= p20 else 0
            run_max = max(run_max, run)
    if run_max / float(fps) > MAX_CLOSED_VOICED_S and LIP_STILL not in d:
        d.append(LIP_CLOSED_VOICED)
    for a, b in ev["rests"]:
        if b - a > MAX_MOVING_REST_S:
            w = _win(m, fps, a + TOL_S, b - TOL_S)
            if w and max(w) - min(w) >= 0.5 * rng and rng >= STILL_RANGE:
                d.append(LIP_MOVING_REST)
                break
    return d


def event_sync(mouth, ev, control_events, fps, extra_defects=()):
    """Judge one clip. mouth: per-frame inner-lip gap / face height (NaN = no
    face); ev: events() of the lead-vocal span; control_events: events() of the
    chapter's OTHER lines. Returns a dict with verdict, hit, control_hit, margin,
    lag_s, n_events, face_frac, hard_defects."""
    if fps <= 0:
        raise ValueError(LIP_UNMEASURED)
    m, face = _fill(list(mouth))
    n_ev = _n_events(ev)
    base = {"hit": 0.0, "control_hit": 0.0, "margin": 0.0, "lag_s": 0.0,
            "n_events": n_ev, "face_frac": round(face, 4), "hard_defects": [],
            "fps": fps, "tol_s": TOL_S}
    if not m or face < MIN_FACE_FRAC or n_ev < MIN_EVENTS:
        why = "face in %.0f%% of frames" % (face * 100) if face < MIN_FACE_FRAC \
            else "%d events (need %d)" % (n_ev, MIN_EVENTS)
        return dict(base, verdict=UNMEASURABLE, reason=why,
                    hard_defects=list(extra_defects))
    m = _smooth(m)
    p5, p95 = _pct(m, 5), _pct(m, 95)
    rng = p95 - p5
    # below the p35, but never above 40% of the way up the range (a mouth that
    # is open most of the time has a p35 inside its open values)
    lo, p20 = min(_pct(m, LOW_PCT), p5 + 0.4 * rng), _pct(m, CLOSED_PCT)
    hit = _rate(m, fps, ev, lo, rng)
    ctrl = []
    for d in SHIFTS_S:
        ctrl.append(_rate(m, fps, _shift(ev, d), lo, rng))
    dur = len(m) / float(fps)
    for oc in control_events:
        sc = dur / oc["dur"] if oc.get("dur") else 1.0
        ctrl.append(_rate(m, fps, _shift(oc, 0.0, sc), lo, rng))
    best_ctrl = max(ctrl) if ctrl else 0.0
    # lag: the shift (frames, -6..6) at which the real events match best; smaller |lag| wins ties
    lags = sorted(range(-6, 7), key=abs)
    lag = max(lags, key=lambda k: (_rate(m, fps, _shift(ev, k / float(fps)), lo, rng), -abs(k)))
    defects = list(extra_defects) + _defects(m, fps, ev, rng, p20)
    if hit <= HARD_HIT and n_ev >= HARD_HIT_MIN_EVENTS:
        defects.append(LIP_HIT_LOW)
    if defects:
        verdict = NOT_SYNCED
    elif hit >= SYNCED_HIT and hit - best_ctrl >= SYNCED_MARGIN:
        verdict = SYNCED
    else:
        verdict = WEAK
    return dict(base, verdict=verdict, hit=round(hit, 4),
                control_hit=round(best_ctrl, 4), margin=round(hit - best_ctrl, 4),
                lag_s=round(-lag / float(fps), 4), hard_defects=defects)


def judge(j):
    """Row-level view of an event_sync result."""
    return dict(j, hard=bool(j.get("hard_defects")) or j["verdict"] == NOT_SYNCED)


def score(j):
    """Higher is better (design 2f): no hard defect, then verdict tier, then
    hit and margin, then smaller |lag|."""
    return (not (j.get("hard_defects") or j["verdict"] == NOT_SYNCED),
            TIER[j["verdict"]], j.get("hit", 0.0), j.get("margin", 0.0),
            -abs(j.get("lag_s", 0.0)))


# ------------------------------------------------------------- selftest ----

def synth_clip(seed, fps=30, dur=6.0, n_words=9):
    """Synthetic (mouth, events) pair for the control battery: an irregular
    word rhythm with rests, a mouth that opens at onsets, closes at offsets and
    dips on p/b/m words."""
    import random
    r = random.Random(seed)
    t, words, voiced = 0.4, [], []
    while len(words) < n_words and t < dur - 0.8:
        s = t
        for _ in range(r.randint(3, 5)):
            w = r.uniform(0.25, 0.6)
            words.append({"word": r.choice(["map", "love", "be", "sun", "you", "my", "dream", "go"]),
                          "start": t, "end": t + w})
            t += w + r.uniform(0.0, 0.05)
        voiced.append((s, t))
        t += r.uniform(0.3, 0.45)
    n = int(dur * fps)
    mouth = [0.02] * n
    for a_, b_ in voiced:                 # legato: open through the phrase, shut in rests
        ph = r.uniform(0, 6.28)
        for i in range(int(a_ * fps), min(n, int(b_ * fps))):
            mouth[i] = 0.13 + 0.02 * math.sin(ph + i / 5.0)
    for w in words:
        if any(c in "pbm" for c in w["word"]):       # lip closure at the word start
            for i in range(int(w["start"] * fps), min(n, int((w["start"] + 0.15) * fps))):
                mouth[i] = 0.02
    return mouth, events(voiced, words, dur)


def selftest(extra_controls=()):
    """The control battery. extra_controls: [(name, 'positive'|'negative', mouth,
    ev, others, fps)] from real clips. Returns a list of failures; empty = pass.
    FAILS if ANY negative control comes out SYNCED or any positive NOT_SYNCED
    (the bug in the old v2: wrong audio passed and the selftest still said PASS)."""
    fps, bad, rows = 30, [], []
    pool = [synth_clip(s) for s in range(1, 7)]
    for i, (mouth, ev) in enumerate(pool):
        others = [e for j, (_, e) in enumerate(pool) if j != i]
        rows.append(("own audio #%d" % i, "positive", mouth, ev, others, fps))
        sh = int(0.5 * fps)
        rows.append(("own audio shifted 0.5 s #%d" % i, "negative",
                     mouth[sh:] + [mouth[-1]] * sh, ev, others, fps))
        rows.append(("still face #%d" % i, "negative", [0.07] * len(mouth), ev, others, fps))
        rows.append(("no face (cartoon) #%d" % i, "unmeasurable",
                     [float("nan")] * len(mouth), ev, others, fps))
        for k, (_, wrong) in enumerate(pool):
            if k != i:
                rows.append(("wrong audio %d on clip %d" % (k, i), "negative",
                             mouth, wrong, [e for j, (_, e) in enumerate(pool) if j not in (i, k)], fps))
    rows += list(extra_controls)
    for name, kind, mouth, ev, others, f in rows:
        v = event_sync(mouth, ev, others, f)["verdict"]
        if kind == "negative" and v == SYNCED:
            bad.append("%s: negative control read SYNCED" % name)
        elif kind == "positive" and v == NOT_SYNCED:
            bad.append("%s: positive control read NOT_SYNCED" % name)
        elif kind == "unmeasurable" and v != UNMEASURABLE:
            bad.append("%s: expected UNMEASURABLE, got %s" % (name, v))
    return bad


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["selftest"]:
        fails = selftest()
        print("SELFTEST", "FAIL" if fails else "PASS")
        for f in fails:
            print(" ", f)
        sys.exit(1 if fails else 0)
    sys.exit(__doc__)
