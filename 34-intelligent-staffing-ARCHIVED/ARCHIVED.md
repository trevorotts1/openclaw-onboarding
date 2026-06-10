# ARCHIVED — Skill 34: Intelligent Staffing

This skill has been merged into **Skill 23 (AI Workforce Blueprint)** as of the v6.0.0 onboarding package rewrite.

## What Skill 34 used to do

Skill 34 — "Intelligent Staffing" — was a standalone classification layer that ran *after* the workforce was already built. It answered three questions per role:

1. **Permanent or on-call?** — Is this role a 24/7 standing agent or an as-needed specialist?
2. **Which persona governs this role?** — Run the 5-layer scoring matrix (mission / owner_values / company_kpis / dept_kpis / task_fit) and pick the best persona from `coaching-personas/`.
3. **What package tier does this role get?** — Light / Standard / Heavy compute allocation per the role's expected workload.

The output was a per-role classification stamp written into `IDENTITY.md` (`specialist_type: permanent | on-call`, `assigned_persona: <slug>`, `package: light | standard | heavy`).

## What replaced it

All three Skill 34 capabilities now live inside **Skill 23**, not as a separate post-build pass:

| Old Skill 34 capability | Where it lives now |
|------------------------|--------------------|
| `specialist_type` classification (permanent vs on-call) | `23-ai-workforce-blueprint/scripts/build-workforce.py::determine_specialists()` — runs inline during the workforce build, not as a separate skill |
| 5-layer persona alignment (mission, owner_values, company_kpis, dept_kpis, task_fit) | `23-ai-workforce-blueprint/scripts/persona-selector-v2.py` — the canonical persona engine; resolves at dispatch time, not at install time |
| Package tier (light / standard / heavy) | `23-ai-workforce-blueprint/scripts/build-workforce.py::DEFAULT_MODEL_ASSIGNMENTS` — model class per department type, replaces the package tier concept |
| Per-role specialist templates (specialist-templates/ folder in this archive) | Templates are now generated dynamically by `build-workforce.py` from `RECOMMENDED_DEPARTMENTS` (canonical floor departments per the naming map — run `scripts/list-canonical-departments.py`) — no static template files |

## Why merge, not standalone

Three reasons:

1. **N5 (no self-QC) was hard to enforce when Skill 34 ran post-build.** The same agent that built the workforce (Skill 23) often re-ran Skill 34's classification, which violates the structural rule that QC happens in a different sub-agent. Merging the classification into the build pass means the QC sub-agent (a different model) scores against the final output once, not twice.

2. **Persona alignment moved from install-time to dispatch-time.** v7.0+ wires persona governance into every non-mechanical dispatch via `persona-selector-v2.py` (N16). The install-time stamp Skill 34 produced was redundant: the dispatch-time resolver consults `tasks.persona_id` and `persona_assignment` directly. Hop 10 in the dashboard's `intelligence-resolver.ts` is the consumer.

3. **Specialist classification has stable rules.** Whether a role is permanent vs on-call is determined by the workforce interview (Phase 2 of the interview script: "Which roles need 24/7 coverage?"), not by a separate scoring pass.

## Status

- **Archived:** v6.0.0 onboarding-package rewrite (March 2026).
- **Skill folder retained because:** several v5-era onboardings have `Skill 34: INSTALLED` markers in their `MEMORY.md` and `.onboarding-status` files. Removing this folder would break those backward-compat lookups during update checks.
- **Do NOT install this skill on a new onboarding.** It's not in the Wave plan, the QC framework, or the audit phase list. Skill 23 + the dispatch-time resolver cover everything Skill 34 used to do.
- **Do NOT update this folder going forward.** Persona alignment changes go to `persona-selector-v2.py`. Specialist-type changes go to `build-workforce.py::determine_specialists()`.

## Cross-references

- **Skill 23** (`23-ai-workforce-blueprint/`) — absorbed all 3 Skill 34 capabilities
- **`persona-selector-v2.py`** — canonical 5-layer scoring (Layer 5 task_fit is what Skill 34 used to score)
- **Dashboard `intelligence-resolver.ts`** — Hop 10 consumer; reads what the selector writes to `persona_assignment`
- **`AGENTS.md` N16 + N20 + N21** — the non-negotiables that govern persona placement (N16 binding rule, N20 makes the matrix bread-and-butter, N21 makes Hop 10 the keystone)
- **Audit Phase 16 + 17** — verify the matrix and Hop 10 both clear 9.0 thresholds (current: 9.28 / 9.08 as of v10.12.0 audit)

---

*v10.13.0 — closes audit Phase 4 finding "Skill 34 ARCHIVED.md was byte-identical to Skill 33's; needs Skill-34-specific context"*
