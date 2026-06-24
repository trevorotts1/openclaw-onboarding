# Skill 47: Movie Producer (Automated Video Production) — CORE_UPDATES

## Core files this skill is allowed to update

- `TOOLS.md`
- `MEMORY.md`

Do NOT update any other core files for this skill unless the user explicitly requests it.

## What to add (exact text)

### TOOLS.md

Add this section under the Video Skills Suite heading (create it if not present):

```md
## Video Skills Suite

### Movie Producer — Automated Video Production (Skill 47)
- Location: `~/.openclaw/skills/47-movie-producer/`
- Clone location (client box): `~/.openclaw/skills/47-movie-producer/OpenMontage/`
- Purpose: autonomous multi-pipeline video production — free documentary montage (real public-domain footage) or Kie.AI-powered image/video generation
- Use when: client needs a finished video produced end-to-end from a brief, script, or pipeline manifest
- Free path: `pipeline_defs/documentary-montage.yaml` (zero API keys)
- Kie path: set `KIE_API_KEY` in `.env` — all image/video generation routes through Kie.AI automatically
- Handoffs: captions → Skill 26, TTS → Skill 30, editorial → Skill 27
- AGPLv3: OpenMontage is cloned onto client box at install; source is never vendored into this template
```

### MEMORY.md

Add this pointer:

```md
## Video Skills Suite
- Movie Producer — Automated Video Production (Skill 47): `~/.openclaw/skills/47-movie-producer/`
  - Clone: `~/.openclaw/skills/47-movie-producer/OpenMontage/`
  - Free path: documentary-montage.yaml (zero keys)
  - Paid path: KIE_API_KEY only (client's own key)
```
