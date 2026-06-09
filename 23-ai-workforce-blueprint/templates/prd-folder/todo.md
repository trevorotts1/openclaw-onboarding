# Work Queue — {{PROJECT_NAME}}

**Project Slug:** {{project-slug}}
**Loop gate:** only items with status `done` (QC ≥8.5 + committed) advance the checklist.
**Format:** `[status] Item title — Owner Role — QC Score — Commit SHA`

Status values: `open` | `in-progress` | `done` | `failed` | `blocked`

---

## Open Items

- [ ] `open` **{{WORK_ITEM_1}}** — {{OWNER_ROLE}} — QC: — — Commit: —
- [ ] `open` **{{WORK_ITEM_2}}** — {{OWNER_ROLE}} — QC: — — Commit: —
- [ ] `open` **{{WORK_ITEM_3}}** — {{OWNER_ROLE}} — QC: — — Commit: —

---

## In Progress

*(Items currently being worked by a spawned sub-agent)*

---

## Done

*(Items QC'd at ≥8.5 and committed — linked to checklist.md)*

---

## Failed / Blocked

*(Items that exceeded 3 QC loops or are blocked on external input — escalated to owner)*

---

## Notes

- One item at a time per loop iteration (Chief Project Architect picks the first `open` item each loop).
- Items move from `open` → `in-progress` when a sub-agent is spawned.
- Items move from `in-progress` → `done` only when QC score ≥8.5 AND commit SHA recorded.
- Never mark `done` without a commit SHA.
