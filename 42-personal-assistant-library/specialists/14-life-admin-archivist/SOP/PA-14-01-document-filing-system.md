# PA-14-01 — Document Filing System

**Department:** Life-Admin Archivist
**SOP ID:** PA-14-01 | **Token:** {{TOKEN}}
**Version:** 1.1.0 | **Last Updated:** 2026-06-03

---

## Purpose

Establish a consistent, searchable, low-friction system for storing, naming, and organizing all personal and business documents — digital files, cloud storage, email attachments, scanned paperwork, shared repos — so nothing is ever "lost in a folder" again.

## Trigger

Any new document enters {{TOKEN}}'s ecosystem (download, scan, email attachment, shared file, screenshot, form, contract, receipt).

## Inputs / Prerequisites

- macOS Finder (with Tags enabled) or equivalent file browser
- Google Drive access (via service account or browser)
- Scanner Pro (iOS) or equivalent for paper-to-PDF
- Hazel or equivalent automation tool (optional but recommended)
- Folder hierarchy pre-created (see Define step)

---

## DMAIC Procedure

### Define

1. **Establish the single root folder** — `~/Documents/` or equivalent cloud root. Announce: "All documents flow through this system. No exceptions."
2. **Confirm the folder hierarchy exists:**
   ```
   ~/Documents/
   ├── Personal/
   │   ├── Finance/ (Taxes, Banking, Insurance, Investments)
   │   ├── Health/
   │   ├── Home/
   │   ├── Legal/
   │   └── Education/
   ├── Business/
   │   ├── Legal-Entities/
   │   ├── Contracts/
   │   ├── Financials/
   │   ├── HR/
   │   └── Clients/{ClientName}/
   └── Archive/ (inactive, read-only)
   ```
   No file lives at root. Every document has a home within three clicks.
3. **State the naming convention** so every team member follows one format: `YYYY-MM-DD — [Type] — Sender/Entity — Description.ext`
   - Date always leads (ISO 8601).
   - Use spaces and human-readable names — no `final_v3_REVISED_2.pdf`.
   - Truncate at 80 characters.
4. **Define tagging taxonomy** — apply where platform supports (macOS Tags, Drive labels, Notion properties):
   `active` | `reference` | `tax-related` | `expires-YYYY-MM` | `signed`
5. **Set version-control rule:** Drafts append `— v2`, `— v3`. Never "final." Once signed/locked, move drafts to Archive; keep only the finalized version in the active folder. For collaborative docs, rely on built-in version history.

### Measure

6. **Count loose files at root** — `ls ~/Documents/* | wc -l`. Baseline the number. Target: zero.
7. **Sample the five most recently modified files** across the hierarchy. Check each against the naming convention. Record pass/fail.
8. **Count items in the Downloads folder.** Baseline.
9. **Check Archive last-review date** — is it within the last 90 days? Record.
10. **Scan for banned filename patterns** — search for "final," "REVISED," "copy," "v1 old," "untitled." Count hits.

### Analyze

11. **Identify failure clusters:**
    - Are loose files concentrated in Desktop, Downloads, or a specific project folder?
    - Are naming-convention failures clustered by document type (e.g., scanned PDFs vs. downloaded PDFs)?
    - Is the Archive overdue because the annual review didn't fire, or because the review happened but wasn't logged?
12. **Root-cause each cluster.** Example findings and fixes:
    - "Scanned PDFs never get renamed because Scanner Pro auto-names them `Scan_2026-06-03.pdf`" → fix in Improve step.
    - "Email attachments pile up because there's no auto-save-to-Drive rule" → fix in Improve step.
    - "Collaborative docs create fork chaos because people download instead of using shared links" → fix in Improve step.
13. **Document the top 3 root causes** in the Filing System Health Log (a running note pinned in the Archive folder or a Notion page under Department 14).

### Improve

14. **Fix Scanner Pro naming:** Configure Scanner Pro to use a default naming template (`YYYY-MM-DD — Scan — [Description].pdf`) or add a Hazel rule that renames any `Scan_*.pdf` to the convention on arrival.
15. **Fix Downloads drift:** Create a Hazel rule (or weekly automation) that moves any file sitting in `~/Downloads/` >7 days into an `~/Documents/Inbox/` folder — and if Inbox exists, add Inbox processing to the Sunday ritual.
16. **Fix email-attachment chaos:** Set up a Gmail filter that labels emails with attachments as "Has-Attachment." During the Sunday sweep, process that label folder: download-and-file or delete-and-archive each attachment email.
17. **Fix collaborative-doc fork chaos:** For shared Google Docs, add a pinned comment that says "DO NOT DOWNLOAD — use File > Make a Copy in Drive." For shared repos, pin a README with the link.
18. **Fix Archive staleness:** Add a recurring quarterly calendar event "Archive Review" that links to the health log. After each review, update the `Last Archive Review: YYYY-MM-DD` field in the health log.
19. **Implement the Sunday Capture Ritual** if not already running. Every Sunday evening: sweep Downloads, Desktop, email attachments labeled "Has-Attachment," and phone photos. File or delete every item. Zero Downloads = the goal.
20. **After each improve action, re-Measure** — did the root-cause metric drop? If yes, lock in the fix (move to Control). If no, try the next candidate fix or escalate.

### Control

21. **Weekly CTQ self-audit:** Every Monday morning, run the Measure checklist (steps 6–10). Log results in the Filing System Health Log. Green if all 5 CTQ checks pass; yellow if 1–2 fail; red if 3+ fail.
22. **Red-status trigger:** If red, execute the Improve loop (steps 14–20) within the same week. Do not let red status carry into the next Monday.
23. **Monthly health report** to {{TOKEN}} via Specialist 09 (Daily Check-In): one line — "Filing health: [Green/Yellow/Red], [X] loose files, [Y] naming violations, Downloads [clean/dirty], Archive [current/stale]."
24. **Archive audit:** Review Archive annually. Shred documents past the 7-year retention window unless tax or legal hold applies. Document the shred date and reason in the health log.
25. **Tooling refresh:** Every 6 months, verify Hazel rules are still running, Scanner Pro is configured, and Google Drive sync is healthy. Fix or replace any broken automation.

---

## Tools

| Tool | Purpose |
|------|---------|
| macOS Finder + Tags | Local organization |
| Google Drive | Collaborative docs |
| Hazel (macOS) | Automated sorting |
| Scanner Pro (iOS) | Paper-to-PDF |
| Google Drive for Desktop | Cloud sync |

---

## CTQ Checks (Critical-to-Quality)

- [ ] Root folder structure exists and contains zero loose files
- [ ] Five most recent documents follow naming convention (YYYY-MM-DD — Type — Entity — Description)
- [ ] Downloads folder contains zero items
- [ ] Archive folder reviewed within the last 90 days
- [ ] No file named with "final," "REVISED," "copy," "untitled," or "v1 old" in its name

---

## Metrics

| Metric | Target | Frequency |
|--------|--------|-----------|
| Loose-file count at root | 0 | Weekly (Monday scan) |
| Naming-convention compliance | 100% (5/5 sampled) | Weekly (Monday scan) |
| Downloads-folder item count | 0 | Weekly (Sunday ritual) |

---

## Escalation

- Root folder structure corrupted or missing critical folders → flag to {{TOKEN}} via Specialist 09 (Daily Check-In); rebuild within 24 hours
- Document misfiled during retrieval → move to correct location; if pattern (3+ per week), cc Specialist 14's PA-14-04 (Capture Flow) for intake-process review
- Shared Drive/cloud permission issue → escalate to Specialist 14's PA-14-03 (Account & Credential Hygiene) for credential/access verification
- Physical document index out of date (>30 days) → flag for Sunday ritual; escalate to PA-14-04 if backlog exceeds 10 unfiled items
- CTQ red status (3+ failures) two weeks in a row → escalate to {{TOKEN}} with root-cause summary and proposed fix plan

## Definition of Done

Every document {{TOKEN}} owns is findable in under 60 seconds — named consistently, filed correctly, Downloads folder empty, Archive current, and the Monday health scan shows green.

## Tone & Persona Note

You're building the system Future {{TOKEN}} will bless you for at 11 PM when she needs one specific document. Filing isn't clerical — it's peace-of-mind infrastructure. Every file named well is a small act of care. For the Black woman professional juggling personal finances, business contracts, family paperwork, and community obligations, a clean filing system says: "I've got this. Nothing falls through the cracks." Lead with warmth, celebrate green weeks, and treat a red week as a system improvement opportunity — never a personal failure.

*Generated by Life-Admin Archivist | Department 14 | {{TOKEN}}*
