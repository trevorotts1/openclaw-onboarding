#!/usr/bin/env python3
"""Lyric timing guard: observed-vs-approved checks before storyboard/assembly/export.

Directive 12.4 + 24.2 row 7. Stdlib only. Thresholds come from
core/acceptance-profile.json; approved lyrics stay the textual source of
truth. ASR/alignment output is timing and mismatch evidence, never a license
to rewrite approved text: omitting or changing critical words fails song QC.
Product names align against the known script, never blind ASR trust.

Checks: lyric coverage (100% critical, 98% overall normalized), ordered
timestamps, confidence (low -> REVIEW, never invented precision), frame-grid
rounding (round once), cumulative drift cap, clip durations, final AV sync,
alignment error stats, CTA hold.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

TOOL_NAME = "timing_guard"
TOOL_VERSION = "1.0.0"

_PROFILE_PATH = Path(__file__).resolve().parent / "acceptance-profile.json"

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
_EPS = 1e-9


class TimingError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_profile(path=None):
    """Acceptance thresholds. Caller-supplied dict wins; else the shipped file."""
    if isinstance(path, dict):
        return path
    with open(path or _PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _profile_numbers(profile):
    t = profile["timing"]
    return {
        "fps": profile["export"]["fps"],
        "frame": 1.0 / profile["export"]["fps"],
        "critical_cov": profile["lyrics"]["critical_word_coverage_required"],
        "overall_cov": profile["lyrics"]["overall_normalized_coverage_min"],
        "median_max_ms": t["median_max_ms"],
        "p95_max_ms": t["p95_max_ms"],
        "critical_max_ms": t["critical_boundary_max_ms"],
        "av_max_frames": profile["timeline"]["max_av_duration_diff_frames"],
        "cta_hold_min": profile["cta"]["hold_seconds_min"],
    }


def normalize_text(text, pronunciation_map=None):
    """Lowercase alphanumeric tokens. Mapped phonetic spellings canonicalize
    (mapping changes spelling in generation input, never meaning)."""
    pmap = pronunciation_map or {}
    return [pmap.get(w, w) for w in _WORD_RE.findall((text or "").lower())]


def _word_of(entry):
    return entry["word"] if isinstance(entry, dict) else entry


def check_coverage(approved_lines, observed_words, pronunciation_map=None,
                   overall_min=0.98):
    """100% of critical approved words present; overall >= overall_min.
    Raises MISSING_CRITICAL / LOW_COVERAGE with the missing tokens."""
    from collections import Counter
    approved = []
    for line in approved_lines or []:
        crit = bool(line.get("critical"))
        for w in normalize_text(line.get("text", ""), pronunciation_map):
            approved.append((w, crit))
    if not approved:
        raise TimingError("NO_APPROVED_LYRICS", "nothing approved to cover")
    obs = Counter(normalize_text(" ".join(_word_of(w) for w in
                                          (observed_words or [])),
                                 pronunciation_map))
    missing_critical, missing, covered = [], [], 0
    for w, crit in approved:
        if obs[w] > 0:
            obs[w] -= 1
            covered += 1
        elif crit:
            missing_critical.append(w)
        else:
            missing.append(w)
    if missing_critical:
        raise TimingError("MISSING_CRITICAL",
                          "critical words absent: %s"
                          % sorted(set(missing_critical)))
    overall = covered / len(approved)
    if overall + _EPS < overall_min:
        raise TimingError("LOW_COVERAGE",
                          "overall %.3f < %.2f; missing: %s"
                          % (overall, overall_min, sorted(set(missing))))
    return {"overall": overall, "approved_n": len(approved), "covered": covered}


def _stamp(entry, i):
    try:
        s, e = float(entry["start"]), float(entry["end"])
    except (KeyError, TypeError, ValueError):
        raise TimingError("BAD_TIMESTAMP", "entry %d needs numeric start/end"
                          % i)
    if s < 0 or e < 0:
        raise TimingError("BAD_TIMESTAMP",
                          "entry %d has start=%s end=%s" % (i, s, e))
    if e + _EPS < s:
        raise TimingError("UNORDERED_TIMESTAMPS", "entry %d ends before start"
                          % i)
    return s, e


def check_order(entries):
    """Strictly non-overlapping, non-decreasing timestamps. Raises
    UNORDERED_TIMESTAMPS on any backward step or overlap."""
    prev_end = None
    for i, entry in enumerate(entries or []):
        s, e = _stamp(entry, i)
        if prev_end is not None and s + _EPS < prev_end:
            raise TimingError("UNORDERED_TIMESTAMPS",
                              "entry %d starts %s before prior end %s"
                              % (i, s, prev_end))
        prev_end = e
    return True


def check_containment(parent, children, label):
    """Children ordered and inside the parent span."""
    check_order(children)
    if children:
        s0, _ = _stamp(children[0], 0)
        _, e1 = _stamp(children[-1], len(children) - 1)
        if s0 + _EPS < float(parent["start"]) or \
                float(parent["end"]) + _EPS < e1:
            raise TimingError("BOUNDARY_ESCAPE",
                              "%s children exceed [%s, %s]"
                              % (label, parent["start"], parent["end"]))
    return True


def round_to_grid(t, fps):
    """Round once to the declared frame grid. Never re-round output."""
    return round(t * fps) / fps


def check_frame_grid(stamps, fps):
    """Every stamp already on the grid (rounded once by the producer)."""
    for t in stamps:
        if abs(t - round_to_grid(t, fps)) > 1e-6:
            raise TimingError("BAD_FRAME_ROUNDING",
                              "%s off %dfps grid" % (t, fps))
    return True


def check_cumulative_drift(deltas_seconds, fps, cap_frames=1):
    """Signed rounding/boundary deltas must not accumulate past one frame.
    Small per-step shifts that cascade past the cap reject."""
    cap = cap_frames / fps
    cum = 0.0
    for d in deltas_seconds:
        cum += d
        if abs(cum) > cap + _EPS:
            raise TimingError("DRIFT_CASCADE",
                              "cumulative drift %.4fs exceeds %d frame(s)"
                              % (cum, cap_frames))
    return {"cumulative_seconds": cum}


def low_confidence_entries(entries, min_confidence=0.70):
    """IDs needing human review. Missing confidence counts as low: review,
    never invented precision."""
    # ponytail: 0.70 placeholder, profile uncalibrated; pass calibrated value
    # from the acceptance profile once qualification sets one.
    low = []
    for i, e in enumerate(entries or []):
        if not isinstance(e, dict):
            continue
        c = e.get("confidence")
        if c is None or float(c) < min_confidence:
            low.append(e.get("word", e.get("line_id", "#%d" % i)))
    return low


def _p95(vals):
    s = sorted(vals)
    return s[max(0, -(-95 * len(s) // 100) - 1)]


def check_alignment(sample_errors_ms, critical_errors_ms, *, median_max_ms,
                    p95_max_ms, critical_max_ms):
    """Independently annotated sample stats vs profile. Raises on breach."""
    if not sample_errors_ms:
        raise TimingError("NO_TIMING_SAMPLE", "no annotated sample recorded")
    med = statistics.median(sample_errors_ms)
    p95 = _p95(sample_errors_ms)
    crit = max((abs(x) for x in (critical_errors_ms or [])), default=0)
    if med > median_max_ms + _EPS:
        raise TimingError("TIMING_MEDIAN_EXCEEDED", "median %.1fms" % med)
    if p95 > p95_max_ms + _EPS:
        raise TimingError("TIMING_P95_EXCEEDED", "p95 %.1fms" % p95)
    if crit > critical_max_ms + _EPS:
        raise TimingError("TIMING_CRITICAL_EXCEEDED", "critical %.1fms" % crit)
    return {"median_ms": med, "p95_ms": p95, "critical_max_ms": crit}


def check_av_sync(audio_seconds, video_seconds, fps, max_frames=1):
    """Final A/V duration difference within max_frames output frames."""
    if abs(audio_seconds - video_seconds) > max_frames / fps + _EPS:
        raise TimingError("AV_SYNC_EXCEEDED",
                          "|%.3f - %.3f| exceeds %d frame(s)"
                          % (audio_seconds, video_seconds, max_frames))
    return True


def check_clips(clips, fps, max_frames=1):
    """Clips ordered; each duration matches its mapped span within one
    frame; boundary mismatches must not cascade past one frame."""
    check_order([{"start": c["start"], "end": c["end"]}
                 for c in (clips or [])])
    tol = max_frames / fps
    deltas = []
    for c in clips or []:
        dur = float(c["end"]) - float(c["start"])
        if dur <= 0:
            raise TimingError("BAD_TIMESTAMP", "clip %s non-positive"
                              % c.get("clip_id"))
        if c.get("span_start") is not None:
            span = float(c["span_end"]) - float(c["span_start"])
            if abs(dur - span) > tol + _EPS:
                raise TimingError("CLIP_DURATION_MISMATCH",
                                  "clip %s %.3fs vs mapped %.3fs"
                                  % (c.get("clip_id"), dur, span))
    for prev, cur in zip(clips or [], (clips or [])[1:]):
        deltas.append(float(cur["start"]) - float(prev["end"]))
    check_cumulative_drift(deltas, fps, cap_frames=max_frames)
    return True


def validate(approved_lines, observed_words, timing_map=None, *,
             profile=None, pronunciation_map=None, min_confidence=0.70,
             sample_errors_ms=None, critical_errors_ms=None,
             clips=None, audio_seconds=None, video_seconds=None,
             cta_hold_seconds=None):
    """Run every guard; return a QC-style receipt. FAIL on any hard breach,
    REVIEW when only low-confidence/sample gaps need a human, else PASS."""
    prof = _profile_numbers(load_profile(profile))
    fps = prof["fps"]
    fails, evidence = [], {}

    try:
        evidence["coverage"] = check_coverage(
            approved_lines, observed_words, pronunciation_map,
            prof["overall_cov"])
    except TimingError as e:
        fails.append(e)

    words = [w for w in (observed_words or []) if isinstance(w, dict)
             and "start" in w and "end" in w]
    try:
        if words:
            check_order(words)
            check_frame_grid([float(w["start"]) for w in words]
                             + [float(w["end"]) for w in words], fps)
            raw = [float(w["start"]) - float(w["raw_start"])
                   for w in words if "raw_start" in w] + \
                  [float(w["end"]) - float(w["raw_end"])
                   for w in words if "raw_end" in w]
            if raw:
                evidence["drift"] = check_cumulative_drift(raw, fps)
    except TimingError as e:
        fails.append(e)

    sections = (timing_map or {}).get("sections", []) if timing_map else []
    try:
        check_order([{"start": s["start"], "end": s["end"]}
                     for s in sections])
        for s in sections:
            check_containment(s, s.get("lyrics", []),
                              s.get("section_id", "?"))
        if len(sections) > 1:
            check_cumulative_drift(
                [float(nxt["start"]) - float(prv["end"])
                 for prv, nxt in zip(sections, sections[1:])], fps)
    except TimingError as e:
        fails.append(e)

    if sample_errors_ms is not None or critical_errors_ms is not None:
        try:
            evidence["alignment"] = check_alignment(
                sample_errors_ms or [], critical_errors_ms or [],
                median_max_ms=prof["median_max_ms"],
                p95_max_ms=prof["p95_max_ms"],
                critical_max_ms=prof["critical_max_ms"])
        except TimingError as e:
            fails.append(e)

    try:
        if clips is not None:
            check_clips(clips, fps, prof["av_max_frames"])
        if audio_seconds is not None and video_seconds is not None:
            check_av_sync(audio_seconds, video_seconds, fps,
                          prof["av_max_frames"])
        if cta_hold_seconds is not None and \
                cta_hold_seconds + _EPS < prof["cta_hold_min"]:
            raise TimingError("CTA_HOLD_SHORT", "%.2fs < %ds"
                              % (cta_hold_seconds, prof["cta_hold_min"]))
    except TimingError as e:
        fails.append(e)

    review = sorted(set(low_confidence_entries(words, min_confidence)))
    if sample_errors_ms is None and critical_errors_ms is None:
        review.append("timing-sample-unrecorded")
    evidence["low_confidence"] = review
    evidence["profile"] = {"fps": fps, "median_max_ms": prof["median_max_ms"],
                           "p95_max_ms": prof["p95_max_ms"],
                           "critical_max_ms": prof["critical_max_ms"]}

    if fails:
        verdict, code = "FAIL", fails[0].code
    elif review:
        verdict, code = "REVIEW", "LOW_CONFIDENCE"
    else:
        verdict, code = "PASS", "OK"
    return {"tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "verdict": verdict, "reason_code": code,
            "detail": "; ".join("%s: %s" % (e.code, e) for e in fails),
            "evidence": evidence}
