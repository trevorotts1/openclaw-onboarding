#!/usr/bin/env python3
"""
synthesize_full_speech.py — FULL-LENGTH presenter-audio synthesis for the
Presentations department (audio-demonstration-specialist, SOP 9.2 / 9.3).

WHY THIS EXISTS
---------------
The original Corey run synthesized only a 7-section "KEY BEATS" sizzle demo
(~4 min) instead of the whole 62-slide speech (~25.6 min). There was no
committed script that walked the ENTIRE speech, and no gate that caught the
audio being far shorter than the written script. This script fixes both:

  1. Splits the ENTIRE speech into Fish-Audio-safe chunks (sentence/paragraph
     boundaries, each <= --chunk-chars UTF-8-safe characters).
  2. Synthesizes EACH chunk via Fish Audio /v1/tts (same key + voice + model).
  3. Concatenates all chunks with ffmpeg into ONE mp3 and loudness-normalizes.
  4. DURATION SANITY GATE (hard, FAIL LOUD): the rendered audio duration MUST
     be >= --min-ratio (default 0.80) of the expected length computed from the
     spoken word count at --wpm (default 140). If the audio is far short of the
     speech, the script EXITS NON-ZERO and does NOT overwrite the deliverable.

Fish Audio facts (per 30-fish-audio-api-reference/references/fish-audio-api-reference.md):
  - POST https://api.fish.audio/v1/tts , Bearer auth, header model: s2-pro
  - chunk_length param max 300; we additionally pre-chunk the text ourselves and
    send each chunk as its own request so a single oversized request can never
    silently truncate the talk.
  - format mp3, mp3_bitrate 192, normalize true (set false only for tag fidelity).

USAGE
-----
  FISH_AUDIO_API_KEY=... FISH_AUDIO_VOICE_ID=... \
  python3 synthesize_full_speech.py \
      --speech /path/PRESENTER-SPEECH.md \
      --out    /path/PRESENTER-AUDIO.mp3 \
      [--voice-id <reference_id>] [--api-key <key>] \
      [--model s2-pro] [--bitrate 192] [--wpm 140] [--min-ratio 0.80] \
      [--chunk-chars 280] [--workdir <dir>]

The speech is cleaned the same way the word-count gate expects: markdown
headers (## Slide N), the how-to blockquote, horizontal rules, and bold-only
label lines are NOT spoken; everything else is.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error


# ----------------------------------------------------------------------------
# Speech cleaning  — keep ONLY what a presenter actually says aloud.
# Must match the word-count gate exactly so the gate is honest.
# ----------------------------------------------------------------------------
def extract_spoken(md_text: str) -> str:
    lines = md_text.splitlines()
    # Front-matter (title block, byline, how-to) lives before the first
    # slide/section heading and is NOT spoken. Drop everything up to the first
    # "## " (or "# ") heading that introduces actual slide content.
    start = 0
    for i, line in enumerate(lines):
        # First "## " (or deeper) heading begins the spoken slide content.
        if re.match(r"^#{2,6}\s", line):
            start = i
            break
    spoken = []
    for line in lines[start:]:
        s = line.strip()
        if not s:
            spoken.append("")
            continue
        if s.startswith("#"):              # slide headings / titles — not spoken
            continue
        if s.startswith(">"):              # how-to blockquote — not spoken
            continue
        if s.startswith("---"):            # horizontal rule
            continue
        if re.match(r"^\*\*.*\*\*$", s):   # bold-only label lines
            continue
        if re.match(r"^\*[^*].*\*$", s):   # italic-only stage directions (*...*)
            continue
        # Strip inline markdown emphasis so the engine never voices asterisks.
        s = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", s)
        spoken.append(s)
    text = "\n".join(spoken)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def word_count(text: str) -> int:
    return len(text.split())


# ----------------------------------------------------------------------------
# Chunking — split into <= chunk_chars pieces on sentence/paragraph boundaries.
# Never splits mid-sentence unless a single sentence exceeds the limit (then it
# splits on the nearest space). Every word of the speech ends up in some chunk.
# ----------------------------------------------------------------------------
def chunk_text(text: str, chunk_chars: int) -> list[str]:
    # Split into sentence-ish units, preserving terminal punctuation.
    raw = re.split(r"(?<=[.!?])\s+", text.replace("\n\n", " \n\n "))
    units = []
    for u in raw:
        u = u.strip()
        if u:
            units.append(u)

    chunks: list[str] = []
    cur = ""
    for u in units:
        if len(u) > chunk_chars:
            # flush current, then hard-split the long unit on spaces
            if cur:
                chunks.append(cur.strip())
                cur = ""
            words = u.split(" ")
            piece = ""
            for w in words:
                if len(piece) + len(w) + 1 > chunk_chars:
                    if piece:
                        chunks.append(piece.strip())
                    piece = w
                else:
                    piece = (piece + " " + w).strip()
            if piece:
                cur = piece
            continue
        if len(cur) + len(u) + 1 > chunk_chars:
            chunks.append(cur.strip())
            cur = u
        else:
            cur = (cur + " " + u).strip()
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if c.strip()]


# ----------------------------------------------------------------------------
# Fish Audio synthesis (one request per chunk).
# ----------------------------------------------------------------------------
FISH_URL = "https://api.fish.audio/v1/tts"


def synth_chunk(text, api_key, voice_id, model, bitrate, out_path,
                normalize=True, retries=3):
    body = {
        "text": text,
        "format": "mp3",
        "mp3_bitrate": bitrate,
        "chunk_length": 300,
        "normalize": normalize,
        "latency": "normal",
    }
    if voice_id:
        body["reference_id"] = voice_id
    data = json.dumps(body).encode("utf-8")

    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            FISH_URL, data=data, method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "model": model,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                audio = resp.read()
            if not audio or len(audio) < 256:
                raise RuntimeError(f"empty/tiny audio ({len(audio)} bytes)")
            with open(out_path, "wb") as f:
                f.write(audio)
            return len(audio)
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            last_err = f"HTTP {e.code}: {err_body}"
            # 429 / 5xx: back off and retry; 4xx (auth/validation): FAIL LOUD now
            if e.code == 429 or 500 <= e.code < 600:
                time.sleep(min(20, 5 * attempt))
                continue
            break
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            time.sleep(min(20, 5 * attempt))
    raise RuntimeError(f"Fish Audio synthesis failed for chunk -> {out_path}: {last_err}")


# ----------------------------------------------------------------------------
# ffmpeg helpers
# ----------------------------------------------------------------------------
def ffprobe_duration(path: str) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]).decode().strip()
    return float(out)


def ffmpeg_concat_normalize(chunk_paths, raw_out, final_out, bitrate):
    list_path = raw_out + ".concat.txt"
    with open(list_path, "w") as f:
        for p in chunk_paths:
            f.write(f"file '{p}'\n")
    # Concat (stream copy where possible; re-encode to be safe across chunks)
    subprocess.check_call([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k", raw_out,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Loudness-normalize to -16 LUFS (broadcast spoken-word standard)
    subprocess.check_call([
        "ffmpeg", "-y", "-i", raw_out,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k", final_out,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Full-length presenter-audio synthesis with duration gate.")
    ap.add_argument("--speech", required=True, help="Path to PRESENTER-SPEECH.md")
    ap.add_argument("--out", required=True, help="Path to write the final full-length mp3")
    ap.add_argument("--api-key", default=os.environ.get("FISH_AUDIO_API_KEY"))
    ap.add_argument("--voice-id", default=os.environ.get("FISH_AUDIO_VOICE_ID"))
    ap.add_argument("--model", default="s2-pro")
    ap.add_argument("--bitrate", type=int, default=192)
    ap.add_argument("--wpm", type=float, default=140.0, help="Expected speaking rate for the duration gate")
    ap.add_argument("--min-ratio", type=float, default=0.80,
                    help="Hard floor: audio_sec must be >= min_ratio * expected_sec")
    ap.add_argument("--chunk-chars", type=int, default=280, help="Max chars per Fish request (API cap is 300)")
    ap.add_argument("--workdir", default=None, help="Where to write per-chunk mp3s (default: <out_dir>/_audio_chunks_full)")
    ap.add_argument("--normalize", action="store_true", default=True)
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("FAIL: no Fish Audio API key (set FISH_AUDIO_API_KEY or --api-key).")

    # ffmpeg presence
    for tool in ("ffmpeg", "ffprobe"):
        if subprocess.call(["which", tool], stdout=subprocess.DEVNULL) != 0:
            sys.exit(f"FAIL: {tool} not found on PATH. Install via 'brew install ffmpeg'.")

    md = open(args.speech).read()
    spoken = extract_spoken(md)
    words = word_count(spoken)
    expected_sec = words / args.wpm * 60.0
    floor_sec = expected_sec * args.min_ratio
    print(f"[speech] spoken words = {words}")
    print(f"[speech] expected duration @ {args.wpm:.0f} wpm = {expected_sec:.1f}s ({expected_sec/60:.2f} min)")
    print(f"[gate]   minimum acceptable duration = {floor_sec:.1f}s ({floor_sec/60:.2f} min)  (>= {args.min_ratio:.0%})")

    chunks = chunk_text(spoken, args.chunk_chars)
    total_chars = sum(len(c) for c in chunks)
    print(f"[chunk]  {len(chunks)} chunks, {total_chars} total chars "
          f"(speech is {len(spoken)} chars — {total_chars/max(1,len(spoken)):.0%} coverage)")
    if total_chars < 0.95 * len(re.sub(r'\s+', ' ', spoken)):
        sys.exit("FAIL: chunking dropped text (coverage < 95%). Aborting before synthesis.")

    workdir = args.workdir or os.path.join(os.path.dirname(os.path.abspath(args.out)), "_audio_chunks_full")
    os.makedirs(workdir, exist_ok=True)

    chunk_paths = []
    for i, c in enumerate(chunks):
        cp = os.path.join(workdir, f"chunk_{i:03d}.mp3")
        n = synth_chunk(c, args.api_key, args.voice_id, args.model, args.bitrate, cp,
                        normalize=args.normalize)
        chunk_paths.append(cp)
        print(f"  [{i+1}/{len(chunks)}] {len(c)} chars -> {os.path.basename(cp)} ({n:,} bytes)", flush=True)

    raw_out = os.path.join(workdir, "concat_raw_full.mp3")
    final_out = args.out
    ffmpeg_concat_normalize(chunk_paths, raw_out, final_out, args.bitrate)

    audio_sec = ffprobe_duration(final_out)
    print(f"[render] final audio duration = {audio_sec:.1f}s ({audio_sec/60:.2f} min)")

    # ---- DURATION SANITY GATE (HARD, FAIL LOUD) ----
    if audio_sec < floor_sec:
        # Do not leave a short file masquerading as the deliverable.
        bad = final_out + ".FAILED-SHORT"
        try:
            os.replace(final_out, bad)
        except OSError:
            bad = final_out
        sys.exit(
            "FAIL (DURATION GATE): rendered audio is "
            f"{audio_sec:.1f}s but the speech needs >= {floor_sec:.1f}s "
            f"({audio_sec/expected_sec:.0%} of the {expected_sec:.1f}s expected). "
            f"The audio does NOT cover the full speech. Short file moved to {bad}. "
            "Re-run synthesis over the ENTIRE speech."
        )

    print(f"[PASS]   audio {audio_sec:.1f}s >= floor {floor_sec:.1f}s "
          f"({audio_sec/expected_sec:.0%} of expected). Full-length audio OK -> {final_out}")


if __name__ == "__main__":
    main()
