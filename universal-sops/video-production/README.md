# Video Production Craft SOP Cluster (`universal-sops/video-production/`)

The SHARED, cross-department execution playbook for producing a polished **personal / talking-head video** featuring a consenting person's likeness and cloned Fish Audio voice. It does NOT re-implement the skill; the authoritative machine spine lives in the numbered skill folders (`47-movie-producer/`, `63-agnes-image/`, `64-agnes-video/`, `30-fish-audio-api-reference/`). The SOP/manifest files in this directory govern the procedure; the Intent-triggers header below states which plain-language client intents route here.

**Owning department:** `video` (Director of Video / Head of Video Production).
**Canonical SOP:** `SOP-PVC-01-PERSONAL-VIDEO-CREATOR.md` (v2.0, hardened).
**Enforcement:** `scripts/probe_*.py` — deterministic, fail-closed QC probes (see the gate table below).

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/video-production/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **47** movie-producer | "make me a video of me talking" · "a talking-head video with my face and voice" · "a personal video / founder video / VSL with my likeness" · "turn my script into a video of me speaking" |
| **64** agnes-video | "animate my portrait into a talking video" · "generate a clip of me speaking" |
| **63** agnes-image | "make a consistent reference image of me for the video" |
| **30** fish-audio-api-reference | "clone my voice for the narration" · "generate the master narration in my voice" |
| **24** storyboard-writer | "storyboard my talking-head video from the narration timing" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.

**Disambiguation:** edit supplied footage → `universal-sops/video-pipeline-craft/` (Video Editor, Skill 27); captions only → Captioning Specialist (Skill 26); premium TTS only → Fish Audio (Skill 30); a documentary/montage from a brief with no real-person likeness → `universal-sops/video-pipeline-craft/` (Movie Producer). This cluster is specifically for **likeness + cloned-voice talking-head** production, where lip-sync correction and identity consistency are mandatory.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## What lives here

| File | Purpose |
|---|---|
| `SOP-PVC-01-PERSONAL-VIDEO-CREATOR.md` | The hardened SOP (v2.0). Research-backed identity/lip-sync/motion/continuity best practices, measurable QC gates, fallback hierarchies, error-recovery ladders, SecretRef credential handling, CC + persona integration. |
| `VIDEO-PRODUCTION-MANIFEST.json` | Cluster manifest: SOP library record (slug, department, task_keywords, persona_hints), the gate→probe map, and the fallback hierarchies. |
| `scripts/probe_*.py` | Fail-closed QC probes. Each exits 0 on pass, 2 on violation, 3 on usage/fail-closed. |

## Gate → probe map (a rule not auto-failed at a gate does not exist)

| Gate code | Probe | Enforces |
|---|---|---|
| `AF-PVC-CONSENT` | `probe_consent.py` | likeness + voice consent present and verified |
| `AF-PVC-SECRET-LEAK` | `probe_no_secrets.py` | no API keys / voice IDs / signed URLs in prompts, manifests, logs |
| `AF-PVC-MANIFEST` | `probe_manifest.py` | project_manifest.yaml complete + SecretRef discipline |
| `AF-PVC-ENV` | `probe_environment.py` | ffmpeg/ffprobe present + SecretRefs resolve + .gitignore covers private assets |
| `AF-PVC-PROMPT-FLOOR` / `-CEILING` / `-IDENTITY` | `probe_prompt_band.py` | every likeness/reference prompt in the 5,000–19,000 stripped-char band with identity-anchor + negative blocks |
| `AF-PVC-FRAMEPLAN` | `probe_frame_plan.py` | Agnes `num_frames` satisfies `8n+1`, `<= 441`, covers spoken duration + handles |
| `AF-PVC-SEGMENT-DUR` | `probe_segment_duration.py` | extracted scene WAV duration == audio_end − audio_start (±0.05s) |
| `AF-PVC-CLIP-TECH` | `probe_video_clip.py` | raw clip orientation/resolution/CFR/duration (ffprobe) |
| `AF-PVC-LIPSYNC-OFFSET` | `probe_lipsync_offset.py` | A/V onset offset <= 2 frames; head-to-tail drift <= 1 frame |
| `AF-PVC-DURATION` | `probe_picture_duration.py` | picture duration == master audio (±1 frame) |
| `AF-PVC-AUDIO` | `probe_audio_master.py` | master/mix loudness −16±1 LUFS, true peak <= −1.5 dBTP, no clipping, 48 kHz |
| `AF-PVC-SCENE-QC` | `probe_scene_qc.py` | every TALKING_HEAD scene has a PASS decision + recorded offset <= 2 frames |
| `AF-PVC-FINAL-TECH` | `probe_final_technical.py` | final MP4 codec/pix_fmt/fps/resolution/audio/duration/streams |
| `AF-PVC-FINAL-QC` | `probe_final_qc.py` | every binary final-QC item attested + all probes passed |

## Project folder standard (created before generation)

```text
personal-video-project/
├── 00_admin/        (CONSENT.md, project_brief.md, project_manifest.yaml, production_log.md)
├── 01_likeness/     (source_photos/, approved_references/, identity_bible.md, rejected/)
├── 02_script/       (script_draft.md, script_fish_tagged.md, script_final_clean.md, pronunciation_dictionary.yaml)
├── 03_audio/        (fish_master_raw.wav, fish_master_qc.wav, fish_timestamps.json, fish_alignment.csv, segments/)
├── 04_storyboard/   (storyboard.md, scene_manifest.yaml, shot_list.csv)
├── 05_agnes_raw/    (scene_001/, scene_002/, rejected/)
├── 06_lipsync/      (inputs/, outputs/, rejected/)
├── 07_broll/        (generated/, licensed/, overlays/)
├── 08_music/        (source/, edited/, license_notes.md)
├── 09_captions/     (captions.srt, captions.vtt, caption_style.md)
├── 10_assembly/     (normalized_scenes/, concat.txt, picture_lock.mp4, voice_music_mix.wav, ffmpeg_commands.log)
├── 11_qc/           (scene_qc.csv, final_qc.md, qc_frames/, revision_notes.md)
└── 12_delivery/     (final_master.mp4, final_social.mp4, thumbnail.png, delivery_manifest.md)
```

Naming pattern: `scene_###_<type>_<status>_v##.<ext>` — never overwrite; increment the version.
