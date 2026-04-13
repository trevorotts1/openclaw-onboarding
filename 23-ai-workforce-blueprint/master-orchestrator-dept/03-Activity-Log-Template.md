# Activity Log Template — Master Orchestrator
**Version:** 1.0 | March 16, 2026

## Purpose
The master orchestrator maintains a running log of all cross-department activity. This log is appended to continuously throughout the day — not summarized at end of day.

The daily log lives at:
`my AI company departments/daily-company-logs/YYYY-MM-DD.md`

---

## Log Entry Format

```
HH:MM — [FromDept]→[ToDept]: [action description] [JobID] [status emoji]
```

**Status emojis:**
- 🔄 In progress / requested
- ✅ Delivered / complete
- ❌ Blocked / failed
- ⚠️ Delayed / needs attention

---

## Example Daily Log

```markdown
# Company Activity Log — 2026-03-16

## 09:00 — Day Started
09:00 — master-orchestrator: Day started. Active departments: Sales, Marketing, Video, Audio, Graphics.

## Cross-Department Activity
09:14 — video-dept→audio-dept: Voiceover requested for Product Launch video [VIDEO-20260316-001] 🔄
09:22 — sales-dept→creative-dept: 3-email follow-up sequence requested [SALES-20260316-002] 🔄
09:47 — marketing-dept→graphics-dept: 3 ad creative variants requested [MKTG-20260316-003] 🔄
10:15 — creative-dept→sales-dept: Follow-up email sequence delivered [SALES-20260316-002] ✅
11:32 — audio-dept→video-dept: Voiceover delivered [VIDEO-20260316-001] ✅
14:05 — graphics-dept→marketing-dept: Ad creative variants delivered [MKTG-20260316-003] ✅
15:30 — video-dept: Flagged edge case — no SOP exists for adding lower-third overlays. Creating new file. ⚠️
15:45 — master-orchestrator: Created video-dept/video-editor/06-How-to-Add-Lower-Third-Overlays.md. When-to map updated. ✅

## Decisions Made Today
15:30 — Decision: Lower-third overlay process documented as new SOP in video-dept.
```

---

## Gemini Engine Embed Schedule

- Current day's log: NEVER embedded mid-day (still being written)
- Previous day's log: Embedded every morning at day start
- Commands: `python3 ~/.openclaw/workspace/scripts/gemini-indexer.py` then `# Handled by gemini-indexer.py`
- Annual archive: Move completed year to `daily-company-logs/archive/YYYY/` and Gemini Engine embed the archive

---

## Log Retention Policy

- Current year: All logs stay in `daily-company-logs/`
- End of year: Move full year to `daily-company-logs/archive/YYYY/` and Gemini Engine embed
- Never auto-delete: Archiving only. Deletion is the owner's decision.
- Logs are searchable via Gemini Engine after embedding
