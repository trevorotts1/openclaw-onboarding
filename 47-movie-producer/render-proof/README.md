# Render Proof — OpenMontage documentary-montage FFmpeg path

This directory is the **real render receipt** for Skill 47. It proves that the
documentary-montage compose path produces a valid MP4 using **pure FFmpeg only**
— no Remotion, no HyperFrames, no headless Chromium — exactly the path the
`video-editor`/Operator runs for the free real-footage montage pipeline.

## What was rendered (real run, not an example)

`render-documentary-montage-ffmpeg.sh` reproduces the FFmpeg path that OpenMontage's
`tools/video/video_stitch.py` uses for `pipeline_defs/documentary-montage.yaml`:

1. **Per-beat normalize** — three narrative "beats" (each generated at a DIFFERENT
   native resolution: 640x480, 1920x1080, 854x480 — standing in for mixed-era
   CLIP-retrieved public-domain stock clips) are each normalized to a uniform
   1280x720 spec via
   `scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2` +
   `libx264` (mirrors `video_stitch.VideoStitch._normalize`).
2. **Stitch** — the normalized beats are concatenated with the **FFmpeg concat
   demuxer**: `ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy out.mp4`
   (mirrors `video_stitch.VideoStitch._stitch_cut`).
3. **ffprobe validation** — the mandatory SOP 9.4 step-7 proof.

Real footage requires network/API access to the public-domain corpus
(Archive.org / NASA / Wikimedia); the FFmpeg **compose** path is byte-for-byte
identical regardless of where the clips came from, so the generated beats prove
the render path itself. On a client box with network access, swap the lavfi
beats for CLIP-retrieved stock clips — the normalize + concat-demuxer steps are
unchanged.

## The receipt (captured from the actual run)

- **Renderer:** `ffmpeg version 8.1.1` (Homebrew, FFmpeg 8.x), `libx264`.
- **Output:** `documentary-montage-render-proof.mp4` — 1,133,176 bytes.
- **sha256:** `a055dd2c686240437eed996b23afc9613cc17c9a33a1ffa9200a26e2711f189e`
- **ffprobe JSON** (`documentary-montage-render-proof.ffprobe.json`):
  - `format.duration` = **6.081479** (> 0 ✓)
  - `format.format_name` = `mov,mp4,m4a,3gp,3g2,mj2` (mp4 ✓)
  - video stream: `codec_name h264`, `1280x720` (a video stream is present ✓)
  - audio stream: `codec_name aac`
- **PASS** against the SOP 9.4 step-7 criteria (duration > 0 + a video stream + mp4 format).

The MP4 binary itself is intentionally NOT committed (binary artifacts do not
belong in the fleet template); the reproducible script + the ffprobe JSON receipt
ARE committed so any box can re-run and reproduce the proof:

```bash
bash render-proof/render-documentary-montage-ffmpeg.sh /tmp/montage-out
ffprobe -v error -show_entries "format=duration,format_name:stream=codec_type" \
  -of json /tmp/montage-out/documentary-montage-render-proof.mp4
```

## Kie generative-asset proof (separate receipt)

This render proof covers the FREE documentary-montage render path (zero API cost).
The Kie generative-asset proof (`selected_provider == "kie"` + `kie_task_id` +
`kie_result_url`) requires a funded `KIE_API_KEY` on the client box and is a
client-box step — see `EXAMPLES.md` and the gating proof in `INSTALL.md` /
`INSTRUCTIONS.md` (with only `KIE_API_KEY` set, every native paid provider reports
UNAVAILABLE, so `kie` is the only AVAILABLE generative provider).

### Real Kie video render (operator-side adapter verification)

`kie-video-render-proof.json` + `kie-video-render-proof.ffprobe.json` are the
**real receipt** that the `kie_video` adapter actually generates a video asset
against `api.kie.ai` — captured from a live run on the operator box (operator's
own `KIE_API_KEY`, used for adapter verification only; production uses
client-funded keys).

The run reproduced the EXACT body shape from
`kie-adapters/tools/video/kie_video.py` (the adapter itself is not imported
because it depends on OpenMontage `tools.base_tool`, which is AGPLv3 source and
is NOT vendored here):

1. **createTask** — `POST https://api.kie.ai/api/v1/jobs/createTask` with
   `model=gemini-omni-video`, `input.duration` as a **STRING** (`"4"`, the
   verified 422 fix), `input.aspect_ratio="16:9"` always present (the verified
   422 fix), `generate_audio=true` → **HTTP 200**.
2. **Real Kie task id:** `a27542cb60343417e562afc2be65da5c`.
3. **Poll** — `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=` every 10 s;
   `state` went `waiting → success` at ~90 s.
4. **Result URL** — `https://tempfile.aiquickdraw.com/v/a27542cb60343417e562afc2be65da5c_1782311674.mp4`.
5. **Download** — 1,033,416 bytes;
   sha256 `8ea8ef8ac9c5cd69d2f3bc2ce166ccbc5489f0206473e4231daa1f7953f487a6`.
6. **ffprobe** (`kie-video-render-proof.ffprobe.json`):
   - `format.duration` = **4.010000** (> 0 ✓)
   - `format.format_name` = `mov,mp4,m4a,3gp,3g2,mj2` (mp4 ✓)
   - video stream: `codec_name h264`, `1280x720` (a video stream is present ✓)
   - audio stream: `codec_name aac`
7. **No browser** — the whole path is pure `requests` HTTP. No headless Chrome,
   no remote-debugging, no Puppeteer/Playwright process existed at any point; the
   Chrome PID count was unchanged across the run.
8. **PASS** against the SOP 9.4 step-7 criteria (duration > 0 + a video stream + mp4).

The MP4 binary itself is intentionally NOT committed (binary artifacts do not
belong in the fleet template); the `kie_task_id`, the result URL, the sha256, and
the ffprobe JSON ARE committed as the reproducible receipt.
