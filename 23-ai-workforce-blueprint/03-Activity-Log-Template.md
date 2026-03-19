# Master Orchestrator — Activity Log Template
**Version:** 1.0 | March 16, 2026

## Purpose
The master orchestrator maintains a running daily log of all activity across the company. This log is appended to continuously throughout the day — not written at end of day. It captures every cross-department request, delivery, decision, and task completion.

---

## Log File Location

```
my AI company departments/
  daily-company-logs/
    YYYY-MM-DD.md        ← one file per day
    archive/
      YYYY/              ← annual archive
```

---

## Log Entry Format

Every entry is one line. Concise. No paragraphs.

```
HH:MM — [Source]: [Action] [JobID] [Status]
```

### Status Icons
- 🔄 In progress
- ✅ Completed / Delivered
- ❌ Failed or cancelled
- ⏳ Waiting on input
- 🔀 Re-routed to different department

---

## Example Daily Log

```markdown
# Daily Company Log — 2026-03-16

08:15 — master-orchestrator: Day started, checking pending requests
08:22 — marketing-dept→creative-dept: Email sequence brief sent [MKTG-20260316-001] 🔄
08:45 — video-dept→audio-dept: Voiceover requested for product launch [VIDEO-20260316-001] 🔄
09:30 — sales-dept→graphics-dept: 3 sales deck slides requested [SALES-20260316-001] 🔄
10:12 — creative-dept→marketing-dept: Email sequence delivered [MKTG-20260316-001] ✅
11:00 — audio-dept→video-dept: Voiceover delivered [VIDEO-20260316-001] ✅
11:45 — graphics-dept→sales-dept: Sales deck slides delivered [SALES-20260316-001] ✅
13:00 — marketing-dept: New campaign brief created, assigning to Creative + Graphics + Video
13:05 — marketing-dept→creative-dept: Campaign copy brief [MKTG-20260316-002] 🔄
13:06 — marketing-dept→graphics-dept: Campaign visuals brief [MKTG-20260316-003] 🔄
13:07 — marketing-dept→video-dept: Campaign video brief [MKTG-20260316-004] 🔄
15:30 — master-orchestrator: Edge case — client asked for audio transcription, no SOP exists
15:35 — master-orchestrator: Created 01-How-to-Transcribe-with-Whisper-Local.md in audio-dept
17:00 — master-orchestrator: End of day — 7 tasks completed, 3 in progress, 1 new SOP created
```

---

## QMD Integration

- Every morning: run `python3 ~/clawd/scripts/gemini-indexer.py` + `# Handled by gemini-indexer.py` on yesterday's completed log
- Current day's live log is never embedded mid-day
- End of year: move all daily logs to `archive/YYYY/` and QMD embed the archive

---

## Annual Archive Protocol

At the start of each new year:
1. Create `archive/[previous year]/` folder
2. Move all daily log files from the previous year into it
3. Run `python3 ~/clawd/scripts/gemini-indexer.py` + `# Handled by gemini-indexer.py` on the archive
4. Keep the archive permanently — never auto-delete
5. Deletion is the owner's decision only

---

## Rules

1. Log entries are appended in real time as things happen — never wait until end of day
2. Every cross-dept request and delivery gets a log entry
3. Every new SOP creation gets a log entry
4. Keep entries to one line — concise is the standard
5. Use Job IDs consistently to make searching easy
6. If QMD is not installed, daily logs still work — they're just plain .md files
