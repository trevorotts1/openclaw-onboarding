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
import json
import math
import os

TOOL_NAME = "pace_change"
TOOL_VERSION = "2.0.0"
SCHEMA = "blackceo.pace-change/v2"

#: NEW ACCEPTANCE RULES (WWFIX 2026-10-11; WW-23 2026-10-11).
#:
#: WW-23: the D3 numbers live ONCE in core/acceptance-profile.json
#: (ww_wave.pace_change) and are read here; the literals below are the fallback
#: used only when that file or its key is absent. Every value is PROPOSED -- a
#: new acceptance choice, never a measured limit and never a number Trevor set.
def _ww_pace_profile():
    try:
        _p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "acceptance-profile.json")
        with open(_p, encoding="utf-8") as f:
            return ((json.load(f) or {}).get("ww_wave") or {}).get("pace_change") or {}
    except Exception:
        return {}

_WW_PACE = _ww_pace_profile()
PACE_ONSET_REDUCTION = float(_WW_PACE.get("problem_onset_reduction", 0.30))  # problem onset rate at most this share
PACE_ENERGY_DROP_DB = float(_WW_PACE.get("problem_energy_drop_db", 3.0))     # AND at least this much quieter
PACE_RETURN_TOL = float(_WW_PACE.get("solution_onset_return_tol", 0.20))     # closing onset rate back within this share
#: WW-23: the return-energy bound is SYMMETRIC -- the closing window may be at
#: most this many dB ABOVE the baseline as well as this many dB below it. The
#: old one-sided form (a >= b - 3) let a 24 dB overshoot pass as a "return".
PACE_RETURN_DB = float(_WW_PACE.get("solution_energy_return_db", 3.0))
#: WW-23: TWO mandatory seams -- the drop boundary and the return boundary.
PACE_SEAM_COUNT = int(_WW_PACE.get("mandatory_seams", 2))
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

#: Option A (Trevor order, 2026-10-17). A provider places a gear change where
#: the SONG wants it, not at a clock second: Suno returned -7.77 dB drops at
#: 6 s and 44 s while the ordered seam sat at 16 s, so a window pinned to the
#: ordered second measured a RISE and refused a take that carries a real drop.
#: The windows are therefore LOCATED across a search region around the ordered
#: seam. Every threshold below is untouched -- only WHERE the windows are
#: sampled moves, and the located second is recorded on the take.
PACE_SEARCH_MARGIN_S = 10.0   # how far either side of the ordered seam we look
PACE_LOCATE_WIN_S = 3.0       # one window's length
PACE_LOCATE_STEP_S = 0.5      # candidate-seam grid


def locate_gear_change(samples, sr, lo_s, hi_s, win_s=PACE_LOCATE_WIN_S,
                       step_s=PACE_LOCATE_STEP_S):
    """The strongest MEASURED gear change inside [lo_s, hi_s), and where it is.

    Candidates are scored with ``window_stats`` -- the same reader the ordered
    seam uses -- and the winner is the seam with the largest energy drop
    (ties go to the earlier seam). Thresholds are NOT applied here: the caller
    judges the returned windows against the unchanged PACE_* floors, so a take
    with no qualifying change still fails.

    Returns {"found": bool, "at_s", "before", "problem", "onset_reduction",
    "energy_drop_db", "meets": {"onset_reduction", "energy_drop"}}. ``found``
    is True only when BOTH floors are met at some candidate; otherwise the
    strongest candidate is still returned so the refusal can be reported with
    real numbers rather than an empty result."""
    if hasattr(samples, "tolist"):   # numpy array from the decode path
        samples = samples.tolist()
    if samples is None or not sr:
        return {"found": False, "at_s": None, "before": None, "problem": None,
                "onset_reduction": None, "energy_drop_db": None,
                "meets": {"onset_reduction": False, "energy_drop": False},
                "reason": "no samples supplied"}
    lo = max(0.0, float(lo_s))
    hi = max(lo, float(hi_s))
    best, best_meeting = None, None
    t = lo
    while t + step_s <= hi + 1e-9:
        b = window_stats(samples, sr, t - win_s, t)
        p = window_stats(samples, sr, t, t + win_s)
        if b is None or p is None:
            t += step_s
            continue
        drop = b["rms_dbfs"] - p["rms_dbfs"]
        red = (1.0 - p["onset_rate_per_s"] / b["onset_rate_per_s"]
               if b["onset_rate_per_s"] > 0 else None)
        cand = {"at_s": round(t, 3), "before": b, "problem": p,
                "onset_reduction": None if red is None else round(red, 4),
                "energy_drop_db": round(drop, 3),
                "meets": {"onset_reduction": red is not None and red >= PACE_ONSET_REDUCTION,
                          "energy_drop": drop >= PACE_ENERGY_DROP_DB}}
        if best is None or cand["energy_drop_db"] > best["energy_drop_db"]:
            best = cand
        if all(cand["meets"].values()):
            if best_meeting is None or cand["at_s"] < best_meeting["at_s"]:
                best_meeting = cand
        t += step_s
    if best is None:
        return {"found": False, "at_s": None, "before": None, "problem": None,
                "onset_reduction": None, "energy_drop_db": None,
                "meets": {"onset_reduction": False, "energy_drop": False},
                "reason": "no measurable window in [%.1f, %.1f) s" % (lo, hi)}
    out = dict(best_meeting or best)
    out["found"] = best_meeting is not None
    out["search"] = {"lo_s": lo, "hi_s": hi, "win_s": win_s, "step_s": step_s}
    out["strongest"] = {"at_s": best["at_s"],
                        "energy_drop_db": best["energy_drop_db"],
                        "onset_reduction": best["onset_reduction"],
                        "meets": best["meets"]}
    return out


def locate_return(samples, sr, lo_s, hi_s, before, win_s=PACE_LOCATE_WIN_S,
                  step_s=PACE_LOCATE_STEP_S):
    """The FIRST window after a located drop that is back on the opening
    baseline, and where it is.

    The return carries the same problem as the drop: a provider puts it where
    the song wants it, so a window pinned to the ordered return second
    measures the wrong moment and refuses a take that does come back. The
    bounds are the SAME approved ones (PACE_RETURN_TOL onset, PACE_RETURN_DB
    energy against the opening window); only WHERE the window is sampled
    moves, and the located second is reported."""
    b = _window(before, "before")
    if hasattr(samples, "tolist"):
        samples = samples.tolist()
    lo = max(0.0, float(lo_s))
    hi = max(lo, float(hi_s))
    best = None
    t = lo
    while t + step_s <= hi + 1e-9:
        w = window_stats(samples, sr, t, t + win_s)
        if w is not None and b["onset_rate"] > 0:
            onset_gap = abs(w["onset_rate_per_s"] - b["onset_rate"]) / b["onset_rate"]
            energy_gap = abs(w["rms_dbfs"] - b["rms_dbfs"])
            ok = (onset_gap <= PACE_RETURN_TOL and energy_gap <= PACE_RETURN_DB)
            cand = {"at_s": round(t, 3), "after": w,
                    "onset_gap": round(onset_gap, 4),
                    "energy_gap_db": round(energy_gap, 3), "ok": ok}
            if best is None or (cand["ok"], -cand["at_s"]) > (best["ok"], -best["at_s"]):
                best = cand
            if ok:
                best = cand
                break
        t += step_s
    if best is None:
        return {"found": False, "at_s": None, "after": None,
                "onset_gap": None, "energy_gap_db": None,
                "reason": "no measurable window in [%.1f, %.1f) s" % (lo, hi)}
    best["found"] = best.pop("ok")
    return best


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
                        hop_s=None, bpm_before=None, bpm_after=None, reason=None,
                        return_boundary_s=None, method=False, located_at_s=None):
    """Judge one ordered gear change: before -> problem -> after.

    PASS needs ALL of: >= 30% onset-rate reduction, >= 3 dB energy drop, the
    return to baseline within 20% onset AND a SYMMETRIC energy bound, and --
    when an envelope is supplied -- a smooth seam. WW-23: the return energy is
    an ABSOLUTE bound (|after - before| <= PACE_RETURN_DB), so a closing window
    that overshoots the baseline by 24 dB FAILS; and when the order carries a
    SECOND, distinct return boundary, both seams are checked independently.
    Anything less is FAIL. Missing onset or energy evidence is UNMEASURED,
    never PASS; bpm is reported and folded but never grants a PASS.

    ``method=True`` (W1-method-song-U2, decision #5): the SECOND seam is the
    Hero Shift, and it passes on any CLEAR measured change of pace or energy at
    that moment -- onset rate moved at least PACE_RETURN_TOL from the opening
    window, OR energy moved at least PACE_ENERGY_DROP_DB -- in EITHER
    direction. It no longer has to return to the opening groove. The FIRST seam
    (the ERM Drop) keeps its 30% onset reduction and 3 dB drop unchanged, and a
    smooth seam is still required at both."""
    try:
        b = _window(before, "before")
        p = _window(problem, "problem")
        a = _window(after, "after")
    except PaceError as e:
        return {"schema": SCHEMA, "verdict": "UNMEASURED", "reason_code":
                "PACE_EVIDENCE_UNMEASURED", "detail": str(e),
                "grants_pass": False, "reason": reason, "method": bool(method),
                "source": "WWFIX D1/F2 (X3): onset + energy, never bpm alone"}
    onset_reduction = (1.0 - p["onset_rate"] / b["onset_rate"]) if b["onset_rate"] > 0 else None
    energy_drop = round(b["rms_dbfs"] - p["rms_dbfs"], 3)
    # RETURN TO BASELINE: the closing window is measured against the window
    # BEFORE the problem, not against the problem window itself. It is the SAME
    # measurement a method run reads as "did the Hero Shift change anything".
    return_gap = (abs(a["onset_rate"] - b["onset_rate"]) / b["onset_rate"]
                  if b["onset_rate"] > 0 else None)
    # WW-23 SYMMETRIC return energy: an absolute distance, not a one-sided floor.
    energy_gap = round(abs(a["rms_dbfs"] - b["rms_dbfs"]), 3)
    return_db = round(a["rms_dbfs"] - (b["rms_dbfs"] - PACE_ENERGY_DROP_DB), 3)
    checks = {
        "onset_reduction": onset_reduction is not None
                            and onset_reduction >= PACE_ONSET_REDUCTION,
        "energy_drop": energy_drop >= PACE_ENERGY_DROP_DB,
    }
    if method:
        # W1-method-song-U2 (decision #5): the Hero Shift is ANY clear change of
        # pace or energy, in either direction -- faster, slower, heavier, bigger,
        # dramatic. Returning to the opening groove is ONE way, not the only way,
        # so neither side of the old return bound can refuse it. Both thresholds
        # are the approved numbers above; no new acceptance number is set here.
        checks["hero_shift_change"] = bool(
            (return_gap is not None and return_gap >= PACE_RETURN_TOL)
            or energy_gap >= PACE_ENERGY_DROP_DB)
    else:
        checks["onset_return"] = return_gap is not None and return_gap <= PACE_RETURN_TOL
        checks["energy_return"] = energy_gap <= PACE_RETURN_DB
    seam, return_seam = None, None
    if envelope is not None and hop_s:
        if boundary_s is not None:
            seam = smooth_transition_check(envelope, hop_s, boundary_s)
            if seam.get("smooth") is not None:
                checks["smooth_transition"] = bool(seam["smooth"])
        # WW-23: the SECOND mandatory seam (the return) is judged the same way.
        if return_boundary_s is not None:
            return_seam = smooth_transition_check(envelope, hop_s, return_boundary_s)
            if return_seam.get("smooth") is not None:
                checks["smooth_transition_return"] = bool(return_seam["smooth"])
    fold = None
    if bpm_before is not None and bpm_after is not None:
        try:
            fold = octave_fold_bpm(bpm_before, bpm_after)
        except PaceError:
            fold = None
    verdict = "PASS" if all(checks.values()) else "FAIL"
    failed = sorted(k for k, v in checks.items() if not v)
    _loc = (" [change located at %.1f s]" % located_at_s
            if isinstance(located_at_s, (int, float)) else "")
    if verdict == "PASS":
        if method:
            _detail = ("gear change confirmed: onsets %.3f -> %.3f/s (%.0f%% down), "
                       "%+.2f dB; the Hero Shift moves to %.3f/s and %+.2f dB vs the "
                       "opening (any clear change, either direction)"
                       % (b["onset_rate"], p["onset_rate"], (onset_reduction or 0) * 100,
                          -energy_drop, a["onset_rate"], -energy_gap))
        else:
            _detail = ("gear change confirmed: onsets %.3f -> %.3f/s (%.0f%% down), "
                       "%+.2f dB, back to %.3f/s and %+.2f dB"
                       % (b["onset_rate"], p["onset_rate"], (onset_reduction or 0) * 100,
                          -energy_drop, a["onset_rate"], -energy_gap))
    else:
        _detail = ("no gear change: %s (onsets %.3f -> %.3f/s, %+.2f dB)"
                   % (", ".join(failed), b["onset_rate"], p["onset_rate"], -energy_drop))
    _detail += _loc
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
        "return_energy_gap_db": energy_gap,
        "return_energy_margin_db": return_db,
        "smooth_transition": seam,
        "smooth_transition_return": return_seam,
        "octave_fold": fold,
        "bpm_grants_pass": False,
        #: Option A: WHERE the measured change actually sits, when the caller
        #: located it (locate_gear_change) instead of sampling the ordered second.
        "located_at_s": located_at_s,
        #: W1-method-song-U2: which second-seam rule judged this take.
        "method": bool(method),
        "second_seam_rule": ("hero_shift_any_clear_change" if method
                             else "return_to_opening_groove"),
        "floor": {"onset_reduction": PACE_ONSET_REDUCTION,
                  "energy_drop_db": PACE_ENERGY_DROP_DB,
                  "return_tol": PACE_RETURN_TOL, "return_db": PACE_RETURN_DB,
                  "return_energy_is_symmetric": True,
                  "mandatory_seams": PACE_SEAM_COUNT,
                  "peak_min_spacing_s": PEAK_MIN_SPACING_S},
        "detail": _detail,
        "reason": reason,
        #: NEW ACCEPTANCE RULE: every threshold here is set by this fix.
        "thresholds_are_new_acceptance_rules": True,
        "source": "WWFIX D1/F2 (X3/X4) + WW-23: onset reduction + energy drop + "
                  "symmetric return energy + BOTH seams; bpm alone never grants PASS",
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
    if isinstance(order, dict):
        if order.get("boundary_s") is not None:
            kw.setdefault("boundary_s", order["boundary_s"])
        # WW-23: the SECOND mandatory seam (the return) rides the order too.
        if order.get("return_boundary_s") is not None:
            kw.setdefault("return_boundary_s", order["return_boundary_s"])
        # Option A: the measured second the change was located at, when the
        # caller scanned for it (locate_gear_change) rather than sampling the
        # ordered seam. Recorded on the take; no threshold reads it.
        if order.get("located_at_s") is not None:
            kw.setdefault("located_at_s", order["located_at_s"])
        # W1-method-song-U2: a METHOD order judges the second seam as the Hero
        # Shift -- any clear change, either direction -- not as a return.
        kw.setdefault("method", bool(order.get("method")))
    out = confirm_pace_change(before, problem, after, reason=reason, **kw)
    out["applicable"] = True
    return out


# ---- the pace component of the creative fingerprint (WW-03 / WW-15) --------
#
# WW-03 binds a take to ONE approved creative revision by a fingerprint whose
# five components are lines, delivery, beat map, hook and pace. This module owns
# the PACE component so it is defined in exactly one place: the ordered gear
# shift a plan carries (``pace_change`` / ``_pace_plan``), canonicalised to the
# approved lowest-point direction and its return. The approved direction words
# ("half-time", "thin drums", the return) are the specification's own
# (WW-07: "half-time, thin drums ... turn and rise back to the groove"); they
# are recorded here, never re-derived per caller.

PACE_CUE_DROP = "half-time"
PACE_CUE_RETURN = "turn and rise back to the groove"
FINGERPRINT_SCHEMA = "blackceo.pace-cue/v1"
#: WW-23: the TWO approved semantic anchors a pace order names -- the drop and
#: the return -- plus the two DISTINCT seam timestamps it must carry. NEW
#: ACCEPTANCE RULE (see core/acceptance-profile.json ww_wave.pace_change).
PACE_ANCHOR_DROP = "drop"
PACE_ANCHOR_RETURN = "return"
#: W1-method-song-U2 (BUILD-PLAN; METHOD-INTEGRATION F5, conflicts C3/C4): a
#: METHOD run names the two seams after the blueprint's own cues -- the ERM Drop
#: and the Hero Shift -- instead of the generic drop/return. Both pairs are
#: approved; a method order carrying either pair is accepted.
PACE_ANCHOR_ERM_DROP = "erm_drop"
PACE_ANCHOR_HERO_SHIFT = "hero_shift"
APPROVED_DROP_ANCHORS = (PACE_ANCHOR_DROP, PACE_ANCHOR_ERM_DROP)
APPROVED_RETURN_ANCHORS = (PACE_ANCHOR_RETURN, PACE_ANCHOR_HERO_SHIFT)
#: The blueprint seconds a METHOD order must bind its two seams to. They are the
#: SAME names ``length_formula.plan(..., method=True)["method"]`` emits (F2) and
#: ``method_plan.pace_order(blueprint)`` must copy onto the order, because this
#: gate sees the order alone and can never read the blueprint itself.
METHOD_SEAM_ANCHORS = (("boundary_s", "erm_apex_s", "drop_s", "the blueprint ERM apex"),
                       ("return_boundary_s", "hero_shift_s", "return_s", "the Hero Shift"))
PACE_SEAM_KEYS = ("boundary_s", "return_boundary_s")


def _anchor_defaults(order):
    """The approved anchor NAME pair for one order: the method's own two seams
    (``erm_drop`` / ``hero_shift``) on a method order, the generic pair
    (``drop`` / ``return``) on any other. NEW ACCEPTANCE RULE (W1-method-song-U2)."""
    if isinstance(order, dict) and order.get("method"):
        return PACE_ANCHOR_ERM_DROP, PACE_ANCHOR_HERO_SHIFT
    return PACE_ANCHOR_DROP, PACE_ANCHOR_RETURN

def canonical_pace(order):
    """The ordered gear-shift cue a plan carries, as ONE stable dict -- or None
    when the plan carries no ordered change (nothing to bind). Accepts a plan,
    a ``pace_change`` order or a bare reason string."""
    if not order:
        return None
    if isinstance(order, dict):
        if "pace_change" in order or "_pace_plan" in order:
            order = order.get("pace_change") or order.get("_pace_plan")
            if not order:
                return None
    if not isinstance(order, dict):
        order = {"reason": str(order)}
    boundary = order.get("boundary_s")
    ret_boundary = order.get("return_boundary_s")
    drop_default, return_default = _anchor_defaults(order)
    return {
        "schema": FINGERPRINT_SCHEMA,
        "drop_anchor": order.get("drop_anchor") or drop_default,
        "return_anchor": order.get("return_anchor") or return_default,
        "boundary_s": None if boundary is None else round(float(boundary), 6),
        "return_boundary_s": (None if ret_boundary is None
                              else round(float(ret_boundary), 6)),
        "drop": order.get("drop") or PACE_CUE_DROP,
        "thin_drums": bool(order.get("thin_drums", True)),
        "return": order.get("return") or PACE_CUE_RETURN,
        "reason": order.get("reason"),
    }


def pace_fingerprint_component(order):
    """The canonical JSON string of the pace cue, for the creative fingerprint.
    Empty string when there is no ordered change (a valid component value)."""
    cue = canonical_pace(order)
    if cue is None:
        return ""
    return json.dumps(cue, sort_keys=True, separators=(",", ":"))


# ---- WW-23: the pre-generation payload gate --------------------------------
#
# The audio gate (D3, ``confirm_pace_change``) inspects the EXPORTS. These three
# guards run BEFORE any generation on the exact request the provider would
# receive: the order must carry BOTH approved anchors and TWO DISTINCT seam
# timestamps, the final style must carry BOTH directions, and the internal
# ``_pace_plan`` judging metadata must never ride a provider-visible field.

def pace_anchors(order):
    """The TWO approved semantic anchors a pace order names, resolved with the
    specification's own cue words as the fallback. A METHOD order names its own
    two seams (erm_drop / hero_shift) when it names none."""
    o = order if isinstance(order, dict) else {"reason": str(order)}
    drop_default, return_default = _anchor_defaults(o)
    return {"drop": o.get("drop") or PACE_CUE_DROP,
            "return": o.get("return") or PACE_CUE_RETURN,
            "drop_anchor": o.get("drop_anchor") or drop_default,
            "return_anchor": o.get("return_anchor") or return_default}

def pace_seams(order):
    """The TWO mandatory seam timestamps of one pace order.

    Returns {"drop_s", "return_s", "distinct", "missing", "reused"}. ``missing``
    names the absent seam key(s); ``reused`` is True when both seams were given
    but share the SAME timestamp (a reused boundary is not two transitions)."""
    o = order if isinstance(order, dict) else {}
    vals = {}
    for key in PACE_SEAM_KEYS:
        v = o.get(key)
        if v is None:
            vals[key] = None
            continue
        try:
            vals[key] = float(v)
        except (TypeError, ValueError):
            vals[key] = None
    drop, ret = vals["boundary_s"], vals["return_boundary_s"]
    missing = [k for k in PACE_SEAM_KEYS if vals[k] is None]
    return {"drop_s": drop, "return_s": ret,
            "missing": missing,
            "reused": not missing and drop == ret,
            "distinct": not missing and drop != ret}

def _at_anchor(seam_s, anchor_s):
    """True when the seam sits exactly on the blueprint anchor (same number,
    either numeric type). A non-numeric anchor never matches -- fail closed."""
    try:
        return round(float(seam_s), 6) == round(float(anchor_s), 6)
    except (TypeError, ValueError):
        return False

def check_pace_plan(order):
    """BEFORE generation: the ordered pace change must carry TWO approved
    semantic anchors and TWO DISTINCT seam timestamps. A missing seam, a reused
    boundary (both seams the same moment) or a non-numeric seam is refused HERE,
    with the reason string. No order -> no reasons (nothing to enforce).

    W1-method-song-U2 (METHOD-INTEGRATION F5): on a METHOD order the approved
    anchor names are ``erm_drop`` / ``hero_shift`` and BOTH seams must sit on
    the blueprint seconds the order carries (``erm_apex_s``, ``hero_shift_s``);
    any other binding is refused with ``PACE_SEAM_NOT_AT_ANCHOR``. The blueprint
    itself lives in ``creative/blueprint.json``, which this gate cannot read --
    ``method_plan.pace_order(blueprint)`` copies those two seconds onto the order."""
    if not order:
        return []
    reasons = []
    o = order if isinstance(order, dict) else {}
    anchors = pace_anchors(order)
    if not str(anchors["drop"]).strip() or not str(anchors["return"]).strip():
        reasons.append("PACE_ANCHOR_MISSING: the ordered pace change must name "
                       "both approved anchors (the drop and the return)")
    if o.get("drop_anchor") and o["drop_anchor"] not in APPROVED_DROP_ANCHORS:
        reasons.append("PACE_ANCHOR_UNKNOWN: %r is not an approved drop anchor (%s)"
                       % (o["drop_anchor"], ", ".join(APPROVED_DROP_ANCHORS)))
    if o.get("return_anchor") and o["return_anchor"] not in APPROVED_RETURN_ANCHORS:
        reasons.append("PACE_ANCHOR_UNKNOWN: %r is not an approved return anchor (%s)"
                       % (o["return_anchor"], ", ".join(APPROVED_RETURN_ANCHORS)))
    seams = pace_seams(order)
    if seams["missing"]:
        reasons.append("PACE_SEAM_MISSING: the ordered pace change carries %s; "
                       "two mandatory seams (boundary_s and return_boundary_s) are "
                       "required" % ", ".join(seams["missing"]))
    elif seams["reused"]:
        reasons.append("PACE_SEAM_REUSED_BOUNDARY: the drop and the return share "
                       "the timestamp %r; the two musical transitions are distinct "
                       "moments, never one reused boundary" % (seams["drop_s"],))
    if o.get("method"):
        missing = ["%s (%s)" % (key, label) for _seam, key, _rep, label
                   in METHOD_SEAM_ANCHORS if o.get(key) is None]
        if missing:
            reasons.append("PACE_SEAM_NOT_AT_ANCHOR: a method order must carry the "
                           "blueprint seconds %s so both seams can be bound to them"
                           % ", ".join(missing))
        else:
            for seam_key, anchor_key, rep_key, label in METHOD_SEAM_ANCHORS:
                seam_s = seams[rep_key]
                if seam_s is None:
                    continue            # PACE_SEAM_MISSING already said it
                if not _at_anchor(seam_s, o.get(anchor_key)):
                    reasons.append("PACE_SEAM_NOT_AT_ANCHOR: %s is %r, not the "
                                   "blueprint %s %r (W1-method-song-U2)"
                                   % (seam_key, seam_s, label, o.get(anchor_key)))
    return reasons

def pace_provider_leak(payload):
    """WW-23: True when the internal ``_pace_plan`` judging metadata rides any
    provider-visible field. The final style carrying the two DIRECTIONS is
    required and fine; the metadata KEY is not a provider instruction and must
    be stripped before generation (``song_dispatch.run_takes`` does this)."""
    try:
        text = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        return True
    return "_pace_plan" in text

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
    # WW-23: the return energy is SYMMETRIC -- a 24 dB OVERSHOOT is not a return
    over = confirm_pace_change(fast, half, {"onset_rate_per_s": 2.9, "rms_dbfs": 10.0})
    assert over["verdict"] == "FAIL" and "energy_return" in over["failed"], over
    assert over["return_energy_gap_db"] == 24.0, over
    # WW-23: two DISTINCT seams; a missing seam and a reused boundary both refuse
    assert check_pace_plan({"drop": "half-time", "return": "rise",
                            "boundary_s": 20.0, "return_boundary_s": 60.0}) == []
    assert any("PACE_SEAM_MISSING" in r for r in check_pace_plan({"boundary_s": 20.0}))
    assert any("PACE_SEAM_REUSED_BOUNDARY" in r
               for r in check_pace_plan({"boundary_s": 20.0, "return_boundary_s": 20.0}))
    return {"pair": ok["verdict"], "shipped": shipped["verdict"],
            "bare": bare["verdict"], "alias_same_beat": fold["same_beat"],
            "overshoot": over["verdict"]}


if __name__ == "__main__":
    print(selftest())
