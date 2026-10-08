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
   the sung vocal for All Suno ads, or a song bed under the voiceover for
   Velvet Voiceover ads. Sung share is judged ONLY by Trevor's band around
   the ad's own sung target (choice card / plan, default from the G10
   constants in core/spoken_share, 77.5): within 5 points accept, 5-10 accept
   with a flag, past 10 redo. Sung is measured against VOICE time, sung /
   (sung + spoken): a music-only intro, gaps and the end card never count
   against it (SPK001). There is NO absolute floor;
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
  SUNG_COVERAGE_LOW  -- sung share is more than 10 points from the ad's own
                        sung target (Trevor's band: redo).

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

try:
    import spoken_share as _SS            # core/ on sys.path (see above)
except ImportError:                      # pragma: no cover
    from .. import spoken_share as _SS

TOOL_NAME = "final_assembler.sung_vocal_guard"
TOOL_VERSION = "1.1.0"

#: Trevor (2026-10-08): "It's not an absolute 55% or 20% ... within about 5
#: percentage points" and "Once you get past 10%, it's got to be redone."
#: The old 55 % hard floor (Decision 39 / E7-AMEND) is GONE. The target and
#: band numbers live in ONE place, the G10 constants in core/spoken_share
#: (SUNG_TARGET_PCT, ACCEPT_PTS, FLAG_PTS). The only hard reject besides the
#: band is H8's "no real singing" (no NO_REAL_SINGING_STRETCH_S sung stretch).
SUNG_TARGET = _SS.SUNG_TARGET_PCT / 100.0

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


def resolve_sung_target(profile=None, target=None):
    """The ad's own sung target as a fraction of VOICE time.

    Order: explicit ``target`` argument, then the choice card / plan record
    (``sung_target`` or ``sung_target_pct``, top level or under ``style``),
    then the G10 default. A value above 1 is read as a percent.
    """
    raw = target
    if raw is None and isinstance(profile, dict):
        for src in (profile, profile.get("style")):
            if isinstance(src, dict):
                for key in ("sung_target", "sung_target_pct"):
                    if src.get(key) is not None:
                        raw = src[key]
                        break
            if raw is not None:
                break
    if raw is None:
        return SUNG_TARGET
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise SungGuardError("BAD_TARGET", "sung target must be a number, "
                             "got %r" % (raw,))
    raw = float(raw)
    raw = raw / 100.0 if raw > 1.0 else raw
    if not 0.0 < raw <= 1.0:
        raise SungGuardError("BAD_TARGET",
                             "sung target must be in (0, 100] %%, got %r" % raw)
    return raw


# ------------------------------------------------------------ evidence ------
def sung_voice_seconds_from_timing(timing, spoken_section_ids=None):
    """(sung_s, spoken_s) from the 12.4 timing map: line windows in the
    ``spoken_section_ids`` sections are spoken, every other line window is
    sung. Gaps no line covers (intro, breaks, end card) are in neither."""
    t = load_timing_map(timing)
    sung_s = sum(en - st for st, en in _sung_windows(t, spoken_section_ids))
    spoken_s = sum(en - st for st, en in
                   _sung_windows(t, spoken_section_ids, spoken=True))
    return sung_s, spoken_s


def sung_coverage_from_timing(timing, runtime_s=None, spoken_section_ids=None):
    """Sung share of VOICE time, sung / (sung + spoken), from the planner's
    12.4 song timing map, as (ratio 0..1, runtime_s).

    Normalizes the map through shot_planner.load_timing_map. Music-only
    seconds (intro, gaps, end card) are not voice time and never count
    against singing (SPK001). ``spoken_section_ids`` names the spoken-line
    sections (E8 lays those lines on the bed, they are not sung). ``runtime_s``
    (default: the map's own duration_seconds) is returned for the receipt.
    Raises ValueError on a bad shape (never coerces it to "no sung").
    """
    t = load_timing_map(timing)
    dur = float(runtime_s) if runtime_s is not None \
        else float(t["duration_seconds"])
    if dur <= 0:
        raise ValueError("BAD_RUNTIME: runtime must be positive")
    sung_s, spoken_s = sung_voice_seconds_from_timing(timing, spoken_section_ids)
    if sung_s + spoken_s <= 0:
        return 0.0, dur
    return sung_s / (sung_s + spoken_s), dur


def _sung_windows(t, spoken_section_ids=None, spoken=False):
    """(start, end) of every sung line window in a normalized timing map
    (``spoken=True``: of every spoken line window instead)."""
    ids = {_norm(s) for s in (spoken_section_ids or []) if isinstance(s, str)}
    out = []
    for ln in t["lines"].values():
        is_spoken = bool(ids and ln["section_id"]
                         and _norm(ln["section_id"]) in ids)
        if is_spoken != spoken:
            continue
        st, en = float(ln["start"]), float(ln["end"])
        if en > st:
            out.append((st, en))
    return out


def longest_sung_stretch_from_timing(timing, spoken_section_ids=None):
    """Longest sung stretch (s) in a 12.4 map, via the one shared rule."""
    segs = [{"delivery": "sung", "start": a, "end": b}
            for a, b in _sung_windows(load_timing_map(timing),
                                      spoken_section_ids)]
    return _SS.longest_sung_stretch_s(segs) if segs else 0.0


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
                     spoken_section_ids=None, target=None):
    """E7 verdict: the master is sung (All Suno) or has its bed (Velvet).

    Primary path  -- ``timing``: 12.4 map -> sung coverage ratio.
                     no sung stretch of 6 s  -> FAIL VOCAL_MISSING
                     within 5 points of the ad's target   -> PASS
                     (sung share of VOICE time, sung / (sung + spoken);
                     pass ``spoken_section_ids`` so spoken lines count)
                     5-10 points off                      -> PASS + flag
                     more than 10 points off              -> FAIL
                                                SUNG_COVERAGE_LOW (redo)
                     ``target`` (fraction) or the card's ``sung_target``;
                     default: the G10 constant. No absolute floor.
    Secondary path-- no map: ``master_path``/``scan_stderr`` gives the
                     vocal-presence signal; detected -> PASS (All Suno) /
                     bed present (Velvet); absent -> FAIL VOCAL_MISSING.
                     Neither evidence -> FAIL UNAVAILABLE-ish gate verdict
                     UNAVAILABLE (17.8: missing evidence never passes).

    Returns the verdict dict (record_for_gate builds the qc record from it).
    """
    mode, defaulted = resolve_voice_mode(profile)
    target = resolve_sung_target(profile, target)
    ver = {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
           "voice_mode": mode, "voice_mode_defaulted": defaulted,
           "target": round(target, 4), "evidence_path": None,
           "sung_coverage": None, "outcome": "FAIL", "reason_code": None,
           "next_action": None, "flags": []}
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
        ver["measured_over"] = "voice_time"
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
        stretch = longest_sung_stretch_from_timing(timing, spoken_section_ids)
        ver["longest_sung_stretch_s"] = stretch
        if stretch + 1e-9 < _SS.NO_REAL_SINGING_STRETCH_S:
            ver["outcome"] = "FAIL"
            ver["reason_code"] = "VOCAL_MISSING"
            ver["next_action"] = (
                "no real singing: longest sung stretch %.1f s, needs %.0f s; "
                "re-cut with the Suno song master"
                % (stretch, _SS.NO_REAL_SINGING_STRETCH_S))
            return ver
        j = _SS.judge_gap(ratio * 100.0, target * 100.0)
        ver["gap_pts"] = j["gap_pts"]
        if j["verdict"] == _SS.VERDICT_FAIL:
            ver["outcome"] = "FAIL"
            ver["reason_code"] = "SUNG_COVERAGE_LOW"
            ver["next_action"] = (
                "sung %.2f%% of voice time is %.1f points from the %g%% target, "
                "past %d: redo" % (ratio * 100.0, j["gap_pts"],
                                   target * 100.0, _SS.FLAG_PTS))
            return ver
        ver["outcome"] = "PASS"
        ver["reason_code"] = "SUNG_COVERAGE_OK"
        if j["verdict"] == _SS.VERDICT_FLAG:
            ver["flags"] = [
                "sung %.2f%% of voice time is %.1f points from the %g%% target: "
                "accepted with a flag" % (ratio * 100.0, j["gap_pts"],
                                          target * 100.0)]
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
        summary = ("sung_vocal_guard %s: %s (mode=%s, sung_coverage=%s)%s"
                   % (TOOL_VERSION, reason, verdict.get("voice_mode"),
                      verdict.get("sung_coverage"),
                      "".join(" FLAG: " + f for f in verdict.get("flags", []))))
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