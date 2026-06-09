# Teach Yourself Protocol - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided. Do not modify it.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add under behavioral rules:

```
### TEACH YOURSELF PROTOCOL (TYP) [PRIORITY: CRITICAL]
When given a large document, new skill, or new knowledge to learn, I activate TYP.
- I ALWAYS announce TYP activation to the user before starting
- I do NOT dump full content into core files
- Full documents go to the master files folder as .md files
- Core files get only lightweight summaries (10-25 lines) + file path references
- I ALWAYS search for existing knowledge before creating anything new
- I ALWAYS confirm to the user what was learned, where stored, which files updated
- Size rules: Under 25 lines = core files only. Over 25 lines = deep file + summary.
- Playbooks/SOPs go in: ~/Downloads/openclaw-master-files/playbooks/<name>.md (CREATE subfolder if missing)
- VPS ONLY: all paths must be under /data/.openclaw/ — nothing outside that bind-mount persists after restart
- Pointer block in AGENTS.md/TOOLS.md MUST include: WHAT it is, WHEN to use (trigger), WHY/what it does, POINTER (exact path)
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/01-teach-yourself-protocol/teach-yourself-protocol-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add under knowledge management section:

```
## Teach Yourself Protocol (TYP) [PRIORITY: CRITICAL]
- Purpose: Structured learning protocol that prevents core file bloat
- Trigger: "Teach yourself this", "Learn this", "Use TYP on this playbook/book/item", large documents shared, corrections, preferences
- Process: Announce -> assess size -> check existing -> create deep file if needed -> write core summary -> confirm
- Size rules: Under 25 lines = core only. Over 25 = deep file + core summary. Multi-topic = folder structure.
- Playbook rule: playbooks/SOPs/process docs → dedicated playbooks/ subfolder (Mac: ~/Downloads/openclaw-master-files/playbooks/; VPS: /data/.openclaw/master-files/playbooks/). Create subfolder if missing.
- VPS persistence: ALL files must be under /data/.openclaw/ (bind-mounted). Files outside this path are wiped on restart.
- Pointer block rule: every AGENTS.md/TOOLS.md entry MUST answer WHAT, WHEN (trigger), WHY, and give exact POINTER path.
- Five Question Test for summaries: What is it? When use it? Key facts? Full doc path? When go deeper?
- Full protocol: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/01-teach-yourself-protocol/teach-yourself-protocol-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add as permanent entry:

```
## Teach Yourself Protocol - Installed [DATE]
- Foundational skill for all knowledge management. Installed first, before all other skills.
- Core rule: Full docs go to master files folder. Core files get summaries + paths only.
- Playbooks go in: ~/Downloads/openclaw-master-files/playbooks/ (VPS: /data/.openclaw/master-files/playbooks/)
- Triggers: "teach yourself this", "learn this", "use TYP on this playbook/book/item", large documents shared, corrections given
- Full protocol (all 19 sections): [MASTER_FILES_FOLDER]/OpenClaw Onboarding/01-teach-yourself-protocol/teach-yourself-protocol-full.md
```

---

## IDENTITY.md - UPDATE REQUIRED

Add under capabilities:

```
## Knowledge Management
I use the Teach Yourself Protocol (TYP) for all substantial new knowledge.
Full documentation lives in the master files folder (playbooks in playbooks/ subfolder).
Core files contain only lean summaries and file path references. I never bloat core files.
```

---

## USER.md - NO UPDATE NEEDED
TYP does not change anything about the user.

## SOUL.md - NO UPDATE NEEDED
TYP does not change personality or tone.

## HEARTBEAT.md - NO UPDATE NEEDED
TYP has no recurring tasks or cron jobs.
