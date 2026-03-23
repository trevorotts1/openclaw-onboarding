# BlackCEO System Update Playbook
# Version 1.0 | March 22, 2026

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

"Every Sunday at 3 AM, check for updates: Go to https://github.com/trevorotts1/openclaw-onboarding, read the version file, compare it to your installed version. If there is a new version, follow UPDATE-PLAYBOOK.md. If all changes are LOW risk, apply them automatically. If any changes are MEDIUM or HIGH risk, message me with what changed and wait for approval."

The agent checks automatically on schedule and follows this same playbook.

---

## The Update Process (All Methods)

### STEP 1: BACKUP FIRST
Before anything else, back up your 7 core files:
- AGENTS.md
- MEMORY.md
- SOUL.md
- USER.md
- IDENTITY.md
- HEARTBEAT.md
- TOOLS.md

Copy them to a backup location with a timestamp in the filename. If anything goes wrong, you restore from these. Do not proceed until backup is confirmed.

### STEP 2: DOWNLOAD THE LATEST VERSION
Go to https://github.com/trevorotts1/openclaw-onboarding
Download the full repository. Save it to a temporary location. Do not overwrite your existing installation yet.

### STEP 3: READ THE CHANGELOG
Open CHANGELOG.md from the downloaded repo. Find your current version by reading the "version" file in your existing installation. Read every entry between your version and the latest version. Make a list of what changed.

### STEP 4: BUILD YOUR GAP REPORT
Compare what you have installed vs what is in the new repo:
- Which skills are NEW (you do not have them at all)?
- Which skills have been UPDATED (newer version in the repo)?
- Which skills are UNCHANGED?

Write out the gap report so it is clear what needs attention.

### STEP 5: RISK ASSESSMENT
For each change, assign a risk level:

**LOW RISK:** Brand new skill folder. Nothing existing gets touched. Safe to apply automatically.

**MEDIUM RISK:** An existing skill folder has updates. The skill files changed but core files are not affected. Show what changed and ask before applying.

**HIGH RISK:** Anything that could affect core files, company department folders, custom SOPs, or requires a migration. Do NOT apply. Show the details and wait for explicit approval.

### STEP 6: APPLY LOW RISK CHANGES
Copy new skill folders into your skills directory. These are safe because nothing existing gets touched.

### STEP 7: HANDLE MEDIUM RISK CHANGES
For each MEDIUM risk item:
- Show exactly what changed (old version vs new version)
- Explain what the change does
- Ask for approval before applying
- If approved, replace the skill folder with the updated version

### STEP 8: CORE FILE UPDATES (CAREFUL)
For each new or updated skill, check if it has a CORE_UPDATES.md file inside its folder. If it does:

1. Read what CORE_UPDATES.md says to add to each core file
2. Check if that content ALREADY EXISTS in your core file. If it does, skip it.
3. Check if the new content CONFLICTS with something already in your core file. If it does, STOP. Report the conflict:
   - What the CORE_UPDATES.md wants to add
   - What already exists that conflicts
   - Let the client or Trevor decide how to handle it
4. If it is new and does not conflict, APPEND it to the correct core file. Do not delete or rewrite anything that is already there.

### STEP 9: PROTECTED ITEMS - NEVER TOUCH
These are off-limits no matter what:
- Company department folders (anything inside "my AI company departments")
- Custom SOPs the client created
- Any file the client has customized beyond what the original skill installed
- The client's personal data, contacts, or business information

### STEP 10: POST-UPDATE VERIFICATION
- If Skill 22 or 23 was updated, run the Gemini indexer to reindex personas
- Verify each updated skill folder is complete (check for INSTALL.md, SKILL.md, QC.md at minimum)
- Update the local version file to match the new version
- Write a summary report:
  - What was updated (list each skill and what changed)
  - What was skipped and why
  - What needs attention or approval
  - Whether a gateway restart is recommended

### STEP 11: GATEWAY RESTART
Do NOT restart the gateway yourself. Tell the client: "The update is complete. You may want to restart your gateway for the new changes to take effect." Let them decide when to restart.

---

## Quick Reference: What Gets Protected

| Item | Rule |
|------|------|
| AGENTS.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite existing content. |
| MEMORY.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite existing content. |
| SOUL.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite existing content. |
| USER.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite existing content. |
| IDENTITY.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite existing content. |
| HEARTBEAT.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite existing content. |
| TOOLS.md | APPEND only via CORE_UPDATES.md. Never delete or rewrite existing content. |
| Company dept folders | NEVER touch. These are client work. |
| Custom SOPs | NEVER touch. These are client work. |
| Client personal data | NEVER touch. |

## Conflict Resolution
If a CORE_UPDATES.md entry says to add something that conflicts with existing content:
1. Do not change anything
2. Report the exact conflict to the client or Trevor
3. Show what currently exists and what the update wants to add
4. Wait for a decision before proceeding
5. Document the decision in the update log

## Update Log
After every update, append to ~/.openclaw/skills/.update-log:
- Date and time
- Previous version and new version
- What was applied
- What was skipped
- Any conflicts found and how they were resolved
- Whether gateway restart was recommended
