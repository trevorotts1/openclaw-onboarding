# Skill 42 — Personal Assistant Library — Changelog

## 1.0.5 — 2026-07-05

Materialization contract hardening (FIX-XC-11b, FIX-S36-19, FIX-S36-20).

- **Mandatory closing Command Center converge (FIX-XC-11b).** Materialization never ran
  the CC converge, so a materialized specialist could land in the workspace un-registered.
  Added a fail-soft closing `sync-extensions.sh --converge` step to INSTALL.md §3 and
  INSTRUCTIONS.md §2 (skipped when Skill 32 is absent), plus QC doc-truth asserts that
  both docs wire it and a `--live` assert that the converge tool is reachable when a PA
  department is materialized.
- **Complete placeholder table + residual scan (FIX-S36-19).** INSTRUCTIONS.md §3
  documented only 8 placeholders while specialists use 40+ owner-data tokens (and the
  example fill pass substituted 2). Completed the owner-data placeholder table from the
  real inventory, split it from the runtime output-template slots (`{{PERCENT}}`,
  `{{WIN_1}}`, `{{COUNT}}`, … — filled each run, left in place), expanded the example
  fill pass, and added a post-materialization residual scan that **exits 1** on any
  surviving owner-data placeholder. A `--live` QC assert enforces zero residuals on a
  materialized department.
- **Specialist-19 QC tightened (FIX-S36-20 i).** `qc-personal-assistant-library.sh` and
  `scripts/verify-pa-install.sh` previously checked only 2 of Study Partner's role files;
  they now assert all 12 (the standard 6 + the 6 sub-role files). SKILL.md updated to match.
- **QC path resolution fixed (FIX-S36-20 ii).** `qc-personal-assistant-library.sh` now
  resolves its own dir absolutely, falls back to the skill's own dir when the installed
  copy is absent (repo/pre-deploy QC — sibling-43 pattern), and its lib-shared fallback
  sets `WORKSPACE=$HOME/.openclaw/workspace` (the old `$HOME/clawd` literal was bogus).
- No specialist content or SOP logic changed; all `{{TOKEN}}` templates unchanged.

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
