# ARCHIVED — Skill 11: SuperDesign

This skill is no longer part of the active OpenClaw onboarding (41 active skills as of v12.26.0). It is kept in the repo for historical reference only.

## Why this was archived

SuperDesign (superdesign.dev) was a v3/v4-era onboarding step that pre-installed an AI website design tool on every client box. Two things changed:

1. **Design Intelligence Library (Skill 45) supersedes it.** Skill 45 ships a full Design Intelligence Unit (DIU) — 13 specialist roles covering style analysis, deck generation, photo-shoot direction, brand systems, and motion design — backed by the operator's own image-generation endpoints (Kie.ai via Skill 07). SuperDesign was a third-party SaaS dependency; the DIU is self-contained and does not require a SuperDesign account.

2. **Operator heterogeneity.** Later onboardings service operators who have no use case for a third-party website-design tool. Forcing a SuperDesign setup created an onboarding cliff for those operators and added a dependency on an external CLI (`superdesign`) that has to be separately installed, logged into, and kept active.

## What replaced it

| Old Skill 11 capability | Where it lives now |
|------------------------|--------------------|
| AI website layout / landing-page design | Skill 45 DIU (style-analyst, deck-systems-specialist, generation-operator) |
| HTML / React code export | Skill 45 DIU render-dispatcher + Kie.ai (Skill 07) |
| Style guide document | Skill 45 DIU style-librarian + style-card library (SHORT/MEDIUM/LONG prompt tiers) |
| Funnel / booking-page design | Skill 45 DIU + Skill 29 (GHL Convert and Flow) for page publishing |
| Cloning an existing website | Agent Browser (Skill 03) + Skill 45 DIU |

## Status

- **Archived:** v12.26.0 (June 2026).
- **Skill folder retained because:** some v5/v6-era client onboardings may reference `Skill 11: SuperDesign` in their `MEMORY.md` or `.onboarding-status` files. Removing the folder would break backward-compat lookups during update checks.
- **Do NOT install this skill on a new onboarding.** It is not in the Wave plan, the QC framework, or the audit phase list.
- **Do NOT update this folder going forward.** Any design/UI capability change goes to Skill 45 (Design Intelligence Library).

## Cross-references

- **Skill 45** (`45-design-intelligence-library/`) — canonical design capability (DIU)
- **Skill 07** (`07-kie-setup/`) — image-generation backbone for the DIU
- **Skill 03** (`03-agent-browser/`) — Playwright-backed website cloning + scraping

---

*v12.26.0 — archived as part of Tavily + SuperDesign skills cleanup*
