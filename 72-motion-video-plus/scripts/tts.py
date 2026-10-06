#!/usr/bin/env python3
"""
Skill 72 chunked voiceover via Fish Audio TTS.

One request per scene (2,000-4,000 chars, split at scene/paragraph
boundaries, never mid-sentence). Same reference_id on every request,
temperature 0.3-0.5. Requests fire CONCURRENTLY with bounded parallelism
(default 5, the starter-tier concurrent-request limit; tune with
--max-workers), each with exponential backoff on 429, and results are
reassembled in scene order. Chunks are joined with short crossfades.
AUDIO-FIRST TIMING: each chunk's measured duration sets its scene's
timeline (written to durations.json). Concurrency only changes how the
chunks are fetched; timing is unchanged.

Model rules (see references/fish-audio-tts.md):
- Default model is s2.1-pro.
- drama-3-preview is OPT-IN only. The API SILENTLY falls back to s2.1-pro
  for unrecognized model values, so this script verifies the SERVED model
  from the response metadata on every request and hard-fails on mismatch.
  It never silently accepts the fallback.
- If the served model cannot be determined from the response, the script
  refuses unless --allow-unverified is passed, and says so plainly.

Key from FISH_AUDIO_API_KEY env. Never write it to disk.

Usage:
  python3 scripts/tts.py --manifest run/manifest.json --outdir work/audio [--max-workers 5]
"""
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

API = "https://api.fish.audio/v1/tts"
CROSSFADE = 0.25  # seconds between chunks
DEFAULT_MAX_WORKERS = 5  # starter-tier concurrent-request limit


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max-workers", type=int, default=None,
                    help="concurrent TTS requests (default: manifest tts.max_concurrent, else 5)")
    ap.add_argument("--allow-unverified", action="store_true",
                    help="continue when the served model cannot be read from response metadata")
    args = ap.parse_args()

    api_key = os.environ.get("FISH_AUDIO_API_KEY")
    if not api_key:
        fail("FISH_AUDIO_API_KEY is not set")

    manifest = json.load(open(args.manifest))
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

    os.makedirs(args.outdir, exist_ok=True)
    scenes = manifest["scenes"]
    print("fetching %d voiceover chunks with up to %d concurrent requests (model %s)"
          % (len(scenes), max_workers, model), file=sys.stderr)

    def fetch(scene):
        text = scene["voiceover_text"].strip()
        if not (2000 <= len(text) <= 4000):
            print("TTS WARNING: scene %s text is %d chars (target 2,000-4,000)" % (scene["id"], len(text)),
                  file=sys.stderr)
        audio, served = tts_request(api_key, model, reference_id, temperature, text)
        return scene["id"], audio, served

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_id = {pool.submit(fetch, s): s["id"] for s in scenes}
        for fut, sid in future_to_id.items():
            try:
                rid, audio, served = fut.result()
            except RuntimeError as e:
                fail("scene %s: %s" % (sid, e))
            results[rid] = (audio, served)
            print("  fetched %s (served_model=%s)" % (rid, served or "unverified"), file=sys.stderr)

    # Reassemble in manifest scene order; verify the served model per chunk.
    chunks = []
    durations = {}
    for scene in scenes:
        sid = scene["id"]
        audio, served = results[sid]
        if served and served != model:
            fail("MODEL MISMATCH on %s: requested '%s' but the API served '%s'. "
                 "The request silently fell back. Stopping; fix model access and rerun."
                 % (sid, model, served))
        if not served and not args.allow_unverified:
            fail("could not determine the served model for %s from response metadata. "
                 "Refusing to silently accept a possible fallback. Rerun with --allow-unverified "
                 "only if you accept this risk." % sid)
        if not served:
            print("TTS WARNING: served model unverifiable for %s; continuing per --allow-unverified"
                  % sid, file=sys.stderr)
        chunk_path = os.path.join(args.outdir, sid + ".mp3")
        open(chunk_path, "wb").write(audio)
        dur = probe_duration(chunk_path)
        durations[sid] = dur
        chunks.append(chunk_path)
        print("  -> %s  %.2fs" % (chunk_path, dur), file=sys.stderr)

    # Join chunks with short crossfades.
    if len(chunks) == 1:
        final = os.path.join(args.outdir, "voiceover.mp3")
        subprocess.run(["cp", chunks[0], final], check=True)
    else:
        inputs = []
        for c in chunks:
            inputs += ["-i", c]
        filt = ""
        for i in range(len(chunks) - 1):
            a = "[%d:a]" % i if i == 0 else "[m%d]" % i
            filt += "%s[%d:a]acrossfade=d=%.2f:c1=tri:c2=tri[m%d];" % (a, i + 1, CROSSFADE, i + 1)
        filt = filt.rstrip(";")
        final = os.path.join(args.outdir, "voiceover.mp3")
        subprocess.run(["ffmpeg", "-y"] + inputs +
                       ["-filter_complex", filt, "-map", "[m%d]" % (len(chunks) - 1),
                        "-c:a", "libmp3lame", "-b:a", "192k", final], check=True)

    json.dump(durations, open(os.path.join(args.outdir, "durations.json"), "w"), indent=2)
    print("voiceover complete: %s" % final)
    print("AUDIO-FIRST TIMING: scene durations must match durations.json before rendering.")


if __name__ == "__main__":
    main()
