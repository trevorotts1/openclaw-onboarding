# Project Checklist — {{PROJECT_NAME}}

**Project Slug:** {{project-slug}}
**Gate:** ≥8.5 QC score required on each item before marking done.
**Handoff condition:** ALL items ✅ → PAO runs Handoff SOP (SOP-08).

---

## Acceptance Checklist

Each item is derived from a Success Metric in `PRD.md`. Items are binary: done or not done. No partial credit.

- [ ] **Item 1** — {{GOAL_1_BINARY_TEST}}
  - QC Score: — / 10
  - Committed: —
  - Notes: —

- [ ] **Item 2** — {{GOAL_2_BINARY_TEST}}
  - QC Score: — / 10
  - Committed: —
  - Notes: —

- [ ] **Item 3** — {{GOAL_3_BINARY_TEST}}
  - QC Score: — / 10
  - Committed: —
  - Notes: —

---

## Verification Protocol

To mark an item ✅:
1. The deliverable exists on disk at the committed path.
2. The `qc-agent` has scored it ≥8.5 (score logged in this file).
3. The commit SHA is recorded in this file.
4. No acceptance criterion from `PRD.md` is unmet.

To mark an item ❌ (blocked):
- Log the reason in the Notes field.
- Notify owner if blocked for >4 hours.

---

## Auto-Handoff Trigger

When all items above are ✅, the Chief Project Architect automatically runs SOP-08 (Handoff to Building Department). The handoff package includes this file, `PRD.md`, `QC.md`, repo/PR links, and deploy URLs.
