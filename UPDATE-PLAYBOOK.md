# BlackCEO System Update Playbook
# Version 1.1 | March 22, 2026

This playbook defines how updates are applied to an already-onboarded BlackCEO system. There are three ways to trigger an update. All three follow the same steps below.

## How Updates Get Triggered

### Method 1: Terminal (Manual)
The client or Trevor runs the update script directly in Terminal:
```
bash ~/.openclaw/workspace/scripts/update-skills.sh
```
The script follows this playbook automatically.

### Method 2: Direct-to-Agent (Trevor sends a message)
Trevor messages the client's agent on Telegram via Skill 15 (BlackCEO Management):

"There is an update available for your BlackCEO system. Follow the UPDATE-PLAYBOOK.md in the onboarding repo at https://github.com/trevorotts1/openclaw-onboarding to update yourself to the latest version."

The agent reads this playbook and executes it. No terminal. No client involvement.

### Method 3: Remote/Heartbeat (Scheduled)
Add this to the agent's HEARTBEAT.md:

"Every Sunday at 3 AM, check for updates: Go to https://github.com/trevorotts1/openclaw-onboarding, read the version file, compare it to your installed version. If there is a new version, follow UPDATE-PLAYBOOK.md."

The agent checks automatically on schedule and follows this same playbook.

---

## The Update Process (All Methods)

### STEP 1: RUN THE FULL BACKUP PROTOCOL
Before touching anything, run the Back Yourself Up Protocol (Skill 02). This means:
- Back up openclaw.json (the config with all models, API keys, auth profiles)
- Back up all 7 core .md files (AGENTS.md, MEMORY.md, SOUL.md, USER.md, IDENTITY.md, HEARTBEAT.md, TOOLS.md)
- Back up the skills folder
- Back up the secrets folder
- Save everything to the backup folder in Downloads with a human-readable timestamp
- Verify backups are not empty
- If any backup fails, STOP. Do not proceed. Fix the backup first.

### STEP 2: DOWNLOAD THE LATEST VERSION
Go to https://github.com/trevorotts1/openclaw-onboarding
Download the full repository. Save it to a temporary location. Do not overwrite your existing installation yet.

### STEP 3: READ THE CHANGELOG
Open CHANGELOG.md from the downloaded repo. Find your current version by reading the "version" file in your existing installation. Read every entry between your version and the latest. Make a list of what changed.

### STEP 4: BUILD YOUR GAP REPORT
Compare what you have installed vs what is in the new repo:
- Which skills are NEW (you do not have them)?
- Which skills have been UPDATED?
- Which skills are UNCHANGED?
Write out the gap report.

### STEP 5: RISK ASSESSMENT
For each change, assign a risk level:

**LOW RISK:** Brand new skill folder. Nothing existing gets touched. 
→ Auto-apply. No approval needed.

**MEDIUM RISK:** An existing skill folder has updates. Skill files changed but does not require migration or affect company data.
→ Auto-apply. No approval needed.

**HIGH RISK:** Anything that could affect core files, company department folders, custom SOPs, requires a migration, or could break existing functionality.
→ STOP. Show exactly what the change is, what it affects, and why it is high risk. Ask for explicit approval before proceeding. Do NOT apply until you get a YES.

### STEP 6: APPLY LOW AND MEDIUM RISK CHANGES
- Copy new skill folders (LOW) into your skills directory
- Replace updated skill folders (MEDIUM) with the new versions
- These are safe to apply without asking

### STEP 7: HANDLE HIGH RISK CHANGES
For each HIGH risk item:
- Show exactly what changed
- Explain what it affects and why it is flagged high risk
- Ask: "This is a high risk change. Do you want me to apply it? Please reply YES or NO."
- Do NOT proceed until you get an explicit YES
- If NO, skip it and move on

### STEP 8: CORE FILE UPDATES
For each new or updated skill, check for CORE_UPDATES.md inside the skill folder. If it exists:
- Read what it says to add to each core file
- If the content ALREADY EXISTS in your core file, skip it
- If the new content CONFLICTS with something already there, STOP. Report the exact conflict: what the update wants to add, what already exists, and what the problem is. Wait for a decision before changing anything.
- If it is new and does not conflict, APPEND it to the correct core file. Never delete or rewrite existing content.

### STEP 9: CHECK FOR MODEL OR CONFIG CHANGES
Some updates add new models, change auth profiles, or update openclaw.json settings. If the CHANGELOG mentions model or config changes:
- Read the new configuration from the updated skill
- Compare against your current openclaw.json
- Follow the config backup protocol (Skill 02) before editing openclaw.json
- Add new models to the allow list
- Do not remove existing models unless the CHANGELOG explicitly says to
- If a model change conflicts with existing config, flag it as HIGH RISK and ask before changing

### STEP 10: PROTECTED ITEMS - NEVER TOUCH
These are off-limits no matter what:
- Company department folders (anything inside "my AI company departments")
- Custom SOPs the client created
- Any file the client has customized beyond what the original skill installed
- Client personal data, contacts, or business information

### STEP 11: POST-UPDATE VERIFICATION
- If Skill 22 or 23 was updated, run the Gemini indexer to reindex personas
- Verify each updated skill folder is complete (check for INSTALL.md, SKILL.md, QC.md at minimum)
- Update the local version file to match the new version
- Write a summary report:
  - What was updated (list each skill and what changed)
  - What was skipped and why
  - What conflicts were found and how they were resolved
  - Whether a gateway restart is recommended

### STEP 12: GATEWAY RESTART
Do NOT restart the gateway yourself. Tell the client or Trevor: "The update is complete. You may want to restart your gateway for the new changes to take effect." Let them decide when to restart.

---

## Quick Reference: Risk Levels

| Risk | What It Means | Action |
|------|--------------|--------|
| LOW | New skill folder, nothing existing touched | Auto-apply |
| MEDIUM | Existing skill updated, no migration needed | Auto-apply |
| HIGH | Affects core files, company data, or needs migration | ASK first, wait for YES |

## Quick Reference: What Gets Protected

| Item | Rule |
|------|------|
| AGENTS.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite. Flag conflicts. |
| MEMORY.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite. Flag conflicts. |
| SOUL.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite. Flag conflicts. |
| USER.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite. Flag conflicts. |
| IDENTITY.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite. Flag conflicts. |
| HEARTBEAT.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite. Flag conflicts. |
| TOOLS.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite. Flag conflicts. |
| openclaw.json | Config backup protocol (Skill 02) BEFORE any edit. |
| Company dept folders | NEVER touch. Client work. |
| Custom SOPs | NEVER touch. Client work. |

## Conflict Resolution
If a CORE_UPDATES.md entry conflicts with existing content:
1. Do not change anything
2. Report the exact conflict
3. Show what currently exists and what the update wants to add
4. Wait for a decision before proceeding
5. Document the decision in the update log

## Update Log
After every update, append to ~/.openclaw/skills/.update-log:
- Date and time
- Previous version and new version
- What was applied (LOW + MEDIUM items)
- What was flagged HIGH and the decision made
- Any conflicts found and how they were resolved
- Whether gateway restart was recommended
