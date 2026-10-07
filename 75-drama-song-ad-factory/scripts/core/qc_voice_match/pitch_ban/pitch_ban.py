#!/usr/bin/env python3
"""Pitch-shift ban (owner Decision 36 / D22a, 2026-10-07; plan 6.12 item 3),
aligned with the D17 voice-match rules. Stdlib only, no network, no spend.

Four fail-closed rules. Every one of them is a refusal or a mismatch: a
pitch-displaced voice is NEVER accepted as the same voice.

1. NO DECLARED SHIFT, EVER. Any record carrying a pitch-shift declaration
   (``pitch_shift_semitones``, ``transpose*``, ``*semitone*``) whose value is
   not provably zero is refused ``PITCH_SHIFT_REFUSED`` -- request records,
   registry identities and line records alike. So a registry record can never
   record a shift: ``registry_records_never_pitch_shift`` walks a whole
   registry and reports every declaration by path.
2. TRANSPOSED MATCHES ARE REJECTED. Measured pitch against the line's
   intended (design) pitch: a displacement of MIN_SHIFT_SEMITONES or more
   that lands within SHIFT_TOLERANCE_CENTS of a whole number of semitones is
   a transposition -> ``PITCH_SHIFTED_MISMATCH``. The D22a incident line
   (+3 semitones) is refused here even when the shifted value still sits
   inside the claimed gender band.
3. OCTAVE DISPLACEMENT IS A MISMATCH (D17 + D22a). The same test with a
   whole multiple of 12 semitones classifies as ``OCTAVE_MISMATCH``: an
   octave-off take is the wrong voice even when the measured value still
   falls inside the claimed gender band (a female line detected an octave
   down lands at 85-127 Hz and must not pass a male claim).
4. EVERYTHING ELSE OUT OF TOLERANCE FAILS. Drift beyond
   DRIFT_TOLERANCE_CENTS -> ``PITCH_MISMATCH``; no intended pitch anywhere
   (line keys and character/registry keys all silent) ->
   ``INTENDED_PITCH_UNKNOWN``: UNAVAILABLE never becomes PASS (17.8).

Delegation, one source of truth: the gender ranges, the on-screen speaker
rule, same-gender distinctness and the pitch estimator belong to the sibling
``qc_voice_match`` package (D17) and are imported from it, never
re-implemented. ``evaluate`` runs those parent checks PLUS the rules above,
so one report is rejected by all of them -- band, speaker, distinctness,
transposition, octave.

Deterministic: synthetic tones, fixed search window, no randomness, no
provider call, no spend.

ponytail: the intended pitch is a single scalar Hz value taken from the line
record or the character/registry record. Raise DRIFT_TOLERANCE_CENTS only if
real takes are shown to drift further on their own; the transposition and
octave rules do not depend on it.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

try:                                    # package import (core/ on sys.path)
    from .. import qc_voice_match as base
except ImportError:                     # direct execution from anywhere
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    import qc_voice_match.qc_voice_match as base

TOOL_NAME = "pitch_ban"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.qc-pitch-ban/report/v1"
CHECK = "audio"                     # qc-schema check this module scores
CHECK_ID = "pitch-ban"
REPORT_COMPATIBLE = set(base.REPORT_COMPATIBLE)

# Owner D17: the ranges are the parent module's; one source of truth.
PITCH_RANGES_HZ = base.PITCH_RANGES_HZ
SAME_GENDER_MIN_SEPARATION_HZ = base.SAME_GENDER_MIN_SEPARATION_HZ

# D22a tolerance ladder (cents). Drift window first, then transposition:
DRIFT_TOLERANCE_CENTS = 50.0    # half a semitone of ordinary drift/noise
SHIFT_TOLERANCE_CENTS = 50.0    # window around an exact N-semitone value
MIN_SHIFT_SEMITONES = 2         # >= this whole semitones = deliberate shift

# Where the intended (design) pitch may be declared.
LINE_INTENDED_KEYS = ("intended_hz", "intended_pitch_hz", "target_pitch_hz")
CHAR_INTENDED_KEYS = ("intended_hz", "intended_pitch_hz", "voice_pitch_hz",
                      "pitch_center", "pitch_hz")

EXIT = dict(base.EXIT)

VoiceMatchError = base.VoiceMatchError
AssemblyBlocked = base.AssemblyBlocked
refuse_before_assembly = base.refuse_before_assembly


class PitchBanError(Exception):
    """Structural problem in the report itself (exit 1, never a verdict)."""


def _usable(v):
    """Positive finite number (bool excluded)."""
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v) and v > 0.0)


# ------------------------------------------------------- transposition -----

def cents_between(reference_hz, measured_hz):
    """Signed cents from reference to measured. None = undeterminable."""
    if not _usable(reference_hz) or not _usable(measured_hz):
        return None
    return 1200.0 * math.log2(float(measured_hz) / float(reference_hz))


def _half_away(x):
    """Round half away from zero (banker's rounding would call 0.5 -> 0)."""
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


def shift_verdict(reference_hz, measured_hz, drift_cents=None,
                  shift_cents=None, min_shift_semitones=None):
    """Match verdict for one measured take against its intended pitch.

    Returns a dict: ``ok``, ``code`` ("" when ok),
    ``OCTAVE_MISMATCH`` / ``PITCH_SHIFTED_MISMATCH`` / ``PITCH_MISMATCH`` /
    ``PITCH_UNDETERMINABLE``, plus ``cents``, ``semitones``,
    ``integer_semitones``, ``octaves`` and a human ``detail``.
    """
    cents = cents_between(reference_hz, measured_hz)
    drift_tol = DRIFT_TOLERANCE_CENTS if drift_cents is None \
        else float(drift_cents)
    shift_tol = SHIFT_TOLERANCE_CENTS if shift_cents is None \
        else float(shift_cents)
    min_shift = MIN_SHIFT_SEMITONES if min_shift_semitones is None \
        else int(min_shift_semitones)
    if cents is None:
        return {"ok": False, "code": "PITCH_UNDETERMINABLE",
                "cents": None, "semitones": None, "integer_semitones": None,
                "octaves": None,
                "detail": "cannot compare measured %r against intended %r"
                          % (measured_hz, reference_hz)}
    semis = cents / 100.0
    k = int(_half_away(semis))
    near = abs(cents - 100.0 * k) <= shift_tol
    if k != 0 and near and abs(k) >= min_shift:
        if abs(k) % 12 == 0:
            octaves = abs(k) // 12
            return {"ok": False, "code": "OCTAVE_MISMATCH", "cents": cents,
                    "semitones": semis, "integer_semitones": k,
                    "octaves": octaves,
                    "detail": "measured %.1f Hz is %d octave(s) (%+.0f cents) "
                              "from intended %.1f Hz; an octave displacement "
                              "is a mismatch, never a match (D17+D22a)"
                              % (float(measured_hz), octaves, cents,
                                 float(reference_hz))}
        return {"ok": False, "code": "PITCH_SHIFTED_MISMATCH", "cents": cents,
                "semitones": semis, "integer_semitones": k, "octaves": 0,
                "detail": "measured %.1f Hz is transposed %+d semitones "
                          "(%+.0f cents) from intended %.1f Hz; a transposed "
                          "take is rejected, never accepted as the same voice "
                          "(D22a)"
                          % (float(measured_hz), k, cents,
                             float(reference_hz))}
    if abs(cents) > drift_tol:
        return {"ok": False, "code": "PITCH_MISMATCH", "cents": cents,
                "semitones": semis, "integer_semitones": k, "octaves": 0,
                "detail": "measured %.1f Hz drifts %+.0f cents (%+.2f "
                          "semitones) from intended %.1f Hz, beyond the "
                          "%.0f cent drift tolerance"
                          % (float(measured_hz), cents, semis,
                             float(reference_hz), drift_tol)}
    return {"ok": True, "code": "", "cents": cents, "semitones": semis,
            "integer_semitones": k, "octaves": 0,
            "detail": "measured %.1f Hz matches intended %.1f Hz (%+.0f cents)"
                      % (float(measured_hz), float(reference_hz), cents)}


def check_match(reference_hz, measured_hz, line_id=None, **tol):
    """Failure dict for one comparison, or None when it matches."""
    v = shift_verdict(reference_hz, measured_hz, **tol)
    if v["ok"]:
        return None
    return {"code": v["code"], "line": line_id or "?",
            "detail": v["detail"]}


# ---------------------------------------------------- declared shifts ------

def _shift_key(key):
    k = str(key).casefold()
    return "pitch_shift" in k or "semitone" in k or "transpose" in k


def _shift_declared(value):
    """True unless the value is PROVABLY zero (fail-closed)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return True                      # True/False proves nothing about 0 Hz
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return False
        try:
            return float(s) != 0.0       # "nan"/"inf" -> not provably zero
        except ValueError:
            return True
    return True                          # containers/objects: unprovable


def scan_shift_declarations(node, path="record"):
    """Every non-zero pitch-shift declaration under ``node``.

    Returns [{"path", "key", "value"}]; empty list = nothing declares a
    shift. Walks dicts and lists (report/registry data is JSON, no cycles).
    """
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = "%s.%s" % (path, key)
            if _shift_key(key) and _shift_declared(value):
                found.append({"path": here, "key": str(key), "value": value})
            found.extend(scan_shift_declarations(value, here))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(scan_shift_declarations(value, "%s[%d]" % (path, i)))
    return found


def _refusal(entry):
    return {"code": "PITCH_SHIFT_REFUSED",
            "detail": "%s declares %s=%r; D22a: no code path may pitch-shift "
                      "a voice" % (entry["path"], entry["key"],
                                   entry["value"])}


def refuse_pitch_shift(record, where="record"):
    """Refusal list for one record (empty = provably shift-free)."""
    if not isinstance(record, (dict, list)):
        return [{"code": "PITCH_SHIFT_REFUSED",
                 "detail": "%s is not a record object" % (where,)}]
    return [_refusal(e) for e in scan_shift_declarations(record, where)]


def registry_records_never_pitch_shift(registry, where="registry"):
    """Whole-registry shift scan: every entry, every record, by path.

    Fail-closed: a registry that is not a dict/list is itself an error, so a
    malformed registry can never prove "no shift".
    """
    if not isinstance(registry, (dict, list)):
        return [{"code": "REGISTRY_INVALID",
                 "detail": "%s is %s, not a record object"
                           % (where, type(registry).__name__)}]
    return [_refusal(e) for e in scan_shift_declarations(registry, where)]


# --------------------------------------------------------------- checks ----

def intended_pitch(line, char_index=None):
    """(hz, status, source) for a line's intended pitch.

    status: "ok" | "missing" | "invalid". Resolution order: line keys,
    then the character/registry entry matching the line's speaker.
    """
    if not isinstance(line, dict):
        return None, "missing", None
    for key in LINE_INTENDED_KEYS:
        if key in line and line[key] is not None:
            v = line[key]
            return (float(v), "ok", key) if _usable(v) \
                else (None, "invalid", key)
    speaker = line.get("speaker")
    if isinstance(speaker, str) and speaker.strip() and char_index:
        entry = char_index.get(speaker.strip())
        if isinstance(entry, dict):
            for key in CHAR_INTENDED_KEYS:
                if key in entry and entry[key] is not None:
                    v = entry[key]
                    where = "characters[%s].%s" % (speaker.strip(), key)
                    return (float(v), "ok", where) if _usable(v) \
                        else (None, "invalid", where)
    return None, "missing", None


def char_index(report):
    """speaker/id -> character record from report["characters"] (else {})."""
    chars = report.get("characters") if isinstance(report, dict) else None
    index = {}
    for ch in chars or []:
        if not isinstance(ch, dict):
            continue
        for key in ("id", "name"):
            v = ch.get(key)
            if isinstance(v, str) and v.strip():
                index[v.strip()] = ch
                break
    return index


def check_line(line, char_index=None):
    """(failures, measured_hz) -- parent D17 checks plus the pitch ban."""
    failures, hz, _ = base.check_line(line)
    if not isinstance(line, dict):
        return failures, hz
    line_id = line.get("line_id") if isinstance(line.get("line_id"), str) \
        and line.get("line_id").strip() else "?"

    # Rule 1: the record itself may never declare a shift.
    failures.extend(refuse_pitch_shift(line, "lines[%s]" % line_id))

    intended, status, _source = intended_pitch(line, char_index)
    if status != "ok":
        failures.append({
            "code": "INTENDED_PITCH_UNKNOWN",
            "line": line_id,
            "detail": "no usable intended pitch on the line or its "
                      "character/registry entry; the transposition and "
                      "octave checks cannot run (fail-closed, 17.8 "
                      "UNAVAILABLE never becomes PASS)",
        })
        return failures, hz
    if hz is None:
        # Parent already failed the line (missing audio / no fundamental);
        # the comparison is undeterminable and the line never passes.
        return failures, hz
    failure = check_match(intended, hz, line_id=line_id)
    if failure is not None:
        failures.append(failure)
    return failures, hz


def evaluate(report):
    """Full run verdict. Structural problems raise VoiceMatchError."""
    if not isinstance(report, dict):
        raise VoiceMatchError("BAD_INPUT", "report must be an object")
    if report.get("schema_version") not in REPORT_COMPATIBLE:
        raise VoiceMatchError(
            "BAD_INPUT", "schema_version must be one of %s"
            % sorted(REPORT_COMPATIBLE))
    run_id = report.get("run_id")
    stage = report.get("stage")
    run_id = run_id.strip() if isinstance(run_id, str) and run_id.strip() \
        else None
    stage = stage.strip() if isinstance(stage, str) and stage.strip() \
        else None
    if not run_id or not stage:
        raise VoiceMatchError("BAD_INPUT", "run_id and stage are required")
    lines = report.get("lines")
    if not isinstance(lines, list) or not lines:
        raise VoiceMatchError("BAD_INPUT", "lines must be a non-empty list")

    index = char_index(report)
    failures = []
    measured = []
    compared = []
    for line in lines:
        line_fail, hz = check_line(line, index)
        failures.extend(line_fail)
        if hz is not None:
            measured.append(hz)
        if isinstance(line, dict):
            lid = line.get("line_id") if isinstance(line.get("line_id"), str) \
                and line.get("line_id").strip() else "?"
            intended, status, _src = intended_pitch(line, index)
            verdict = shift_verdict(intended, hz) if (
                intended is not None and hz is not None) else None
            compared.append({
                "line": lid,
                "intended_hz": intended,
                "measured_hz": None if hz is None else round(hz, 2),
                "cents": None if verdict is None
                         else round(verdict["cents"], 1),
                "code": "" if verdict is None else verdict["code"],
                "intended_status": status,
            })

    # Registry and character records carry no shift either (rule 1).
    characters = report.get("characters")
    if isinstance(characters, list) and characters:
        failures.extend(refuse_pitch_shift(characters, "characters"))
        failures.extend(base.check_distinct_same_gender(characters))
    registry = report.get("registry")
    if registry is not None:
        failures.extend(registry_records_never_pitch_shift(registry))

    codes = sorted({f["code"] for f in failures})
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "command": "check",
        "run_id": run_id,
        "stage": stage,
        "outcome": "ok" if not failures else "rejected",
        "reason_code": "PITCH_BAN_OK" if not failures
                       else "+".join(codes),
        "next_action": "assembly may proceed" if not failures else
                       "regenerate the failing line(s) in Suno at the "
                       "character's own pitch -- never pitch-shifted, never "
                       "retried by any other voice tool -- then re-run "
                       "pitch-ban QC; assembly stays blocked",
        "evidence": {
            "lines_checked": len(lines),
            "measured_hz": [round(h, 2) for h in measured],
            "failures": failures,
            "pitch_ranges_hz": {k: list(v) for k, v in
                                sorted(PITCH_RANGES_HZ.items())},
            "same_gender_min_separation_hz": SAME_GENDER_MIN_SEPARATION_HZ,
            "drift_tolerance_cents": DRIFT_TOLERANCE_CENTS,
            "shift_tolerance_cents": SHIFT_TOLERANCE_CENTS,
            "min_shift_semitones": MIN_SHIFT_SEMITONES,
            "intended_vs_measured": compared,
        },
    }


def envelope(result):
    return result


def to_qc_record(result, reviewer, check_id=None, checker_version=None):
    """qc-schema 1.0.0 verdict record (check=audio) for core/qc_gate.py."""
    return base.to_qc_record(result, reviewer,
                             check_id=check_id or CHECK_ID,
                             checker_version=checker_version or TOOL_VERSION)


# ------------------------------------------------------------------ CLI ----

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="pitch_ban",
        description="D22a pitch-shift ban + D17 octave guard: transposed and "
                    "octave-displaced takes are mismatches (fail-closed, "
                    "runs before assembly)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check", help="evaluate a line report")
    a.add_argument("--report", required=True, help="report JSON path")
    a.add_argument("--qc-record", default="",
                   help="also write the qc-schema audio verdict record here")
    a.add_argument("--reviewer-identity", default="pitch_ban/%s"
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
