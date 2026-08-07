# SOP -- Webinar Video Creator (Feature L2-G)

**Cluster:** Presentations — additional deliverable (Gauntlet Loop 2, Feature C).
**Phase:** `P9.6-WEBINAR-VIDEO` (order 8.92 — after GHL upload, before the teleprompter and P9-DELIVER).
**Owning role:** `media-librarian-ghl-updater` (this role already owns GHL media hosting + the delivery bundle).
**Executor:** `scripts/build_webinar_video.py`.
**Timing sub-executor:** `scripts/webinar_timing.py`.
**Render sub-executor:** `scripts/webinar_ffmpeg.py`.
**Research:** `~/Downloads/GAUNTLET-LOOP-WORK/WEBINAR-CREATOR-PLAN-OPUS.md`.

---

## 0. WHAT THIS DELIVERABLE IS

Every presentation gets a **webinar video** — a third client deliverable alongside the
deck and the workbook. The already-built per-deck artifacts (slide PNGs, the per-slide
script, the Fish-Audio-tagged speech, and the full TTS mp3) are assembled into **one
continuous, fluid video slideshow**: slide 1 is on screen while its spoken segment plays,
then a smooth crossfade to slide 2, and so on through all slides. One mp4, no stop-start
jank, slide changes timed to what is actually being spoken.

Three hard constraints:

1. **Timing** — slide changes are synced to the spoken audio via a per-slide timing track
   derived from the REAL Fish chunk durations, never from the `SECONDS:` planned estimate
   (which drifts off the real audio by minutes).
2. **Size** — target < 500 MB, hard cap 900 MB. A ~29 min business-webinar video at CRF 22
   1080p lands ~300-460 MB, inside the GHL 500 MB video-upload ceiling.
3. **GHL storage** — the mp4 lives in GHL media storage (the v3 video tier), never on the
   VPS or in Downloads. Local sources are never deleted until the upload is CONFIRMED.

The webinar is an ADDITIONAL deliverable. It does NOT replace any of the required build
deliverables; it rides the same run dir and is uploaded to GHL through the shared media
path.

## 1. WHEN IT RUNS

`P9.6-WEBINAR-VIDEO` runs after `P9.2-GHL-UPLOAD` (order 8.9) and before `P9-DELIVER`
(order 9.0). It consumes — all already produced by earlier phases, never rebuilt here:

- `renders/slide-NN.png` — the per-slide renders (2048x1152), one file per timing entry
- `working/delivery/PRESENTER-AUDIO.mp3` — the single continuous TTS mp3
- `working/delivery/_audio_chunks_full/chunk_NNN.mp3` — the real per-chunk Fish audio
- `working/deliverables/PRESENTERS-SPEECH.md` — the UNTAGGED speech (what was synthesized)
- `working/copy/intake.json` — brand palette + client name + deck slug

It produces:

- `working/delivery/{deck_slug}-WEBINAR.mp4` — the webinar video (1920x1080 h264 yuv420p)
- `working/checkpoints/webinar_timing.json` — the per-slide timing track (single source of
  truth for the render AND the verifier)

## 2. THE PIPELINE (four steps inside the executor)

1. **Time (webinar_timing.py):** derive the per-slide timing track by re-running the EXACT
   same chunking code path (`synthesize_full_speech.extract_spoken` + `chunk_text`, default
   `--chunk-chars 280`) over the same speech markdown, tagging each sentence unit with its
   slide number, then summing the real ffprobe durations of the on-disk chunk mp3s that
   flowed into each slide. Writes `webinar_timing.json`.
2. **Render (webinar_ffmpeg.py):** per slide N, render a Ken Burns clip sized to
   `timing[N].duration` — slow 6% push-in (zoompan 1.0 → 1.06) with a 0.5s fade-in at 0 and
   fade-out ending at `duration - 0.5`; then chain every clip with the `xfade` filter
   (0.5s crossfade centered on each slide boundary); then mux the single continuous mp3
   with `-map 0:v -map 1:a -shortest` so the video ends with the last spoken word.
3. **Gate size (AF-WEBINAR-SIZE):** ffprobe the output. Fail loud > 500 MB target; hard
   fail > 900 MB. A near-static 1080p CRF 22 render lands ~300-420 MB — inside the cap.
4. **Upload (ghl_media.upload_video):** host the mp4 to GHL via the **v3 video tier**
   (`Version: v3` + `Content-Type: video/mp4`, 500 MB ceiling) into the SAME per-deck GHL
   media folder as the deck. Record the result in the merged media ledger. Cleanup the
   local delivery-path copy ONLY after the upload is confirmed.

## 3. TIMING TRACK

`working/checkpoints/webinar_timing.json` is the single source of truth for both the
renderer and the verifier:

```json
{
  "deck_slug": "<slug>",
  "audio": "working/delivery/PRESENTER-AUDIO.mp3",
  "total_audio_sec": 1760.622,
  "chunk_chars": 280,
  "n_chunks": 90,
  "n_slides": 20,
  "fallback": null,
  "timing": [
    {"slide": 1, "chunks": [0,1,2,3],
     "audio_start": 0.0, "audio_end": 86.334, "duration": 86.334}
  ]
}
```

- `duration` is what the ffmpeg renderer uses to size each slide's Ken Burns clip.
- `audio_start`/`audio_end` are the REAL spoken windows in the single continuous mp3 —
  the renderer never splits the audio; it honors the track exactly.
- **Guard (fail-loud):** `len(rechunked) == len(on-disk chunk mp3s)`. If the counts
  disagree (`--chunk-chars` drift between the synthesis run and the installed chunker),
  the executor falls back to assigning on-disk chunks to slides by the `SECONDS:`
  -proportional split (deterministic, documented) and records `"fallback":
  "seconds_proportional"` plus a warning on stderr. Never silently emit a wrong mapping.
- **Slides with no speech:** a slide whose chunk list is empty gets a default **3.0s**
  static hold (section/visual-only slides) and is logged.
- **Contiguity:** timing slides must be contiguous 1..N; a gap is refused.

## 4. RULES

- **Deterministic render, no AI judgement in the render step.** Given the same slides,
  timing track, and audio, the ffmpeg pipeline produces the same video. ffmpeg is the only
  renderer — no image model, no browser, no UI automation.
- **Never print a credential value.** The GHL LOCATION PIT is read exactly as the existing
  `ghl_media.py` does — never echoed into the transcript.
- **GHL v3 small-probe gate (fail-closed):** `ghl_media.verify_video` runs BEFORE any
  network call — the file must exist, be non-empty, be <= 500 MB, and carry an MP4 `ftyp`
  box. A missing / oversized / non-MP4 file raises with zero bytes sent. `require_video`
  is NOT relaxed for a real webinar mp4.
- **No browser / no UI automation for GHL** — only the REST media path, same as the deck
  upload.
- **Never delete until confirmed.** The local `*-WEBINAR.mp4` (and chunk mp3s / timing
  JSON) stay put until the upload is CONFIRMED: HTTP 2xx AND `ghl_media_id` present AND a
  READ-ONLY list-back finds the entry by fileId/name. Only then is the local copy moved out
  of the delivery path. No VPS-root / Downloads copy, ever.
- **The executor runs ONLY via the canonical entry** (nonce check), mirroring
  `build_deck.py` — a hand-rolled webinar cannot bypass the door.
- **Operator credits for tests; never a client.** A sample webinar is built on the
  operator account and saved to `~/Downloads`. No client messaging.
- The webinar does NOT go through `build_deck.py` and is NOT a deck render.

## 5. VERIFY (operator smoke on a sample)

```bash
python3 scripts/webinar_timing.py \
    --speech <sample>/working/deliverables/PRESENTERS-SPEECH.md \
    --chunks-dir <sample>/working/delivery/_audio_chunks_full \
    --audio <sample>/working/delivery/PRESENTER-AUDIO.mp3 \
    --out ~/Downloads/webinar_timing.sample.json
```

Expect: `timing total = <T>s vs audio <A>s -> PASS` (diff < 1s), and the timing entries are
contiguous 1..N. Then:

```bash
python3 scripts/webinar_ffmpeg.py \
    --slides <sample>/renders --timing ~/Downloads/webinar_timing.sample.json \
    --audio <sample>/working/delivery/PRESENTER-AUDIO.mp3 \
    --out ~/Downloads/<deck>-WEBINAR.sample.mp4
```

Expect: the ffprobe verification dict — `1920x1080 h264+aac`, duration within ±1s of the
timing total, size < 500 MB. The executor's `build_webinar_video.py` runs both steps plus
the size gate and the GHL upload in one dispatch; a failed size gate or a failed upload
fails the phase (never fabricates a GHL url).

## 6. HANDBACK

After a successful build + size-gate + upload, the run's checkpoints record:

- `working/checkpoints/webinar_timing.json` — the timing track (schema above), the single
  source of truth for render and verify.
- The merged media ledger (`working/checkpoints/media_library.json`) gains a `webinar_mp4`
  record: `ghl_media_id`, `ghl_url` (public GCS url), `ghl_remote_name`,
  `http_status` (2xx), `size_bytes`, and `uploaded_at`. `tier` is `"v3"` and `content_type`
  is `video/mp4` on the wire.
