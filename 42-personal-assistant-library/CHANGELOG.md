# Skill 42 — Personal Assistant Library — Changelog

## 1.0.2 — 2026-07-01

Client-name redaction (fleet privacy invariant).

- `specialists/25-imposter-syndrome/how-to.md`: replaced real client account name in example coaching dialogue with generic "Meridian" placeholder.
- `specialists/16-motivation-momentum/IDENTITY.md`: replaced real client account name in core-principle example with "a major deal".
- No behavior change; all `{{TOKEN}}` template placeholders and SOP logic unchanged.

## 1.0.1

(internal patch — no changelog entry at time of release)

## 1.0.0 — 2026-06-03

Initial release. Ships the Personal Assistant Library as standalone Skill 42.

- 29 personal-life specialists under `specialists/` (inbox, calendar, daily briefing, tasks, meetings, research, brainstorming, coaching, emotional support, travel, finance, relationships, errands, life-admin, spiritual life, motivation, challenger, family, study partner, passion/purpose, clarity, YouTube teacher, goals, superwoman, imposter, therapeutic support, focus, celebration, greatness).
- Each specialist ships 6 role files (`00-START-HERE.md`, `IDENTITY.md`, `SOUL.md`, `governing-personas.md`, `how-to.md`, `ROSTER.md`) plus a `SOP/` folder. Specialist 19 (Study Partner) additionally ships 6 sub-specialist role files (`01-snippet-curator` … `06-study-partner-director`) alongside its standard 6-file set, for 12 role files. Total role files: 28 × 6 + 12 = 180.
- 162 DMAIC SOPs (`PA-NN-NN-slug.md`, consistently hyphen-slug named across all 29 specialists) + 29 `SOP/00-INDEX.md`.
- `specialists/_index.md` navigation index.
- `scripts/verify-pa-install.sh` + `qc-personal-assistant-library.sh` install QC.
- SKILL.md / INSTALL.md / INSTRUCTIONS.md / CORE_UPDATES.md / EXAMPLES.md.
- Additive to Skill 23; does NOT modify Skill 23. The optional `department-naming-map.json`
  auto-build patch is documented in INSTALL.md §5 and intentionally deferred to a product decision.
- All content uses `{{TOKEN}}` placeholders only. No client PII, scores, or working artifacts shipped.
  Coaching-scope crisis resources (988 / NAMI / DV Hotline) are public references, not PII.
