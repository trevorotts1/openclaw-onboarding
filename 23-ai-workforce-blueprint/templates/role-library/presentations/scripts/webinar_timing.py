#!/usr/bin/env python3
# =============================================================================
# webinar_timing.py — per-slide timing-track derivation for the Webinar Creator
# (P9.6-WEBINAR-VIDEO). Consumed by build_webinar_video.py and webinar_ffmpeg.py.
#
# WHY IT EXISTS
# -------------
# A webinar video must change slides in sync with what is being SPOKEN. The
# speech markdown's `SECONDS:` per-slide values are *planned* estimates
# (words/wpm); the REAL spoken durations live in the Fish-Audio chunk mp3s that
# `synthesize_full_speech.py` wrote to `<delivery>/_audio_chunks_full/`. This
# module derives a deterministic per-slide [audio_start, audio_end] mapping by
# re-running the EXACT same chunking code path over the same speech markdown
# (tagging each sentence unit with its slide number), then summing the real
# ffprobe durations of the chunks that flowed into each slide.
#
# Proven on the reference run (90 chunks -> 20 slides, sum = 1760.62s =
# the final PRESENTER-AUDIO.mp3 duration within 7ms).
#
# DETERMINISM
# -----------
# Given the same speech md + chunk directory + --chunk-chars, the mapping is
# identical every run. The chunker never splits a sentence mid-unit and only
# accumulates units, so a chunk that spans a slide boundary is exactly the one
# containing the boundary unit — the assignment is unambiguous.
#
# GUARD (fail-loud, then documented fallback)
# -------------------------------------------
#   1. Rechunk the speech with the same code path as the synthesis run.
#   2. Assert len(rechunked) == len(on-disk chunk mp3s).
#   3. If the counts disagree (e.g. --chunk-chars drift between the run that
#      made the audio and the installed chunker), FALL BACK to assigning chunks
#      to slides by the SECONDS:-proportional split (deterministic, documented),
#      and emit a warning on stderr. Never silently emit a wrong mapping.
#
# Usage:
#   python3 webinar_timing.py \
#       --speech     /path/PRESENTERS-SPEECH.md   (UNTAGGED — what was synthesized)
#       --chunks-dir /path/_audio_chunks_full/    (on-disk chunk mp3s)
#       --out        /path/webinar_timing.json
#   Optional:
#       --chunk-chars 280     # must match the synthesis run (default 280)
#       --audio      /path/PRESENTER-AUDIO.mp3    # optional: for verification only
#       --deck-slug  untitled
#       --verbose
#
# Timing-track JSON schema (written to --out):
#   {
#     "deck_slug":       "untitled",
#     "audio":           "working/delivery/PRESENTER-AUDIO.mp3",
#     "total_audio_sec": 1760.622,
#     "chunk_chars":     280,
#     "n_chunks":        90,
#     "n_slides":        20,
#     "fallback":        null,          # "seconds_proportional" when the guard failed
#     "timing": [
#       {"slide": 1, "chunks": [0,1,2,3],
#        "audio_start": 0.0, "audio_end": 86.334, "duration": 86.334},
#       ...
#     ]
#   }
#
# `duration` is what webinar_ffmpeg.py uses to size each slide's Ken Burns clip.
# Slides with NO speech default to a 3.0s hold (logged).
# =============================================================================

import argparse
import json
import os
import re
import subprocess
import sys

# The EXACT chunking code from synthesize_full_speech.py (imported, never
# reimplemented) so the re-derived mapping is byte-identical to the synthesis.
from synthesize_full_speech import extract_spoken, chunk_text  # noqa: E402

DEFAULT_CHUNK_CHARS = 280
EMPTY_SLIDE_HOLD_SEC = 3.0  # visual-only / section slides with no speech

_SECONDS_RE = re.compile(r"SECONDS:\s*(\d+)\s*s")


class TimingError(RuntimeError):
    """Raised when the timing track cannot be derived (never silently wrong)."""


def log(msg: str) -> None:
    print(f"[webinar_timing] {msg}", file=sys.stderr)


def ffprobe_duration(path: str) -> float:
    """Real duration of an audio file. Raised (not returned 0) on probe failure."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise TimingError(f"ffprobe not found on PATH — required to measure {path!r}")
    if out.returncode != 0:
        raise TimingError(f"ffprobe failed on {path!r}: {out.stderr[:300]}")
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise TimingError(f"could not parse duration from ffprobe for {path!r}: {out.stdout!r}")


def list_chunk_files(chunks_dir: str) -> list:
    """Ordered list of chunk mp3 paths (chunk_000.mp3 .. chunk_NNN.mp3)."""
    if not os.path.isdir(chunks_dir):
        raise TimingError(f"chunks dir not found: {chunks_dir!r}")
    names = [n for n in os.listdir(chunks_dir) if re.match(r"^chunk_\d{3}\.mp3$", n)]
    if not names:
        raise TimingError(f"no chunk_*.mp3 files found in {chunks_dir!r}")
    names.sort()
    paths = [os.path.join(chunks_dir, n) for n in names]
    # Sanity: indices must be contiguous 000..N-1 (a gap = a dropped chunk).
    indices = [int(n[6:9]) for n in names]
    if indices != list(range(len(indices))):
        raise TimingError(f"chunk indices not contiguous in {chunks_dir!r}: {indices}")
    return paths


def parse_slides(md_text: str) -> list:
    """Split the speech markdown into [(slide_no, spoken_text), ...].

    Mirrors synthesize_full_speech.extract_spoken() per-slide: drops front
    matter, headings, how-to blockquotes, horizontal rules, and bold/italic-only
    label lines; strips inline emphasis. Slide number comes from the `## Slide N`
    header.
    """
    lines = md_text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if re.match(r"^#{2,6}\s", line):
            start = i
            break
    slides = []
    current = []
    current_no = None
    for line in lines[start:]:
        s = line.strip()
        m = re.match(r"^##+ \s*Slide (\d+)\b", s)
        if m:
            if current_no is not None:
                slides.append((current_no, "\n".join(current)))
            current_no = int(m.group(1))
            current = []
            continue
        if not s:
            current.append("")
            continue
        if s.startswith("#"):
            continue
        if s.startswith(">"):
            continue
        if s.startswith("---"):
            continue
        if re.match(r"^\*\*.*\*\*$", s):   # bold-only label lines
            continue
        if re.match(r"^\*[^*].*\*$", s):   # italic-only stage directions
            continue
        s = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", s)
        current.append(s)
    if current_no is not None:
        slides.append((current_no, "\n".join(current)))
    if not slides:
        raise TimingError("could not find any `## Slide N` headers in the speech")
    return slides


def chunk_to_slide(md_text: str, chunk_chars: int) -> list:
    """Return [(chunk_index, slide_no, chunk_text), ...].

    Re-runs the EXACT chunk_text() accumulation over per-slide sentence units,
    tagging each unit with its slide number. A chunk's slide is the slide of the
    LAST unit that flowed into it (the chunker never splits a unit mid-sentence).
    """
    slides = parse_slides(md_text)
    # Sentence-unit split exactly as chunk_text() does, tagged per slide.
    tagged_units = []
    for slide_no, txt in slides:
        raw = re.split(r"(?<=[.!?])\s+", txt.replace("\n\n", " \n\n "))
        for u in raw:
            u = u.strip()
            if u:
                tagged_units.append((slide_no, u))

    chunks = []  # (slide_no, text)
    cur = ""
    cur_slide = None
    for slide_no, u in tagged_units:
        if len(u) > chunk_chars:
            if cur:
                chunks.append((cur_slide, cur))
                cur = ""
                cur_slide = None
            words = u.split(" ")
            piece = ""
            for w in words:
                if len(piece) + len(w) + 1 > chunk_chars:
                    if piece:
                        chunks.append((slide_no, piece.strip()))
                    piece = w
                else:
                    piece = (piece + " " + w).strip()
            if piece:
                cur = piece
                cur_slide = slide_no
            continue
        if len(cur) + len(u) + 1 > chunk_chars:
            chunks.append((cur_slide, cur))
            cur = u
            cur_slide = slide_no
        else:
            cur = (cur + " " + u).strip()
            cur_slide = slide_no
    if cur.strip():
        chunks.append((cur_slide, cur.strip()))
    chunks = [(n, c) for n, c in chunks if c.strip()]

    # Verify the rechunked text is identical to the flat extract_spoken+chunk_text
    # path — if not, our per-slide tagging broke the accumulation (fail loud).
    flat = chunk_text(extract_spoken(md_text), chunk_chars)
    flat = [c for c in flat if c.strip()]
    if len(flat) != len(chunks):
        raise TimingError(
            f"per-slide rechunk produced {len(chunks)} chunks but flat rechunk produced "
            f"{len(flat)} — accumulation mismatch. Refusing to emit a wrong mapping."
        )
    for i, ((_, c), fc) in enumerate(zip(chunks, flat)):
        if c != fc:
            raise TimingError(f"chunk {i} text differs between per-slide and flat rechunk.")
    return [(i, n, c) for i, (n, c) in enumerate(chunks)]


def seconds_proportional_fallback(speech_md: str, chunk_durations: list,
                                  n_slides: int) -> list:
    """Documented fallback when the rechunk-count guard fails.

    Assign the on-disk chunk durations to slides in proportion to each slide's
    `SECONDS:` metadata (a load-bearing, verified contract in the pipeline —
    parsed by build_teleprompter.py too). Deterministic and honest.
    """
    lines = speech_md.splitlines()
    slide_seconds = {}
    current = None
    for line in lines:
        m = re.match(r"^##+ \s*Slide (\d+)\b", line.strip())
        if m:
            current = int(m.group(1))
            continue
        if current is not None:
            sm = _SECONDS_RE.search(line)
            if sm:
                slide_seconds[current] = float(sm.group(1))
                current = None
    if len(slide_seconds) != n_slides:
        raise TimingError(
            f"SECONDS:-proportional fallback needs {n_slides} SECONDS entries, found "
            f"{len(slide_seconds)}. Cannot derive a timing track."
        )
    total_planned = sum(slide_seconds.values())
    total_real = sum(chunk_durations)
    per_slide = []
    cursor = 0.0
    for s in range(1, n_slides + 1):
        frac = slide_seconds.get(s, 0.0) / max(1e-9, total_planned)
        dur = frac * total_real
        per_slide.append({"slide": s, "duration": dur,
                          "audio_start": cursor, "audio_end": cursor + dur,
                          "chunks": None, "fallback_proportional": True})
        cursor += dur
    return per_slide


def derive_timing(speech_md_path: str, chunks_dir: str, chunk_chars: int = DEFAULT_CHUNK_CHARS,
                  audio_path: str = None, deck_slug: str = "untitled", verbose: bool = False):
    """Derive the per-slide timing track from the speech + real chunk durations.

    Returns the webinar_timing.json dict (see module docstring for schema).
    Raises TimingError on any undecidable condition — never silently wrong.
    """
    if not os.path.isfile(speech_md_path):
        raise TimingError(f"speech markdown not found: {speech_md_path!r}")
    md_text = open(speech_md_path, "r", encoding="utf-8").read()
    chunk_paths = list_chunk_files(chunks_dir)
    n_disk = len(chunk_paths)

    # Real durations of every on-disk chunk (the ground truth for timing).
    chunk_durations = [ffprobe_duration(p) for p in chunk_paths]

    rechunked = chunk_to_slide(md_text, chunk_chars)
    n_rechunked = len(rechunked)
    total_audio = sum(chunk_durations)
    if verbose:
        log(f"on-disk chunks={n_disk} rechunked={n_rechunked} total_audio={total_audio:.3f}s")

    timing_entries = []
    fallback = None
    if n_rechunked == n_disk:
        # Primary path: chunk index -> slide, durations summed per slide.
        slide_chunks = {}
        for idx, slide_no, _ in rechunked:
            slide_chunks.setdefault(slide_no, []).append(idx)
        n_slides = max(slide_chunks) if slide_chunks else 0
        cursor = 0.0
        for s in range(1, n_slides + 1):
            idxs = slide_chunks.get(s, [])
            dur = sum(chunk_durations[i] for i in idxs) if idxs else EMPTY_SLIDE_HOLD_SEC
            if not idxs:
                log(f"slide {s}: no speech chunks — default {EMPTY_SLIDE_HOLD_SEC:.1f}s hold")
            timing_entries.append({
                "slide": s,
                "chunks": idxs,
                "audio_start": round(cursor, 3),
                "audio_end": round(cursor + dur, 3),
                "duration": round(dur, 3),
            })
            cursor += dur
    else:
        # Guard failed -> documented proportional fallback.
        log(f"WARNING: rechunk count {n_rechunked} != on-disk chunk count {n_disk}; "
            f"falling back to SECONDS:-proportional split")
        # F45 (SMOKE-1, 2026-09-01): the fallback hardcoded 20 slides (the reference
        # deck). A 12-slide deck carries 12 SECONDS: entries, so the fallback could
        # NEVER derive a timing track for any small deck — P9.6 was structurally
        # impossible below 20 slides. Derive the slide count from the speech's own
        ## Slide N headers (same parser the fallback itself uses), floor 1.
        # FIX 103 (MASTER Part 8): no 20-slide literal remains — when the speech
        # carries no Slide headers the count is genuinely undeterminable, and the
        # fallback raises TimingError (fail-loud) instead of guessing the reference
        # deck's size.
        import re as _re
        _heads = {int(m.group(1)) for m in _re.finditer(r"^##+ \s*Slide (\d+)\b", md_text, _re.M)}
        if not _heads:
            raise TimingError(
                "SECONDS:-proportional fallback needs Slide headers to size the "
                "deck: the speech carries no '## Slide N' headings, so the slide "
                "count is undeterminable (FIX 103: never guess a reference-deck "
                "constant). Re-derive the rechunk path or fix the speech markdown."
            )
        n_slides = max(_heads)
        timing_entries = seconds_proportional_fallback(md_text, chunk_durations, n_slides)
        fallback = "seconds_proportional"

    result = {
        "deck_slug": deck_slug,
        "audio": audio_path or "working/delivery/PRESENTER-AUDIO.mp3",
        "total_audio_sec": round(total_audio, 3),
        "chunk_chars": chunk_chars,
        "n_chunks": n_disk,
        "n_slides": len(timing_entries),
        "fallback": fallback,
        "timing": timing_entries,
    }
    return result


def verify_timing(result: dict, audio_path: str) -> str:
    """Best-effort cross-check: timing total vs the real audio file duration.

    Returns a human-readable verdict string; never raises (verification only).
    """
    total = sum(t["duration"] for t in result["timing"])
    if not audio_path or not os.path.isfile(audio_path):
        return f"timing total = {total:.3f}s (no audio file given for cross-check)"
    try:
        audio_dur = ffprobe_duration(audio_path)
    except TimingError as exc:
        return f"timing total = {total:.3f}s; audio cross-check failed: {exc}"
    diff = abs(total - audio_dur)
    status = "PASS" if diff < 1.0 else "DRIFT"
    return (f"timing total = {total:.3f}s vs audio {audio_dur:.3f}s "
            f"(diff {diff:.3f}s) -> {status}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Derive per-slide timing track (webinar_timing.json) from speech + Fish chunks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--speech", required=True, help="PRESENTERS-SPEECH.md (UNTAGGED)")
    ap.add_argument("--chunks-dir", required=True, help="dir of chunk_*.mp3 (the synthesis output)")
    ap.add_argument("--out", required=True, help="output webinar_timing.json path")
    ap.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    ap.add_argument("--audio", default=None, help="optional final mp3 to cross-check total")
    ap.add_argument("--deck-slug", default="untitled")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    try:
        result = derive_timing(args.speech, args.chunks_dir, args.chunk_chars,
                               args.audio, args.deck_slug, args.verbose)
        verdict = verify_timing(result, args.audio)
        log(verdict)
        out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
        os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        log(f"wrote {args.out} ({len(result['timing'])} slides)")
        print(verdict)
        return 0
    except (TimingError, OSError) as exc:
        print(f"webinar_timing ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
