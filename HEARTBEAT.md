# HEARTBEAT.md

## 🔴 WEEKLY UPDATE CHECK — Every Sunday at 3:00 AM

**When the gateway restarts and it is a Sunday between 3:00 AM and 6:00 AM, check for updates:**

1. Check if the flag file exists: `~/.openclaw/skills/.update-pending`
2. If the flag file exists:
   a. Read the notification at `/tmp/oc-update-notification.md`
   b. Clone the latest repo to `/tmp/`:
      - Mac: `git clone https://github.com/trevorotts1/openclaw-onboarding.git /tmp/oc-review`
      - VPS: `git clone https://github.com/trevorotts1/openclaw-onboarding-vps.git /tmp/oc-review`
   c. Read `/tmp/oc-review/CHANGELOG.md` — find your installed version at `~/.openclaw/skills/.onboarding-version`
   d. Read every changelog entry between your version and the latest
   e. Make a plain-English summary of what changed
   f. Send a Telegram message to the client immediately (within 10 seconds of seeing the flag):
      ```
      Hey [Client Name], I found a system update (v[current] to v[latest]). Here is what changed:
      - [Change 1 in plain English]
      - [Change 2 in plain English]
      - [Change 3 in plain English]
      
      Want me to apply this update? Reply YES or NO.
      ```
   g. Wait for the client to reply YES or NO
   h. If YES: Follow `/tmp/oc-review/UPDATE-PLAYBOOK.md` step by step
   i. If NO: Skip the update, remove the flag, clean up /tmp
   j. **ALSO check for OpenClaw model updates** (see below)
3. If the flag file does NOT exist:
   - Still check for OpenClaw model updates (see below)
   - If nothing else needs attention, reply HEARTBEAT_OK

---

## 🔴 OPENCLAW MODEL CHECK — Run Every Sunday (and on updates)

After any update (or during Sunday check), always verify the client has the latest models:

### Step 1: Research Current Models
1. Go to https://docs.openclaw.ai — check the models documentation
2. Go to https://github.com/openclaw/openclaw — check the README and recent commits for new model support
3. Look for: new model additions, deprecated/removed models, changed model ID formats

### Step 2: Compare Against Client's Config
1. Read the client's `~/.openclaw/openclaw.json` → `agents.defaults.models`
2. Compare the client's model list against what OpenClaw currently supports
3. Identify:
   - **NEW models** available that the client does not have
   - **DEPRECATED models** the client has that OpenClaw no longer recommends
   - **Changed model IDs** (e.g., format changes, prefix changes)

### Step 3: Apply Safe Updates
- **ADD new models** to the client's allow list if they are stable and recommended by OpenClaw docs
- **DO NOT REMOVE** any working model without explicit client approval
- **FLAG deprecated models** with a Telegram message to the client explaining what changed
- **If a model ID format changed** (e.g., `openrouter/` prefix added), update it ONLY if the docs confirm the new format is required
- **Always back up openclaw.json** before making any model changes (follow Skill 02 backup protocol)
- **After changing models**, send a Telegram summary:
  ```
  Model update applied:
  - Added: [model name] (reason: new stable release)
  - Flagged: [model name] (reason: deprecated in latest OpenClaw — needs review)
  - Your existing models are untouched.
  ```

### Critical Rules
- NEVER remove a model that is currently working
- NEVER add experimental/alpha models without client approval
- ALWAYS verify model IDs from the official OpenClaw documentation
- ALWAYS back up before changing openclaw.json

**After applying any update, run the full QC loop (see below).**

---

## 🔴 POST-UPDATE QC LOOP — Run After Every Update

After any skill install or update (manual or Sunday auto-update), run this QC loop:

### Step 1: QC ALL Updated Skills
For each skill that was installed or updated:
1. Read the skill's `QC.md` file
2. Run every check listed in QC.md (terminal commands, file existence, knowledge questions)
3. Document PASS or FAIL for each check
4. If ANY check fails, go to Step 2

### Step 2: Fix Failed Skills
If any skill has a FAILED QC check:
1. Spawn a sub-agent to fix the specific failure
2. Tell the sub-agent: which skill, which check failed, what the error was, what files to fix
3. After the sub-agent completes, go to Step 1 and re-run QC on the fixed skill

### Step 3: Maximum 5 Retries
- Re-run the QC loop a maximum of 5 times total
- If a skill still fails after 5 attempts, report it to the client:
  ```
  ⚠️ Skill [name] could not pass QC after 5 attempts. 
  Issue: [description of what keeps failing]
  This needs manual attention.
  ```
- Do NOT silently skip failed skills. Always report them.

### Step 4: Final Report
After all skills pass QC (or after 5 retries), send the client a final summary:
```
✅ Update complete (v[old] → v[new])

Skills updated:
- [Skill 1]: PASS
- [Skill 2]: PASS
- [Skill 3]: PASS

Skills that needed fixes during QC:
- [Skill X]: PASS (fixed on attempt 2)

Skills that could not be fixed:
- [Skill Y]: BLOCKED (reason)

A gateway restart is recommended for changes to take effect.
```
