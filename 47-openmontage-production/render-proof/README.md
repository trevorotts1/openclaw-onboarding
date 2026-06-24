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
