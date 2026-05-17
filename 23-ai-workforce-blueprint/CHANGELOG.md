## [v10.4.0] — 2026-05-17 — Zero-Human Company Spec (PRD v2.1)

### Added
- `INSTRUCTIONS.md` rewritten for v2.1 — 30-question interview, 16 mandatory departments, 3 vertical packs
- `department-naming-map.json` reorganized into mandatory / vertical_packs / deprecated tiers
- `templates/universal-how-to-template.md` — 18-section template every role document follows
- `prompts/role-doc-generation-prompt.md` — sub-agent generation prompt with research protocol
- `suggested-roles/crm-suggested-roles.md` — CRM department roles including Email Deliverability flagship
- `suggested-roles/openclaw-maintenance-suggested-roles.md` — OpenClaw Maintenance department with recursive-modification guard
- `suggested-roles/social-media-suggested-roles.md` — Social Media organic department with 10 platform specialists
- `suggested-roles/paid-advertisement-suggested-roles.md` — Paid Advertisement department with 12 platform-specific ad specialists
- Persona Governance Override clause baked into INSTRUCTIONS.md (standard + CEO variant)

### Changed
- Interview density: ~50-65 questions → ~28-30 questions
- All assisting language preserved from v9.6.0: "I Don't Know" 6-step flow, hesitation detection, plain-English progress, pause/resume, specialist auto-staffing

### skill-version.txt
Bumped to `10.4.0`

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Replaced "say to your AI" instructions with a real multi-phase autonomous execution flow.
