# Skill 34 — Intelligent Staffing (ARCHIVED)

This skill is **archived** as of OpenClaw v6.0.0 — merged into Skill 23 (AI Workforce Blueprint). See `ARCHIVED.md` for the full reasoning + per-capability migration map.

**Short version:** Skill 34's three jobs (specialist classification, 5-layer persona alignment, package-tier assignment) now happen inline during Skill 23's workforce build OR at dispatch-time via `persona-selector-v2.py`. There is no separate post-build classification pass.

**Do not install this skill on a new onboarding.** It is preserved here only so that v5-era client states with `Skill 34: INSTALLED` markers in their `MEMORY.md` continue to resolve.

For all current capabilities that this skill previously provided, see:
- `ARCHIVED.md` — full migration map (what moved where)
- Skill 23 — workforce build + inline specialist classification (`determine_specialists()`)
- `persona-selector-v2.py` — dispatch-time 5-layer scoring (N16)
- Dashboard `intelligence-resolver.ts` — Hop 10 consumer
- `AGENTS.md` N16 / N20 / N21 — binding non-negotiables that govern persona placement
