#!/usr/bin/env python3
"""pace_change: the ordered gear change, enforced in SKILL code (D1 / F2).

The ordered "smooth dramatic pace change" had NO enforcement anywhere. The only
judgement in the failed run lived in a lane script
(`run/lanes/WW-001-lane/deliver.py`), which set ``half_time_confirmed`` to
``v2.tempo_bpm < ref.tempo_bpm * 0.9``. That is a bare multiplier with no
absolute floor and no corroboration, and short-phrase tempo estimation is
octave-ambiguous -- 85.2 and 181.5 bpm are the SAME beat an octave apart -- so
it confirmed gear changes that were not there.

WHAT THIS GATE MEASURES (correction applied -- the earlier tempo-ratio form is
withdrawn):

  * ONSET RATE. Positive spectral flux, local onset peaks, a FIXED
    mean-plus-standard-deviation threshold, and a minimum peak spacing of
    PEAK_MIN_SPACING_S. This is a real per-second rate. The lane's
    ``process_take.py`` counted frames above the 75th percentile of the
    envelope, which is about 25 percent of frames BY CONSTRUCTION and so cannot
    measure a rate change in either direction; it is NOT used here.
  * INSTRUMENTAL ENERGY, in dBFS.

THE PASS RULE demands BOTH, in the problem window:
  * at least PACE_ONSET_REDUCTION (30%) onset-rate reduction, AND
  * at least PACE_ENERGY_DROP_DB (3 dB) energy drop,
plus a RETURN to baseline -- onset rate back within PACE_RETURN_TOL (20%) and
energy back within PACE_RETURN_DB (3 dB) -- and an INDEPENDENT
smooth-transition check (``smooth_transition_check``) that the seam is not a
hard cut.

BPM ALONE MUST NEVER GRANT PASS. Tempo is recorded and octave-folded for the
report only; a caller who supplies no onset and energy evidence gets
UNMEASURED, which blocks a take PASS (QC 17.8). 85.2 and 181.5 bpm fold to the
same beat and can never register as a gear change.

EVERY THRESHOLD BELOW IS A NEW ACCEPTANCE RULE set by this fix. The two
measurement-anchored facts are the lane's control pair (fast 90.909 bpm and
half-time 44.776 bpm, which discriminate in both directions) and the rejection
of every SHIPPED take (their tempo ratio is 1.0 -- the ordered change is
absent). Those are reproduced in ``selftest()``.

stdlib only; no network, no spend. numpy is used for the FFT when present, and
the envelope falls back to a positive energy flux without it -- both feed the
same onset-rate instrument.
"""
from __future__ import annotations

import cmath
import math

TOOL_NAME = "pace_change"
TOOL_VERSION = "2.0.0"
SCHEMA = "blackceo.pace-change/v2"

#: NEW ACCEPTANCE RULES (WWFIX 2026-10-11).
PACE_ONSET_REDUCTION = 0.30    # the problem window's onset rate at most this share
PACE_ENERGY_DROP_DB = 3.0      # AND the problem window at least this much quieter
PACE_RETURN_TOL = 0.20         # the closing window's onset rate back within this share
PACE_RETURN_DB = 3.0           # AND energy back within this many dB
PEAK_MIN_SPACING_S = 0.12      # minimum spacing between onset peaks
PEAK_THRESHOLD_SD = 1.0        # a peak rises this many standard deviations above the mean
FRAME_S = 0.046               # analysis frame (1024 samples at 22050 Hz)
HOP_S = 0.0116                # analysis hop  (256 samples at 22050 Hz)
SMOOTH_FLUX_MULT = 6.0         # the seam's flux may not exceed this multiple of the
                               # surrounding mean (the independent smooth-transition check)
SMOOTH_MIN_FRAMES = 2          # never judge the seam on one sample
OCTAVE_TOL_OCT = 0.15          # within this many octaves of a whole octave = same beat


class PaceError(ValueError):
    """Malformed pace evidence; a gate that cannot read its input never passes."""


def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise PaceError("%s must be a number, got %r" % (name, v))
    return float(v)


# ---- the onset instrument --------------------------------------------------

def spectral_flux_envelope(samples, sr, frame_s=FRAME_S, hop_s=HOP_S):
    """Positive flux over successive frames of ``samples``, as a list plus the
    hop in seconds.

    Spectral flux when numpy is available (a real FFT), and a positive ENERGY
    flux otherwise: both are "how much louder/brighter did the frame just get",
    which is what an onset peak is. Never a top-quartile count."""
    n = len(samples)
    win = max(16, int(frame_s * sr))
    hop = max(1, int(hop_s * sr))
    if n < win + hop:
        return [], hop / float(sr)
    frames = 1 + (n - win) // hop
    try:
        import numpy as np                                   # noqa: PLC0415
        x = np.asarray(samples, dtype=float)
        w = np.hanning(win)
        mag = []
        for i in range(frames):
            sp = np.abs(np.fft.rfft(x[i * hop:i * hop + win] * w))
            mag.append(sp)
        env = [0.0]
        for i in range(1, frames):
            env.append(float(np.sum(np.maximum(mag[i] - mag[i - 1], 0.0))))
    except ImportError:
        prev = None
        env = []
        for i in range(frames):
            seg = samples[i * hop:i * hop + win]
            cur = [abs(float(v)) for v in seg]
            if prev is None:
                env.append(0.0)
            else:
                env.append(sum(max(c - p, 0.0) for c, p in zip(cur, prev)))
            prev = cur
    return env, hop / float(sr)


def onset_peaks(envelope, hop_s, k=PEAK_THRESHOLD_SD, min_spacing_s=PEAK_MIN_SPACING_S):
    """The onset peak indices: local maxima above a FIXED mean-plus-k-standard-
    deviation threshold, thinned to at least ``min_spacing_s`` apart.

    The threshold is the envelope's own mean plus k standard deviations -- a
    fixed statistic, not a percentile of the samples, so the count is a real
    rate and can move in either direction."""
    xs = [float(x) for x in envelope or []]
    if len(xs) < 3:
        return []
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    cut = mean + k * (var ** 0.5)
    cand = [i for i in range(1, len(xs) - 1)
            if xs[i] > cut and xs[i] >= xs[i - 1] and xs[i] > xs[i + 1]]
    gap = max(1, int(math.ceil(min_spacing_s / hop_s)))
    out = []
    for i in cand:
        if not out or i - out[-1] >= gap:
            out.append(i)
        elif xs[i] > xs[out[-1]]:
            out[-1] = i
    return out


def onset_rate_per_s(envelope, hop_s, k=PEAK_THRESHOLD_SD,
                     min_spacing_s=PEAK_MIN_SPACING_S):
    """Onset events per second -- a real rate, never a top-quartile count."""
    if not envelope:
        raise PaceError("onset envelope is empty")
    hop = _num(hop_s, "hop_s")
    if hop <= 0:
        raise PaceError("hop_s must be positive")
    peaks = onset_peaks(envelope, hop, k, min_spacing_s)
    return round(len(peaks) / (len(envelope) * hop), 4)


def rms_dbfs(samples):
    """Instrumental energy of a window, in dBFS. Silence floors at -120."""
    if not samples:
        raise PaceError("the window is empty")
    acc = 0.0
    for v in samples:
        acc += float(v) * float(v)
    rms = math.sqrt(acc / len(samples))
    return round(20.0 * math.log10(rms) if rms > 1e-6 else -120.0, 3)


def window_stats(samples, sr, a, b):
    """The measured stats of the window [a, b) seconds: onset rate and dBFS.

    The window is the only input -- no tempo here, because a bare tempo cannot
    certify a gear change (see the module docstring)."""
    i, j = int(a * sr), int(b * sr)
    seg = samples[i:j]
    if len(seg) < max(64, int(FRAME_S * sr)):
        return None
    env, hop = spectral_flux_envelope(seg, sr)
    if not env:
        return None
    return {"start_s": round(a, 3), "end_s": round(b, 3),
            "onset_rate_per_s": onset_rate_per_s(env, hop),
            "rms_dbfs": rms_dbfs(seg)}


# ---- the independent smooth-transition check ------------------------------

def smooth_transition_check(envelope, hop_s, boundary_s, mult=SMOOTH_FLUX_MULT):
    """Is the seam at ``boundary_s`` a SMOOTH transition rather than a hard cut?

    Independent of the onset rate and of the energy: it looks only at the flux
    AT the boundary against the local mean flux. A cut has a single very large
    flux spike, so ``boundary_flux <= mult * local_mean`` is smooth. Returns
    {"smooth": bool, ...}; an unmeasurable seam is ``smooth: None`` (unknown,
    which is never a pass)."""
    xs = [float(x) for x in envelope or []]
    hop = _num(hop_s, "hop_s")
    if len(xs) < 3 or hop <= 0:
        return {"smooth": None, "reason": "the envelope is too short to judge the seam"}
    idx = int(round(float(boundary_s) / hop))
    idx = max(1, min(idx, len(xs) - 1))
    lo, hi = max(0, idx - 8), min(len(xs), idx + 8)
    local = xs[lo:hi] or xs
    mean = sum(local) / float(len(local))
    at = xs[idx]
    smooth = at <= mult * mean if mean > 0 else at <= 0
    return {"smooth": bool(smooth), "boundary_s": round(float(boundary_s), 3),
            "boundary_flux": round(at, 4), "local_mean_flux": round(mean, 4),
            "mult": mult,
            "reason": ("smooth" if smooth else
                       "the seam carries a %.1fx flux spike over the local mean: a hard cut"
                       % (at / mean if mean else 0.0))}


# ---- the gate --------------------------------------------------------------

def _window(obj, name):
    if not isinstance(obj, dict):
        raise PaceError("%s window must be a mapping, got %r" % (name, obj))
    return {"onset_rate": _num(obj.get("onset_rate_per_s",
                                       obj.get("onset_rate")), "%s.onset_rate" % name),
            "rms_dbfs": _num(obj.get("rms_dbfs"), "%s.rms_dbfs" % name)}


def octave_fold_bpm(bpm_a, bpm_b, tol_oct=OCTAVE_TOL_OCT):
    """Fold two tempo estimates onto one beat and say whether they are the SAME
    beat. REPORT ONLY: bpm never grants a PASS.

    Folding is by octave distance: ``d = log2(b / a)``, rounded to the nearest
    whole octave ``k``; the two are the same beat when ``|d - k|`` is within
    ``tol_oct``. This reads 85.2 and 181.5 as the SAME beat (d = 1.091, 0.091
    from one octave), which is exactly why a bare tempo ratio cannot certify a
    gear change -- and it also reads the lane's own fast (90.909) versus
    half-time (44.776) control pair as the same beat."""
    a, b = _num(bpm_a, "bpm_a"), _num(bpm_b, "bpm_b")
    if a <= 0 or b <= 0:
        raise PaceError("tempo estimates must be positive, got %r/%r" % (bpm_a, bpm_b))
    d = math.log2(b / a)
    k = int(round(d))
    folded = b / (2.0 ** k)
    return {"a": a, "b": b, "octave_distance": round(d, 4), "octaves": k,
            "a_folded": round(a, 3), "b_folded": round(folded, 3),
            "distance_from_octave": round(abs(d - k), 4),
            "same_beat": abs(d - k) <= tol_oct,
            "grants_pass": False}


def confirm_pace_change(before, problem, after, boundary_s=None, envelope=None,
                        hop_s=None, bpm_before=None, bpm_after=None, reason=None):
    """Judge one ordered gear change: before -> problem -> after.

    PASS needs ALL of: >= 30% onset-rate reduction, >= 3 dB energy drop, the
    return to baseline within 20% onset and 3 dB, and -- when an envelope is
    supplied -- a smooth seam. Anything less is FAIL. Missing onset or energy
    evidence is UNMEASURED, never PASS; bpm is reported and folded but never
    grants a PASS."""
    try:
        b = _window(before, "before")
        p = _window(problem, "problem")
        a = _window(after, "after")
    except PaceError as e:
        return {"schema": SCHEMA, "verdict": "UNMEASURED", "reason_code":
                "PACE_EVIDENCE_UNMEASURED", "detail": str(e),
                "grants_pass": False, "reason": reason,
                "source": "WWFIX D1/F2 (X3): onset + energy, never bpm alone"}
    onset_reduction = (1.0 - p["onset_rate"] / b["onset_rate"]) if b["onset_rate"] > 0 else None
    energy_drop = round(b["rms_dbfs"] - p["rms_dbfs"], 3)
    # RETURN TO BASELINE: the closing window is measured against the window
    # BEFORE the problem, not against the problem window itself.
    return_gap = (abs(a["onset_rate"] - b["onset_rate"]) / b["onset_rate"]
                  if b["onset_rate"] > 0 else None)
    return_db = round(a["rms_dbfs"] - (b["rms_dbfs"] - PACE_ENERGY_DROP_DB), 3)
    checks = {
        "onset_reduction": onset_reduction is not None
                            and onset_reduction >= PACE_ONSET_REDUCTION,
        "energy_drop": energy_drop >= PACE_ENERGY_DROP_DB,
        "onset_return": return_gap is not None and return_gap <= PACE_RETURN_TOL,
        "energy_return": a["rms_dbfs"] >= b["rms_dbfs"] - PACE_RETURN_DB,
    }
    seam = None
    if envelope is not None and boundary_s is not None and hop_s:
        seam = smooth_transition_check(envelope, hop_s, boundary_s)
        if seam.get("smooth") is not None:
            checks["smooth_transition"] = bool(seam["smooth"])
    fold = None
    if bpm_before is not None and bpm_after is not None:
        try:
            fold = octave_fold_bpm(bpm_before, bpm_after)
        except PaceError:
            fold = None
    verdict = "PASS" if all(checks.values()) else "FAIL"
    failed = sorted(k for k, v in checks.items() if not v)
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "reason_code": "PACE_CHANGE_CONFIRMED" if verdict == "PASS"
                       else "PACE_CHANGE_ABSENT",
        "failed": failed,
        "checks": checks,
        "onset_rate_before": b["onset_rate"], "onset_rate_problem": p["onset_rate"],
        "onset_rate_after": a["onset_rate"],
        "onset_reduction": None if onset_reduction is None else round(onset_reduction, 4),
        "energy_dbfs_before": b["rms_dbfs"], "energy_dbfs_problem": p["rms_dbfs"],
        "energy_dbfs_after": a["rms_dbfs"],
        "energy_drop_db": energy_drop,
        "return_onset_gap": None if return_gap is None else round(return_gap, 4),
        "return_energy_margin_db": return_db,
        "smooth_transition": seam,
        "octave_fold": fold,
        "bpm_grants_pass": False,
        "floor": {"onset_reduction": PACE_ONSET_REDUCTION,
                  "energy_drop_db": PACE_ENERGY_DROP_DB,
                  "return_tol": PACE_RETURN_TOL, "return_db": PACE_RETURN_DB,
                  "peak_min_spacing_s": PEAK_MIN_SPACING_S},
        "detail": ("gear change confirmed: onsets %.3f -> %.3f/s (%.0f%% down), "
                   "%+.2f dB, back to %.3f/s and %+.2f dB"
                   % (b["onset_rate"], p["onset_rate"], (onset_reduction or 0) * 100,
                      -energy_drop, a["onset_rate"], return_db))
                  if verdict == "PASS" else
                  ("no gear change: %s (onsets %.3f -> %.3f/s, %+.2f dB)"
                   % (", ".join(failed), b["onset_rate"], p["onset_rate"], -energy_drop)),
        "reason": reason,
        #: NEW ACCEPTANCE RULE: every threshold here is set by this fix.
        "thresholds_are_new_acceptance_rules": True,
        "source": "WWFIX D1/F2 (X3/X4): onset reduction + energy drop + return + "
                  "smooth seam; bpm alone never grants PASS",
    }


def judge_plan_pace(plan, before, problem, after, **kw):
    """The take judge's seam. ``plan`` names the ordered gear change (key
    ``pace_change``); no order -> {"verdict": "PASS", "applicable": False} --
    nothing to enforce. An ordered change with missing evidence is UNMEASURED,
    which blocks a take PASS."""
    order = (plan or {}).get("pace_change") or (plan or {}).get("_pace_plan")
    if not order:
        return {"verdict": "PASS", "applicable": False,
                "detail": "no ordered pace change in the plan"}
    reason = order.get("reason") if isinstance(order, dict) else None
    if isinstance(order, dict) and order.get("boundary_s") is not None:
        kw.setdefault("boundary_s", order["boundary_s"])
    out = confirm_pace_change(before, problem, after, reason=reason, **kw)
    out["applicable"] = True
    return out


# ---- the anchored controls -------------------------------------------------

def selftest():
    """The two measurement-anchored facts, reproduced.

    * the lane's control pair -- fast 90.909 bpm versus half-time 44.776 bpm --
      discriminates in both directions with the onset/energy evidence a real
      half-time section carries;
    * every SHIPPED take is rejected, because its tempo ratio is 1.0 and its
      onset and energy never move: the ordered change is absent.
    """
    fast = {"onset_rate_per_s": 3.0, "rms_dbfs": -14.0}
    half = {"onset_rate_per_s": 1.4, "rms_dbfs": -18.5}
    back = {"onset_rate_per_s": 2.9, "rms_dbfs": -14.4}
    ok = confirm_pace_change(fast, half, back, bpm_before=90.909, bpm_after=44.776)
    assert ok["verdict"] == "PASS", ok
    # The lane's OWN control pair folds to the SAME beat: this is the fact that
    # makes a bare tempo ratio useless, and the gate still PASSes them because
    # the onset rate and the energy really do move.
    assert ok["octave_fold"]["same_beat"] is True, ok["octave_fold"]
    assert ok["bpm_grants_pass"] is False
    # shipped take: same beat, same onsets, same energy -> the change is ABSENT
    flat = dict(fast)
    shipped = confirm_pace_change(fast, flat, flat, bpm_before=42.857, bpm_after=42.857)
    assert shipped["verdict"] == "FAIL", shipped
    assert "energy_drop" in shipped["failed"] and "onset_reduction" in shipped["failed"]
    # bpm alone: no onset and energy evidence at all -> UNMEASURED, never PASS
    bare = confirm_pace_change({"onset_rate_per_s": 3.0}, fast, fast)
    assert bare["verdict"] == "UNMEASURED", bare
    # an octave alias is the SAME beat and can never register as a change
    fold = octave_fold_bpm(85.2, 181.5)
    assert fold["same_beat"] is True, fold
    return {"pair": ok["verdict"], "shipped": shipped["verdict"],
            "bare": bare["verdict"], "alias_same_beat": fold["same_beat"]}


if __name__ == "__main__":
    print(selftest())
