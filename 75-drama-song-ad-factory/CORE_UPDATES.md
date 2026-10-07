# Skill 75: Drama Song Ad Factory - CORE_UPDATES

## Core .md files this skill is allowed to update

- `AGENTS.md`
- `TOOLS.md`
- `MEMORY.md`

Do NOT update any other core file for this skill unless the user
explicitly requests it. In particular never touch `SOUL.md`,
`IDENTITY.md`, `USER.md`, `HEARTBEAT.md`, or the shared core files
documented in `docs/SHARED-CORE-FILES.md`.

Apply only the labeled sections below, to the labeled files only - no
other edits, no reformatting of surrounding text.

## What to add (exact text)

### AGENTS.md

Add this rule:

```md
## Drama Song Ad Factory (Skill 75) - Song Ad Production Rules
- Route: song-driven direct-response ads only -> Skill 75; motion graphics -> motion-video-plus; landing pages -> blackceo-signature-page; plain KIE dispatch -> 74-kie-live-adapter
- Every intake/preflight/resume runs through scripts/core/intake_preflight/factory.py (exit map: ok 0, error 1, waiting 2, parked 3, rejected 4) - no runtime prompt bypasses a failed guard
- No recorded spend ceiling = no paid call; uncertain submissions are reconciled, never auto-resubmitted
- A maker never judges its own output; UNAVAILABLE never becomes PASS
```

### TOOLS.md

Add this section:

```md
## Drama Song Ad Factory (Skill 75)

- Location: `~/.openclaw/skills/75-drama-song-ad-factory/` (VPS: `/data/.openclaw/skills/75-drama-song-ad-factory/`)
- Purpose: end-to-end drama-song ad production - intake, preflight, storyboard, KIE music/image/video generation, timed assembly, independent QC, delivery
- Control CLI: `python3 scripts/core/intake_preflight/factory.py intake|preflight ...` (stdlib only, JSON envelope `blackceo.intake-preflight/envelope/v1`)
- Prereq checker: `bash "$SKILLS_DIR/shared-utils/check-skill-prereqs.sh" "$SKILLS_DIR/75-drama-song-ad-factory"`
- Providers: music via Skill 68 (Suno), image Skill 66, video Skill 67, transport Skill 74, callbacks Skill 46, voice Skill 30
- Docs: INSTRUCTIONS.md (operating), EXAMPLES.md (verified commands), QC.md (checklist), INSTALL.md (install/update), PREREQS.json (executable mirror)
```

### MEMORY.md

Add this pointer:

```md
- Drama Song Ad Factory (Skill 75): `~/.openclaw/skills/75-drama-song-ad-factory/` - canonical mode name `drama-song-vsl`
```
