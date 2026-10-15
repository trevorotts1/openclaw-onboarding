#!/usr/bin/env python3
"""
Skill 72 voiceover via Fish Audio TTS: narration production and measured
timings for the narrated production branch (INSTRUCTIONS.md stage 6).

WHAT THIS SCRIPT DOES
- Reads a job manifest and decides whether the job has narration at all.
  A silent job exits cleanly with a structured no-narration result BEFORE
  any credential check and with no network access: short silent graphics
  need no TTS key.
- Segmentation: narration text is split at sentence boundaries and packed
  into provider-limited TRANSPORT chunks. A chunk is a transport unit for
  one API request, never a visual scene and never a per-scene quota.
  There is NO minimum chunk size and NO padding: a short scene produces
  one short chunk, and a long scene produces as many chunks as the cap
  requires. Chunk boundaries never depend on a per-scene character band.
- The per-request cap is a named, configurable maximum:
  DEFAULT_MAX_CHARS_PER_REQUEST (4,000, the per-request ceiling this
  skill documents for the Fish Audio endpoint in
  references/fish-audio-tts.md), overridable per job via manifest
  tts.max_chars_per_request or per run via --max-chars. It is a
  transport cap only.
- AUDIO-FIRST TIMING: chunk durations are measured with ffprobe and
  summed per scene into durations.json. In the narrated branch the
  timeline is compiled from these measured durations; the picture is
  timed to the audio, never the reverse.
- NARRATION FINGERPRINT: durations.json carries a sha256 fingerprint of
  the exact narration text plus the provider settings that produced it
  (model, reference_id, temperature, chunk cap). Changing the narration
  or those settings changes the fingerprint, which is how downstream
  stages know a compiled timeline and approvals bound to the old
  revision are invalid.

durations.json shape (narrated run):
  {"status": "ok", "narration_fingerprint": "sha256:...",
   "fingerprint_inputs": {...}, "scenes": {scene_id: seconds, ...},
   "chunks": [{"file": ..., "scene_id": ..., "chars": n,
               "duration": seconds}, ...],
   "total_speech_seconds": seconds}
A silent run writes {"status": "no_narration", "reason": ...,
"narration_fingerprint": null, "scenes": {}, "chunks": []} instead and
prints the same record to stdout.

Model rules (see references/fish-audio-tts.md):
- Default model is s2.1-pro.
- drama-3-preview is OPT-IN only. The API SILENTLY falls back to s2.1-pro
  for unrecognized model values, so this script verifies the SERVED model
  from the response metadata on every request and hard-fails on mismatch.
  It never silently accepts the fallback.
- If the served model cannot be determined from the response, the script
  refuses unless --allow-unverified is passed, and says so plainly.

Requests fire CONCURRENTLY with bounded parallelism (default 5, the
starter-tier concurrent-request limit; tune with --max-workers), each
with exponential backoff on 429. Chunks are fetched independently and
joined in narration order with short crossfades. Concurrency only
changes how the chunks are fetched; timing is unchanged.

Key from FISH_AUDIO_API_KEY env. Never write it to disk. A job with no
narration never reaches the credential check.

Usage:
  python3 scripts/tts.py --manifest run/manifest.json --outdir work/audio [--max-workers 5] [--max-chars 4000]
"""
import argparse, hashlib, json, os, re, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

API = "https://api.fish.audio/v1/tts"
CROSSFADE = 0.25  # seconds between chunks
DEFAULT_MAX_WORKERS = 5  # starter-tier concurrent-request limit
# Per-request transport cap in characters. This is the ceiling on ONE API
# request, not a scene requirement: there is no matching minimum, and no
# scene is ever padded or trimmed to reach a character band.
DEFAULT_MAX_CHARS_PER_REQUEST = 4000


def fail(msg):
    print("TTS FATAL: " + msg, file=sys.stderr)
    sys.exit(1)


def served_model(resp):
    """Read the serving model from response metadata. Multiple locations,
    because the exact field varies; undetectable => None (caller decides)."""
    for hdr in ("x-fish-audio-model", "x-served-model", "x-model"):
        v = resp.headers.get(hdr)
        if v:
            return v.strip()
    body_hint = getattr(resp, "_body_hint", None)
    if body_hint:
        try:
            meta = json.loads(body_hint)
            for k in ("model", "served_model", "voice_model"):
                if meta.get(k):
                    return str(meta[k]).strip()
        except Exception:
            pass
    return None


def tts_request(api_key, model, reference_id, temperature, text):
    """One TTS request with exponential backoff on 429. Raises
    RuntimeError on failure (the caller runs this in worker threads,
    where sys.exit would only kill the thread)."""
    payload = json.dumps({
        "text": text,
        "model": model,
        "reference_id": reference_id,
        "temperature": temperature,
        "format": "mp3",
    }).encode()
    backoff = 5
    for attempt in range(6):
        req = urllib.request.Request(API, data=payload, method="POST", headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "User-Agent": "motion-video-plus/72",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio = resp.read()
                served = served_model(resp)
                return audio, served
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                print("429 rate limit, backing off %ss (attempt %d)" % (backoff, attempt + 1), file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError("HTTP %d: %s" % (e.code, e.read().decode()[:500]))
        except Exception as e:
            raise RuntimeError("request failed: %s" % e)
    raise RuntimeError("exhausted retries")


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True)
    return float(out.stdout.strip())


# ---------------------------------------------------------------------------
# Narration segmentation and fingerprinting (pure functions; unit-tested).
# ---------------------------------------------------------------------------

_SENTENCE_END = re.compile(r"[.!?]+[\"'”’)\]]*(?:\s+|$)")


def split_sentence_spans(text):
    """Split text into sentence spans whose concatenation is the text
    exactly (lossless: ''.join(spans) == text). A span ends at terminal
    punctuation plus any closing quotes/brackets and trailing whitespace.

    Boundary detection is a punctuation heuristic: an abbreviation with
    internal periods may end a span early. That is safe here because
    spans are only packed into transport chunks and reassembly is
    lossless and in order; no text is ever cut inside a word, reordered,
    padded, or dropped."""
    spans = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        spans.append(text[start:m.end()])
        start = m.end()
    if start < len(text):
        spans.append(text[start:])
    return [s for s in spans if s]


def segment_text(text, max_chars):
    """Pack the sentence spans of one narration text into transport
    chunks of at most max_chars characters. Lossless:
    ''.join(chunks) == text. A single span longer than the cap becomes
    its own chunk and exceeds the cap rather than being cut mid-sentence;
    the caller warns about it plainly."""
    chunks = []
    current = ""
    for span in split_sentence_spans(text):
        if current and len(current) + len(span) > max_chars:
            chunks.append(current)
            current = span
        else:
            current += span
    if current:
        chunks.append(current)
    return chunks


def plan_chunks(scene_texts, max_chars):
    """Build the ordered transport-chunk plan for a whole narration.
    scene_texts is an ordered list of (scene_id, text) with empty texts
    already removed. Chunk order is narration order; each chunk belongs
    to exactly one scene so measured chunk durations sum exactly into
    per-scene durations."""
    plan = []
    for sid, text in scene_texts:
        for chunk_text in segment_text(text, max_chars):
            plan.append({"index": len(plan), "scene_id": sid, "text": chunk_text})
    return plan


def narration_fingerprint(scene_texts, settings):
    """sha256 over the exact narration (ordered scene ids and texts) and
    the provider settings that produced it. Any change to the copy or to
    those settings changes the fingerprint; downstream stages compare it
    to detect that compiled timings and approvals have gone stale."""
    payload = {
        "scenes": [{"id": sid, "text": text} for sid, text in scene_texts],
        "settings": settings,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def narration_requirement(manifest):
    """Decide whether this job has narration to synthesize.

    Returns (required, reason, scene_texts), where scene_texts is the
    ordered list of (scene_id, stripped_text) for scenes carrying
    narration text. V2 manifests (an "audio" block) declare narration
    only when audio.mode is "own" and audio.create_voiceover is true;
    every other V2 audio policy is silent or parent-owned. V1 manifests
    (no audio block) have narration when any scene carries voiceover_text.
    """
    scene_texts = []
    for scene in manifest.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        text = scene.get("voiceover_text")
        if isinstance(text, str) and text.strip():
            scene_texts.append((scene.get("id", ""), text.strip()))
    audio = manifest.get("audio")
    if isinstance(audio, dict):
        if audio.get("mode") != "own" or audio.get("create_voiceover") is not True:
            return False, ("manifest audio block declares no voiceover for this job "
                           "(mode=%r, create_voiceover=%r)"
                           % (audio.get("mode"), audio.get("create_voiceover"))), []
        if not scene_texts:
            return True, ("manifest audio block requires voiceover (mode 'own', "
                          "create_voiceover true)"), []
        return True, "manifest audio block requires voiceover (mode 'own', create_voiceover true)", scene_texts
    if scene_texts:
        return True, "manifest scenes carry voiceover_text", scene_texts
    return False, "no scene in the manifest carries voiceover_text", []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max-workers", type=int, default=None,
                    help="concurrent TTS requests (default: manifest tts.max_concurrent, else 5)")
    ap.add_argument("--max-chars", type=int, default=None,
                    help="per-request transport cap in characters (default: manifest "
                         "tts.max_chars_per_request, else %d)" % DEFAULT_MAX_CHARS_PER_REQUEST)
    ap.add_argument("--allow-unverified", action="store_true",
                    help="continue when the served model cannot be read from response metadata")
    args = ap.parse_args()

    try:
        manifest = json.load(open(args.manifest))
    except Exception as e:
        fail("cannot read manifest %s: %s" % (args.manifest, e))

    # Narration decision comes FIRST: a silent job must not need a
    # credential, a voice reference, or any network access.
    required, reason, scene_texts = narration_requirement(manifest)
    os.makedirs(args.outdir, exist_ok=True)
    if not required:
        result = {"status": "no_narration", "reason": reason,
                  "narration_fingerprint": None, "scenes": {}, "chunks": []}
        with open(os.path.join(args.outdir, "durations.json"), "w") as fh:
            json.dump(result, fh, indent=2)
        print(json.dumps(result))
        print("no narration for this job (%s); nothing to synthesize and no "
              "TTS credential is required." % reason, file=sys.stderr)
        return
    if not scene_texts:
        fail("the job declares voiceover (%s) but no scene in the manifest carries "
             "voiceover_text. Supply the approved narration text in the manifest "
             "before running the voiceover stage." % reason)

    api_key = os.environ.get("FISH_AUDIO_API_KEY")
    if not api_key:
        fail("FISH_AUDIO_API_KEY is not set")

    tts = manifest.get("tts", {})
    model = tts.get("model", "s2.1-pro")
    reference_id = tts.get("reference_id")
    temperature = tts.get("temperature", 0.4)
    if not reference_id:
        fail("manifest tts.reference_id is missing")
    if not (0.3 <= temperature <= 0.5):
        print("TTS WARNING: temperature %s outside 0.3-0.5 delivery-consistency band" % temperature,
              file=sys.stderr)
    max_workers = args.max_workers or tts.get("max_concurrent") or DEFAULT_MAX_WORKERS
    if max_workers < 1:
        fail("--max-workers must be at least 1")
    max_chars = args.max_chars or tts.get("max_chars_per_request") or DEFAULT_MAX_CHARS_PER_REQUEST
    if max_chars < 1:
        fail("--max-chars must be at least 1")

    settings = {"model": model, "reference_id": reference_id,
                "temperature": temperature, "max_chars_per_request": max_chars}
    fingerprint = narration_fingerprint(scene_texts, settings)
    plan = plan_chunks(scene_texts, max_chars)
    for chunk in plan:
        if len(chunk["text"]) > max_chars:
            print("TTS WARNING: chunk %d (scene %s) is a single sentence of %d chars, over the "
                  "%d-char transport cap; sending it whole rather than cutting mid-sentence"
                  % (chunk["index"], chunk["scene_id"], len(chunk["text"]), max_chars),
                  file=sys.stderr)
    print("fetching %d transport chunks for %d narrated scene(s) with up to %d concurrent "
          "requests (model %s, cap %d chars/request)"
          % (len(plan), len(scene_texts), max_workers, model, max_chars), file=sys.stderr)

    def fetch(chunk):
        audio, served = tts_request(api_key, model, reference_id, temperature, chunk["text"])
        return chunk["index"], audio, served

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_index = {pool.submit(fetch, c): c["index"] for c in plan}
        for fut, idx in future_to_index.items():
            try:
                ridx, audio, served = fut.result()
            except RuntimeError as e:
                fail("chunk %d (scene %s): %s" % (idx, plan[idx]["scene_id"], e))
            results[ridx] = (audio, served)
            print("  fetched chunk %d (scene %s, served_model=%s)"
                  % (ridx, plan[idx]["scene_id"], served or "unverified"), file=sys.stderr)

    # Verify the served model for EVERY chunk before any audio is kept:
    # a silent provider fallback must never reach the timeline.
    for chunk in plan:
        audio, served = results[chunk["index"]]
        if served and served != model:
            fail("MODEL MISMATCH on chunk %d (scene %s): requested '%s' but the API served '%s'. "
                 "The request silently fell back. Stopping; fix model access and rerun."
                 % (chunk["index"], chunk["scene_id"], model, served))
        if not served and not args.allow_unverified:
            fail("could not determine the served model for chunk %d (scene %s) from response "
                 "metadata. Refusing to silently accept a possible fallback. Rerun with "
                 "--allow-unverified only if you accept this risk."
                 % (chunk["index"], chunk["scene_id"]))
        if not served:
            print("TTS WARNING: served model unverifiable for chunk %d (scene %s); continuing "
                  "per --allow-unverified" % (chunk["index"], chunk["scene_id"]), file=sys.stderr)

    # Write chunks in narration order and measure each one; a scene's
    # duration is the sum of its chunks' measured durations.
    chunk_paths = []
    chunk_records = []
    durations = {}
    for chunk in plan:
        audio, served = results[chunk["index"]]
        chunk_path = os.path.join(args.outdir, "chunk-%03d.mp3" % chunk["index"])
        open(chunk_path, "wb").write(audio)
        dur = probe_duration(chunk_path)
        durations[chunk["scene_id"]] = durations.get(chunk["scene_id"], 0.0) + dur
        chunk_paths.append(chunk_path)
        chunk_records.append({"file": os.path.basename(chunk_path),
                              "scene_id": chunk["scene_id"],
                              "chars": len(chunk["text"]),
                              "duration": dur})
        print("  -> %s  %.2fs" % (chunk_path, dur), file=sys.stderr)

    # Join chunks with short crossfades, in narration order.
    if len(chunk_paths) == 1:
        final = os.path.join(args.outdir, "voiceover.mp3")
        subprocess.run(["cp", chunk_paths[0], final], check=True)
    else:
        inputs = []
        for c in chunk_paths:
            inputs += ["-i", c]
        filt = ""
        for i in range(len(chunk_paths) - 1):
            a = "[%d:a]" % i if i == 0 else "[m%d]" % i
            filt += "%s[%d:a]acrossfade=d=%.2f:c1=tri:c2=tri[m%d];" % (a, i + 1, CROSSFADE, i + 1)
        filt = filt.rstrip(";")
        final = os.path.join(args.outdir, "voiceover.mp3")
        subprocess.run(["ffmpeg", "-y"] + inputs +
                       ["-filter_complex", filt, "-map", "[m%d]" % (len(chunk_paths) - 1),
                        "-c:a", "libmp3lame", "-b:a", "192k", final], check=True)

    durations = {sid: round(d, 3) for sid, d in durations.items()}
    record = {"status": "ok",
              "narration_fingerprint": fingerprint,
              "fingerprint_inputs": settings,
              "scenes": durations,
              "chunks": chunk_records,
              "total_speech_seconds": round(sum(durations.values()), 3)}
    with open(os.path.join(args.outdir, "durations.json"), "w") as fh:
        json.dump(record, fh, indent=2)
    print("voiceover complete: %s" % final)
    print("narration fingerprint: %s" % fingerprint)
    print("AUDIO-FIRST TIMING: compile the timeline from the per-scene durations in "
          "durations.json before rendering; the fingerprint identifies the narration "
          "revision those durations belong to.")


if __name__ == "__main__":
    main()
