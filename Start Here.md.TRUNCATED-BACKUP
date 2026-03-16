# START HERE - OpenClaw Onboarding

## EXECUTION CHECKLIST (Do This Now)

**STEP 1: Verify Trigger**
```bash
grep "ONBOARDING PENDING" ~/clawd/AGENTS.md || echo "ERROR: No flag found"
```
If no flag: Stop. Tell user to run install script first.

**STEP 2: Check Resume State**
```bash
cat ~/.openclaw/onboarding/.onboarding-status 2>/dev/null
```
If skills marked INSTALLED/ALREADY_INSTALLED: Skip them. Resume from first incomplete.

**STEP 3: Test Parallel Capability**
Try spawning one test sub-agent. If it works → use PARALLEL mode. If fails → use SEQUENTIAL mode.

**STEP 4: Execute Installation**

### PARALLEL MODE (if sessions_spawn works):

**WAVE 1** (You do these):
- Install 01, 02, QMD, 03 sequentially
- Mark each: `echo "SKILL-XX: INSTALLED" >> ~/.openclaw/onboarding/.onboarding-status`

**WAVE 2** (Spawn 4 sub-agents simultaneously):
```
Agent A: 04,05,06,07
Agent B: 08,09,10,11
Agent C: 12,14,15,16,17,18,19,20,21 (skip 13 - archived)
Agent D: QC monitor
```
Wait for ALL to report INSTALLED before Wave 3.

**WAVE 3** (You do these):
- Install 22, 23 sequentially
- Skill 23: Notify user first, wait for response

**WAVE 4** (Spawn 2 sub-agents simultaneously):
```
Agent E: 24,25,26
Agent F: 27,28,29
```
Wait for ALL to report INSTALLED.

**WAVE 5** (You do these):
- Verify skill 15
- Final QMD index: `qmd update && qmd embed`
- Remove ONBOARDING PENDING from AGENTS.md
- Write "ONBOARDING COMPLETE" to MEMORY.md

### SEQUENTIAL MODE (if sessions_spawn fails):
Install 01→29 one at a time. Skip 13.

---

## DETAILED WAVE INSTRUCTIONS

### How to Install a Single Skill

For EVERY skill:
1. Find all .md files: `ls ~/.openclaw/onboarding/[skill-folder]/*.md`
2. Read SKILL.md, INSTALL.md, CORE_UPDATES.md
3. Execute steps exactly as written
4. Verify completion
5. Write status: `echo "SKILL-XX: INSTALLED" >> ~/.openclaw/onboarding/.onboarding-status`
6. Report: "Skill XX complete"

### How to Spawn Wave 2 Agents (Copy-Paste Ready)

**Agent A (04-07):**
```json
{
  "task": "Install skills 04,05,06,07 from ~/.openclaw/onboarding/. Read all .md files first. Report after each: 'Skill XX: [INSTALLED/FAILED]'. Write to ~/.openclaw/onboarding/.onboarding-status.",
  "label": "wave2-agent-a"
}
```

**Agent B (08-11):**
```json
{
  "task": "Install skills 08,09,10,11 from ~/.openclaw/onboarding/. Read all .md files first. Report after each: 'Skill XX: [INSTALLED/FAILED]'. Write to ~/.openclaw/onboarding/.onboarding-status.",
  "label": "wave2-agent-b"
}
```

**Agent C (12,14-21):**
```json
{
  "task": "Install skills 12,14,15,16,17,18,19,20,21 from ~/.openclaw/onboarding/. Skip 13. Read all .md files first. Report after each: 'Skill XX: [INSTALLED/FAILED]'. Write to ~/.openclaw/onboarding/.onboarding-status.",
  "label": "wave2-agent-c"
}
```

**Agent D (QC Monitor):**
```json
{
  "task": "Monitor ~/.openclaw/onboarding/.onboarding-status. Check every 60 seconds. Count skills marked INSTALLED. When count reaches 18 (skills 04-12,14-21), report 'Wave 2 complete'. If any FAILED found, report which ones.",
  "label": "wave2-qc-agent"
}
```

Spawn all 4 at once. Wait for QC agent to report "Wave 2 complete".

### How to Spawn Wave 4 Agents

**Agent E (24-26):**
```json
{
  "task": "Install skills 24,25,26 from ~/.openclaw/onboarding/. Read all .md files first. Report after each: 'Skill XX: [INSTALLED/FAILED]'. Write to ~/.openclaw/onboarding/.onboarding-status.",
  "label": "wave4-agent-e"
}
```

**Agent F (27-29):**
```json
{
  "task": "Install skills 27,28,29 from ~/.openclaw/onboarding/. Read all .md files first. Report after each: 'Skill XX: [INSTALLED/FAILED]'. Write to ~/.openclaw/onboarding/.onboarding-status.",
  "label": "wave4-agent-f"
}
```

Spawn both at once. Monitor status file until 29 skills marked complete.

---

## FAILURE HANDLING

**If a sub-agent reports FAILED:**
1. Note which skill failed
2. Try installing that skill yourself (sequential)
3. If it still fails: Mark as `SKILL-XX: FAILED - [reason]`
4. Continue with other skills
5. At end, report failed skills to user

**If Wave 2 QC times out (>45 min):**
1. Kill all Wave 2 sub-agents
2. Switch to sequential mode for remaining Wave 2 skills
3. Continue to Wave 3

**If sub-agent spawn fails at any point:**
Immediately switch to sequential mode. Do not try parallel again.

---

## WAVE DEPENDENCY ENFORCEMENT

**CRITICAL:** Each wave MUST complete before next starts.

**Enforcement method:** Check status file count before spawning next wave.

```bash
# Before Wave 2: Must have 3 skills (01,02,03) + QMD
count=$(grep -c "INSTALLED" ~/.openclaw/onboarding/.onboarding-status)
[ "$count" -ge 3 ] || echo "ERROR: Wave 1 not complete"

# Before Wave 3: Must have 21 skills (01-12,14-21) + 3 from Wave 1
count=$(grep -c "INSTALLED" ~/.openclaw/onboarding/.onboarding-status)
[ "$count" -ge 21 ] || echo "ERROR: Wave 2 not complete"

# Before Wave 4: Must have 23 skills
count=$(grep -c "INSTALLED" ~/.openclaw/onboarding/.onboarding-status)
[ "$count" -ge 23 ] || echo "ERROR: Wave 3 not complete"
```

---

## STATUS FILE FORMAT

Write to `~/.openclaw/onboarding/.onboarding-status` after EVERY skill:

```
SKILL-01: INSTALLED
SKILL-02: INSTALLED
SKILL-03: INSTALLED
SKILL-04: FAILED - missing API key
SKILL-05: SKIPPED - user requested
```

Valid statuses: INSTALLED, ALREADY_INSTALLED, FAILED, SKIPPED

---

## CRITICAL RULES

1. **Skills 22 and 23:** Main orchestrator ONLY. Never sub-agents.
2. **Skill 23:** Notify user first. Wait for response before proceeding.
3. **Skill 13:** Skip. It's archived.
4. **Core files:** Keep summaries to 10-25 lines. Full docs go to master-files.
5. **QMD indexing:** Run `qmd update && qmd embed` after Skills 22 and at final.
6. **Gateway restarts:** Never trigger autonomously. Ask user first.

---

## SKILL LIST

| # | Skill | Wave | Mode |
|---|-------|------|------|
| 01 | Teach Yourself Protocol | 1 | Sequential |
| 02 | Back Yourself Up Protocol | 1 | Sequential |
| 03 | Agent Browser | 1 | Sequential |
| 04 | Superpowers | 2 | Parallel (Agent A) |
| 05 | GHL Setup | 2 | Parallel (Agent A) |
| 06 | GHL Install Pages | 2 | Parallel (Agent A) |
| 07 | KIE Setup | 2 | Parallel (Agent A) |
| 08 | Vercel Setup | 2 | Parallel (Agent B) |
| 09 | Context7 | 2 | Parallel (Agent B) |
| 10 | GitHub Setup | 2 | Parallel (Agent B) |
| 11 | SuperDesign | 2 | Parallel (Agent B) |
| 12 | OpenRouter Setup | 2 | Parallel (Agent C) |
| 13 | Google Workspace Setup | SKIP | Archived |
| 14 | Google Workspace Integration | 2 | Parallel (Agent C) |
| 15 | BlackCEO Team Management | 2 | Parallel (Agent C) |
| 16 | Summarize YouTube | 2 | Parallel (Agent C) |
| 17 | Self-Improving Agent | 2 | Parallel (Agent C) |
| 18 | Proactive Agent | 2 | Parallel (Agent C) |
| 19 | Humanizer | 2 | Parallel (Agent C) |
| 20 | YouTube Watcher | 2 | Parallel (Agent C) |
| 21 | Tavily Search | 2 | Parallel (Agent C) |
| 22 | Book-to-Persona | 3 | Sequential |
| 23 | AI Workforce Blueprint | 3 | Sequential |
| 24 | Storyboard Writer | 4 | Parallel (Agent E) |
| 25 | Video Creator | 4 | Parallel (Agent E) |
| 26 | Caption Creator | 4 | Parallel (Agent E) |
| 27 | Video Editor | 4 | Parallel (Agent F) |
| 28 | Cinematic Forge | 4 | Parallel (Agent F) |
| 29 | GHL Convert and Flow | 4 | Parallel (Agent F) |

---

## COMPLETION CHECKLIST

- [ ] All 29 skills installed (or marked FAILED/SKIPPED)
- [ ] QMD indexed: `qmd status` shows all collections
- [ ] ONBOARDING PENDING removed from AGENTS.md
- [ ] ONBOARDING COMPLETE written to MEMORY.md
- [ ] Final report sent to user
