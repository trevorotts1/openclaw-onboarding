#!/usr/bin/env python3
"""sung_vocal_guard: final master always carries the sung vocal (manual 02 E7).

Critical gap proven in a real failed ad: the master came back all-spoken --
no Suno sung vocal anywhere in its runtime -- and nothing checked. The
planner's intake already stores the two voice modes (`voice` style field:
`all_suno` default, `velvet_voiceover`) and the planner's 12.4 song timing
map already carries the sung line windows (shot_planner.load_timing_map),
but the shared final QC gate had no record proving the master is sung.

What this module owns and nothing else:

1. the **coverage check** -- ``check_sung_vocal()`` decides a master carries
   the sung vocal across >= ``MIN_SUNG_COVERAGE`` (70 %) of its run for All
   Suno ads, or a song bed under the voiceover for Velvet Voiceover ads;
2. two **code-only evidence paths** (no paid call):
   primary  -- the 12.4 song timing map (shot_planner.load_timing_map)
              gives the sung_runtime / runtime coverage ratio;
   secondary-- vocal presence on the assembled master via ffmpeg astats /
              ebur128 stderr, parsed by pure functions so tests need no
              real audio (``parse_astats`` / ``parse_ebur128``);
3. the **mode resolution** -- ``resolve_voice_mode()`` reads the intake
   `voice` field (or the card's hyphen slug), as the pipeline already
   stores it; absent -> All Suno (requiring sung coverage), unknown -> a
   clean refusal rather than a silently swapped mode;
4. the **gate record** -- ``record_for_gate()`` returns a qc-schema
   (schema_version 1.0.0) verdict record for the `audio` check, so the
   run's Final edit QC (17.5) includes it in the records array it hands
   qc_gate.evaluate (core/qc_gate.py) -- wiring into the shared final QC
   gate by contract: the record must pass qc_gate.validate_record, and a
   FAIL record fails the Final edit stage fail-closed.

Reason codes (exactly the manual's two):
  VOCAL_MISSING      -- all-spoken master: no sung vocal detected
                        (0 % sung coverage, or no vocal energy on master);
  SUNG_COVERAGE_LOW  -- sung vocal present but below the 70 % floor.

stdlib only. No network module, no provider call, no spend, no absolute
operator path.

Run: python3 core/final_assembler/test_sung_vocal_e7.py
"""
from __future__ import annotations

import os
import re
import sys
import subprocess

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:
    from shot_planner.shot_planner import PlanError, load_timing_map
except ImportError:                      # core/ imported as a top-level package
    from shot_planner.shot_planner import PlanError, load_timing_map  # type: ignore # noqa: F401,E501

TOOL_NAME = "final_assembler.sung_vocal_guard"
TOOL_VERSION = "1.0.0"

#: Manual 02 E7: "carry the Suno sung vocal across most of its runtime
#: (e.g. >= 70 % for All Suno ...)". One floor, one module.
MIN_SUNG_COVERAGE = 0.70

#: Canonical intake voice ids (plan 4.1 / voice_velvet_echo constants);
#: copied here so the guard never needs the voice catalog to decide mode.
ALL_SUNO = "all_suno"
VELVET = "velvet_voiceover"

#: Spellings the pipeline already emits for the same two modes: the intake
#: style ids, the card's hyphen slugs, the retired slug, the intake labels
#: and the two plan labels, all case/separator-insensitive.
_ALL_SUNO_SPELLINGS = (
    ALL_SUNO, "all-suno", "All Suno", "All Suno (default)", "AllSuno")
_VELVET_SPELLINGS = (
    VELVET, "velvet-voiceover", "velvet-echo",
    "Velvet Voiceover", "Velvet Echo", "Velvet Voiceover (default)")
_MODE_SPELLINGS = {}
for _s in _ALL_SUNO_SPELLINGS:
    _MODE_SPELLINGS[re.sub(r"[^a-z0-9]", "", _s.lower())] = ALL_SUNO
for _s in _VELVET_SPELLINGS:
    _MODE_SPELLINGS[re.sub(r"[^a-z0-9]", "", _s.lower())] = VELVET

#: ebur128/astats floor: anything at or below this is silence, not a bed.
SILENCE_FLOOR_LUFS = -70.0

MODE_UNKNOWN = "VOICE_MODE_UNKNOWN"


class SungGuardError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


# ------------------------------------------------------------------ mode ---
def resolve_voice_mode(profile):
    """Voice mode from the pipeline's own intake/profile data.

    Reads the `voice` field where the pipeline stores it: the intake style
    record (``initial_questions.resolve_style``), the same dict nested under
    ``style``, or the choice-card dict (hyphen slug under the same key).
    Returns ``(mode, defaulted)``; absent -> ``(ALL_SUNO, True)`` -- the
    guard defaults to REQUIRING sung coverage, never to letting a master
    through. An unknown spelling raises SungGuardError(MODE_UNKNOWN): the
    guard never guesses an owner's voice choice.
    """
    if profile is None:
        return ALL_SUNO, True
    if isinstance(profile, str):
        raw = profile
    elif isinstance(profile, dict):
        if "voice" in profile:
            raw = profile["voice"]
        elif isinstance(profile.get("style"), dict) \
                and "voice" in profile["style"]:
            raw = profile["style"]["voice"]
        else:
            return ALL_SUNO, True
    else:
        raise SungGuardError(
            MODE_UNKNOWN,
            "profile must carry the intake voice field "
            "(style['voice'] / card['voice']), got %r" % (type(profile),))
    mode = _MODE_SPELLINGS.get(_norm(raw))
    if mode is None:
        raise SungGuardError(
            MODE_UNKNOWN,
            "unknown voice %r; expected %r or a known spelling" % (raw, ALL_SUNO))
    return mode, False


# ------------------------------------------------------------ evidence ------
def sung_coverage_from_timing(timing, runtime_s=None, spoken_section_ids=None):
    """Sung coverage ratio from the planner's 12.4 song timing map.

    Normalizes the map through shot_planner.load_timing_map, sums the line
    windows and divides by the master runtime (default: the map's own
    duration_seconds). ``spoken_section_ids`` excludes spoken-line sections
    from the sung sum (E8 lays those lines on the bed, they are not sung).
    Raises ValueError on a bad shape (never coerces it to "no sung").
    """
    t = load_timing_map(timing)
    dur = float(runtime_s) if runtime_s is not None \
        else float(t["duration_seconds"])
    if dur <= 0:
        raise ValueError("BAD_RUNTIME: runtime must be positive")
    spoken = {_norm(s) for s in (spoken_section_ids or []) if isinstance(s, str)}
    sung_s = 0.0
    for ln in t["lines"].values():
        if spoken and ln["section_id"] and _norm(ln["section_id"]) in spoken:
            continue
        sung_s += max(0.0, float(ln["end"]) - float(ln["start"]))
    return min(1.0, sung_s / dur), dur


def vocal_argv(master_path, ffmpeg="ffmpeg"):
    """ffmpeg argv for the ebur128 loudness scan of the assembled master.

    E7's secondary evidence path: measure what the assembler produced (the
    master itself, audio only), bounded like every other render call
    (nice -n 10 per manual M7), printing per-frame ebur128 summary lines on
    stderr for ``parse_ebur128``. No network, no provider.
    """
    return ["nice", "-n", "10", ffmpeg, "-hide_banner", "-nostats", "-y",
            "-i", str(master_path), "-vn", "-af", "ebur128", "-f", "null", "-"]


def run_vocal_scan(master_path, ffmpeg="ffmpeg", timeout=300):
    """Run vocal_argv on the real master; returns (argv, stderr_text).

    Subprocess use only -- the caller decides what the stderr says (pure
    ``parse_ebur128`` below needs nothing real, so tests stay offline).
    """
    argv = vocal_argv(master_path, ffmpeg)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("SCAN_UNAVAILABLE: %s" % (exc,)) from exc
    return argv, proc.stderr or ""


_ASTATS_RMS = re.compile(r"Rms level dB:\s*(-?\d+(?:\.\d+)?)")
_EBUR_I = re.compile(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS")


def parse_ebur128(stderr_text):
    """Pure: integrated LUFS from ffmpeg ebur128 stderr (None if absent)."""
    matches = _EBUR_I.findall(stderr_text or "")
    return float(matches[-1]) if matches else None


def parse_astats(stderr_text):
    """Pure: RMS levels (dB) from ffmpeg astats stderr; [] when absent."""
    return [float(v) for v in _ASTATS_RMS.findall(stderr_text or "")]


def vocal_presence(stderr_text, floor_lufs=None):
    """Pure: True when ebur128/astats show audio energy above the floor."""
    floor = SILENCE_FLOOR_LUFS if floor_lufs is None else float(floor_lufs)
    i_val = parse_ebur128(stderr_text)
    if i_val is not None:
        return i_val > floor
    rms = parse_astats(stderr_text)
    return any(v > floor for v in rms) if rms else False


# ----------------------------------------------------------------- check ----
def check_sung_vocal(timing=None, runtime_s=None, profile=None,
                     master_path=None, scan_stderr=None,
                     min_coverage=MIN_SUNG_COVERAGE, spoken_section_ids=None):
    """E7 verdict: the master is sung (All Suno) or has its bed (Velvet).

    Primary path  -- ``timing``: 12.4 map -> sung coverage ratio.
                     >= min  -> PASS SUNG_COVERAGE_OK
                     0        -> FAIL VOCAL_MISSING (all-spoken master)
                     (0,min)  -> FAIL SUNG_COVERAGE_LOW
    Secondary path-- no map: ``master_path``/``scan_stderr`` gives the
                     vocal-presence signal; detected -> PASS (All Suno) /
                     bed present (Velvet); absent -> FAIL VOCAL_MISSING.
                     Neither evidence -> FAIL UNAVAILABLE-ish gate verdict
                     UNAVAILABLE (17.8: missing evidence never passes).

    Returns the verdict dict (record_for_gate builds the qc record from it).
    """
    mode, defaulted = resolve_voice_mode(profile)
    ver = {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
           "voice_mode": mode, "voice_mode_defaulted": defaulted,
           "min_coverage": min_coverage, "evidence_path": None,
           "sung_coverage": None, "outcome": "FAIL", "reason_code": None,
           "next_action": None}
    # ---- primary: the timing map ----
    if timing is not None:
        try:
            ratio, dur = sung_coverage_from_timing(
                timing, runtime_s, spoken_section_ids)
        except (ValueError, PlanError) as exc:
            ver["outcome"] = "UNAVAILABLE"
            ver["reason_code"] = "TIMING_UNREADABLE"
            ver["next_action"] = str(exc)
            return ver
        ver["evidence_path"] = "timing_map"
        ver["sung_coverage"] = round(ratio, 4)
        if mode == VELVET:
            if ratio <= 0.0:
                # Velvet's bed is the song: a map with no song windows means
                # the voiceover ran with NO bed (the real failed-ad shape).
                ver["outcome"] = "FAIL"
                ver["reason_code"] = "VOCAL_MISSING"
                ver["next_action"] = (
                    "Velvet Voiceover master has no song bed: timing map "
                    "carries 0 s of song windows")
                return ver
            ver["outcome"] = "PASS"
            ver["reason_code"] = "VELVET_BED_PRESENT"
            ver["next_action"] = "song bed present under voiceover per timing map"
            return ver
        if ratio <= 0.0:
            ver["outcome"] = "FAIL"
            ver["reason_code"] = "VOCAL_MISSING"
            ver["next_action"] = (
                "all-spoken master: timing map carries 0 s of sung lines; "
                "re-cut with the Suno song master")
            return ver
        if ratio < min_coverage:
            ver["outcome"] = "FAIL"
            ver["reason_code"] = "SUNG_COVERAGE_LOW"
            ver["next_action"] = (
                "sung runtime %.2f%% < floor %.0f%%; add sung sections"
                % (ratio * 100.0, min_coverage * 100.0))
            return ver
        ver["outcome"] = "PASS"
        ver["reason_code"] = "SUNG_COVERAGE_OK"
        ver["next_action"] = "final QC continues"
        return ver
    # ---- secondary: vocal-presence signal on the assembled master ----
    ver["evidence_path"] = "vocal_presence"
    if isinstance(scan_stderr, str) and scan_stderr:
        present = vocal_presence(scan_stderr)
    elif master_path is not None:
        _, stderr = run_vocal_scan(master_path)
        present = vocal_presence(stderr)
    else:
        ver["outcome"] = "UNAVAILABLE"
        ver["reason_code"] = "NO_EVIDENCE"
        ver["next_action"] = (
            "no timing map and no master scan: supply timing or master_path")
        return ver
    is_song = "song" if present else "no"
    if not present:
        ver["outcome"] = "FAIL"
        ver["reason_code"] = "VOCAL_MISSING"
        ver["next_action"] = (
            "all-spoken master: no vocal/bed energy above %.0f LUFS"
            % SILENCE_FLOOR_LUFS)
        return ver
    ver["outcome"] = "PASS"
    ver["reason_code"] = ("VELVET_BED_PRESENT" if mode == VELVET
                          else "SUNG_COVERAGE_OK")
    ver["next_action"] = ("secondary path over %s; primary timing map absent"
                          % ("bed" if is_song else "master audio"))
    return ver


# ------------------------------------------------------------------ gate ----
def record_for_gate(verdict, run_id, stage, reviewer_identity,
                    reviewer_session, reviewer_authority):
    """qc-schema record for the shared final QC gate (check `audio`).

    The run's Final edit QC (17.5) passes the record in the records array
    it hands core/qc_gate.evaluate; validated against qc_gate.validate_record
    in the tests. Fail-closed: a UNAVAILABLE verdict cannot advance (17.8);
    session/authority are REQUIRED (24.4: an unbound record never advances a
    stage), so callers hand the real reviewer binding, never blanks.
    """
    if not reviewer_session or not reviewer_authority:
        raise SungGuardError(
            "REVIEWER_UNBOUND",
            "24.4: record_for_gate needs reviewer_session and "
            "reviewer_authority (a blank record can never advance a stage)")
    reason = verdict.get("reason_code") or "SUNG_GUARD"
    if verdict["outcome"] == "PASS":
        summary = ("sung_vocal_guard %s: %s (mode=%s, sung_coverage=%s)"
                   % (TOOL_VERSION, reason, verdict.get("voice_mode"),
                      verdict.get("sung_coverage")))
    else:
        summary = ("%s: %s" % (reason, verdict.get("next_action")))
    rec = {"schema_version": "1.0.0", "check_id": "final:audio:sung_vocal",
           "run_id": run_id, "stage": stage, "check": "audio",
           "verdict": "PASS" if verdict["outcome"] == "PASS" else "FAIL",
           "evidence": {"summary": summary},
           "checker_version": TOOL_VERSION,
           "reviewer": {"identity": reviewer_identity,
                        "session": reviewer_session,
                        "authority": reviewer_authority}}
    return rec