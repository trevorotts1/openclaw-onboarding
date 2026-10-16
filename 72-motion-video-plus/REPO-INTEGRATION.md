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

## 5. Caller references reconciled by MG-042

- Skill 47 (`47-movie-producer/SKILL.md`, `47-movie-producer/INSTRUCTIONS.md`): the file inventory and handoff boundaries name the shipped motion bridges, `47-movie-producer/scripts/vsl_handoff.py` (returned inserts) and `47-movie-producer/scripts/motion_status.py` (status, board, and attestation transport under `72-motion-video-plus/references/status-and-delivery.md`).
- Skill 45 (`45-design-intelligence-library/SKILL.md`): the scope section names the one legal crossing with Skill 72, the explicit style-analysis bridge in `72-motion-video-plus/references/design-intelligence-bridge.md`. Skill 45 performs no motion work and Skill 72 never re-scores a style card.
- Presentation roles: the governed-motion audit (SOP 9.5 in the pptx-assembly specialist's SOPs) already states the shipped contract, including PowerPoint playback as UNVERIFIED on every platform; MG-042 verified it against `references/integration-contracts.md` and changed nothing there.
- The map entry's description (this file's step 2 object, mirrored in the canonical map) is the managed guidance every generated role block derives from; `72-motion-video-plus/scripts/check_authority.py` fails if the two copies drift or the obsolete V1 description returns.
