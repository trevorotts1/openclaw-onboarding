# OpenMontage Production (Skill 47) — Instructions

## Rule-Zero workflow (MANDATORY before any paid call)

Every production run follows this order, regardless of pipeline:

1. **Read the brief** — intake the client's production brief or script.
2. **Select a pipeline** — choose a `pipeline_defs/*.yaml` that matches the brief (see table below).
3. **Announce before paying** — BEFORE executing any tool that calls a paid API, post:
   > "Preparing to call `{provider}` / model `{model}` — estimated cost `${estimated_usd}`. Approve to proceed."
   Then wait for explicit approval. This is enforced by `config.yaml: single_action_approval_usd: 0.50` and `require_approval_for_new_paid_tool: true`.
4. **Run the pipeline** — drive OpenMontage's stage skills via your AI coding assistant.
5. **Checkpoint approval** — honor `config.yaml: checkpoint.policy: guided` (stops at every checkpoint for human review).
6. **Validate the output** — run `ffprobe` on every rendered MP4 (see Validation section below).
7. **Check budget** — confirm total spend is within `config.yaml: budget.total_usd`.
8. **Hand off** — deliver the MP4 path + ffprobe receipt to the downstream skill (captions → Skill 26, TTS → Skill 30, editorial → Skill 27).

---

## Pipeline selection guide

| Brief type | Recommended pipeline | Cost |
|---|---|---|
| Documentary / educational / history | `documentary-montage.yaml` | Free (public-domain stock footage) |
| Short social video from a script | `script-to-video.yaml` | Kie.AI usage |
| Product demo or explainer | `explainer-video.yaml` | Kie.AI usage |
| Brand video with visuals | `brand-video.yaml` | Kie.AI usage |
| News-style recap | `news-recap.yaml` | Free + optional Kie |
| Fully generated AI video | run `image_selector` / `video_selector` directly | Kie.AI usage |

### The free documentary-montage path (zero API keys needed)

This is the default and preferred path. It assembles real footage from public-domain archives:
- Archive.org
- NASA image and video library
- Wikimedia Commons
- Library of Congress
- National Archives (NARA)
- NOAA
- ESA and JAXA
- Pond5 public-domain collection

Run it:

```bash
cd ~/.openclaw/skills/47-openmontage-production/OpenMontage

# Edit documentary-montage.yaml with your brief and topic, then:
python3 -c "
from tools.tool_registry import registry
registry.discover()
# Drive the documentary-montage pipeline via stage skills
"
```

Budget cap: set `total_usd: 1.00` in `config.yaml` for the free path (stock sources are free; only narration TTS has cost if you use a cloud TTS instead of Piper).

---

## Driving pipelines via the AI coding assistant

OpenMontage has no binary orchestrator. Your AI coding assistant IS the orchestrator (README line 329: "There is no code orchestrator. Your AI coding assistant IS the orchestrator.").

Workflow:

1. Open the cloned directory in your AI coding assistant.
2. Load the target `pipeline_defs/*.yaml`.
3. Follow the stage sequence in the YAML (`stages:` list).
4. For each stage, the assistant invokes the corresponding stage skill from `skills/{core,creative,pipelines,meta}/`.
5. Paid tool calls go through `image_selector.py` or `video_selector.py`, which auto-discover available providers via the registry. With only `KIE_API_KEY` set, Kie.AI wins every selection.

### Setting `preferred_provider`

In `config.yaml`, add:

```yaml
preferred_provider: kie
```

This gives Kie.AI priority in scoring so it wins tool selection even if future keys are present.

---

## Kie.AI routing — how it works

When `KIE_API_KEY` is in `.env`:

- `tools/graphics/image_selector.py` calls `registry.get_by_capability("image_generation")`. Only `kie_image` has status `AVAILABLE` (native paid providers are UNAVAILABLE — their env keys are absent). Kie image is selected.
- `tools/video/video_selector.py` calls `registry.get_by_capability("video_generation")`. Only `kie_video` has status `AVAILABLE`. Kie video is selected.
- Free engines (FFmpeg, Remotion, HyperFrames, Piper, free stock corpus) are unaffected — they report AVAILABLE regardless of API keys.

**Kie image models:**
- `gpt-image-2-image-to-image` — when source images are provided (edit mode)
- `gpt-image-2-text-to-image` — when no source image (text-to-image)
- Output: 16:9 aspect ratio, 2K resolution, PNG

**Kie video models:**
- `gemini-omni-video` (default) — image-to-video, accepts reference image URLs, duration as STRING (e.g. `"8"`), `generate_audio: true`
- `veo3` / `veo3_fast` (fallback) — text-to-video, POST `/api/v1/veo/generate`

---

## Output validation (ffprobe — mandatory)

Every rendered MP4 MUST be validated before handoff:

```bash
ffprobe -v error \
  -show_entries "format=duration,format_name:stream=codec_type" \
  -of json \
  /path/to/output.mp4
```

Accept the output only if:
- `format_name` contains `mp4` or `mov`
- `duration` is a positive number > 0
- At least one stream with `codec_type: "video"` is present

Example passing output:
```json
{
  "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
  "format": {"duration": "32.4", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"}
}
```

If validation fails (zero duration, no video stream, corrupt format): do NOT deliver to the client. Re-run the pipeline or file a bug against the failing stage.

---

## TTS (narration) — Piper first, cloud fallback

Piper is the free, offline, zero-key TTS engine installed by `make setup`. Use it by default for all narration.

If Piper is unavailable (soft-fail at install), the pipeline falls back to the cloud TTS providers installed in `tools/audio/`. For premium TTS, hand off to Skill 30 (`fish-audio-api-reference`) instead of adding new API keys here.

---

## Handoff boundary vs Skill 27 (Video Editor)

**This skill (Skill 47):** autonomously produces a finished video FROM a brief or pipeline manifest. It is an AI-driven render pipeline — it does not accept pre-existing footage for editorial cuts.

**Skill 27 (Video Editor):** hands-on editing of supplied footage — cuts, trims, transitions, color grade, timeline work.

If the client supplies raw footage to edit, use Skill 27. If the client wants a video produced end-to-end from a brief (no supplied footage), use this skill.

---

## Config reference

Key `config.yaml` fields for client boxes:

```yaml
budget:
  mode: cap                         # hard cap — stops when reached
  total_usd: 5.00                   # set low; adjust per client
  single_action_approval_usd: 0.50  # gate on every action > $0.50
  require_approval_for_new_paid_tool: true

checkpoint:
  policy: guided                    # stops at every pipeline checkpoint

preferred_provider: kie             # belt-and-suspenders Kie routing
```

For the free documentary-montage path, set `total_usd: 1.00` — the only potential cost is cloud TTS if Piper is unavailable.
