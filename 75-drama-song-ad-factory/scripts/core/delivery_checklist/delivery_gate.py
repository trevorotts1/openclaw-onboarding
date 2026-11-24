"""3B.6 delivery check on the finished master (N-33), under 3J levels (N-100).

All four parts are required before anything is delivered:

  * an audio stream is present, as long as the video, and not silent
    (``MASTER_NO_AUDIO`` / ``MASTER_SILENT``);
  * the master's length equals the chosen length (``MASTER_WRONG_LENGTH``);
  * the text scan of section 3A.4 passes on the master;
  * the style check runs on one frame every 5 seconds (``STYLE_MISMATCH``).

A scan or style check that cannot run fails closed (``CHECK_UNAVAILABLE``),
never by default. Only a MAJOR refuses delivery; every MEDIUM is kept on the
result so the receipt can list it. Stdlib + ffprobe/ffmpeg through the load
governor; zero spend, zero network.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import load_governor as _LG                     # noqa: E402
from delivery_checklist import severity as SEV  # noqa: E402

PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"
TOOL_NAME = "delivery_gate"
TOOL_VERSION = "1.0.0"

MASTER_MISSING = "MASTER_MISSING"
MASTER_NO_AUDIO = "MASTER_NO_AUDIO"           # 3J item 14
MASTER_SILENT = "MASTER_SILENT"               # 3J item 14
MASTER_WRONG_LENGTH = "MASTER_WRONG_LENGTH"   # 3J item 14
TEXT_SCAN_FAILED = "MASTER_TEXT_SCAN_FAILED"
STYLE_MISMATCH = "STYLE_MISMATCH"
CHECK_UNAVAILABLE = "CHECK_UNAVAILABLE"       # 3J item 15

LENGTH_TOLERANCE_S = 0.5      # one length, measured against the master
SILENT_DB = -50.0
STYLE_SAMPLE_S = 5.0
PROBE_TIMEOUT_S = 120

def style_sample_times(duration_s, every_s=STYLE_SAMPLE_S):
    """One frame every 5 seconds across the whole master (N-33)."""
    duration = float(duration_s)
    if not duration > 0 or not every_s > 0:
        raise ValueError("duration_s and every_s must be positive")
    times, t = [], 0.0
    while t < duration:
        times.append(round(t, 6))
        t += every_s
    return times

def probe_master(path, ffprobe="ffprobe", ffmpeg="ffmpeg"):
    """Measured facts about the master: duration, audio stream, loudness.

    Raises ValueError when ffprobe/ffmpeg cannot measure it; the caller
    reports that as unavailable, never as a pass.
    """
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,duration", "-of", "json",
         str(path)], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
    if proc.returncode != 0:
        raise ValueError("ffprobe cannot read %s: %s"
                         % (path, (proc.stderr or "")[-200:]))
    doc = json.loads(proc.stdout or "{}")
    try:
        duration = float((doc.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        duration = None
    if duration is None or not math.isfinite(duration) or duration <= 0:
        raise ValueError("no measured duration for %s" % path)
    audio = [s for s in doc.get("streams") or []
             if s.get("codec_type") == "audio"]
    audio_duration = None
    if audio:
        try:
            audio_duration = float(audio[0].get("duration"))
        except (TypeError, ValueError):
            audio_duration = duration
    loudness_db = None
    if audio:
        argv = _LG.ffmpeg_argv(["-hide_banner", "-nostats", "-i", str(path),
                                "-vn", "-af", "volumedetect", "-f", "null",
                                "-"], ffmpeg=ffmpeg)
        run = _LG.run_ffmpeg(argv, "delivery-gate-silence",
                             capture_output=True, text=True,
                             timeout=PROBE_TIMEOUT_S)
        m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)\s*dB",
                      run.stderr or "")
        if run.returncode == 0 and m:
            loudness_db = (float("-inf") if m.group(1) == "-inf"
                           else float(m.group(1)))
    return {"duration_s": duration, "has_audio": bool(audio),
            "audio_duration_s": audio_duration, "loudness_db": loudness_db}

def check_master(master, chosen_length_s, text_scan=None, style_check=None,
                 probe_fn=probe_master, tolerance=LENGTH_TOLERANCE_S,
                 every_s=STYLE_SAMPLE_S):
    """The delivery check on the finished master. Returns the 3J gate result.

    ``text_scan(master)`` and ``style_check(master, times)`` are the section
    3A.4 scan and the look's style check; each returns a list of findings
    (dicts with ``code``) or raises when it cannot run. A missing or failing
    check is ``CHECK_UNAVAILABLE`` and refuses delivery (fail closed).
    """
    findings = []
    path = Path(master)
    if not path.is_file() or path.stat().st_size == 0:
        findings.append({"code": MASTER_MISSING, "detail": str(master)})
        return _result(findings, {})
    try:
        facts = probe_fn(str(path))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        findings.append({"code": CHECK_UNAVAILABLE,
                         "detail": "probe: %s" % exc})
        return _result(findings, {})
    if not facts.get("has_audio"):
        findings.append({"code": MASTER_NO_AUDIO,
                         "detail": "%s has no audio stream" % path})
    else:
        audio_s = facts.get("audio_duration_s") or facts["duration_s"]
        if float(audio_s) + tolerance < float(facts["duration_s"]):
            findings.append({"code": MASTER_NO_AUDIO,
                             "detail": "audio runs %.3f s of %.3f s"
                             % (audio_s, facts["duration_s"])})
        loudness = facts.get("loudness_db")
        if loudness is None:
            findings.append({"code": CHECK_UNAVAILABLE,
                             "detail": "no measured audio level"})
        elif loudness < SILENT_DB:
            findings.append({"code": MASTER_SILENT,
                             "detail": "audio is silent (mean %.1f dB)"
                             % loudness})
    try:
        chosen = float(chosen_length_s)
    except (TypeError, ValueError):
        chosen = None
    if chosen is None or abs(facts["duration_s"] - chosen) > tolerance:
        findings.append({"code": MASTER_WRONG_LENGTH,
                         "detail": "master %.3f s vs chosen %r s"
                         % (facts["duration_s"], chosen_length_s)})
    for name, fn, args, code in (
            ("text_scan", text_scan, (str(path),), TEXT_SCAN_FAILED),
            ("style_check", style_check,
             (str(path), style_sample_times(facts["duration_s"], every_s)),
             STYLE_MISMATCH)):
        if fn is None:
            findings.append({"code": CHECK_UNAVAILABLE,
                             "detail": "%s not supplied" % name})
            continue
        try:
            got = fn(*args)
        except Exception as exc:            # noqa: BLE001 - fail closed
            findings.append({"code": CHECK_UNAVAILABLE,
                             "detail": "%s could not run: %s" % (name, exc)})
            continue
        for finding in got or ():
            row = dict(finding) if isinstance(finding, dict) else {
                "code": str(finding)}
            row["code"] = row.get("code") or code
            findings.append(row)
    return _result(findings, {"master": str(path), **facts})

def _result(findings, evidence):
    gate = SEV.gate(findings)
    verdict = PASS if gate["pass"] else FAIL
    if any(f.get("code") == CHECK_UNAVAILABLE for f in findings):
        verdict = UNAVAILABLE      # cannot run: never a pass
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "verdict": verdict, "pass": gate["pass"],
            "major": gate["major"], "medium": gate["medium"],
            "minor": gate["minor"], "evidence": evidence}
