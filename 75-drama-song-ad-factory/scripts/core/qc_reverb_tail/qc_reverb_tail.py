#!/usr/bin/env python3
"""Reverb-tail QC for vocal lines (owner decision D22a, plan 6.12 item 3).
Stdlib only, no network module, no provider call, no spend.

The fault this gate exists for (AUDIO-FIX-BRIEF 2026-10-07): Suno's own
reverb carried into the separated vocal stems, so a line kept ringing after
its words ended and the whole chapter read as echo/ghost. D22a says a line
that rings on is a QC failure, and the repair is a fresh Suno take - never a
second pass through a text-to-speech tool.

Scope: EVERY line handed to this gate, spoken or sung. The brief measures the
tail after the end of every vocal phrase; a line whose ``delivery`` says
``sung`` is judged by the same three numbers as a spoken one, so nothing
escapes the gate by being a song.

What it measures
----------------
Every line in the report carries ``body_end_s``: the instant its spoken
content stops (the timing annotation already produced for captions). QC
never guesses that instant. From there it frames the tail at 10 ms and
records three numbers against the line's own body level:

  * ``to_quiet_ms``     -- milliseconds until the tail falls to 2% of the
                           body level (-34 dB). ``None`` means it never
                           does inside the buffer: the line rings on.
  * ``decay_db_per_s``  -- least-squares slope of the tail above that floor.
                           Shallow slope = a ring that will not let go.
  * ``end_level_db``    -- level still present at the last frame, relative
                           to the body. Loud at the buffer end = ringing.

Fail-closed on every one of those, plus on the structural cases: no audio,
unreadable audio, no anchor, an anchor outside the buffer, a tail too short
to frame, a line so quiet there is nothing to measure. None of those ever
become PASS - an unmeasured line is UNDETERMINED and undetermined is a
failure here, not a pass.

Repair path
-----------
Every failing line is queued on ``regen_queue`` with its regeneration path
recorded: provider ``suno`` on the Skill 74 KIE live-adapter path only
(``POST /api/v1/jobs/createTask`` + ``ai-music-api/generate``), style back to
dry close-mic vocals, ``tts: never``. ``regen_path`` refuses any other
provider by name and any transport that is not Skill 74, so a ringing line
can never be re-tried through a voice tool.

Fixtures are synthesized in the test suite - a deterministic exponential
impulse response convolved with a generated tone - so no media file ever
ships in this repository.

Run: python3 core/qc_reverb_tail/test_qc_reverb_tail.py

ponytail: the tail anchor is caller-supplied (``body_end_s``). An automatic
end-detector would free callers from supplying it but would also mistake a
mid-line pause for the end of speech; add one only if a real pipeline cannot
produce the anchor.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import struct
import sys
import wave

TOOL_NAME = "qc_reverb_tail"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.qc-reverb-tail/report/v1"
QC_SCHEMA_VERSION = "1.0.0"
CHECK = "audio"                    # qc-schema check this module scores
CHECK_ID = "reverb-tail"
REPORT_COMPATIBLE = {"blackceo.qc-reverb-tail/report/v1"}

RULE_ID = "D22a"

#: Owner D22a thresholds. Everything is measured against the line's own body
#: level, so a quiet take and a loud take are judged by the same rule.
FRAME_MS = 10.0                    # tail frame length
QUIET_RATIO = 0.02                 # -34 dB: "the tail has let go"
TAIL_BUDGET_MS = 250.0             # line ends -> quiet, max milliseconds
MIN_DECAY_DB_PER_S = 40.0          # shallower than this is still ringing
END_LEVEL_LIMIT_DB = -30.0         # level still present at the buffer end
SILENCE_RMS = 1e-3                 # full scale = 1.0
DB_FLOOR = -140.0                  # log guard, never printed below this

#: Codes that mean "this line rings on". Only those drive the regen queue
#: headline; every other failure still queues a fresh take (see evaluate()).
RINGING_CODES = frozenset(("RINGING_TAIL", "TAIL_DECAY_TOO_SLOW",
                           "TAIL_ENDS_LOUD"))

#: The one repair path. Suno, on the Skill 74 KIE live adapter - no second
#: KIE client, no other provider, no text-to-speech tool.
PROVIDER = "suno"
TTS = "never"
REGEN_TRANSPORT = "skill-74-kie-live-adapter"
REGEN_ENDPOINT = "POST /api/v1/jobs/createTask"
REGEN_MODEL = "ai-music-api/generate"
REGEN_INPUT_MODEL = "V6"
#: Style the regeneration asks for. The authoritative negative-tag set lives
#: with the no-echo rule (D22a / D37); this is what the queued take carries.
REGEN_STYLE = ("dry, close-mic, intimate; negative tags reverb, echo, delay, "
               "hall, room, ethereal, ambient, choir, choir pad, "
               "atmospheric, spacious, cinematic, wet, shimmer; never "
               "pitch-shift a voice")

EXIT = {"ok": 0, "error": 1, "rejected": 5}


class ReverbTailError(Exception):
    """Structural problem in the report or the line audio (exit 1 or FAIL)."""

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


def _db(ratio):
    if ratio <= 0.0:
        return DB_FLOOR
    return max(DB_FLOOR, 20.0 * math.log10(ratio))


def _rms(chunk):
    if not chunk:
        return 0.0
    return math.sqrt(sum(c * c for c in chunk) / len(chunk))


# ----------------------------------------------------------------- audio ----

def load_wav_samples(path):
    """Mono float samples from a PCM WAV file. Raises ReverbTailError."""
    try:
        with wave.open(path, "rb") as w:
            nch = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            raw = w.readframes(w.getnframes())
    except (OSError, EOFError, wave.Error) as e:
        raise ReverbTailError("AUDIO_UNREADABLE", "%s: %s" % (path, e))
    if nch < 1 or rate <= 0:
        raise ReverbTailError("AUDIO_UNREADABLE", "%s: bad header" % path)
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
        raise ReverbTailError("AUDIO_UNREADABLE",
                              "%s: unsupported sample width %d"
                              % (path, width))
    mono = [vals[i] / scale for i in range(0, len(vals) - nch + 1, nch)] \
        if nch > 1 else [v / scale for v in vals]
    if not mono:
        raise ReverbTailError("AUDIO_UNREADABLE", "%s: no samples" % path)
    return rate, mono


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
    except ReverbTailError as e:
        return None, None, e.code
    return rate, samples, None

# ----------------------------------------------------------------- tail -----

def _linfit_db_per_s(points):
    """Least-squares slope of dB over seconds. points = [(second, dB), ...]."""
    m = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    den = m * sxx - sx * sx
    if abs(den) < 1e-12:
        return 0.0
    return (m * sxy - sx * sy) / den

def measure_tail(samples, rate, body_end_s):
    """Tail metrics after the line's content stops. Raises ReverbTailError.

    Deterministic: fixed 10 ms frames, one reference level (the loudest body
    frame), a fixed quiet floor and a plain least-squares slope. No
    randomness, no state, no provider.
    """
    if not isinstance(rate, (int, float)) or rate <= 0:
        raise ReverbTailError("AUDIO_UNREADABLE", "sample_rate must be > 0")
    if body_end_s is None:
        raise ReverbTailError(
            "TAIL_ANCHOR_MISSING",
            "body_end_s is required: QC never guesses where the spoken "
            "content ends (D22a measures the tail AFTER the line)")
    if not isinstance(body_end_s, (int, float)) or not (body_end_s > 0):
        raise ReverbTailError("TAIL_ANCHOR_INVALID",
                              "body_end_s must be a positive number, got %r"
                              % (body_end_s,))
    xs = [float(s) for s in (samples or [])]
    n = len(xs)
    if n < 64:
        raise ReverbTailError("TAIL_UNMEASURABLE",
                              "only %d sample(s); nothing to frame" % n)
    peak = max(abs(x) for x in xs)
    if peak > 1.5:                       # int16 fixtures -> full scale 1.0
        scale = 32768.0
        xs = [x / scale for x in xs]
        peak /= scale
    if peak <= 0.0:
        raise ReverbTailError("LINE_SILENT", "line contains no signal")

    frame = max(1, int(round(rate * FRAME_MS / 1000.0)))
    end_i = int(round(float(body_end_s) * rate))
    if end_i <= 0 or end_i >= n:
        raise ReverbTailError(
            "TAIL_ANCHOR_INVALID",
            "body_end_s=%r sits outside the %d-sample line"
            % (body_end_s, n))

    # Body reference: the loudest frame fully before the anchor.
    body = [_rms(xs[i:i + frame])
            for i in range(0, end_i - frame + 1, frame)]
    if not body:
        if end_i < 8:
            raise ReverbTailError("TAIL_ANCHOR_INVALID",
                                  "body_end_s leaves %d sample(s) of speech"
                                  % end_i)
        body = [_rms(xs[:end_i])]
    ref = max(body)
    if ref < SILENCE_RMS:
        raise ReverbTailError("LINE_SILENT",
                              "body level %.2e is below the silence floor"
                              % ref)

    # Tail frames from the anchor; a stub shorter than half a frame is noise.
    tail = []
    i = end_i
    while i < n:
        stop = min(n, i + frame)
        if stop - i >= max(1, frame // 2):
            tail.append(_rms(xs[i:stop]))
        i += frame
    if len(tail) < 2:
        raise ReverbTailError("TAIL_UNMEASURABLE",
                              "%d usable tail frame(s); need 2" % len(tail))

    floor = QUIET_RATIO * ref
    to_quiet_ms = None
    for k, r in enumerate(tail):
        if r <= floor:
            to_quiet_ms = k * FRAME_MS
            break

    end_level_db = _db(tail[-1] / ref)
    above = [(k * FRAME_MS / 1000.0, _db(r / ref))
             for k, r in enumerate(tail) if r > floor]
    # Positive magnitude: how many dB the tail sheds per second.
    decay_db_per_s = -_linfit_db_per_s(above) if len(above) >= 3 else None

    return {
        "body_end_s": float(body_end_s),
        "sample_rate": int(rate),
        "tail_ms": len(tail) * FRAME_MS,
        "to_quiet_ms": to_quiet_ms,
        "decay_db_per_s": None if decay_db_per_s is None
                          else round(decay_db_per_s, 2),
        "end_level_db": round(end_level_db, 2),
        "body_level_rms": round(ref, 6),
    }

# --------------------------------------------------------------- checks -----

def check_line(line):
    """One line verdict. Returns (failures, metrics_or_None)."""
    if not isinstance(line, dict):
        return ([{"code": "LINE_MALFORMED", "line": "?",
                  "detail": "line is not an object"}], None)
    line_id = _norm(line.get("line_id")) or "?"
    rate, samples, audio_code = _line_audio(line)
    if audio_code:
        return ([{"code": audio_code, "line": line_id,
                  "detail": "line audio unavailable"}], None)
    try:
        metrics = measure_tail(samples, rate, line.get("body_end_s"))
    except ReverbTailError as e:
        return ([{"code": e.code, "line": line_id, "detail": str(e)}], None)

    failures = []
    budget = TAIL_BUDGET_MS
    if metrics["to_quiet_ms"] is None:
        failures.append({
            "code": "RINGING_TAIL", "line": line_id,
            "detail": "tail still audible across the whole %.0f ms window "
                      "after the line; never reached %.0f%% of the body level"
                      % (metrics["tail_ms"], QUIET_RATIO * 100.0),
        })
    elif metrics["to_quiet_ms"] > budget:
        failures.append({
            "code": "RINGING_TAIL", "line": line_id,
            "detail": "tail took %.0f ms to quiet, budget is %.0f ms"
                      % (metrics["to_quiet_ms"], budget),
        })
    decay = metrics["decay_db_per_s"]
    if decay is not None and decay < MIN_DECAY_DB_PER_S:
        failures.append({
            "code": "TAIL_DECAY_TOO_SLOW", "line": line_id,
            "detail": "tail sheds %.1f dB/s, %.1f dB/s minimum"
                      % (decay, MIN_DECAY_DB_PER_S),
        })
    if metrics["end_level_db"] > END_LEVEL_LIMIT_DB:
        failures.append({
            "code": "TAIL_ENDS_LOUD", "line": line_id,
            "detail": "tail still %.1f dB below the body level at the buffer "
                      "end (limit %.1f dB)"
                      % (metrics["end_level_db"], END_LEVEL_LIMIT_DB),
        })
    return failures, metrics

# ------------------------------------------------------------ regen path ----

def _provider_norm(provider):
    return re.sub(r"[^a-z0-9]", "", str(provider).lower())

def regen_path(line_id, reason_code, metrics=None, attempt=1,
               provider=PROVIDER, transport=REGEN_TRANSPORT):
    """Queue record for one failing line. TTS and foreign transports refused.

    Returns an envelope: ``outcome`` is ``queued`` or ``rejected``. Only
    ``suno`` on the Skill 74 KIE live-adapter path is ever accepted, so a
    ringing line can never be re-tried through a voice tool.
    """
    base = {
        "line_id": line_id,
        "reason_code": reason_code,
        "attempt": attempt,
        "tts": TTS,
        "provider": PROVIDER,
        "transport": REGEN_TRANSPORT,
        "errors": [],
    }
    if _provider_norm(provider) != _provider_norm(PROVIDER):
        return dict(base, outcome="rejected",
                    reason_code="external-tts-refused",
                    errors=["PROVIDER_REFUSED:%s (a ringing line is "
                            "regenerated in Suno, never re-tried through a "
                            "voice tool: D22a)" % provider],
                    regen=None)
    if transport != REGEN_TRANSPORT:
        return dict(base, outcome="rejected",
                    reason_code="transport-not-skill-74",
                    errors=["TRANSPORT_REFUSED:%s (only %s may submit a "
                            "regeneration: Skill 74 is the one KIE path)"
                            % (transport, REGEN_TRANSPORT)],
                    regen=None)
    return dict(base, outcome="queued", reason_code=reason_code,
                regen={
                    "provider": PROVIDER,
                    "route": "suno-reverb-tail-regen",
                    "transport": REGEN_TRANSPORT,
                    "endpoint": REGEN_ENDPOINT,
                    "model": REGEN_MODEL,
                    "input_model": REGEN_INPUT_MODEL,
                    "style": REGEN_STYLE,
                    "rule": RULE_ID,
                    "metrics": metrics or {},
                })

# ------------------------------------------------------------- evaluate -----

def evaluate(report):
    """Full run verdict. Structural problems raise ReverbTailError."""
    if not isinstance(report, dict):
        raise ReverbTailError("BAD_INPUT", "report must be an object")
    if report.get("schema_version") not in REPORT_COMPATIBLE:
        raise ReverbTailError(
            "BAD_INPUT", "schema_version must be one of %s"
            % sorted(REPORT_COMPATIBLE))
    run_id = _norm(report.get("run_id"))
    stage = _norm(report.get("stage"))
    if not run_id or not stage:
        raise ReverbTailError("BAD_INPUT", "run_id and stage are required")
    lines = report.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ReverbTailError("BAD_INPUT", "lines must be a non-empty list")

    failures, per_line, regen_queue, regen_errors = [], [], [], []
    measured, ringing = 0, 0
    for line in lines:
        line_fail, metrics = check_line(line)
        line_id = _norm(line.get("line_id")) if isinstance(line, dict) else None
        codes_here = sorted({f["code"] for f in line_fail})
        failures.extend(line_fail)
        if metrics is not None:
            measured += 1
        if any(c in RINGING_CODES for c in codes_here):
            ringing += 1
        per_line.append({
            "line_id": line_id or "?",
            "outcome": "ok" if not line_fail else "rejected",
            "reason_code": "TAIL_OK" if not line_fail
                           else "+".join(codes_here),
            "metrics": metrics,
            "failures": line_fail,
        })
        # Every failing line needs a fresh take. A line that rings on is the
        # D22a case; a line whose audio never arrived needs one just as much.
        if line_fail and line_id:
            queued = regen_path(line_id, "+".join(codes_here), metrics)
            if queued["outcome"] == "queued":
                regen_queue.append(queued)
            else:
                regen_errors.extend(queued["errors"])

    codes = sorted({f["code"] for f in failures})
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "command": "check",
        "run_id": run_id,
        "stage": stage,
        "outcome": "ok" if not failures else "rejected",
        "reason_code": "REVERB_TAIL_OK" if not failures
                       else "+".join(codes),
        "next_action": "assembly may proceed" if not failures else
                       "queue every failed line for Suno regeneration on the "
                       "Skill 74 KIE path (%s); never re-try a line through a "
                       "text-to-speech tool; assembly stays blocked"
                       % REGEN_TRANSPORT,
        "evidence": {
            "rule": RULE_ID,
            "lines_checked": len(lines),
            "lines_measured": measured,
            "lines_ringing": ringing,
            "failures": failures,
            "per_line": per_line,
            "regen_queue": regen_queue,
            "regen_errors": regen_errors,
            "thresholds": {
                "frame_ms": FRAME_MS,
                "quiet_ratio": QUIET_RATIO,
                "tail_budget_ms": TAIL_BUDGET_MS,
                "min_decay_db_per_s": MIN_DECAY_DB_PER_S,
                "end_level_limit_db": END_LEVEL_LIMIT_DB,
            },
        },
    }

def envelope(result):
    return result

# ------------------------------------------------------------ qc record -----

def to_qc_record(result, reviewer, check_id=None, checker_version=None):
    """qc-schema 1.0.0 verdict record (check=audio) for core/qc_gate.py.

    reviewer must carry identity/session/authority and must differ from the
    maker of the lines (qc_gate enforces independence).
    """
    if not isinstance(reviewer, dict):
        raise ReverbTailError("BAD_INPUT", "reviewer must be an object")
    failures = result["evidence"]["failures"]
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "check_id": check_id or CHECK_ID,
        "run_id": result["run_id"],
        "stage": result["stage"],
        "check": CHECK,
        "verdict": "PASS" if result["outcome"] == "ok" else "FAIL",
        "evidence": {
            "summary": "reverb-tail %s: %d line(s), %d failure(s), "
                       "%d queued for Suno regen%s"
                       % (result["outcome"],
                          result["evidence"]["lines_checked"],
                          len(failures),
                          len(result["evidence"]["regen_queue"]),
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
        raise ReverbTailError("BAD_INPUT", "reviewer.%s is required" % key)
    return v

def refuse_before_assembly(result):
    """Assembly hook: raises AssemblyBlocked unless QC passed."""
    if result.get("outcome") != "ok":
        raise AssemblyBlocked(result.get("reason_code", "REVERB_TAIL_FAIL"))
    return True

# ------------------------------------------------------------------ CLI ----

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="qc_reverb_tail",
        description="D22a reverb-tail QC: a spoken line that rings on fails "
                    "and is queued for Suno regeneration (fail-closed, runs "
                    "before assembly)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check", help="evaluate a line report")
    a.add_argument("--report", required=True, help="report JSON path")
    a.add_argument("--qc-record", default="",
                   help="also write the qc-schema audio verdict record here")
    a.add_argument("--reviewer-identity", default="qc_reverb_tail/%s"
                   % TOOL_VERSION)
    a.add_argument("--reviewer-session", default="cli")
    a.add_argument("--reviewer-authority", default="owner-decision-D22a")
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
    except ReverbTailError as e:
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
