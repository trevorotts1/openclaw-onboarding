# Changelog — Skill 37: ZHC Closeout

## [1.0.0] — 2026-05-23 — Initial release (shipped with onboarding v10.14.17)

### What's in this release
- `SKILL.md`, `INSTRUCTIONS.md`, `INSTALL.md`, `CORE_UPDATES.md`
- `scripts/run-closeout.sh` — top-level orchestrator
- `scripts/generate-infographics.sh` — KIE.AI gpt-image-1 (fallback nano-banana-pro)
- `scripts/generate-celebration-video.sh` — KIE.AI Veo 3.1 (veo3_fast default)
- `scripts/create-notion-closeout.sh` — Notion API 9-section page tree
- `scripts/send-telegram-celebration.sh` — 6-message paced delivery
- `templates/infographic-1-prompt.md`, `infographic-2-prompt.md`, `veo-prompt.txt`, `notion-page-tree.json`
- `skill-version.txt = 1.0.0`

### Why this exists
Before v10.14.17, the post-build pipeline had NO enforced closeout. Skill 23 wrote `buildCompletedAt`, then nothing — Skill 32 was supposed to fire by documentation, but documentation is not enforcement. Diagnosed today on Evelyn Bethune's VPS: build completed at 20:22, the client heard nothing. No celebration, no infographics, no closeout doc, no Command Center URL.

This skill is the state-machine-driven closeout layer. Same architectural pattern as the build-resume layer fixed the build-interruption gap in v10.14.16.

### What it delivers to the client
6 paced Telegram messages: announcement, structure infographic, workflow infographic, celebration video, Notion closeout doc link, Command Center URL. Plus a 9-section Notion page tree in the client's own workspace.

### Cost envelope
~$0.60 / client in KIE credits (worst case).
