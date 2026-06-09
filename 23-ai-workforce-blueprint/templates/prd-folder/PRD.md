# PRD — {{PROJECT_NAME}}

**Project Slug:** {{project-slug}}
**Owner:** {{OWNER_NAME}}
**Created:** {{ISO_DATE}}
**Department:** Project Architecture Office (PAO)
**Status:** draft | active | complete | abandoned

---

## Problem

{{ONE_PARAGRAPH — What problem does this project solve? What does the owner want to change, create, or fix? Be specific about the current state and the desired future state.}}

---

## Goals

List goals as binary-verifiable statements. WRONG: "the site should be fast." RIGHT: "homepage loads in <2 seconds on a 4G connection (measured via Lighthouse)."

1. {{GOAL_1 — binary verifiable}}
2. {{GOAL_2 — binary verifiable}}
3. {{GOAL_3 — binary verifiable}}

---

## Scope

What is IN this project:
- {{IN_SCOPE_1}}
- {{IN_SCOPE_2}}

---

## Non-Goals

What is explicitly NOT in this project (helps prevent scope creep):
- {{OUT_OF_SCOPE_1}}
- {{OUT_OF_SCOPE_2}}

---

## Success Metrics

Each metric maps to a checklist item in `checklist.md`. Must be measurable and binary.

| Metric | Target | How Measured | Checklist Item |
|--------|--------|--------------|----------------|
| {{METRIC_1}} | {{TARGET}} | {{MEASUREMENT_METHOD}} | Item #1 |
| {{METRIC_2}} | {{TARGET}} | {{MEASUREMENT_METHOD}} | Item #2 |

---

## Milestones

| Milestone | Deliverable | Owner Role | Target Date |
|-----------|-------------|------------|-------------|
| M1 | {{DELIVERABLE_1}} | {{ROLE}} | {{DATE}} |
| M2 | {{DELIVERABLE_2}} | {{ROLE}} | {{DATE}} |

---

## Tech Stack

{{DESCRIBE the technology choices: language, frameworks, hosting, key services, APIs. Be specific — "React + Next.js deployed on Vercel, GHL forms for lead capture, Stripe for payments."}}

---

## Constraints

- **Timeline:** {{DEADLINE}}
- **Budget:** {{BUDGET or "owner approval required for Tier 3 models"}}
- **Tech:** {{Any hard technology constraints — must use X, cannot use Y}}
- **Access:** {{API keys available, staging environments, etc.}}

---

## Building Department

After PAO completes this PRD and all checklist items are green, the project hands off to:

**{{BUILDING_DEPT_SLUG}}** — {{reason: why this department executes the build}}

---

## CHANGELOG

| Date | Change | Who |
|------|--------|-----|
| {{ISO_DATE}} | PRD created | Chief Project Architect |
