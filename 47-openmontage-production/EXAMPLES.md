# OpenMontage Production (Skill 47) — Examples

## Table of contents

1. [Free documentary-montage path (zero API keys)](#free-documentary-montage-path)
2. [Kie.AI image generation example](#kieai-image-generation)
3. [Kie.AI video generation example (gemini-omni-video)](#kieai-video-generation)
4. [Validate a rendered MP4 with ffprobe](#validate-a-rendered-mp4)
5. [Run make preflight to see available providers](#run-make-preflight)
6. [Remotion zero-key demo](#remotion-zero-key-demo)

---

## Free documentary-montage path

Zero API keys needed. Assembles real footage from Archive.org, NASA, Wikimedia, and other public-domain archives.

### 1 — Set a $1 budget cap

In `~/.openclaw/skills/47-openmontage-production/OpenMontage/config.yaml`:

```yaml
budget:
  mode: cap
  total_usd: 1.00
  single_action_approval_usd: 0.50
  require_approval_for_new_paid_tool: true
```

### 2 — Run the documentary-montage pipeline

```bash
cd ~/.openclaw/skills/47-openmontage-production/OpenMontage

python3 -c "
import yaml, json
with open('pipeline_defs/documentary-montage.yaml') as f:
    pipeline = yaml.safe_load(f)
print('Pipeline:', pipeline.get('name'))
print('Budget default:', pipeline.get('budget_default_usd'))
print('Stages:', [s.get('name') or s.get('stage') for s in pipeline.get('stages', [])])
"
```

Then open the directory in your AI coding assistant and instruct it to run the documentary-montage pipeline with your topic. The assistant drives the stage skills in sequence; all footage is pulled from free stock sources.

Expected output: an MP4 in the configured `outputs/` directory.

---

## Kie.AI image generation

With `KIE_API_KEY` set in `.env`, the `image_selector` auto-routes to Kie.

### Image-to-image edit (source image provided)

```python
# Run from ~/.openclaw/skills/47-openmontage-production/OpenMontage/
from tools.tool_registry import registry
registry.discover()

selector = registry.get_tool("image_selector")
result = selector.execute({
    "prompt": "A cinematic hero shot of a modern city skyline at golden hour",
    "image_urls": ["https://example.com/source-image.jpg"],
    "generation_mode": "edit",
    "aspect_ratio": "16:9",
    "resolution": "2K",
    "output_path": "outputs/hero-shot.png"
})

print("Provider selected:", result.data.get("selected_provider"))
print("Kie task ID:", result.data.get("kie_task_id"))
print("Kie result URL:", result.data.get("kie_result_url"))
print("Output path:", result.data.get("output_path"))
```

Expected `selected_provider`: `kie`

### Text-to-image (no source image)

```python
from tools.tool_registry import registry
registry.discover()

selector = registry.get_tool("image_selector")
result = selector.execute({
    "prompt": "Abstract digital art representing innovation and growth",
    "aspect_ratio": "16:9",
    "resolution": "2K",
    "output_path": "outputs/title-card.png"
})

print("Provider selected:", result.data.get("selected_provider"))
print("Kie task ID:", result.data.get("kie_task_id"))
```

---

## Kie.AI video generation

### Image-to-video with gemini-omni-video (primary)

```python
from tools.tool_registry import registry
registry.discover()

selector = registry.get_tool("video_selector")
result = selector.execute({
    "prompt": "The skyline transforms as the sun sets, casting long shadows over the city",
    "image_urls": ["https://example.com/hero-shot.png"],
    "duration": "8",          # STRING not integer — required by gemini-omni-video
    "aspect_ratio": "16:9",
    "generate_audio": True,
    "output_path": "outputs/hero-video.mp4"
})

print("Provider selected:", result.data.get("selected_provider"))
print("Kie task ID:", result.data.get("kie_task_id"))
print("Kie result URL:", result.data.get("kie_result_url"))
```

Expected `selected_provider`: `kie`

### Text-to-video fallback (no source image)

The `kie_video.py` adapter automatically falls back to `veo3_fast` when no source image is provided:

```python
from tools.tool_registry import registry
registry.discover()

selector = registry.get_tool("video_selector")
result = selector.execute({
    "prompt": "A time-lapse of a bustling farmers market from dawn to dusk",
    "aspect_ratio": "16:9",
    "duration": "8",
    "generate_audio": True,
    "output_path": "outputs/market-timelapse.mp4"
})

print("Model used:", result.data.get("kie_model"))
print("Kie task ID:", result.data.get("kie_task_id"))
```

---

## Validate a rendered MP4

Run this after every render — mandatory before handoff:

```bash
ffprobe -v error \
  -show_entries "format=duration,format_name:stream=codec_type" \
  -of json \
  ~/.openclaw/skills/47-openmontage-production/OpenMontage/outputs/your-video.mp4
```

A passing result looks like:

```json
{
  "streams": [
    {"codec_type": "video"},
    {"codec_type": "audio"}
  ],
  "format": {
    "duration": "32.000000",
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2"
  }
}
```

Failure conditions (do NOT deliver): `duration` is `"0"` or missing, no `video` stream, format is not mp4/mov.

> **This is not just an example — it has been proven.** The committed render
> receipt at `render-proof/` was produced by a REAL FFmpeg documentary-montage
> render on this build (FFmpeg 8.1.1, `libx264`, concat-demuxer path; output
> `6.081479s`, `h264` video stream `1280x720` + `aac` audio, mp4 format —
> ffprobe JSON in `render-proof/documentary-montage-render-proof.ffprobe.json`).
> Reproduce it on any box:
>
> ```bash
> bash render-proof/render-documentary-montage-ffmpeg.sh /tmp/montage-out
> ffprobe -v error -show_entries "format=duration,format_name:stream=codec_type" \
>   -of json /tmp/montage-out/documentary-montage-render-proof.mp4
> ```
>
> The script mirrors `tools/video/video_stitch.py` (`_normalize` + `_stitch_cut`)
> exactly — the same pure-FFmpeg path the documentary-montage pipeline uses. No
> Remotion, no HyperFrames, no headless Chromium.

---

## Run make preflight

Shows which providers are available in the registry:

```bash
cd ~/.openclaw/skills/47-openmontage-production/OpenMontage && make preflight
```

With `KIE_API_KEY` set, expected output (truncated):

```json
{
  "image_generation": [
    {"provider": "kie", "status": "available", "tool": "kie_image"},
    {"provider": "flux", "status": "unavailable"},
    {"provider": "openai", "status": "unavailable"}
  ],
  "video_generation": [
    {"provider": "kie", "status": "available", "tool": "kie_video"},
    {"provider": "veo", "status": "unavailable"},
    {"provider": "runway", "status": "unavailable"}
  ],
  "tts": [
    {"provider": "piper", "status": "available", "tool": "piper_tts"}
  ]
}
```

Without `KIE_API_KEY` (free path), `image_generation` and `video_generation` show no available providers — only the free render engines and free stock sources remain.

---

## Remotion zero-key demo

Tests that Remotion and Node.js are wired correctly without any API keys:

```bash
cd ~/.openclaw/skills/47-openmontage-production/OpenMontage && make demo
```

This renders zero-key animated chart/text/data-viz demos using Remotion components only. If this fails, check Node 18+ is installed (`node -v`) and `remotion-composer/node_modules` exists.
