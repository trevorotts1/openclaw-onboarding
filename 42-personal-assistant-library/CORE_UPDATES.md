# Skill 42 — CORE_UPDATES

What this skill appends to the client's workspace core files. Apply once on install.

---

## AGENTS.md (append)

```markdown
## Personal Assistant Library (Skill 42)

The Personal Assistant Library is installed at `~/.openclaw/skills/42-personal-assistant-library/`
(VPS: `/data/.openclaw/skills/42-personal-assistant-library/`). It ships 29 personal-life
specialists (inbox, calendar, coaching, emotional support, travel, finance, relationships,
spiritual life, goals, productivity) as ready-to-deploy sub-workspace templates.

Deploy specialists on demand — materialize the needed `specialists/<slug>/` folder into
`workspace/departments/personal-assistant/<slug>/`, fill placeholders from USER.md, then
follow that specialist's `00-START-HERE.md`. Each specialist's `ROSTER.md` declares its
summon conditions. Specialists 09 / 24 / 26 are coaching-scope ONLY — STOP and refer to
crisis resources (988 / NAMI / DV Hotline) on any crisis signal; never improvise past the
boundary. See the skill's INSTRUCTIONS.md for the full runtime guide.
```

## TOOLS.md (append)

```markdown
## Personal Assistant Library verifier (Skill 42)

- Verify install: `bash ~/.openclaw/skills/42-personal-assistant-library/scripts/verify-pa-install.sh`
  (VPS: `/data/.openclaw/skills/42-personal-assistant-library/scripts/verify-pa-install.sh`)
  Checks all 29 specialist folders, each specialist's 6 role files, and SOP presence.
- Full install QC: `bash ~/.openclaw/skills/42-personal-assistant-library/qc-personal-assistant-library.sh`
```

## MEMORY.md (append — once any specialist is deployed)

```markdown
PA Library: [N] specialist(s) active | deployed: [slug] | Skill 42
```

Update `[N]` and the deployed-slug list as specialists are materialized.
