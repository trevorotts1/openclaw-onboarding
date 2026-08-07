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

EXPRESSIVE AUDIO (GAUNTLET LOOP 2, Feature A) — why this is no longer flat
-------------------------------------------------------------------------
Fish Audio S2 / S2.1-Pro expressiveness is driven by INLINE [bracket] reader
tags embedded in the text (e.g. `[confident]` `[pause]` `[whispering]`) — there
is NO SSML / emotion request field. The department already produces those tags
in `speech_fish_tag.py` -> `PRESENTERS-SPEECH-FISH-TAGGED.md`, but the executor
fed the UNTAGGED `PRESENTERS-SPEECH.md` to the API, so the tags never reached
the model and every read came out flat. This script now:

  - Synthesizes the **FISH-TAGGED** speech (`--tagged-speech`) when provided,
    so `[bracket]` emotion / reader tags actually reach the API.
  - Sends the documented expressiveness knobs the API supports:
      temperature          0.9 (higher = more expressive; default 0.7)
      top_p                0.8 (nucleus-sampling diversity)
      repetition_penalty   1.2 (suppress repetitive audio patterns)
      prosody              {speed, volume, normalize_loudness}
    (Fish OpenAPI: https://api.fish.audio/openapi.json — verified field names.)
  - Splices **measured** silence at pause markers (see PAUSES below) so the
    1-5 s dramatic pauses are EXACT, not whatever the model decides.

PAUSES — exact 1-5 s dramatic silence
-------------------------------------
The Fish API pause tags (`[pause]`, `[long pause]`, `[long-break]`, `[break]`,
`[short pause]`) have NO documented duration (docs only say "brief"/"extended").
To get deterministic 1-5 s silences we do NOT rely on the model's guess: pause
markers are stripped from the text sent to the API and replaced with a measured
silent mp3 (ffmpeg anullsrc) spliced at the exact position in the concat.
Defaults (override with --pause-short / --pause / --pause-long):
  [short pause]                    -> 0.8 s
  [pause] / [break] / [PAUSE]      -> 1.2 s
  [BREATHE]                        -> 1.2 s (breath cue -> beat)
  [long pause] / [long-break]      -> 2.5 s
  (PAUSE N seconds)                -> N seconds (parsed)
Director cues `(OWNER: ...)` are dropped entirely (never spoken aloud).

USAGE
-----
  FISH_AUDIO_API_KEY=... FISH_AUDIO_VOICE_ID=... \
  python3 synthesize_full_speech.py \
      --speech        /path/PRESENTERS-SPEECH.md \
      --tagged-speech /path/PRESENTERS-SPEECH-FISH-TAGGED.md \
      --out           /path/PRESENTER-AUDIO.mp3 \
      [--voice-id <reference_id>] [--api-key <key>] \
      [--model s2.1-pro] [--bitrate 192] [--wpm 140] [--min-ratio 0.80] \
      [--chunk-chars 280] [--workdir <dir>] \
      [--temperature 0.9] [--top-p 0.8] [--repetition-penalty 1.2] \
      [--prosody-speed 1.0] [--prosody-volume 0] \
      [--pause-short 0.8] [--pause 1.2] [--pause-long 2.5]

The word-count / duration gate is computed from the UNTAGGED `--speech` (bracket
tags are not spoken words). Synthesis chunks come from `--tagged-speech` when
given, else fall back to `--speech`.

The speech is cleaned the same way the word-count gate expects: markdown
headers (## Slide N), the how-to blockquote, horizontal rules, and bold-only
label lines are NOT spoken; everything else is. `[bracket]` tags are preserved;
director cues (`[PAUSE]`/`[BREATHE]`/`(PAUSE N seconds)`/`(OWNER: ...)`) are
converted to measured silence or dropped rather than spoken.
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


def strip_cues(text: str) -> str:
    """Remove director/pause cues for WORD COUNTING only — the duration gate must
    count real spoken words, not `[PAUSE]`/`(OWNER: ...)` tokens. Pause cues are
    later re-inserted as measured silence by segment_pauses(); this helper exists
    so a cue never inflates the expected-duration estimate."""
    text = _OWNER_CUE_RE.sub(" ", text)
    text = _PAUSE_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


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
# Pause markers -> measured silence (seconds).
#
# Fish S2/S2.1-Pro pause tags have NO documented duration. To get deterministic
# 1-5 s dramatic pauses we splice a measured silent mp3 at the ffmpeg stage
# instead of trusting the model's "brief"/"extended" guess. The tag is stripped
# from the text sent to the API so it is never voiced as a word and never
# double-pauses. Defaults are overridable via CLI.
# ----------------------------------------------------------------------------
DEFAULT_PAUSE_SECONDS = {
    "short pause": 0.8,       # [short pause]  — quick beat
    "pause": 1.2,             # [pause] / [break] / [PAUSE]  — beat / let it land
    "breathe": 1.2,           # [BREATHE]  — breath cue -> beat
    "long pause": 2.5,        # [long pause] / [long-break]  — big silence
}

# Regex that matches a pause marker ANYWHERE in the text (standalone line or
# inline mid-sentence). Group(1) = numeric seconds for `(PAUSE N seconds)`.
_PAUSE_TAG_RE = re.compile(
    r"\[\s*short\s*pause\s*\]"                       # [short pause]
    r"|\[\s*long\s*[- ]?pause\s*\]"                  # [long pause] / [long-pause]
    r"|\[\s*long\s*[- ]?break\s*\]"                  # [long-break] / [long break]
    r"|\[\s*(?:PAUSE|BREATHE|BREAK)\s*\]"            # [pause] [PAUSE] [breathe] [break]
    r"|\(\s*PAUSE\s+(\d+(?:\.\d+)?)\s*seconds?\s*\)"  # (PAUSE 2 seconds) -> exact
    ,
    re.IGNORECASE,
)

# Regex that matches a (OWNER: ...) director cue INLINE so it is dropped, never
# voiced as text.
_OWNER_CUE_RE = re.compile(r"\(\s*OWNER\s*:.*?\)", re.IGNORECASE | re.DOTALL)


def segment_pauses(text: str, pause_seconds: dict) -> list:
    """Split *text* into an ordered list of ("speech", str) and ("silence", float)
    items.

    Pause markers (standalone or inline) are removed from the speech text and
    turned into measured-silence items; `(OWNER: ...)` director cues are dropped
    entirely. Adjacent silence items are merged so `[pause][long pause]` becomes
    one 3.7 s gap instead of two separate files.
    """
    # Drop (OWNER: ...) director cues before anything else — they are notes, not
    # spoken words, and must never reach the API.
    text = _OWNER_CUE_RE.sub(" ", text)

    items: list = []           # ("speech"|"silence", payload)
    cursor = 0
    for m in _PAUSE_TAG_RE.finditer(text):
        before = text[cursor:m.start()]
        if before.strip():
            items.append(("speech", before.strip()))
        tag = m.group(0)
        if m.group(1) is not None:
            seconds = float(m.group(1))
        else:
            low = tag.lower().strip()
            if "short pause" in low:
                seconds = pause_seconds["short pause"]
            elif "long" in low:
                seconds = pause_seconds["long pause"]
            elif "breathe" in low:
                seconds = pause_seconds["breathe"]
            else:
                seconds = pause_seconds["pause"]
        items.append(("silence", seconds))
        cursor = m.end()
    tail = text[cursor:]
    if tail.strip():
        items.append(("speech", tail.strip()))

    # Merge adjacent silence items.
    merged: list = []
    for kind, payload in items:
        if kind == "silence" and merged and merged[-1][0] == "silence":
            merged[-1] = ("silence", merged[-1][1] + payload)
        else:
            merged.append((kind, payload))
    return merged


def make_silence_mp3(seconds: float, out_path: str, bitrate: int,
                     sample_rate: int = 44100) -> str:
    """Generate a *measured* silent MP3 of exactly *seconds* via ffmpeg anullsrc.
    Deterministic and reliable for the 1-5 s dramatic-pause requirement."""
    subprocess.check_call([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
        "-t", f"{seconds:.3f}",
        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
        out_path,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_path


# ----------------------------------------------------------------------------
# Fish Audio synthesis (one request per chunk).
# ----------------------------------------------------------------------------
FISH_URL = "https://api.fish.audio/v1/tts"

# The authoritative Fish Audio model for CLIENT production (FIX-9 / T-10 model
# truth): S2.1 Pro (paid), per 30-fish-audio-api-reference/references/
# fish-audio-api-reference.md and SKILL.md. The interim `s2-pro` id was superseded
# by S2.1 Pro; `s2.1-pro-free` is operator-internal ONLY (no SLA, may train on
# submitted inputs, expires end of July 2026) and is FORBIDDEN for client work.
# This is the single source for the argparse default.
MAIN_MODEL_DEFAULT = "s2.1-pro"


def synth_chunk(text, api_key, voice_id, model, bitrate, out_path,
                normalize=True, retries=3,
                temperature=0.9, top_p=0.8, repetition_penalty=1.2,
                prosody_speed=1.0, prosody_volume=0.0,
                prosody_normalize_loudness=True):
    """Synthesize *text* via Fish Audio /v1/tts.

    EXPRESSIVE REQUEST (GAUNTLET LOOP 2): sends the Fish API's documented
    expressiveness knobs — temperature (0-1, "controls expressiveness", default
    0.7; we raise to 0.9), top_p (0-1, default 0.7 -> 0.8), repetition_penalty
    (>1.0 suppresses repeating audio patterns, default 1.2), and prosody
    {speed 0.5-2.0, volume dB, normalize_loudness}. Field names verified against
    https://api.fish.audio/openapi.json (TTSRequest schema).
    """
    body = {
        "text": text,
        "format": "mp3",
        "mp3_bitrate": bitrate,
        "chunk_length": 300,
        "normalize": normalize,
        "latency": "normal",
        "temperature": temperature,
        "top_p": top_p,
        "repetition_penalty": repetition_penalty,
        "prosody": {
            "speed": prosody_speed,
            "volume": prosody_volume,
            "normalize_loudness": prosody_normalize_loudness,
        },
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


# ----------------------------------------------------------------------------
# MP3 VALIDITY PROBE — FIX-9 / T-10 QC gate. A deliverable that "exists" but is
# not decodable audio is a defect, not an MP3. This proves the file is a REAL MP3:
#   (1) size > 10 KB floor (matches the FIX-9 QC row: "valid MP3 > 10KB");
#   (2) an ID3v2 header (tag 'ID3' at offset 0) — the standard MP3 metadata frame;
#   (3) at least one valid MPEG audio frame header (11-bit frame-sync 0xFFE0)
#       parsed after the ID3 tag (or at offset 0 for tag-less MP3s).
# Returns '' on PASS, or a non-empty reason string on FAIL (fail-loud).
# ----------------------------------------------------------------------------
MP3_MIN_BYTES = 10_000  # 10 KB floor from the FIX-9 QC row


def _is_mp3_frame_sync(b: bytes) -> bool:
    """True iff the two bytes carry a valid MPEG audio frame sync (11-bit 1s)."""
    return (b[0] == 0xFF) and ((b[1] & 0xE0) == 0xE0) and ((b[1] & 0x06) != 0x00)


def verify_mp3(path: str) -> str:
    """Probe an MP3 file for real audio content. Returns '' (PASS) or a reason
    string (FAIL). Never raises: any probe error is a FAIL, never an exception."""
    try:
        if not os.path.exists(path):
            return f"missing file: {path}"
        size = os.path.getsize(path)
        if size < MP3_MIN_BYTES:
            return f"too small: {size} bytes < {MP3_MIN_BYTES} floor"
        with open(path, "rb") as f:
            head = f.read(16)
        if not head:
            return "empty file"
        # ID3v2 header present? tag 'ID3' + major version + 4 syncsafe size bytes.
        offset = 0
        if head.startswith(b"ID3"):
            if len(head) < 10:
                return "truncated ID3v2 header"
            id3_size = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) \
                     | ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
            offset = 10 + id3_size
        # Read the frame header at (or after) the ID3 tag.
        with open(path, "rb") as f:
            f.seek(offset)
            frame = f.read(4)
        if len(frame) < 4:
            return f"no audio frame after ID3 (frame offset {offset})"
        if not _is_mp3_frame_sync(frame[:2]):
            return (f"no valid MPEG audio frame header at offset {offset} "
                    f"(bytes {frame[:2].hex()}); not decodable audio")
        return ""
    except Exception as exc:  # noqa: BLE001 — any probe error fails closed
        return f"probe error: {exc!r}"


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
    ap.add_argument("--speech", required=True, help="Path to PRESENTERS-SPEECH.md (UNTAGGED — used for the word-count / duration gate)")
    ap.add_argument("--tagged-speech", default=None,
                    help="Path to PRESENTERS-SPEECH-FISH-TAGGED.md. When given, THIS is the "
                         "text synthesized (so [bracket] reader tags reach the API). Falls "
                         "back to --speech if omitted.")
    ap.add_argument("--out", required=True, help="Path to write the final full-length mp3")
    ap.add_argument("--api-key", default=os.environ.get("FISH_AUDIO_API_KEY"))
    ap.add_argument("--voice-id", default=os.environ.get("FISH_AUDIO_VOICE_ID"))
    ap.add_argument("--model", default=MAIN_MODEL_DEFAULT,
                    help="Fish Audio model (HTTP model header). Current PAID production "
                         "model is s2.1-pro (per 30-fish-audio-api-reference); the interim "
                         "s2-pro id was superseded and is NOT a durable default for client "
                         "work. Never default to s2.1-pro-free (no SLA / data-retention / "
                         "client-prod prohibited).")
    ap.add_argument("--bitrate", type=int, default=192)
    ap.add_argument("--wpm", type=float, default=140.0, help="Expected speaking rate for the duration gate")
    ap.add_argument("--min-ratio", type=float, default=0.80,
                    help="Hard floor: audio_sec must be >= min_ratio * expected_sec")
    ap.add_argument("--chunk-chars", type=int, default=280, help="Max chars per Fish request (API cap is 300)")
    ap.add_argument("--workdir", default=None, help="Where to write per-chunk mp3s (default: <out_dir>/_audio_chunks_full)")
    ap.add_argument("--normalize", action="store_true", default=True)
    # ---- EXPRESSIVE AUDIO knobs (GAUNTLET LOOP 2) ----
    ap.add_argument("--temperature", type=float, default=0.9,
                    help="Fish API temperature (0-1). 'Controls expressiveness' — higher is "
                         "more varied. Default 0.9 (OpenAPI default is 0.7).")
    ap.add_argument("--top-p", type=float, default=0.8,
                    help="Fish API top_p (0-1). Nucleus-sampling diversity. Default 0.8.")
    ap.add_argument("--repetition-penalty", type=float, default=1.2,
                    help="Fish API repetition_penalty (>1.0 reduces repeating audio patterns). Default 1.2.")
    ap.add_argument("--prosody-speed", type=float, default=1.0,
                    help="prosody.speed (0.5-2.0). Global speaking-rate multiplier. Default 1.0.")
    ap.add_argument("--prosody-volume", type=float, default=0.0,
                    help="prosody.volume (dB, ~ -20..+20). Default 0.")
    ap.add_argument("--prosody-no-normalize-loudness", action="store_true",
                    help="Set prosody.normalize_loudness=false (S2 family only; default true).")
    # ---- measured silence defaults ----
    ap.add_argument("--pause-short", type=float, default=DEFAULT_PAUSE_SECONDS["short pause"],
                    help="Seconds for [short pause]")
    ap.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS["pause"],
                    help="Seconds for [pause]/[break]/[PAUSE]")
    ap.add_argument("--pause-long", type=float, default=DEFAULT_PAUSE_SECONDS["long pause"],
                    help="Seconds for [long pause]/[long-break]")
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("FAIL: no Fish Audio API key (set FISH_AUDIO_API_KEY or --api-key).")

    # ffmpeg presence
    for tool in ("ffmpeg", "ffprobe"):
        if subprocess.call(["which", tool], stdout=subprocess.DEVNULL) != 0:
            sys.exit(f"FAIL: {tool} not found on PATH. Install via 'brew install ffmpeg'.")

    # ---- duration gate input: UNTAGGED speech (tags are not spoken words) ----
    md = open(args.speech).read()
    spoken = extract_spoken(md)
    words = word_count(strip_cues(spoken))
    expected_sec = words / args.wpm * 60.0
    floor_sec = expected_sec * args.min_ratio
    print(f"[speech] spoken words (untagged gate) = {words}")
    print(f"[speech] expected duration @ {args.wpm:.0f} wpm = {expected_sec:.1f}s ({expected_sec/60:.2f} min)")
    print(f"[gate]   minimum acceptable duration = {floor_sec:.1f}s ({floor_sec/60:.2f} min)  (>= {args.min_ratio:.0%})")

    # ---- synthesis input: TAGGED speech (bracket reader tags must reach the API) ----
    synth_md_path = args.tagged_speech or args.speech
    synth_md = open(synth_md_path).read()
    synth_spoken = extract_spoken(synth_md)
    if args.tagged_speech and args.tagged_speech != args.speech:
        # Sanity: the tagged text must contain the untagged words. Strip brackets
        # from the tagged spoken text and assert word-for-word containment, else
        # the tagged file is corrupt and we must not ship flat/broken audio.
        import speech_fish_tag  # local import: same scripts dir
        if not speech_fish_tag.verify_strip_equals_source(synth_spoken, spoken):
            sys.exit("FAIL: --tagged-speech does not word-for-word match --speech after "
                     "stripping tags. Refuse to synthesize a corrupt tagged file. "
                     "Re-run speech_fish_tag.py and verify.")
        print(f"[tagged] synthesis input = {synth_md_path} "
              f"({len(synth_spoken)} chars, tags verified against untagged speech)")

    # ---- segment into speech + measured silence, then chunk the speech ----
    pause_seconds = {
        "short pause": args.pause_short,
        "pause": args.pause,
        "long pause": args.pause_long,
        "breathe": args.pause,  # breath cue -> beat
    }
    items = segment_pauses(synth_spoken, pause_seconds)

    n_speech = sum(1 for k, _ in items if k == "speech")
    n_silence = sum(1 for k, _ in items if k == "silence")
    total_silence = sum(p for k, p in items if k == "silence")
    print(f"[pause]  {n_silence} measured-silence insertions totalling {total_silence:.1f}s "
          f"({n_speech} speech segments)")

    # Build ordered chunks: speech segments chunked to --chunk-chars, silence
    # segments as exact silent mp3s. Order is preserved for the concat.
    workdir = args.workdir or os.path.join(os.path.dirname(os.path.abspath(args.out)), "_audio_chunks_full")
    os.makedirs(workdir, exist_ok=True)

    speech_segments = [p for k, p in items if k == "speech"]
    speech_chunks: list[str] = []
    for seg in speech_segments:
        speech_chunks.extend(chunk_text(seg, args.chunk_chars))

    total_chars = sum(len(c) for c in speech_chunks)
    synth_norm = re.sub(r"\s+", " ", strip_cues(synth_spoken))
    print(f"[chunk]  {len(speech_chunks)} speech chunks, {total_chars} total chars "
          f"({len(synth_norm)} cue-stripped chars — {total_chars/max(1,len(synth_norm)):.0%} coverage of tagged text)")
    if total_chars < 0.95 * len(synth_norm):
        sys.exit("FAIL: chunking dropped text (coverage < 95%). Aborting before synthesis.")

    # Assemble ordered render plan: interleave speech chunk paths and silence paths.
    render_items: list = []      # ("file", path) for concat
    speech_iter = iter(speech_chunks)
    chunk_index = 0
    for kind, payload in items:
        if kind == "silence":
            sp = os.path.join(workdir, f"silence_{chunk_index:03d}.mp3")
            make_silence_mp3(payload, sp, args.bitrate)
            _sp_reason = verify_mp3(sp)
            if _sp_reason:
                sys.exit(f"FAIL (MP3 PROBE): silence segment is not a valid MP3 ({_sp_reason}).")
            render_items.append(("file", sp))
            print(f"  [silence {len([r for r in render_items if r[1].startswith('silence_')]):02d}] "
                  f"{payload:.1f}s -> {os.path.basename(sp)}", flush=True)
        else:
            c = next(speech_iter)
            cp = os.path.join(workdir, f"chunk_{chunk_index:03d}.mp3")
            chunk_index += 1
            n = synth_chunk(c, args.api_key, args.voice_id, args.model, args.bitrate, cp,
                            normalize=args.normalize,
                            temperature=args.temperature, top_p=args.top_p,
                            repetition_penalty=args.repetition_penalty,
                            prosody_speed=args.prosody_speed,
                            prosody_volume=args.prosody_volume,
                            prosody_normalize_loudness=not args.prosody_no_normalize_loudness)
            # FIX-9 MP3 validity probe per chunk — a chunk that is not real audio
            # must fail BEFORE it can poison the concat.
            _mp3_reason = verify_mp3(cp)
            if _mp3_reason:
                sys.exit(f"FAIL (MP3 PROBE): chunk {chunk_index} is not a valid MP3 ({_mp3_reason}). "
                         f"Aborting before concat — a corrupt chunk must never reach the deliverable.")
            render_items.append(("file", cp))
            print(f"  [{chunk_index}/{len(speech_chunks)}] {len(c)} chars -> {os.path.basename(cp)} ({n:,} bytes)", flush=True)

    chunk_paths = [p for _, p in render_items]
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

    # ---- FIX-9 MP3 VALIDITY PROBE (HARD, FAIL LOUD) on the FINAL deliverable ----
    # The FIX-9 / T-10 QC gate: audio_mp3 must EXIST, be > 10 KB, and be a VALID,
    # decodable MP3 (parseable header/frame). Size alone is not proof.
    _final_mp3_reason = verify_mp3(final_out)
    if _final_mp3_reason:
        bad = final_out + ".FAILED-NOT-MP3"
        try:
            os.replace(final_out, bad)
        except OSError:
            bad = final_out
        sys.exit(
            "FAIL (MP3 PROBE): the final deliverable is not a valid MP3 "
            f"({_final_mp3_reason}). Moved to {bad}. A non-audio file must never "
            "ship as the presentation audio."
        )
    print(f"[PASS]   audio {audio_sec:.1f}s >= floor {floor_sec:.1f}s "
          f"({audio_sec/expected_sec:.0%} of expected); MP3 validity probe PASS "
          f"({os.path.getsize(final_out):,} bytes, valid MP3). "
          f"Full-length audio OK -> {final_out}")


if __name__ == "__main__":
    main()
