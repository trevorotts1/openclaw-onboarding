# Project CHANGELOG — {{PROJECT_NAME}}

**Project Slug:** {{project-slug}}
**Format:** Append-only. Each entry: `{iso_date} — {event} — {detail}`.

---

## Log

| Date | Event | Detail |
|------|-------|--------|
| {{ISO_DATE}} | PRD created | Chief Project Architect initialized PRD folder |

---

## Append Protocol

After every loop iteration that produces a commit:
```
{iso_date} — {work_item} — committed {commit_sha} — QC: {score}
```

After every handoff:
```
{iso_date} — Handoff — Package delivered to {building_dept}. Checklist: all {N} items ✅.
```

After every project stop:
```
{iso_date} — Project stopped — Reason: {max_loops|deadline|owner-decision}. Loop count: {N}/{max}.
```

After auto-kill:
```
{iso_date} — Cron killed — Project {slug}. Final status: {status}.
```
