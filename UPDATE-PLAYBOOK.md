# BlackCEO System Update Playbook
# Version 1.5 | March 22, 2026

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

### STEP 4: INFRASTRUCTURE CHECK
Before touching skills, make sure the infrastructure scripts and dependencies from install.sh are up to date. The direct-to-agent method does not run install.sh, so you must do these checks manually:

**4a. Gemini Engine scripts:**
- Check if ~/.openclaw/workspace/scripts/gemini-indexer.py exists
- If it does NOT exist, or if the downloaded repo has a newer version, copy it:
  - From the downloaded repo: scripts/gemini-indexer.py → ~/.openclaw/workspace/scripts/gemini-indexer.py
  - Also copy gemini-search.py if it exists in the repo scripts folder
  - Make them executable

**4b. Python dependencies:**
- Check if the google-genai Python package is installed (try: python3 -c "import google.genai")
- If it is NOT installed, install it: pip3 install google-genai
- Also check for numpy (try: python3 -c "import numpy")
- If missing, install it: pip3 install numpy

**4c. Sub-agent configuration:**
- Check openclaw.json for the sub-agent settings:
  - maxSpawnDepth should be 4
  - maxConcurrent should be 20
  - maxChildrenPerAgent should be 20
- If any of these are missing or different, update them (follow config backup protocol first)

**4d. Model allow list:**
- Check openclaw.json for the model allow list. It should have these 10 models:
  - moonshot/kimi-k2.5
  - openrouter/moonshot/kimi-k2.5
  - openrouter/xiaomi/mimo-v2-pro
  - openrouter/xiaomi/mimo-v2-omni
  - openrouter/minimax/minimax-m2.7
  - openrouter/google/gemini-3.1-flash-lite-preview
  - openrouter/google/gemini-3-flash-preview
  - openai-codex/gpt-5.4
  - openrouter/perplexity/sonar-pro-search
  - openrouter/perplexity/sonar
- If any are missing, add them (follow config backup protocol first)
- Check the official OpenClaw docs (https://docs.openclaw.ai) for the correct config format before editing

### STEP 5: BUILD YOUR GAP REPORT
Compare what you have installed vs what is in the new repo:
- Which skills are NEW (you do not have them)?
- Which skills have been UPDATED?
- Which skills are UNCHANGED?
Write out the gap report.

### STEP 6: CREDENTIAL DEPENDENCY CHECK
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

### STEP 7: SKILL DEPENDENCY CHECK
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

### STEP 8: RISK ASSESSMENT
For each change that has all credentials and dependencies ready, assign a risk level:

**LOW RISK:** Brand new skill folder. Nothing existing gets touched.
→ Auto-apply. No approval needed.

**MEDIUM RISK:** An existing skill folder has updates. Skill files changed but does not require migration or affect company data.
→ Auto-apply. No approval needed.

**HIGH RISK:** Anything that could affect core files, requires a migration, or could break existing functionality.
→ STOP. Show exactly what the change is, what it affects, and why it is high risk. Ask for explicit approval before proceeding. Do NOT apply until you get a YES.

### STEP 9: APPLY LOW AND MEDIUM RISK CHANGES

**For UPDATED skills (MEDIUM):**
- Replace the old skill folder with the new version from the downloaded repo
- Check if the skill has a CORE_UPDATES.md (handled in Step 11)

**For NEW skills that you do not have at all (LOW):**
- Copy the entire skill folder from the downloaded repo into your skills directory
- Open the skill's INSTALL.md and follow the installation instructions step by step
- Each skill has its own INSTALL.md that tells the agent exactly how to set it up
- Some skills are just reference docs (copy and done). Others have setup steps (API configs, file creation, etc.)
- If the INSTALL.md requires a credential you do not have, mark it as BLOCKED and move on to the next skill
- After installation, check the skill's CORE_UPDATES.md and apply any core file additions (handled in Step 11)
- After installation, run the skill's QC.md checks if one exists to verify it installed correctly

### STEP 10: HANDLE HIGH RISK CHANGES
For each HIGH risk item:
- Show exactly what changed
- Explain what it affects and why it is flagged high risk
- Ask: "This is a high risk change. Do you want me to apply it? Please reply YES or NO."
- Do NOT proceed until you get an explicit YES
- If NO, skip it and move on

### STEP 11: CORE FILE UPDATES
For each new or updated skill, check for CORE_UPDATES.md inside the skill folder. If it exists:
- Read what it says to add to each core file
- If the content ALREADY EXISTS in your core file, skip it
- If the new content CONFLICTS with something already there, STOP. Report the exact conflict: what the update wants to add, what already exists, and what the problem is. Wait for a decision before changing anything.
- If it is new and does not conflict, APPEND it to the correct core file. Never delete or rewrite existing content.

### STEP 12: CHECK FOR MODEL OR CONFIG CHANGES
Some updates add new models, change auth profiles, or update openclaw.json settings. If the CHANGELOG mentions model or config changes:

**BEFORE making any config change:**
1. Run the config backup protocol (Skill 02) first. No exceptions.
2. Research the current OpenClaw documentation to verify the correct config format:
   - Official docs: https://docs.openclaw.ai
   - Official GitHub: https://github.com/openclaw/openclaw
3. Check the docs for:
   - The correct property names and structure for the config file
   - Any recently deprecated or renamed fields
   - The correct model ID format for the provider (e.g., openrouter/ prefix, :free suffix)
   - Any breaking changes between OpenClaw versions that affect config
4. Only AFTER you have verified the correct format from the official docs, proceed with the edit.

**When applying model or config changes:**
- Read the new configuration from the updated skill
- Compare against your current openclaw.json
- Add new models to the allow list using the verified format from the docs
- Do not remove existing models unless the CHANGELOG explicitly says to
- If a model change conflicts with existing config, flag it as HIGH RISK and ask before changing
- If the official docs show a different format than what the skill specifies, flag the discrepancy and ask before proceeding

### STEP 13: SENSITIVE ITEMS - CONFIRMATION REQUIRED
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

### STEP 14: POST-UPDATE VERIFICATION
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

### STEP 15: GATEWAY RESTART
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
