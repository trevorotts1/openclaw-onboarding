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
#: Timestamp alignment tolerance: the same 1e-6 ``check_frame_grid`` uses, so
#: the timeline-integrity check (WW-04) never invents a new microsecond rule.
_ALIGN_TOL = 1e-6


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


def _finite(value):
    """float(value) when it is a finite number, else None (bools are not times)."""
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def check_timeline_partition(segments, duration_s, tol=_ALIGN_TOL):
    """WW-04: ONE physical audio timeline.

    The take's delivery partition must be a SINGLE DISJOINT PARTITION of
    ``[0, duration_s]``: every segment lies inside ``[0, duration_s]``, no two
    segments overlap, none is a duplicate, and the union equals the MEASURED
    duration. The runtime denominator is ``duration_s`` itself, NEVER the sum
    of segment lengths. A partition built by concatenating a measured detector
    timeline with a word-aligned timeline over the same audio overlaps itself
    and is refused (``TIMELINE_NOT_DISJOINT``) -- that concatenation is exactly
    how the failed take's doubled denominator arose.

    Refuses non-finite, reversed or out-of-range timestamps
    (``TIMELINE_MALFORMED``). Tolerances are this module's own: ``_EPS`` (1e-9)
    for arithmetic and ``_ALIGN_TOL`` (1e-6, the same alignment tolerance
    ``check_frame_grid`` uses) -- no new universal microsecond rule.

    Returns {"verdict", "reason_code", "duration_s", "partition_seconds",
    "segments", "union_s", ...}; PASS means the partition is sound."""
    D = _finite(duration_s)
    if D is None or D <= 0:
        return {"verdict": "FAIL", "reason_code": "TIMELINE_MALFORMED",
                "duration_s": None, "segments": len(segments or []),
                "detail": "duration_s must be a positive finite number, got %r"
                          % (duration_s,)}
    rows = []
    for i, seg in enumerate(segments or []):
        if not isinstance(seg, dict):
            return {"verdict": "FAIL", "reason_code": "TIMELINE_MALFORMED",
                    "duration_s": D, "segments": len(segments or []),
                    "detail": "segment %d is not a record" % i}
        s, e = _finite(seg.get("start", seg.get("startS"))), \
            _finite(seg.get("end", seg.get("endS")))
        if s is None or e is None:
            return {"verdict": "FAIL", "reason_code": "TIMELINE_MALFORMED",
                    "duration_s": D, "segments": len(segments or []),
                    "detail": "segment %d has a non-finite timestamp (%r, %r)"
                              % (i, seg.get("start"), seg.get("end"))}
        if e < s - _EPS:
            return {"verdict": "FAIL", "reason_code": "TIMELINE_MALFORMED",
                    "duration_s": D, "segments": len(segments or []),
                    "detail": "segment %d is reversed (%.6f -> %.6f)" % (i, s, e)}
        if s < -tol or e > D + tol:
            return {"verdict": "FAIL", "reason_code": "TIMELINE_MALFORMED",
                    "duration_s": D, "segments": len(segments or []),
                    "detail": "segment %d lies outside [0, %.6f]: %.6f -> %.6f"
                              % (i, D, s, e)}
        rows.append((s, e))
    if not rows:
        return {"verdict": "FAIL", "reason_code": "TIMELINE_MALFORMED",
                "duration_s": D, "segments": 0,
                "detail": "the delivery partition is empty"}
    rows.sort()
    total = 0.0
    prev_end = None
    for s, e in rows:
        total += e - s
        if prev_end is not None:
            if s < prev_end - tol:
                return {"verdict": "FAIL", "reason_code": "TIMELINE_NOT_DISJOINT",
                        "duration_s": D, "segments": len(rows),
                        "union_s": round(total, 6),
                        "detail": "overlapping or duplicated segments: a segment "
                                  "starts at %.6f before the prior end %.6f"
                                  % (s, prev_end)}
            if s > prev_end + tol:
                return {"verdict": "FAIL", "reason_code": "TIMELINE_GAP",
                        "duration_s": D, "segments": len(rows),
                        "union_s": round(total, 6),
                        "detail": "a %.6f s gap between %.6f and %.6f"
                                  % (s - prev_end, prev_end, s)}
        prev_end = e
    if rows[0][0] > tol:
        return {"verdict": "FAIL", "reason_code": "TIMELINE_GAP",
                "duration_s": D, "segments": len(rows),
                "union_s": round(total, 6),
                "detail": "the partition starts at %.6f, not 0" % rows[0][0]}
    if rows[-1][1] < D - tol:
        return {"verdict": "FAIL", "reason_code": "TIMELINE_GAP",
                "duration_s": D, "segments": len(rows),
                "union_s": round(total, 6),
                "detail": "the partition ends at %.6f, short of %.6f"
                          % (rows[-1][1], D)}
    if total > D + tol:
        return {"verdict": "FAIL", "reason_code": "TIMELINE_NOT_DISJOINT",
                "duration_s": D, "segments": len(rows),
                "union_s": round(total, 6),
                "detail": "the segment lengths sum to %.6f s over a %.6f s "
                          "duration: the timeline is doubled" % (total, D)}
    return {"verdict": "PASS", "reason_code": "TIMELINE_DISJOINT",
            "duration_s": D, "partition_seconds": D, "segments": len(rows),
            "union_s": round(total, 6),
            "runtime_denominator_is_measured_duration": True,
            "detail": "a single disjoint partition of [0, %.6f]: %d segment(s)"
                      % (D, len(rows))}


# ---- WW-24: measured-only evidence provenance -----------------------------
#
# WW-24 IS NOT A SIXTH AUDIO GATE. It measures no audio and claims no
# audio-quality outcome. It validates the INPUTS the five delivered-audio
# results (D1..D5) are built from: PLANNED or STRETCHED timestamps never become
# returned-audio MEASUREMENTS. An evidence record is admissible as a measurement
# ONLY when it carries a sha256 export digest that MATCHES the take being
# advanced, the ACTUAL returned-audio duration, detector AND alignment
# artifacts, and a TRUSTED measurement context. A hand-set ``source="measured"``
# label is a label -- it satisfies none of these. The one-timeline arithmetic is
# ``check_timeline_partition`` above, reused -- never a second partition rule.
PROVENANCE_SCHEMA = "blackceo.measured-evidence/v1"
#: The only legal source stamp on a returned-audio measurement.
MEASURED_SOURCE = "measured"
#: Any of these on the record or on a segment marks a PLANNED timeline: a plan
#: stretched to fill the runtime with zero gaps is still a plan, never a
#: measurement (WW-24 gate: "zero-gap stretched plans").
_PLANNED_SOURCES = ("planned", "plan", "stretched", "stretch", "stretched-plan",
                    "label", "labels", "labelled", "labeled", "sheet",
                    "schedule", "estimate", "estimated", "annotation",
                    "annotations", "word", "word-annotation", "word_annotations")
#: A context (or a record's own ``source``) naming one of these is a HAND-SET
#: label, never a trusted measurement context.
_UNTRUSTED_CONTEXTS = ("manual", "hand", "handset", "hand-set", "relabel",
                       "relabelled", "relabeled", "typed", "literal", "assumed",
                       "none", "unknown", "default", "")
#: Keys a trusted measurement context must carry.
_CONTEXT_KEYS = ("tool", "tool_version", "measured_at")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


def _norm_src(value):
    return str(value or "").strip().lower().replace("_", "-")


def measured_evidence_reasons(evidence, *, binding=None, export_digest=None,
                              duration_s=None):
    """WW-24: why ``evidence`` is NOT a returned-audio measurement. [] = it is.

    Refuses, each under its own named code:
      * ``PLANNED_TIMESTAMPS`` -- the record (or a segment) is stamped planned,
        stretched, a label, a schedule or a word annotation; covering [0, D] with
        zero gaps does not make a plan a measurement;
      * ``MISSING_EXPORT_DIGEST`` / ``MALFORMED_DIGEST`` -- no sha256 digest;
      * ``WRONG_AUDIO`` -- the digest (or the actual duration) does not match the
        take being advanced;
      * ``MISSING_ACTUAL_DURATION`` -- no positive measured physical duration;
      * ``DUPLICATE_RUNTIME`` -- the partition does not tile ``[0, duration]``
        exactly (reuses ``check_timeline_partition``; a doubled timeline is
        refused), or the recorded segment seconds exceed the measured runtime;
      * ``MISSING_DETECTOR_ARTIFACT`` / ``MISSING_ALIGNMENT_ARTIFACT`` -- a
        hand-set ``source="measured"`` label with nothing behind it;
      * ``UNTRUSTED_CONTEXT`` -- no trusted measurement context.

    ``export_digest`` (or a ``binding`` carrying one) is the take's own digest;
    ``duration_s`` is the take's measured duration when the caller has it.
    """
    if not isinstance(evidence, dict):
        return ["MALFORMED_EVIDENCE: the evidence record is %s, not a mapping"
                % type(evidence).__name__]
    reasons = []
    src = _norm_src(evidence.get("source"))
    segs = evidence.get("segments") or []
    seg_srcs = [_norm_src(s.get("source")) for s in segs if isinstance(s, dict)]
    if src in _PLANNED_SOURCES or any(s in _PLANNED_SOURCES for s in seg_srcs):
        reasons.append("PLANNED_TIMESTAMPS: the evidence is stamped %r; a plan "
                       "stretched to fill the runtime with zero gaps is still a plan, "
                       "never a returned-audio measurement"
                       % (evidence.get("source")
                          or sorted(set(seg_srcs)) or "planned"))

    want = export_digest
    if want is None and isinstance(binding, dict):
        want = binding.get("export_digest")
    dig = evidence.get("export_digest")
    if not isinstance(dig, str) or not _DIGEST_RE.fullmatch(dig.strip().lower()):
        reasons.append("MISSING_EXPORT_DIGEST: the evidence carries no sha256 "
                       "export_digest for the audio it was measured from")
    elif isinstance(want, str) and want.strip() and             dig.strip().lower() != want.strip().lower():
        reasons.append("WRONG_AUDIO: the evidence was measured against export %r "
                       "but the take being advanced is %r"
                       % (dig.strip().lower(), want.strip().lower()))

    D = _finite(evidence.get("actual_duration_s", evidence.get("duration_s")))
    if D is None or D <= 0:
        reasons.append("MISSING_ACTUAL_DURATION: the evidence carries no positive "
                       "measured duration of the returned audio")
    else:
        if duration_s is not None:
            Dm = _finite(duration_s)
            if Dm is not None and Dm > 0 and abs(D - Dm) > _ALIGN_TOL:
                reasons.append("WRONG_AUDIO: the evidence duration %.6f s does not "
                               "match the take's measured duration %.6f s" % (D, Dm))
        if segs:
            part = check_timeline_partition(segs, D)
            if part.get("verdict") != "PASS":
                reasons.append("DUPLICATE_RUNTIME: %s" % (part.get("detail"),))
        else:
            total = _finite(evidence.get("segment_seconds_total"))
            if total is not None and total > D + _ALIGN_TOL:
                reasons.append("DUPLICATE_RUNTIME: the recorded segment seconds "
                               "%.6f exceed the measured runtime %.6f s"
                               % (total, D))

    det = _norm_src(evidence.get("detector"))
    detv = _norm_src(evidence.get("detector_version"))
    if not det or not detv:
        reasons.append("MISSING_DETECTOR_ARTIFACT: the evidence names no detector "
                       "and detector_version; a hand-set source=%r label is not an "
                       "artifact" % evidence.get("source"))
    align = evidence.get("alignment")
    stem = evidence.get("stem_id")
    if not (isinstance(align, dict) and align) and             not (isinstance(stem, str) and stem.strip()):
        reasons.append("MISSING_ALIGNMENT_ARTIFACT: the evidence carries neither an "
                       "alignment record nor a stem id")

    ctx = evidence.get("trusted_context")
    if not isinstance(ctx, dict) or not ctx:
        reasons.append("UNTRUSTED_CONTEXT: the evidence carries no trusted "
                       "measurement context")
    else:
        if _norm_src(ctx.get("source")) in _UNTRUSTED_CONTEXTS:
            reasons.append("UNTRUSTED_CONTEXT: the evidence's context source is %r "
                           "-- a hand-set label is not a trusted context"
                           % (ctx.get("source"),))
        missing = [k for k in _CONTEXT_KEYS if not ctx.get(k)]
        if missing:
            reasons.append("UNTRUSTED_CONTEXT: the context is missing %s"
                           % ", ".join(missing))
    return reasons


def check_measured_evidence(evidence, *, binding=None, export_digest=None,
                            duration_s=None):
    """WW-24: the receipt for one evidence record. PASS only for a record that
    ``measured_evidence_reasons`` admits. Carries zero purchases -- nothing
    here can spend -- and measures no audio, so it is not an audio gate."""
    reasons = measured_evidence_reasons(evidence, binding=binding,
                                        export_digest=export_digest,
                                        duration_s=duration_s)
    ok = not reasons
    return {"tool": TOOL_NAME, "schema": PROVENANCE_SCHEMA,
            "verdict": "PASS" if ok else "FAIL",
            "reason_code": reasons[0].split(":")[0] if reasons else "MEASURED_EVIDENCE_OK",
            "reasons": reasons, "blocked": bool(reasons), "purchases": 0,
            "measures_no_audio": True,
            "detail": "; ".join(reasons) if reasons
            else "the evidence is a measured returned-audio record"}


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
