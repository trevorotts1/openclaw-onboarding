# Module 1 — Planner (content calendar)

**Source:** `planner-sheet-creator` (6 nodes) + `planner-row-append` (5 nodes) +
`00-get-theme-of-week` (12 nodes). **Phases:** P1 (create + theme-sync) and P8 (row write-back).

LOCAL replacement for the n8n `social-planner-sheet-create` / `social-planner-row-append` webhooks —
removes a live infra dependency that Skill 35 still has. On client boxes the planner uses the
client's OWN Google credentials (PRD Open Decision D8: Google Sheets planner kept in 0.1.0).

## What it does

1. **Create** the "`<brandName>` Social Media Planner" sheet from the master template (once per brand).
2. **Theme-of-week sync** — write `themeOfWeek` into the local client config (replacing the
   `Clients_BCEO` n8n data table). This is the ONE `themeOfWeek` per brand; one weekly theme cron
   owns it (57 owns the theme cron; the Skill-35 `skill35-weekly-theme` Saturday cron is removed on
   migration).
3. **Write-back** — append the normalized **20-column** weekly row (`AF-SM-WRITEBACK-COLUMNS`):

   `Week Of, Theme, Research, Core Content, Images, Videos, Facebook, Instagram, LinkedIn, YouTube,
   TikTok, Pinterest, Carousels, Blog, Podcast, Email, QC, Scheduled, Overall, Notes`

## Contract

- P1 artifact `working/plan/plan.json` must carry a non-empty `themeOfWeek` + `plannerSheetId`.
- P8 artifact `working/plan/row_appended.json` must carry a `row` (or `columns`) list of **exactly
  20** values in the order above.

One state spine: ONE planner sheet per brand, ONE `themeOfWeek`, read by 57. A retained Skill 35
reads the same records — it never keeps a rival copy.
