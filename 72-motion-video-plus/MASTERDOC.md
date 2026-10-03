# Motion Video Plus: Skill 72 Master Integration Contract

## Purpose

Skill 72 is the OpenClaw-native home of the deterministic motion-graphics video pipeline proven on the 30-second, 6-scene LiveConvo.chat promo: model-written HTML/JS animation honoring the `window.__setTime(t)` contract, headless-Chromium frame rendering at 30fps, FFmpeg assembly with a Fish Audio TTS voiceover, automated QC with a contact sheet.

## Boundary with existing video skills

| Request | Canonical owner |
|---|---|
| Motion-graphics video from code-driven animation (kinetic type, animated explainer, brand promo) | **Skill 72** |
| AI video-model generation (Kie.ai) | **Skill 67** |
| Documentary montage / VSL / talking-head pipelines (OpenMontage) | **Skill 47** |
| Hands-on editing of existing footage | video-editor craft |
| Captions on a finished video | Skill 26 |

A plain request to "make me a promo video" routes by method: code-driven motion graphics goes to Skill 72; generative footage goes to Skill 67; montage goes to Skill 47. A user does not need to know the skill number or name.

## Department ownership

Primary department: `video`
Primary role: `video-editor`
Secondary roles: `storyboard-pre-production-specialist`, `head-of-video-production`

This uses the repo's existing native-skill invocation architecture; do not create a new department or duplicate role merely for Skill 72.

## Execution seams

- Skill 72 owns the animation contract, manifest schema, frame renderer, preflight, TTS chunking, assembly, QC, and brand-bible template.
- Skill 67 owns Kie.ai video-model routing when generative footage is selected instead.
- Skill 47 owns the OpenMontage pipelines when documentary montage is selected instead.
- Skill 26 owns captioning on the finished MP4.
- Client providers only at runtime; operator keys never touch a client box. No Anthropic models anywhere in the pipeline.
