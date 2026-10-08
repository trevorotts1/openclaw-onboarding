#!/usr/bin/env python3
"""Voice-match QC (owner decision D17, plan section 6.6). Stdlib only.

Fail-closed checks that run on every spoken/sung line BEFORE assembly:

1. Pitch band by gender -- measured fundamental must fall inside the D17 band:
   male 85-155 Hz, female 165-255 Hz (inclusive). The 156-164 Hz gap belongs
   to neither gender, so a line that lands there fails either claim.
2. On-screen speaker -- the character visible while the line plays must be the
   speaker, or a declared voice source (phone/laptop/speaker/...). Any other
   face on screen while someone else's voice plays fails (D17 2026-10-07
   hybrid-test failure: Chanel on screen during the male HR voicemail).
3. Same-gender distinctness -- two characters of one gender whose measured
   pitches sit closer than SAME_GENDER_MIN_SEPARATION_HZ fail as "same voice".

Deterministic reference implementation: autocorrelation pitch estimation over
synthesized fixture tones. No network module, no provider call, no spend.

Fail-closed everywhere: missing audio, unreadable audio, silence, missing or
unknown gender, missing speaker/onscreen field -> failure (or UNAVAILABLE),
never PASS. A failed report exits 5 (rejected) so assembly cannot start.

ponytail: distinctness compares pitch only. Character DNA also carries age and
tone, which D17 accepts as "clearly different"; add those features when a
line-level timbre measure exists.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import wave

TOOL_NAME = "qc_voice_match"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.qc-voice-match/report/v1"
QC_SCHEMA_VERSION = "1.0.0"
CHECK = "audio"                    # qc-schema check this module scores
CHECK_ID = "voice-match"
REPORT_COMPATIBLE = {"blackceo.qc-voice-match/report/v1"}

# Owner D17 / plan 6.6: measured-pitch bands, Hz, inclusive both ends.
PITCH_RANGES_HZ = {"male": (85.0, 155.0), "female": (165.0, 255.0)}

# D17: two same-gender characters must measure as clearly different voices.
SAME_GENDER_MIN_SEPARATION_HZ = 15.0

# Faces that satisfy the rule without being the speaker: the voice's source.
VOICE_SOURCE_TOKENS = frozenset({
    "phone", "mobile", "cell", "laptop", "computer", "speaker", "voicemail",
    "voice mail", "device", "radio", "intercom", "call", "answerphone",
    "answering machine", "tv", "television", "screen",
})

# Search window for the fundamental. Covers both D17 bands with margin.
PITCH_SEARCH_HZ = (70.0, 300.0)
SILENCE_RMS = 1e-3                 # full-scale = 1.0
PEAK_REL = 0.90                    # first local max >= 90% of global max
PEAK_ABS = 0.50                    # ...and >= 0.5 normalized correlation

EXIT = {"ok": 0, "error": 1, "rejected": 5}


class VoiceMatchError(Exception):
    """Structural problem in the report itself (exit 1, never a verdict)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class AssemblyBlocked(Exception):
    """Raised by refuse_before_assembly() when QC rejected the run."""


def _norm(value):
    if isinstance(value, str):
        v = value.strip()
        return v or None
    return None


# ---------------------------------------------------------------- pitch ----

def measure_pitch_hz(samples, sample_rate, fmin=None, fmax=None):
    """Autocorrelation fundamental estimate. None = no usable pitch.

    Deterministic: fixed search window, first qualifying local maximum,
    parabolic interpolation for sub-sample lag. No randomness, no state.
    """
    fmin, fmax = (fmin, fmax) if fmin and fmax else PITCH_SEARCH_HZ
    if not isinstance(sample_rate, (int, float)) or sample_rate <= 0:
        return None
    xs = [float(s) for s in samples]
    n = len(xs)
    if n < 64:
        return None
    # int16 fixtures arrive as ±32767; normalize to full scale 1.0.
    peak = max(abs(x) for x in xs)
    if peak > 1.5:
        scale = 32768.0
        xs = [x / scale for x in xs]
        peak = peak / scale
    mean = sum(xs) / n
    xs = [x - mean for x in xs]
    energy = sum(x * x for x in xs)
    if energy <= 0.0:
        return None
    rms = math.sqrt(energy / n)
    if rms < SILENCE_RMS:
        return None

    lag_min = max(2, int(sample_rate / fmax))
    lag_max = min(n // 2, int(sample_rate / fmin))
    if lag_max <= lag_min + 1:
        return None

    # Normalized autocorrelation for every lag in the window.
    corr = []
    for lag in range(lag_min, lag_max + 1):
        a = xs[:n - lag]
        b = xs[lag:]
        num = sum(x * y for x, y in zip(a, b))
        ea = sum(x * x for x in a)
        eb = sum(y * y for y in b)
        denom = math.sqrt(ea * eb)
        corr.append(num / denom if denom > 0.0 else 0.0)
    rmax = max(corr)
    if rmax <= 0.0:
        return None
    threshold = max(PEAK_REL * rmax, PEAK_ABS)

    # First local maximum at or above the threshold: the true period, not the
    # lower shoulder of a later peak and not an octave-down artifact.
    chosen = None
    for i in range(len(corr)):
        if corr[i] < threshold:
            continue
        left = corr[i - 1] if i > 0 else -1.0
        right = corr[i + 1] if i + 1 < len(corr) else -1.0
        if corr[i] >= left and corr[i] >= right:
            chosen = i
            break
    if chosen is None:
        return None

    # Parabolic interpolation of the peak for sub-sample lag accuracy.
    lag = lag_min + chosen
    if 0 < chosen < len(corr) - 1:
        a, b, c = corr[chosen - 1], corr[chosen], corr[chosen + 1]
        denom = a - 2.0 * b + c
        if abs(denom) > 1e-12:
            delta = 0.5 * (a - c) / denom
            if -0.5 <= delta <= 0.5:
                lag = lag + delta
    if lag <= 0:
        return None
    return sample_rate / lag


def load_wav_samples(path):
    """Mono float samples from a PCM WAV file. Raises VoiceMatchError."""
    try:
        with wave.open(path, "rb") as w:
            nch = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            raw = w.readframes(w.getnframes())
    except (OSError, EOFError, wave.Error) as e:
        raise VoiceMatchError("AUDIO_UNREADABLE", "%s: %s" % (path, e))
    if nch < 1 or rate <= 0:
        raise VoiceMatchError("AUDIO_UNREADABLE", "%s: bad header" % path)
    if width == 2:
        vals = struct.unpack("<%dh" % (len(raw) // 2), raw)
        scale = 32768.0
    elif width == 1:
        vals = [b - 128 for b in raw]
        scale = 128.0
    elif width == 4:
        vals = struct.unpack("<%di" % (len(raw) // 4), raw)
        scale = 2147483648.0
    else:
        raise VoiceMatchError("AUDIO_UNREADABLE",
                              "%s: unsupported sample width %d" % (path, width))
    mono = [vals[i] / scale for i in range(0, len(vals) - nch + 1, nch)] \
        if nch > 1 else [v / scale for v in vals]
    if not mono:
        raise VoiceMatchError("AUDIO_UNREADABLE", "%s: no samples" % path)
    return rate, mono


# --------------------------------------------------------------- checks ----

def pitch_in_range(gender, hz):
    """(in_band, low, high) for a measured pitch. Unknown gender -> False."""
    band = PITCH_RANGES_HZ.get(gender)
    if band is None or hz is None:
        return False, None, None
    return band[0] <= hz <= band[1], band[0], band[1]


def speaker_onscreen_ok(speaker, onscreen):
    """True when the face on screen is the speaker or the voice's source."""
    if not speaker or not onscreen:
        return False
    if onscreen == speaker:
        return True
    return onscreen.lower() in VOICE_SOURCE_TOKENS


def check_distinct_same_gender(characters, min_separation=None):
    """Fail same-gender pairs whose measured pitches are not clearly apart."""
    min_sep = SAME_GENDER_MIN_SEPARATION_HZ if min_separation is None \
        else float(min_separation)
    failures = []
    by_gender = {}
    for ch in characters or []:
        gender = _norm(ch.get("gender")) if isinstance(ch, dict) else None
        hz = ch.get("pitch_hz") if isinstance(ch, dict) else None
        cid = _norm(ch.get("id")) if isinstance(ch, dict) else None
        if gender in PITCH_RANGES_HZ and cid and isinstance(hz, (int, float)):
            by_gender.setdefault(gender, []).append((cid, float(hz)))
    for gender, members in sorted(by_gender.items()):
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a_id, a_hz = members[i]
                b_id, b_hz = members[j]
                gap = abs(a_hz - b_hz)
                if gap < min_sep:
                    failures.append({
                        "code": "SAME_GENDER_NOT_DISTINCT",
                        "detail": "%s (%.1f Hz) and %s (%.1f Hz) differ by "
                                  "%.1f Hz < %.1f Hz" % (a_id, a_hz, b_id,
                                                         b_hz, gap, min_sep),
                    })
    return failures


def _line_audio(line):
    """(rate, samples) for a line, or (None, None) with a failure code."""
    inline = line.get("samples")
    if isinstance(inline, list) and inline:
        rate = line.get("sample_rate")
        if not isinstance(rate, (int, float)) or rate <= 0:
            return None, None, "AUDIO_UNREADABLE"
        return rate, inline, None
    path = _norm(line.get("wav_path"))
    if not path:
        return None, None, "AUDIO_MISSING"
    if not os.path.exists(path):
        return None, None, "AUDIO_MISSING"
    try:
        rate, samples = load_wav_samples(path)
    except VoiceMatchError as e:
        return None, None, e.code
    return rate, samples, None


def check_line(line):
    """One line verdict. Returns (failures, measured_hz, detail_codes)."""
    if not isinstance(line, dict):
        return ([{"code": "LINE_MALFORMED", "detail": "line is not an object"}],
                None, ["LINE_MALFORMED"])
    line_id = _norm(line.get("line_id")) or "?"
    speaker = _norm(line.get("speaker"))
    gender = _norm(line.get("gender"))
    onscreen = _norm(line.get("onscreen"))
    failures = []

    if not speaker:
        failures.append({"code": "SPEAKER_UNKNOWN",
                         "line": line_id,
                         "detail": "line has no speaker"})
    if gender not in PITCH_RANGES_HZ:
        failures.append({"code": "GENDER_UNKNOWN",
                         "line": line_id,
                         "detail": "gender %r is not male/female" % (gender,)})
    if not onscreen:
        failures.append({"code": "ONSCREEN_UNKNOWN",
                         "line": line_id,
                         "detail": "no on-screen character recorded"})
    elif speaker and not speaker_onscreen_ok(speaker, onscreen):
        failures.append({"code": "SPEAKER_MISMATCH",
                         "line": line_id,
                         "detail": "on screen %r but speaker is %r"
                                   % (onscreen, speaker)})

    rate, samples, audio_code = _line_audio(line)
    hz = None
    if audio_code:
        failures.append({"code": audio_code, "line": line_id,
                         "detail": "line audio unavailable"})
    else:
        hz = measure_pitch_hz(samples, rate)
        if hz is None:
            failures.append({"code": "PITCH_UNAVAILABLE", "line": line_id,
                             "detail": "no usable fundamental (silence or "
                                       "too short)"})
        else:
            in_band, low, high = pitch_in_range(gender, hz)
            if not in_band:
                failures.append({
                    "code": "PITCH_RANGE",
                    "line": line_id,
                    "detail": "measured %.1f Hz for %s, band %s-%s Hz"
                              % (hz, gender,
                                 "?" if low is None else low,
                                 "?" if high is None else high),
                })
    return failures, hz, []


def evaluate(report):
    """Full run verdict. Structural problems raise VoiceMatchError."""
    if not isinstance(report, dict):
        raise VoiceMatchError("BAD_INPUT", "report must be an object")
    if report.get("schema_version") not in REPORT_COMPATIBLE:
        raise VoiceMatchError(
            "BAD_INPUT", "schema_version must be one of %s"
            % sorted(REPORT_COMPATIBLE))
    run_id = _norm(report.get("run_id"))
    stage = _norm(report.get("stage"))
    if not run_id or not stage:
        raise VoiceMatchError("BAD_INPUT", "run_id and stage are required")
    lines = report.get("lines")
    if not isinstance(lines, list) or not lines:
        raise VoiceMatchError("BAD_INPUT", "lines must be a non-empty list")

    failures = []
    measured = []
    for line in lines:
        line_fail, hz, _ = check_line(line)
        failures.extend(line_fail)
        if hz is not None:
            measured.append(hz)

    characters = report.get("characters")
    if isinstance(characters, list) and characters:
        failures.extend(check_distinct_same_gender(characters))

    codes = sorted({f["code"] for f in failures})
    result = {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "command": "check",
        "run_id": run_id,
        "stage": stage,
        "outcome": "ok" if not failures else "rejected",
        "reason_code": "VOICE_MATCH_OK" if not failures
                       else "+".join(codes),
        "next_action": "assembly may proceed" if not failures else
                       "repair the failed lines (regenerate in Suno) and "
                       "re-run voice-match QC; assembly stays blocked",
        "evidence": {
            "lines_checked": len(lines),
            "measured_hz": [round(h, 2) for h in measured],
            "failures": failures,
            "pitch_ranges_hz": {k: list(v) for k, v in
                                sorted(PITCH_RANGES_HZ.items())},
            "same_gender_min_separation_hz": SAME_GENDER_MIN_SEPARATION_HZ,
        },
    }
    return result


def envelope(result):
    return result


def to_qc_record(result, reviewer, check_id=None, checker_version=None):
    """qc-schema 1.0.0 verdict record (check=audio) for core/qc_gate.py.

    reviewer must carry identity/session/authority and must differ from the
    maker of the lines (qc_gate enforces independence).
    """
    if not isinstance(reviewer, dict):
        raise VoiceMatchError("BAD_INPUT", "reviewer must be an object")
    failures = result["evidence"]["failures"]
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "check_id": check_id or CHECK_ID,
        "run_id": result["run_id"],
        "stage": result["stage"],
        "check": CHECK,
        "verdict": "PASS" if result["outcome"] == "ok" else "FAIL",
        "evidence": {
            "summary": "voice-match %s: %d line(s), %d failure(s)%s"
                       % (result["outcome"], result["evidence"]["lines_checked"],
                          len(failures),
                          "" if not failures else
                          " [%s]" % ", ".join(sorted({f["code"] for f in
                                                      failures}))),
            "refs": [],
        },
        "reason_code": result["reason_code"],
        "checker_version": checker_version or TOOL_VERSION,
        "reviewer": {
            "identity": _require(reviewer, "identity"),
            "session": _require(reviewer, "session"),
            "authority": _require(reviewer, "authority"),
        },
    }


def _require(d, key):
    v = _norm(d.get(key))
    if not v:
        raise VoiceMatchError("BAD_INPUT", "reviewer.%s is required" % key)
    return v


def refuse_before_assembly(result):
    """Assembly hook: raises AssemblyBlocked unless QC passed."""
    if result.get("outcome") != "ok":
        raise AssemblyBlocked(result.get("reason_code", "VOICE_MATCH_FAIL"))
    return True


# ------------------------------------------------------------------ CLI ----

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="qc_voice_match",
        description="D17 voice-match QC: pitch band + on-screen speaker "
                    "(fail-closed, runs before assembly)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check", help="evaluate a line report")
    a.add_argument("--report", required=True, help="report JSON path")
    a.add_argument("--qc-record", default="",
                   help="also write the qc-schema audio verdict record here")
    a.add_argument("--reviewer-identity", default="qc_voice_match/%s"
                   % TOOL_VERSION)
    a.add_argument("--reviewer-session", default="cli")
    a.add_argument("--reviewer-authority", default="owner-decision-D17")
    ns = p.parse_args(argv)
    try:
        with open(ns.report, encoding="utf-8") as f:
            report = json.load(f)
        result = evaluate(report)
        if ns.qc_record:
            rec = to_qc_record(result, {
                "identity": ns.reviewer_identity,
                "session": ns.reviewer_session,
                "authority": ns.reviewer_authority,
            })
            with open(ns.qc_record, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2, sort_keys=True)
                f.write("\n")
    except VoiceMatchError as e:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
                          "tool_version": TOOL_VERSION, "command": "check",
                          "outcome": "error", "reason_code": e.code,
                          "evidence": {"detail": str(e)}}, indent=2,
                         sort_keys=True))
        return EXIT["error"]
    except (OSError, ValueError) as e:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
                          "tool_version": TOOL_VERSION, "command": "check",
                          "outcome": "error", "reason_code": "BAD_INPUT",
                          "evidence": {"detail": str(e)}}, indent=2,
                         sort_keys=True))
        return EXIT["error"]
    print(json.dumps(envelope(result), indent=2, sort_keys=True))
    if result["outcome"] == "ok":
        refuse_before_assembly(result)   # no-op when QC passed
        return EXIT["ok"]
    try:
        refuse_before_assembly(result)   # proves the pre-assembly block fires
    except AssemblyBlocked:
        return EXIT["rejected"]
    return EXIT["error"]


if __name__ == "__main__":
    sys.exit(main())
