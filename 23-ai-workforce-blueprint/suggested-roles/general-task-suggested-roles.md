# General Task — Suggested Roles

**Department:** General Task
**Slug:** `general-task`
**Purpose:** Catches any task that doesn't fit a dedicated department, so nothing is ever dropped. Re-classifies low-confidence routing fallbacks, executes well-scoped one-off tasks, logs recurrence patterns, and recommends new standing departments when a task type recurs ≥4/month.

---

## Mandatory Roles (every General Task department)

| # | Slug | Title | Type | Purpose |
|---|------|-------|------|---------|
| 0 | `head-of-general-task` | Head of General Task | leadership | Triage lead — re-classifies fallback tasks, accepts genuinely novel tasks, escalates with ONE question |
| 1 | `generalist-operator` | Generalist Operator | on-call | Executes accepted one-off tasks; QC gate ≥8.5; short-lived |
| 2 | `triage-classifier` | Triage Classifier | on-call | Parallel re-classification during volume spikes; returns `{dept_slug, confidence, reason}` |
| 3 | `qc-specialist-general-task` | QC Specialist — General Task | qc | ≥8.5 gate for all General Task deliverables; runs on different model than writer (Rule 6) |
| 4 | `sop-writer` | SOP Writer | on-call | Authors new SOPs when recurring task types need codification |

---

## Role Library Status

All 5 roles are included in `templates/role-library/general-task/`. Added in v11.1.0.

---

## Routing

- **Routing priority:** `1` (lowest) — reached ONLY via the explicit low-confidence fallback in `department-router.ts` `comDispatch()` Step 3.5
- **Keywords:** intentionally empty (this dept is never SELECTED by keyword matching — only reached when all keyword + semantic routing fails)
- **CC canonical slug:** `general-task` (aliases: `general`, `misc`, `catch-all`)
