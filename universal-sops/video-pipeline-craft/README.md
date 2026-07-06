# Video Pipeline Craft SOP Cluster (`universal-sops/video-pipeline-craft/`)

The SHARED, cross-department execution playbook for this craft. It does NOT re-implement the skill; the authoritative machine spine lives in the numbered skill folder. The SOP/manifest files in this directory govern the procedure; the Intent-triggers header below (generated from the skill-department map) states which plain-language client intents route here.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/video-pipeline-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **24** storyboard-writer | "plan my video" · "storyboard this" · "script for a video" · "break my video into scenes" |
| **25** video-creator | "make a video from this text" · "make a video from this image" · "generate a clip" · "turn this script into a video" |
| **26** caption-creator | "add captions" · "burn subtitles" · "make an SRT" · "caption this video" |
| **27** video-editor | "cut this video" · "trim this clip" · "resize this clip for social" · "edit this footage" |
| **28** cinematic-forge | "make a cinematic ad" · "make a cinematic reel" · "produce a polished video" · "a high-end branded video" |
| **47** movie-producer | "produce a full finished video from a brief" · "make me a documentary" · "make me a VSL" · "make me a whole video end to end" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->
