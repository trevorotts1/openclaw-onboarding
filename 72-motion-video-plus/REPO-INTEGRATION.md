# Repository Integration: Skill 72 Motion Video Plus

This file is written for the OpenClaw/onboarding-repo agent that receives this folder.

## 1. Canonical folder and number

Install this folder as:

`72-motion-video-plus/`

The current repository numbering reaches Skill 71 (`71-blackceo-signature-page`), so this capability is Skill 72.

## 2. Native skill binding

The onboarding repo's source of truth is:

`23-ai-workforce-blueprint/skill-department-map.json`

Add the object in `repo-integration/skill-department-map-entry.json` to `skills[]`.

Primary owner:

- department: `video`
- role: `video-editor`

Secondary: `storyboard-pre-production-specialist`, `head-of-video-production`.

Do not create a new department or a duplicate video role.

## 3. Refresh Layer B from the map

From `23-ai-workforce-blueprint/` run the canonical Scenario-E sequence:

```bash
python3 scripts/check-skill-department-map.py
python3 scripts/stamp-skills-you-operate.py
python3 scripts/hash-content-manifest.py
python3 scripts/qc-assert-repo-consistency.py
```

The stamper updates the video roles' marker-guarded `Skills You Operate` blocks. Do not hand-edit those generated blocks.

Because `video` already owns client-facing skills and already participates in the routing reflex, do not add a new department reflex merely for Skill 72 unless the current repo gate proves one is actually missing.

## 4. Routing note

A plain "make me a promo video" request now has three method-specific owners: Skill 72 (code-driven motion graphics), Skill 67 (AI video-model generation), Skill 47 (documentary montage). Update conflicting legacy routing so method, not just intent, selects the skill.
