# BlackCEO System Update Playbook
# Version 1.3 | March 22, 2026

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

### STEP 5: CREDENTIAL DEPENDENCY CHECK
Before applying any changes, scan every new or updated skill for credential requirements. Check the skill's INSTALL.md, SKILL.md, and CORE_UPDATES.md for mentions of:
- API keys (e.g., GOOGLE_API_KEY, KIE_API_KEY, OPENROUTER_API_KEY)
- Tokens (e.g., PRIVATE_INTEGRATION_TOKEN, FISH_AUDIO_API_KEY)
- Passwords (e.g., service account credentials)
- OAuth profiles (e.g., openrouter:default, anthropic:default)

For each credential found:
1. Check ALL env file locations where credentials might be stored:
   - ~/.openclaw/.env
   - ~/.openclaw/secrets/.env
   - ~/.openclaw/workspace/secrets/.env
   - System environment variables
2. Check openclaw.json for auth profiles
3. If the credential EXISTS and is not empty, mark it as READY
4. If the credential is MISSING or empty, mark it as BLOCKED

If any skill has BLOCKED credentials:
- Do NOT install or update that skill yet
- Tell the client or Trevor: "Skill [name] requires [credential name] which is not configured. I need this before I can complete the update. Please provide the key/token/password."
- Continue with all other skills that have their credentials ready
- Keep a list of blocked skills and what they need

When the missing credential is provided:
- Add it to the appropriate env file
- TEST the credential before proceeding (make a simple API call to verify it works)
- Only after the test passes, proceed with installing the blocked skill
- If the test fails, tell the client or Trevor: "The [credential name] you provided did not work. I got this error: [error]. Please check the key and try again."

### STEP 6: SKILL DEPENDENCY CHECK
Some skills depend on other skills being installed or completed first. Before installing a skill, check its INSTALL.md for prerequisites.

Known dependencies:
- Skill 22 (Book-to-Persona): Run the Gemini indexer AFTER installation
- Skill 23 (AI Workforce Blueprint): Requires Skill 22 to be complete with indexed personas
- Skill 32 (Command Center): Requires Skill 23 interview to be COMPLETE (department folders must exist)

If a skill's dependency is not met:
- Do NOT install that skill yet
- Tell the client: "Skill [name] is available in this update, but it requires [dependency] to be completed first. Once you finish [dependency], I can install it."
- Continue with all other skills that have their dependencies met

Example for Command Center:
- If Skill 23 interview is not complete (no department folders exist), tell the client: "The BlackCEO Command Center is included in this update, but it requires your AI Workforce questions to be completed first. Once you finish the workforce interview, I can activate the Command Center for you."

### STEP 7: RISK ASSESSMENT
For each change that has all credentials and dependencies ready, assign a risk level:

**LOW RISK:** Brand new skill folder. Nothing existing gets touched.
→ Auto-apply. No approval needed.

**MEDIUM RISK:** An existing skill folder has updates. Skill files changed but does not require migration or affect company data.
→ Auto-apply. No approval needed.

**HIGH RISK:** Anything that could affect core files, requires a migration, or could break existing functionality.
→ STOP. Show exactly what the change is, what it affects, and why it is high risk. Ask for explicit approval before proceeding. Do NOT apply until you get a YES.

### STEP 8: APPLY LOW AND MEDIUM RISK CHANGES
- Copy new skill folders (LOW) into your skills directory
- Replace updated skill folders (MEDIUM) with the new versions
- These are safe to apply without asking

### STEP 9: HANDLE HIGH RISK CHANGES
For each HIGH risk item:
- Show exactly what changed
- Explain what it affects and why it is flagged high risk
- Ask: "This is a high risk change. Do you want me to apply it? Please reply YES or NO."
- Do NOT proceed until you get an explicit YES
- If NO, skip it and move on

### STEP 10: CORE FILE UPDATES
For each new or updated skill, check for CORE_UPDATES.md inside the skill folder. If it exists:
- Read what it says to add to each core file
- If the content ALREADY EXISTS in your core file, skip it
- If the new content CONFLICTS with something already there, STOP. Report the exact conflict: what the update wants to add, what already exists, and what the problem is. Wait for a decision before changing anything.
- If it is new and does not conflict, APPEND it to the correct core file. Never delete or rewrite existing content.

### STEP 11: CHECK FOR MODEL OR CONFIG CHANGES
Some updates add new models, change auth profiles, or update openclaw.json settings. If the CHANGELOG mentions model or config changes:
- Read the new configuration from the updated skill
- Compare against your current openclaw.json
- Follow the config backup protocol (Skill 02) before editing openclaw.json
- Add new models to the allow list
- Do not remove existing models unless the CHANGELOG explicitly says to
- If a model change conflicts with existing config, flag it as HIGH RISK and ask before changing

### STEP 12: SENSITIVE ITEMS - CONFIRMATION REQUIRED
The following items require confirmation before any changes. They are NOT blocked from updates, but the agent must explain what it wants to change and get a YES before touching them:

**Company department folders** (anything inside "my AI company departments" or department-named folders like marketing/, sales/, operations/):
- An update may need to add new files, update templates, or modify department configurations
- Before touching anything in these folders: explain exactly what will change, why the update requires it, and what the impact is
- Ask: "This update needs to modify [file] in your [department] folder. Here is what it will change: [details]. Should I proceed? Reply YES or NO."
- If NO, skip it and note it in the summary

**Custom SOPs the client created:**
- If an update touches a file the client has customized, flag it
- Show the difference between the original and what the client changed
- Ask before overwriting. Offer to merge if possible.

**Any file the client has customized beyond the original skill install:**
- Same rule. Flag it, explain the change, ask for confirmation.

### STEP 13: POST-UPDATE VERIFICATION
- If Skill 22 or 23 was updated, run the Gemini indexer to reindex personas
- Verify each updated skill folder is complete (check for INSTALL.md, SKILL.md, QC.md at minimum)
- Update the local version file to match the new version
- Write a summary report:
  - What was updated (list each skill and what changed)
  - What was skipped and why
  - What credentials are still missing (blocked skills)
  - What dependencies are not yet met (blocked skills)
  - What sensitive items were flagged and the decisions made
  - What conflicts were found and how they were resolved
  - Whether a gateway restart is recommended

### STEP 14: GATEWAY RESTART
Do NOT restart the gateway yourself. Tell the client or Trevor: "The update is complete. You may want to restart your gateway for the new changes to take effect." Let them decide when to restart.

---

## Quick Reference: Risk Levels

| Risk | What It Means | Action |
|------|--------------|--------|
| LOW | New skill folder, nothing existing touched | Auto-apply |
| MEDIUM | Existing skill updated, no migration needed | Auto-apply |
| HIGH | Affects core files or could break functionality | ASK first, wait for YES |
| BLOCKED (credential) | Missing API key, token, or password | STOP. Ask for credential. Test before proceeding. |
| BLOCKED (dependency) | Prerequisite skill not complete | STOP. Tell client what needs to be done first. |
| SENSITIVE | Company departments, custom SOPs, customized files | Explain the change, ASK for confirmation. |

## Quick Reference: Core Files

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

## Credential Dependency Check - Where to Look

| Location | What Lives There |
|----------|-----------------|
| ~/.openclaw/.env | Primary env file |
| ~/.openclaw/secrets/.env | Secondary env file |
| ~/.openclaw/workspace/secrets/.env | Workspace secrets |
| System environment variables | Exported vars |
| ~/.openclaw/openclaw.json | Auth profiles, model configs |
| ~/.openclaw/agents/main/agent/auth-profiles.json | Registered auth profiles |

Check ALL of these. Do not stop after the first one. A credential might be in any of them.

## Skill Dependencies

| Skill | Depends On | What Must Be True |
|-------|-----------|-------------------|
| Skill 22 | Google API key | GOOGLE_API_KEY must exist in env |
| Skill 23 | Skill 22 complete | Personas must be indexed |
| Skill 32 | Skill 23 interview complete | Department folders must exist |

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
- What credentials were missing and which skills are blocked
- What dependencies were not met and which skills are waiting
- What sensitive items were flagged and the decisions made
- Any conflicts found and how they were resolved
- Whether gateway restart was recommended
