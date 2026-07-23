#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: transcript sync verification (U045)
# -----------------------------------------------------------------------------
# F45: the transcript/timestamps step generates an SRT but never verifies it
# syncs to the actual audio. A transcript for a DIFFERENT episode (zero
# timestamps in range) or a TRUNCATED one (last cue far short of the audio)
# matched nothing and still attached silently. This verifier closes that:
#
#   AC2  the last timestamp must fall within the audio duration (bounded by a
#        small tolerance for end-of-speech rounding);
#   AC3  at least one timestamp must match a spoken-word (non-silence) segment
#        when segment data is available;
#   AC4  a transcript with ZERO timestamps in range (wrong episode) is
#        rejected, never attached;
#   AC5  a truncated transcript (last cue far short of the audio duration) is
#        detected and rejected.
#
# The core is a PURE function (verify_srt_sync) so the pipeline and the unit
# tests drive it without ffmpeg. The CLI adds the optional audio-aware path:
# --audio FILE derives the duration via ffprobe and the spoken segments via
# `ffmpeg -af silencedetect`, so the full AC3 check runs in production while
# the tests stay hermetic.
#
# Usage:
#   python3 verify_transcript_sync.py --srt episode.srt --duration 1834.5
#   python3 verify_transcript_sync.py --srt episode.srt --audio episode.mp3
#
# Exit codes: 0 = verified, 1 = rejected (with the reason on stderr),
#             2 = usage / unreadable input.
# =============================================================================
"""SRT-vs-audio sync verification for the podcast transcript step (U045)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field

# A cue whose end lands this many seconds past the reported duration is still
# "within" it — end-of-speech rounding and encoder padding routinely add a
# second or two; a transcript from the WRONG episode is off by minutes.
DEFAULT_TOLERANCE_S = 2.0

# A transcript whose last cue ends before this fraction of the audio duration
# is truncated (AC5). Half the program is the floor: a genuine full-episode
# transcript runs to the end; a cut-off one stops mid-program.
DEFAULT_MIN_COVERAGE = 0.5

# ffmpeg silencedetect noise floor — speech sits well above -40 dB; this
# catches dead air, not quiet passages.
SILENCE_NOISE_DB = -40


@dataclass(frozen=True)
class Cue:
    """One SRT cue: timing in seconds + the spoken text."""
    index: int
    start: float
    end: float
    text: str


@dataclass
class VerifyResult:
    """The verdict + the facts it was derived from (machine- and human-readable)."""
    ok: bool
    reason: str
    cues: int = 0
    in_range: int = 0
    matched_spoken: int = 0
    last_cue_end: float = 0.0
    audio_duration: float = 0.0
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

_TS = r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
_CUE_RE = re.compile(
    rf"^\s*(\d+)\s*\n\s*{_TS}\s*-->\s*{_TS}\s*\n([\s\S]*?)(?=\n\s*\n|\Z)",
    re.MULTILINE,
)


def _hms_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    # Milliseconds are 1-3 digits in the wild ("00:00:01,5" == 500ms); pad right.
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse_srt(srt_text: str) -> list[Cue]:
    """Parse SRT into cues. Malformed blocks are skipped (never throws) — a
    half-written cue must not hide the rest of the transcript from the check."""
    cues: list[Cue] = []
    for m in _CUE_RE.finditer(srt_text or ""):
        idx = int(m.group(1))
        start = _hms_to_seconds(m.group(2), m.group(3), m.group(4), m.group(5))
        end = _hms_to_seconds(m.group(6), m.group(7), m.group(8), m.group(9))
        text = m.group(10).strip()
        cues.append(Cue(index=idx, start=start, end=end, text=text))
    return cues


# ---------------------------------------------------------------------------
# The verification (pure — no ffmpeg, no I/O)
# ---------------------------------------------------------------------------

def _overlaps(cue: Cue, seg_start: float, seg_end: float) -> bool:
    return cue.start < seg_end and seg_start < cue.end


def verify_srt_sync(
    srt_text: str,
    audio_duration_s: float,
    spoken_segments: list[tuple[float, float]] | None = None,
    *,
    tolerance_s: float = DEFAULT_TOLERANCE_S,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> VerifyResult:
    """Verify an SRT transcript syncs to the audio it claims to transcribe.

    audio_duration_s   the real audio length in seconds.
    spoken_segments    optional non-silence intervals [(start, end), ...]; when
                       given, AC3 is enforced strictly (a cue must overlap a
                       spoken segment). When None, the in-range cues themselves
                       are the speech evidence (the AC4 zero-match check still
                       rejects a wrong-episode transcript).

    Never throws on transcript content; a garbage SRT simply parses to zero
    cues and fails AC4.
    """
    cues = parse_srt(srt_text)
    base = dict(cues=len(cues), audio_duration=audio_duration_s)

    # AC4: a transcript with no cues at all can never be verified.
    if not cues:
        return VerifyResult(False, "no cues parsed from the SRT (empty or malformed transcript)", **base)

    last_cue_end = max(c.end for c in cues)
    base["last_cue_end"] = last_cue_end

    # AC4: every cue must actually fall inside this audio. A transcript from a
    # different episode has its timestamps somewhere else entirely — zero cues
    # in range means nothing matches, and nothing may attach.
    in_range = [c for c in cues if 0 <= c.start <= audio_duration_s + tolerance_s]
    base["in_range"] = len(in_range)
    if not in_range:
        return VerifyResult(
            False,
            f"zero timestamps fall within the {audio_duration_s:.1f}s audio "
            f"(first cue starts at {cues[0].start:.1f}s) — wrong episode?",
            **base,
        )

    # AC3: at least one timestamp must match a spoken-word (non-silence)
    # segment, when the caller supplies the silence map.
    if spoken_segments is not None:
        matched = [c for c in in_range
                   if any(_overlaps(c, s, e) for s, e in spoken_segments)]
        base["matched_spoken"] = len(matched)
        if not matched:
            return VerifyResult(
                False,
                "no timestamp overlaps a spoken-word (non-silence) segment — "
                "the transcript does not line up with the speech in this audio",
                **base,
            )

    # AC2: the last timestamp must fall within the audio duration (bounded by
    # the tolerance). Timestamps far beyond the audio mean the SRT belongs to
    # longer content than this file.
    if last_cue_end > audio_duration_s + tolerance_s:
        return VerifyResult(
            False,
            f"last timestamp {last_cue_end:.1f}s exceeds the {audio_duration_s:.1f}s "
            f"audio duration (beyond the {tolerance_s:.1f}s tolerance)",
            **base,
        )

    # AC5: a transcript that stops far short of the audio is truncated — the
    # tail of the episode would carry no captions.
    if audio_duration_s > 0 and last_cue_end < audio_duration_s * min_coverage:
        return VerifyResult(
            False,
            f"transcript appears truncated: last timestamp {last_cue_end:.1f}s covers "
            f"only {last_cue_end / audio_duration_s:.0%} of the {audio_duration_s:.1f}s audio",
            **base,
        )

    return VerifyResult(True, "transcript syncs to the audio", **base)


# ---------------------------------------------------------------------------
# Audio-aware helpers (CLI path only — ffprobe / silencedetect)
# ---------------------------------------------------------------------------

def probe_duration_s(audio_path: str) -> float:
    """ffprobe the audio length in seconds. Raises on failure (CLI maps to exit 2)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout.strip()
    return float(out)


def probe_spoken_segments(audio_path: str) -> list[tuple[float, float]]:
    """Derive non-silence intervals from `ffmpeg -af silencedetect`. The filter
    prints silence_start / silence_end pairs; the gaps between them (and the
    head/tail) are the spoken segments. Empty list == the whole file is silence."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", audio_path,
         "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d=0.5", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300,
    ).stderr
    silences: list[tuple[float, float]] = []
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start:\s*([0-9.]+)", out)]
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end:\s*([0-9.]+)", out)]
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else float("inf")
        silences.append((s, e))
    duration = probe_duration_s(audio_path)
    segments: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in silences:
        if s > cursor:
            segments.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        segments.append((cursor, duration))
    return segments


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Verify an SRT transcript syncs to its audio (U045).")
    p.add_argument("--srt", required=True, help="the SRT file to verify")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--duration", type=float, help="audio duration in seconds")
    src.add_argument("--audio", help="audio file (duration + spoken segments via ffmpeg)")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_S,
                   help=f"seconds past duration the last cue may land (default {DEFAULT_TOLERANCE_S})")
    p.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE,
                   help=f"minimum fraction of the duration the last cue must reach (default {DEFAULT_MIN_COVERAGE})")
    p.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = p.parse_args(argv)

    try:
        with open(args.srt, "r", encoding="utf-8", errors="replace") as fh:
            srt_text = fh.read()
    except OSError as exc:
        print(f"error: cannot read SRT: {exc}", file=sys.stderr)
        return 2

    spoken_segments = None
    if args.audio:
        try:
            duration = probe_duration_s(args.audio)
            spoken_segments = probe_spoken_segments(args.audio)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            print(f"error: cannot probe audio: {exc}", file=sys.stderr)
            return 2
    else:
        duration = args.duration

    result = verify_srt_sync(
        srt_text, duration, spoken_segments,
        tolerance_s=args.tolerance, min_coverage=args.min_coverage,
    )

    if args.json:
        print(json.dumps({
            "ok": result.ok, "reason": result.reason, "cues": result.cues,
            "in_range": result.in_range, "matched_spoken": result.matched_spoken,
            "last_cue_end": result.last_cue_end, "audio_duration": result.audio_duration,
        }))
    else:
        verdict = "VERIFIED" if result.ok else "REJECTED"
        print(f"{verdict}: {result.reason} "
              f"(cues={result.cues}, in_range={result.in_range}, "
              f"last_cue_end={result.last_cue_end:.1f}s, audio={result.audio_duration:.1f}s)")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
