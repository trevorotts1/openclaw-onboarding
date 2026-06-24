---
name: movie-producer
description: Autonomous multi-pipeline video production (the Movie Producer skill) using the OpenMontage agentic engine — real-footage documentary montage (free, zero-key), or Kie.AI-powered image/video generation. Operates on the client's own optional API keys only.
---

# Movie Producer — Automated Video Production (Skill 47)

Autonomous, multi-pipeline video production driven by the OpenMontage engine — an open-source agentic video production system that the client clones on their own box at install time. (This skill's directory is `47-movie-producer/`; "OpenMontage" throughout this doc names the UPSTREAM engine, not the skill.)

## What you get

- **Free documentary-montage path** — `pipeline_defs/documentary-montage.yaml` clips real footage from Archive.org, NASA, Wikimedia, Library of Congress, NOAA, ESA, JAXA, and Pond5 public-domain. Zero API keys needed. Budget cap ~$1.
- **Kie.AI generative path** — when the client sets `KIE_API_KEY`, the tool registry auto-routes ALL image generation through `kie_image.py` (models `gpt-image-2-image-to-image` / `gpt-image-2-text-to-image`) and ALL video generation through `kie_video.py` (primary `gemini-omni-video`, fallback `veo3`/`veo3_fast`). Native paid providers (FAL/Runway/HeyGen/OpenAI/Google) are never installed.
- **Free render engines preserved** — FFmpeg mux/stitch, Remotion (`remotion-composer/`), HyperFrames (`npx hyperframes`), Piper free TTS. These are never rewired to a paid provider.
- **13 production pipelines** — `pipeline_defs/*.yaml` drive the AI coding-assistant-as-orchestrator model. Stage skills in `skills/{core,creative,pipelines,meta}/` structure the execution. No code orchestrator binary required.
- **Rule-Zero budget discipline** — every client `config.yaml` ships with `budget.mode: cap` + a low `total_usd`. The system announces provider + model + estimated cost BEFORE any paid call and gates approval at `single_action_approval_usd: 0.50`.

## When to invoke this skill

- The `video` department Automated Video Production Specialist role (`video/automated-video-production-specialist-openmontage.md`) is assigned a production brief.
- A client asks for a full finished video produced from a brief, script, or outline (not just a clip or social media short — use Skill 25/27/28 for those).
- A client wants a free documentary-style montage assembled from public-domain real footage.
- A client's Kie.AI key is configured and they want a generated video asset.

## Handoff boundaries

| This skill (Skill 47) | Hand off to |
|---|---|
| Produces a finished MP4 that needs captions burned in | Skill 26 (`caption-creator`) |
| Produces voice narration via Piper or needs premium TTS | Skill 30 (`fish-audio-api-reference`) |
| Output needs manual editorial cuts, color grade, or timeline work | Skill 27 (`video-editor`) |
| Needs a storyboard authored before production starts | Skill 24 (`storyboard-writer`) |

## AGPLv3 boundary (binding)

OpenMontage (`github.com/calesthio/OpenMontage`) is AGPLv3. This skill **clones OpenMontage onto the client's own box at install time**. The fleet template repo (`openclaw-onboarding`) **never vendors OpenMontage source** (`tools/`, `pipeline_defs/`, `remotion-composer/`, `lib/`). Only this skill's installer, wrappers, docs, and the two Kie adapter files are in the template. The AGPLv3 obligation lives on the client's deployment, not the template.

## Department

`video` — no new department needed. Existing `video` department (`23-ai-workforce-blueprint/templates/role-library/video/`), 20 roles before this add.

## Client-own keys only

This skill exposes **only `KIE_API_KEY`** in the client `.env`. Operator keys NEVER appear on the client box. The zero-key path (free stock corpus) is the default.

## Files in this skill

- `SKILL.md` — this file
- `INSTALL.md` — step-by-step installation on a client box
- `INSTRUCTIONS.md` — how to drive pipelines + the Rule-Zero workflow
- `EXAMPLES.md` — copy-paste run examples (free path + Kie path)
- `CORE_UPDATES.md` — which core files this skill may update
- `skill-version.txt` — semver
- `qc-movie-producer.sh` — install QC (fail-loud)
- `verify-deps.sh` — clean-box dependency proof script
- `DEPENDENCY-MANIFEST.md` — the §A no-vendoring decision
- `kie-adapters/` — our two Kie.AI BaseTool adapters (copied into the clone at install)
  - `tools/graphics/kie_image.py` — Kie image generation (gpt-image-2-*)
  - `tools/video/kie_video.py` — Kie video generation (gemini-omni-video / veo3)
