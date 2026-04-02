# QC Checklist - Skill 15: BlackCEO Team Management
**Version:** v6.5.6

Run this after installation. Every section must pass before you mark team management complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/15-blackceo-team-management"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `TEAM_CONFIG.md`, `blackceo-team-management-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.6`

---

## 2. Installed routing file checks

```bash
ls -l ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md
ls -l ~/clawd/WORKFLOW_AUTO.md
ls -lt ~/Downloads/openclaw-backups 2>/dev/null | head
jq empty ~/.openclaw/openclaw.json
```

- [ ] Installed `TEAM_CONFIG.md` exists at `~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md`
- [ ] Installed `WORKFLOW_AUTO.md` exists at `~/clawd/WORKFLOW_AUTO.md`
- [ ] Backup of config exists before edits
- [ ] `openclaw.json` is valid JSON after edits

### 2A. Placeholder check
```bash
rg -n '\[[^]]+\]' ~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md ~/clawd/WORKFLOW_AUTO.md ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```

- [ ] No placeholder values like `[TEAM_MEMBER_1_ID]` remain
- [ ] Team rows use real names, roles, and Telegram IDs

---

## 3. Allowlist checks

```bash
jq '.channels.telegram.allowFrom' ~/.openclaw/openclaw.json
```

- [ ] `channels.telegram.allowFrom` exists and is an array
- [ ] Every Telegram ID in `TEAM_CONFIG.md` appears in `allowFrom`
- [ ] No placeholder strings remain in `allowFrom`
- [ ] Client IDs that should message the bot are included

**PASS:** The bot can actually receive messages from every approved person.

---

## 4. Core file update checks

```bash
grep -n "Team Management\|Dispatcher\|TEAM_CONFIG\|WORKFLOW_AUTO" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```

- [ ] `AGENTS.md` includes dispatcher rules and points to both `~/clawd/WORKFLOW_AUTO.md` and `~/.openclaw/skills/15-blackceo-team-management/TEAM_CONFIG.md`
- [ ] `TOOLS.md` explains directed sends and DM-only default reply routing
- [ ] `MEMORY.md` stores the critical team IDs so the agent remembers them next session
- [ ] Core files do not contain the entire full protocol pasted in

---

## 5. Functional routing tests

These tests must be done with real Telegram senders.

### 5A. Allowed sender test
- [ ] Send a message from each approved Telegram ID
- [ ] The bot responds to each approved sender
- [ ] Reply goes back to the same sender who asked

### 5B. Isolation test
Use two different approved senders.
- [ ] Sender A asks for a specific fact only they know
- [ ] Sender B asks what Sender A said
- [ ] Bot does **not** leak Sender A context to Sender B unless explicitly instructed through dispatcher flow

### 5C. Unapproved sender test
- [ ] Send a message from a Telegram ID not in `allowFrom`
- [ ] Bot ignores or rejects the message as expected

### 5D. Directed-send test
- [ ] From an approved sender, request: "Send [name] this message"
- [ ] Dispatcher routes the outbound message to the correct Telegram ID
- [ ] Directed send does not change default DM reply behavior for future replies

---

## 6. Trevor completion message check

INSTALL.md requires a completion confirmation back to Trevor's DM.

- [ ] Confirmation message was sent to Telegram chat `5252140759`
- [ ] Message listed the exact IDs read back from `allowFrom`
- [ ] Message confirmed placeholders were removed

---

## 7. Failure conditions

Fail this skill if any of these happen:

- [ ] `skill-version.txt` is wrong
- [ ] Any placeholder survives in config or docs
- [ ] A team member ID is missing from `allowFrom`
- [ ] Replies go to the wrong sender
- [ ] One worker leaks another worker's context without explicit dispatch instruction
- [ ] Core files only store IDs in `WORKFLOW_AUTO.md` and nowhere else

---

## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Installed routing files exist and contain real data
- [ ] `allowFrom` includes every approved team ID
- [ ] Core docs preserve the dispatcher rules and team memory
- [ ] Allowed, blocked, isolation, and directed-send tests all pass
- [ ] Trevor received the required completion confirmation
