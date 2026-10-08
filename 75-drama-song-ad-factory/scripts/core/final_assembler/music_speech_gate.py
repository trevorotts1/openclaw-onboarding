#!/usr/bin/env python3
"""music_speech_gate: the music-under-speech delivery gate (manual 02
Part E E10, Critical; owner ADDENDUM 2 build order E8 -> E10).

Closes the hole that let two real ads pass delivery: every pre-E10 check
measured only voices (spoken share, echo tails, word presence) -- nobody
measured the MUSIC under the speech. Both ads had spoken lines recorded
over separate, music-less Suno takes (Leanne: digital silence between
song slices; Kiesett: a 1.3 s loop of the song at about -13 dB), and
both passed.

The gate FAILS when:
  * any spoken line's music sits MORE than 9 dB below the sung parts
    (the E9 duck is 6-8 dB on purpose, so a correct E8/E9 mix never
    trips it)                                          -> MUSIC_UNDER_SPEECH_LOW
  * any stretch anywhere in the ad has NO music longer than 0.3 s
    (the E8 bed is continuous, so a correct mix never has one)
                                                       -> MUSIC_GAP_TOO_LONG

Level math first, audio last: every check consumes a music level curve
[(start_s, end_s, db)], which comes from the E8/E9 mix plan directly or
is measured from the bed/master WAV with the stdlib `wave` module, or is
supplied as separated-stem levels. Tests need no media files.

The delivery receipt carries one field per spoken line,
{line_id, start_s, end_s, music_db, sung_ref_db} -- LINE_RECEIPT_FIELDS.
The writer side is core/delivery_variants/manifests.py write_cost_report,
which gained the optional spoken_lines field in this unit.

stdlib only. Run: python3 core/final_assembler/test_music_speech_gate_e10.py
"""
import math
import os
import wave as _wave
from math import isfinite

TOOL_NAME = "music_speech_gate"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.music-speech-gate/report/v1"

#: Owner ADDENDUM 2: fail any spoken line whose music is MORE than 9 dB
#: below the sung parts.
MAX_DROP_DB = 9.0
#: Owner ADDENDUM 2: no no-music stretch longer than 0.3 s anywhere.
MAX_GAP_S = 0.3
#: A level-curve window at or below this dBFS counts as NO music (digital
#: silence reads -120 dBFS; a real bed, ducked 8 dB, is far above this).
MUSIC_FLOOR_DB = -60.0
#: Level-curve window in seconds (well under the 0.3 s gap limit so the
#: gap check cannot miss a short no-music stretch).
CURVE_WIN_S = 0.05

#: The exact delivery-receipt field shape per spoken line.
LINE_RECEIPT_FIELDS = ("line_id", "start_s", "end_s", "music_db",
                       "sung_ref_db")

_DB_FLOOR = -120.0          # clamp for digital silence
_EPS = 1e-6                 # float edge tolerance (seconds, dB)


class MusicGateError(ValueError):
    """Malformed input -- a caller bug, never a domain verdict."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _num(v, what, code="BAD_INPUT"):
    if isinstance(v, bool) or not isinstance(v, (int, float)) \
            or not isfinite(float(v)):
        raise MusicGateError(code, "%s must be a finite number, got %r"
                             % (what, v))
    return float(v)


def _db(ratio):
    """dBFS of a linear rms ratio (0 -> -120 clamp)."""
    if ratio <= 0.0:
        return _DB_FLOOR
    return max(_DB_FLOOR, 20.0 * math.log10(ratio))


def _linear_db_mean(windows):
    """Mean power in dB over windows [(s, e, db)] (dB-domain mean done in
    the amplitude domain, like a level meter). Digital-silence windows
    contribute 0 amplitude, which pulls the mean down; a fully silent set
    reads _DB_FLOOR."""
    amps = [0.0 if w[2] <= _DB_FLOOR else 10.0 ** (w[2] / 20.0)
            for w in windows]
    if not amps or not any(amps):
        return _DB_FLOOR
    return _db(sum(amps) / len(amps))


# ---- curve sources --------------------------------------------------------

def level_curve_from_samples(mono, rate, win_s=CURVE_WIN_S,
                             full_scale=32768.0):
    """Per-window dBFS curve [(start_s, end_s, db)] from mono samples.

    Non-overlapping windows of win_s; a final short partial window is
    emitted for the uncovered remainder so [0, n/rate] is fully covered.
    ponytail: pure-python RMS is O(n); fine for gate-sized WAVs, swap to
    an array/chunked path when a multi-minute master actually hits it.
    """
    rate = int(rate)
    if rate <= 0:
        raise MusicGateError("BAD_RATE", "sample rate must be positive")
    mono = list(mono)
    if not mono:
        raise MusicGateError("BAD_SAMPLES", "no samples given")
    win = max(1, int(round(rate * float(win_s))))
    fs = float(full_scale)
    curve = []
    w = 0
    n = len(mono)
    while w < n:
        end = min(w + win, n)
        chunk = mono[w:end]
        acc = 0.0
        for v in chunk:
            fv = float(v)
            acc += fv * fv
        curve.append((w / rate, end / rate,
                      _db(math.sqrt(acc / len(chunk)) / fs)))
        w = end
    return curve


def load_wav_curve(path, win_s=CURVE_WIN_S):
    """Measure the music-level curve of a 16- or 32-bit PCM WAV (stereo
    downmixed to mono). stdlib-only measurement of the bed track E8
    produces (or of the master) -- no ffmpeg, no network, $0."""
    import array
    try:
        with _wave.open(os.fspath(path), "rb") as w:
            rate, width, channels = (w.getframerate(), w.getsampwidth(),
                                     w.getnchannels())
            raw = w.readframes(w.getnframes())
    except (_wave.Error, OSError, EOFError) as exc:
        raise MusicGateError("BAD_WAV",
                             "unreadable WAV %s: %s" % (path, exc)) from exc
    if width == 2:
        fmt, fs = "h", 32768.0
    elif width == 4:
        fmt, fs = "i", 2147483648.0
    else:
        raise MusicGateError("BAD_WAV",
                             "unsupported sample width %d" % width)
    data = array.array(fmt)
    frame = width * max(1, channels)
    data.frombytes(raw[: len(raw) - (len(raw) % frame)])
    if channels > 1:
        mono = []
        for i in range(0, len(data), channels):
            acc = 0.0
            for v in data[i:i + channels]:
                acc += v
            mono.append(acc / channels)
    else:
        mono = data
    return level_curve_from_samples(mono, rate, win_s=win_s,
                                    full_scale=fs)


def curve_from_mix_plan(mix_plan, song_db=-10.0):
    """Level curve from an E8/E9 mix plan (or a bare curve).

    Accepts {"music_regions": [{start_s, end_s, music_db}, ...]},
    {"bed_curve": [[start_s, end_s, db], ...]}, a bare list of
    [start_s, end_s, db] triples, or a real E8 bed_mixer plan
    {"gain_points": [(t, song_gain, instr_gain)], "duration_s": n}: the
    gain points are evaluated to a 50 ms level curve (song plays at
    song_db dBFS, the instrumental at song_db - duck_db; sum the linear
    gains, which is exactly what bed_mixer's amix does). Regions may
    carry music_db / level_db / gain_db spellings; anything without a
    numeric level is refused (BAD_MIX_PLAN): a plan without measured
    music levels proves nothing.
    """
    if isinstance(mix_plan, dict):
        raw = mix_plan.get("music_regions")
        if raw is None:
            raw = mix_plan.get("bed_curve")
        if raw is None and isinstance(mix_plan.get("gain_points"), list) \
                and mix_plan.get("gain_points"):
            return curve_from_gain_points(mix_plan, song_db=song_db)
    elif isinstance(mix_plan, list) and mix_plan \
            and isinstance(mix_plan[0], (list, tuple)) \
            and len(mix_plan[0]) == 3:
        raw = mix_plan
    elif isinstance(mix_plan, list) and mix_plan \
            and isinstance(mix_plan[0], dict):
        raw = mix_plan
    elif isinstance(mix_plan, list) and mix_plan \
            and isinstance(mix_plan[0], (list, tuple)) \
            and len(mix_plan[0]) == 3:
        raw = mix_plan
    else:
        raw = None
    if not isinstance(raw, list) or not raw:
        raise MusicGateError(
            "BAD_MIX_PLAN",
            "mix plan needs music_regions[] or bed_curve[] with numeric "
            "music_db levels")
    out = []
    for i, r in enumerate(raw):
        if isinstance(r, dict):
            db = r.get("music_db", r.get("level_db", r.get("gain_db")))
            start, end = r.get("start_s"), r.get("end_s")
            if db is None:
                raise MusicGateError(
                    "BAD_MIX_PLAN",
                    "music_regions[%d] carries no numeric music_db level"
                    % i)
        elif isinstance(r, (list, tuple)) and len(r) == 3:
            start, end, db = r
        else:
            raise MusicGateError("BAD_MIX_PLAN",
                                 "music_regions[%d] not understood" % i)
        s = _num(start, "music_regions[%d].start_s" % i, "BAD_MIX_PLAN")
        e = _num(end, "music_regions[%d].end_s" % i, "BAD_MIX_PLAN")
        d = _num(db, "music_regions[%d].music_db" % i, "BAD_MIX_PLAN")
        if e < s:
            raise MusicGateError("BAD_MIX_PLAN",
                                 "music_regions[%d] end before start" % i)
        out.append((s, e, d))
    return out


def curve_from_gain_points(plan, song_db=-10.0, win_s=CURVE_WIN_S):
    """Level curve from a real E8 bed_mixer plan (gain_points shape):
    [(t, song_gain, instr_gain)] breakpoints, song at song_db dBFS, the
    instrumental at song_db - duck_db (duck_db from the plan). Linear
    gains summed, exactly what bed_mixer's amix renders. 50 ms windows
    tile [0, duration_s]."""
    pts = plan.get("gain_points")
    if not isinstance(pts, list) or len(pts) < 2:
        raise MusicGateError("BAD_MIX_PLAN",
                             "plan gain_points list required")
    duration = _num(plan.get("duration_s"), "plan.duration_s",
                    "BAD_MIX_PLAN")
    duck = plan.get("duck_db", 7.0)
    duck = _num(duck, "plan.duck_db", "BAD_MIX_PLAN")
    # Both inputs are the same song's music at the same reference level;
    # the duck lives in the instrumental's GAIN plateau (10**(-duck/20)),
    # not in a lower source level. Double-dipping here is what turned a
    # 7 dB duck into -24 dB and failed a correct E8/E9 mix.
    song_amp = 10.0 ** (song_db / 20.0)
    instr_amp = song_amp

    def pair_at(t):
        lo, hi = 0, len(pts) - 1
        if t <= pts[lo][0]:
            return pts[lo][1], pts[lo][2]
        if t >= pts[hi][0]:
            return pts[hi][1], pts[hi][2]
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if pts[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        (t0, s0, i0), (t1, s1, i1) = pts[lo], pts[hi]
        if t1 - t0 < 1e-12:
            return s1, i1
        frac = (t - t0) / (t1 - t0)
        return s0 + frac * (s1 - s0), i0 + frac * (i1 - i0)

    curve, t = [], 0.0
    step = float(win_s)
    n = max(1, int(math.ceil(duration / step - 1e-9)))
    for k in range(n):
        a = min(k * step, duration)
        b = min(a + step, duration)
        sg, ig = pair_at((a + b) / 2.0)
        amp = song_amp * sg + instr_amp * ig
        curve.append((round(a, 6), round(b, 6), _db(amp)))
        if b >= duration:
            break
    return curve


# ---- input normalization --------------------------------------------------

def _lines(spoken_lines):
    if not isinstance(spoken_lines, list) or not spoken_lines:
        raise MusicGateError("BAD_SPOKEN_LINES",
                             "spoken_lines must be a non-empty list")
    out = []
    for i, ln in enumerate(spoken_lines):
        if not isinstance(ln, dict) \
                or not str(ln.get("line_id") or "").strip():
            raise MusicGateError("BAD_SPOKEN_LINE",
                                 "spoken_lines[%d] needs line_id" % i)
        start = _num(ln.get("start_s"), "spoken_lines[%d].start_s" % i,
                     "BAD_SPOKEN_LINE")
        end = _num(ln.get("end_s"), "spoken_lines[%d].end_s" % i,
                   "BAD_SPOKEN_LINE")
        if end <= start:
            raise MusicGateError(
                "BAD_SPOKEN_LINE",
                "spoken_lines[%d] end must be after start" % i)
        out.append({"line_id": str(ln["line_id"]).strip(),
                    "start_s": start, "end_s": end})
    return out


def _total(total_s):
    total = _num(total_s, "total_s", "BAD_TOTAL")
    if total <= 0:
        raise MusicGateError("BAD_TOTAL", "total_s must be positive")
    return total


def _sung_windows(sung_regions, lines, total):
    """Sung reference windows: explicit regions when given, else the whole
    ad minus the spoken lines (the model: music carries the sung parts and
    the bed under speech; every non-spoken second is a sung reference)."""
    if sung_regions is not None:
        if not isinstance(sung_regions, list):
            raise MusicGateError("BAD_SUNG_REGIONS",
                                 "sung_regions must be a list")
        spans = []
        for i, r in enumerate(sung_regions):
            if isinstance(r, dict):
                spans.append((_num(r.get("start_s"),
                                   "sung_regions[%d].start_s" % i,
                                   "BAD_SUNG_REGIONS"),
                              _num(r.get("end_s"),
                                   "sung_regions[%d].end_s" % i,
                                   "BAD_SUNG_REGIONS")))
            elif isinstance(r, (list, tuple)) and len(r) == 2:
                spans.append((float(r[0]), float(r[1])))
            else:
                raise MusicGateError("BAD_SUNG_REGIONS",
                                     "sung_regions[%d] not understood" % i)
            if spans[-1][1] < spans[-1][0]:
                raise MusicGateError(
                    "BAD_SUNG_REGIONS",
                    "sung_regions[%d] end before start" % i)
    else:
        spans, cursor = [], 0.0
        for ln in sorted(lines, key=lambda l: l["start_s"]):
            if ln["start_s"] > cursor + _EPS:
                spans.append((cursor, ln["start_s"]))
            cursor = max(cursor, ln["end_s"])
        if cursor < total - _EPS:
            spans.append((cursor, total))
    return [(max(0.0, s), min(total, e)) for s, e in spans if e > s]


# ---- measurement ----------------------------------------------------------

def _window_mean_db(curve, a, b):
    """Mean music dB over the line [a, b]. Windows wholly/partially inside
    are amplitude-averaged (short lines inside one window read that
    window's level)."""
    got = [w for w in curve
           if w[1] > a + _EPS and w[0] < b - _EPS]
    if not got:
        # Line shorter than the curve window: read the window containing
        # the line's midpoint, else the nearest window.
        mid = (a + b) / 2.0
        containing = [w for w in curve if w[0] <= mid <= w[1]]
        if containing:
            got = containing
        elif curve:
            got = [min(curve,
                       key=lambda w: abs((w[0] + w[1]) / 2.0 - mid))]
    if not got:
        return _DB_FLOOR
    return round(_linear_db_mean(got), 3)


def _covered(curve, a, b):
    """True when some window of the curve overlaps [a, b]."""
    return any(w[1] > a + _EPS and w[0] < b - _EPS for w in curve)


def _gaps(curve, total, floor_db, max_gap_s):
    """Every no-music stretch in [0, total] above max_gap_s: windows below
    floor_db AND holes the curve does not cover. Returns [(start_s,
    end_s)]. ponytail: single pass, sorted windows assumed sane."""
    spans = []
    run_start = None            # current no-music run, else None
    cursor = 0.0
    for w in sorted(curve, key=lambda c: c[0]):
        if w[0] >= total - _EPS:             # window entirely past total
            break
        w_end = min(w[1], total)             # clamp to the ad's runtime
        if w[0] > cursor + _EPS:             # hole in the curve coverage
            if run_start is None:
                run_start = cursor
            spans.append((run_start, w[0]))
            run_start = None
        if w[2] < floor_db:                  # below floor opens/continues
            if run_start is None:
                run_start = max(cursor, w[0])
        elif run_start is not None:          # above floor closes the run
            spans.append((run_start, max(cursor, w[0])))
            run_start = None
        cursor = max(cursor, w_end)
    if run_start is not None:                # run to the covered edge...
        spans.append((run_start, cursor))
    elif cursor < total - _EPS:              # ...or the uncovered tail
        spans.append((cursor, total))
    return [(s, e) for s, e in spans if e - s > max_gap_s + _EPS]


# ---- the gate -------------------------------------------------------------

def run_music_gate(*, spoken_lines, total_s, music_curve=None, bed_path=None,
                   mix_plan=None, sung_regions=None, sung_ref_db=None,
                   max_drop_db=MAX_DROP_DB, max_gap_s=MAX_GAP_S,
                   music_floor_db=MUSIC_FLOOR_DB, curve_win_s=CURVE_WIN_S):
    """One gate verdict. Returns {verdict, reason_code, reasons,
    spoken_lines (the delivery-receipt field), gaps, sung_spans, params}.
    Never raises merely because the ad is bad -- malformed input raises
    MusicGateError (caller bug)."""
    lines = _lines(spoken_lines)
    total = _total(total_s)
    max_drop = (MAX_DROP_DB if max_drop_db is None
                else _num(max_drop_db, "max_drop_db", "BAD_PARAM"))
    max_gap = (MAX_GAP_S if max_gap_s is None
               else _num(max_gap_s, "max_gap_s", "BAD_PARAM"))
    floor = (MUSIC_FLOOR_DB if music_floor_db is None
             else _num(music_floor_db, "music_floor_db", "BAD_PARAM"))

    # Curve source precedence: explicit curve > mix plan > bed WAV.
    if music_curve is not None:
        curve = curve_from_mix_plan(music_curve)
    elif mix_plan is not None:
        curve = curve_from_mix_plan(mix_plan)
    elif bed_path is not None:
        curve = load_wav_curve(bed_path, win_s=curve_win_s)
    else:
        raise MusicGateError("NO_MUSIC_SOURCE",
                             "music_curve, mix_plan or bed_path required")

    sung_spans = _sung_windows(sung_regions, lines, total)
    sung_wins = [w for w in curve
                 if any(w[0] >= s - _EPS and w[1] <= e + _EPS
                        for s, e in sung_spans)]
    if sung_ref_db is not None:
        sung_ref = _num(sung_ref_db, "sung_ref_db", "BAD_PARAM")
    elif sung_wins and _linear_db_mean(sung_wins) > floor:
        sung_ref = round(_linear_db_mean(sung_wins), 3)
    else:
        sung_ref = None     # no sung music above the floor; the gap check
                            # still fails a silent ad on its own

    receipt, line_fails = [], []
    for ln in lines:
        music_db = _window_mean_db(curve, ln["start_s"], ln["end_s"])
        drop = (None if sung_ref is None
                else round(sung_ref - music_db, 3))
        receipt.append({"line_id": ln["line_id"],
                        "start_s": round(ln["start_s"], 6),
                        "end_s": round(ln["end_s"], 6),
                        "music_db": music_db, "sung_ref_db": sung_ref})
        if drop is not None and drop > max_drop + _EPS \
                and music_db > floor:
            line_fails.append(
                "line %r music %.1f dB is %.1f dB below the sung parts "
                "(cap %.1f dB)" % (ln["line_id"], music_db, drop,
                                   max_drop))
        elif drop is not None and drop > max_drop + _EPS \
                and music_db <= floor:
            # At/below the music floor the line has NO music: that is the
            # gap check's verdict (one reason per defect, not two).
            pass
    reasons = list(line_fails)

    gaps = _gaps(curve, total, floor, max_gap)
    gap_fails = ["no-music stretch %.3f s at %.3f-%.3f s exceeds the "
                 "%.2f s cap" % (e - s, s, e, max_gap) for s, e in gaps]
    reasons.extend(gap_fails)

    if line_fails:
        reasons.insert(0, "MUSIC_UNDER_SPEECH_LOW")
    if gap_fails:
        reasons.insert(1 if line_fails else 0, "MUSIC_GAP_TOO_LONG")

    verdict = "PASS" if not reasons else "FAIL"
    if not reasons:
        primary = "PASS"
    elif line_fails:
        primary = "MUSIC_UNDER_SPEECH_LOW"
    else:
        primary = "MUSIC_GAP_TOO_LONG"
    return {
        "schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION, "verdict": verdict,
        "reason_code": primary, "reasons": reasons,
        "spoken_lines": receipt,       # THE delivery-receipt field
        "gaps": [{"start_s": round(s, 6), "end_s": round(e, 6),
                  "dur_s": round(e - s, 6)} for s, e in gaps],
        "sung_spans": [{"start_s": round(s, 6), "end_s": round(e, 6)}
                       for s, e in sung_spans],
        "sung_ref_db": sung_ref,
        "params": {"max_drop_db": max_drop, "max_gap_s": max_gap,
                   "music_floor_db": floor},
        "checker_version": TOOL_VERSION,
    }


# ---- delivery-receipt field ----------------------------------------------

def receipt_lines(gate_record):
    """The exact per-line receipt dicts from a gate record (the delivery
    receipt's spoken_lines field). Validates the five-field shape."""
    if not isinstance(gate_record, dict) \
            or not isinstance(gate_record.get("spoken_lines"), list):
        raise MusicGateError("BAD_GATE_RECORD",
                             "gate record carries no spoken_lines")
    out = []
    for i, ln in enumerate(gate_record["spoken_lines"]):
        if not isinstance(ln, dict) \
                or set(ln.keys()) != set(LINE_RECEIPT_FIELDS):
            raise MusicGateError(
                "BAD_GATE_RECORD",
                "spoken_lines[%d] not the receipt shape %s"
                % (i, list(LINE_RECEIPT_FIELDS)))
        out.append({k: ln[k] for k in LINE_RECEIPT_FIELDS})
    return out


# ---- shared final-QC gate step --------------------------------------------

def gate_step(tl, base_dir=".", **overrides):
    """The final-QC gate step for the shared gate: measure + judge the
    music under speech for one assembled ad. Timeline optional gate
    input (see music_gate_input) or explicit kwargs; returns the gate
    record, or None when the timeline declares no music gate input
    (pre-E8/E9 timelines keep rendering exactly as before -- a caller
    that wants the check mandatory passes spoken_lines/total_s here)."""
    kwargs = music_gate_input(tl, base_dir) if tl is not None \
        else dict(overrides)
    if kwargs is None:
        return None
    if overrides:
        kwargs.update({k: v for k, v in overrides.items() if v is not None})
    return run_music_gate(**kwargs)


def assert_gate_passes(gate_record):
    """Assert-style check for the gate record (assembler wiring): raise
    AssertionError carrying the reason codes when the gate is not PASS."""
    if gate_record.get("verdict") != "PASS":
        raise AssertionError(
            "%s: %s" % (gate_record.get("reason_code"),
                        "; ".join(gate_record.get("reasons", []))))
    return True


# ---- timeline seam --------------------------------------------------------

def music_gate_input(tl, base_dir="."):
    """Extract + normalize the declarative music-gate input on a timeline:

        tl["music_gate"] = {"spoken_lines": [{line_id, start_s, end_s}],
                            "total_seconds": n,
                            "music_curve": [[s, e, db]]
                            | "mix_plan": <dict or JSON string>
                            | "bed_path": "bed.wav",   # -> base_dir
                            ["sung_regions" | "sung_ref_db" |
                             "max_drop_db" | "max_gap_s" |
                             "music_floor_db"]}

    Returns kwargs for run_music_gate(), or None when the timeline
    declares no music gate (pre-E8/E9 timelines render exactly as before).
    """
    gate_in = tl.get("music_gate")
    if not isinstance(gate_in, dict):
        return None
    kwargs = {"spoken_lines": gate_in.get("spoken_lines"),
              "total_s": gate_in.get("total_seconds",
                                     gate_in.get("total_s"))}
    if kwargs["total_s"] is None:
        raise MusicGateError("BAD_MUSIC_GATE", "total_seconds required")
    if kwargs["spoken_lines"] is None:
        raise MusicGateError("BAD_MUSIC_GATE", "spoken_lines required")
    src = gate_in.get("music_curve")
    if src is None:
        src = gate_in.get("mix_plan")
    if src is None:
        bp = gate_in.get("bed_path")
        if bp:
            kwargs["bed_path"] = bp if os.path.isabs(bp) \
                else os.path.join(base_dir, bp)
    if src is not None:
        if isinstance(src, str):
            import json
            try:
                src = json.loads(src)
            except json.JSONDecodeError as exc:
                raise MusicGateError(
                    "BAD_MUSIC_GATE",
                    "mix plan not parseable: %s" % exc) from exc
        if gate_in.get("music_curve") is not None:
            kwargs["music_curve"] = gate_in["music_curve"]
        else:
            kwargs["mix_plan"] = src
    if not any(kwargs.get(k) is not None
               for k in ("music_curve", "mix_plan", "bed_path")):
        raise MusicGateError("BAD_MUSIC_GATE",
                             "music_curve, mix_plan or bed_path required")
    for key in ("sung_regions", "sung_ref_db", "max_drop_db",
                "max_gap_s", "music_floor_db"):
        if gate_in.get(key) is not None:
            kwargs[key] = gate_in[key]
    return kwargs


__all__ = [
    "CURVE_WIN_S", "LINE_RECEIPT_FIELDS", "MAX_DROP_DB", "MAX_GAP_S",
    "MUSIC_FLOOR_DB", "SCHEMA_VERSION", "TOOL_NAME", "TOOL_VERSION",
    "MusicGateError", "assert_gate_passes", "curve_from_gain_points",
    "curve_from_mix_plan", "gate_step", "level_curve_from_samples",
    "load_wav_curve", "music_gate_input", "receipt_lines",
    "run_music_gate",
]