# QC Checklist - Skill 15: BlackCEO Team Management
**Version:** v6.7.0

Run this after installation. Every section must pass before you mark team management complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/15-blackceo-team-management"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `TEAM_CONFIG.md`, `blackceo-team-management-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.6.0`

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

## 6. Operator completion message check

INSTALL.md requires a completion confirmation back to the operator's DM. The operator chat ID is resolved at runtime via `shared-utils/operator-chat-id.sh` (reads `env.vars.OPERATOR_TELEGRAM_CHAT_ID`, default `5252140759` for Trevor Otts).

```bash
# Confirm config key is set
openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID
```

- [ ] `env.vars.OPERATOR_TELEGRAM_CHAT_ID` is set in openclaw.json
- [ ] Confirmation message was sent to the resolved operator Telegram chat (default `5252140759` if not overridden)
- [ ] Message listed the exact IDs read back from `allowFrom`
- [ ] Message confirmed placeholders were removed

---

## 7. Remote Rescue agent + OPERATOR/OWNER SESSION ISOLATION (HARD gates)

These gates are auto-failed by `qc-blackceo-team-management.sh`. Per enforcement doctrine, a rule not auto-failed at the gate does not exist.

```bash
bash 15-blackceo-team-management/qc-blackceo-team-management.sh
```

### 7A. Agent presence and binding

```bash
openclaw config get agents.list | grep -A15 "remote-rescue"
openclaw config validate
```

- [ ] `agents.list` contains a `remote-rescue` entry
- [ ] `remote-rescue` has `subagents.allowAgents: ["*"]`
- [ ] `remote-rescue` has `workspace` field (dedicated dir, not shared with `main`)
- [ ] `remote-rescue` has `telegram.allowFrom` listing the operator chat IDs
- [ ] `openclaw config validate` returns Config valid
- [ ] Bootstrap message was sent (or `SKIP_BOOTSTRAP_MSG=1` was explicitly set)

### 7B. Group-session collision gate (HARD FAIL if violated)

- [ ] `channels.telegram.groupAllowFrom` does NOT contain `5252140759`, `6663821679`, or `6771245262`
  - If any are present: run `bash scripts/install-remote-rescue.sh --repair` then re-validate

### 7C. AgentId collision gate (HARD FAIL if violated)

- [ ] The `main` agent's `telegram.allowFrom` (if set) does NOT include operator IDs
- [ ] Operator IDs are bound exclusively to `remote-rescue`
- [ ] Resulting session keys are disjoint: `agent:remote-rescue:telegram:<operatorChatId>` vs `agent:main:telegram:<ownerChatId>`

### 7D. Live-turn verification (cannot be substituted by config check alone)

- [ ] An operator DM'd the bot and received a reply from the `remote-rescue` context
- [ ] The operator's message did NOT appear in the owner's chat


## 8. Failure conditions

Fail this skill if any of these happen:

- [ ] `skill-version.txt` is wrong
- [ ] Any placeholder survives in config or docs
- [ ] A team member ID is missing from `allowFrom`
- [ ] Replies go to the wrong sender
- [ ] One worker leaks another worker's context without explicit dispatch instruction
- [ ] Core files only store IDs in `WORKFLOW_AUTO.md` and nowhere else
- [ ] `env.vars.OPERATOR_TELEGRAM_CHAT_ID` is missing
- [ ] Remote Rescue agent is missing from `agents.list`
- [ ] `remote-rescue` exists WITHOUT `telegram.allowFrom` binding (unbound stub falls through to `main`)
- [ ] `remote-rescue` exists WITHOUT a `workspace` field (sessions could bleed into `main`)
- [ ] Any operator ID appears in `channels.telegram.groupAllowFrom`
- [ ] Operator and owner resolve to the same `agentId`
- [ ] `qc-blackceo-team-management.sh` exits non-zero


## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Installed routing files exist and contain real data
- [ ] `allowFrom` includes every approved team ID
- [ ] Core docs preserve the dispatcher rules and team memory
- [ ] Allowed, blocked, isolation, and directed-send tests all pass
- [ ] Operator received the required completion confirmation
- [ ] Remote Rescue agent is present, has `workspace` + `telegram.allowFrom` binding, and config validates
- [ ] `qc-blackceo-team-management.sh` exits 0 (all HARD gates green)
- [ ] Live-turn operator isolation test passed (section 7D)


## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
| Functional checks pass | 1.5 | The skill's specific smoke tests (API reachability, software present, etc.) all return expected results. No 4xx/5xx unhandled. |
| CORE_UPDATES.md applied surgically | 1.0 | Only labeled sections added to labeled core files. No SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md touched unless this skill's CORE_UPDATES.md explicitly labels them. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in the skill-specific sections of THIS QC.md is ticked. |
| Security | 0.5 | No PIT or other secret leaked into chat / logs / commits / .md files. Secrets file chmod 600. |
| Owner-facing confirmation message sent | 0.5 | The final summary was sent in plain English with structure: "Skill NN active. Anything pending your attention: [list]." |

### Loop-until-passing rule

If score < 8.5:
1. Identify the lowest-scoring section
2. Apply the smallest fix possible
3. Re-run only the failed checks
4. Re-score
5. After 5 loops, STOP and escalate to owner via Telegram with: which sections failed, what you tried, what's blocking

### Bundled `qc-skill-NN.sh`

If a `qc-skill-NN.sh` script exists in this skill folder, run it. Exit 0 is required in addition to the rubric score. The script catches mechanical items the rubric assumes (file modes, env-var format, network reachability).

### Self-audit before declaring done

Recite in your work log:
1. INSTALL-CONTRACT.md acknowledged for this skill: ✓ / ✗
2. All .md files read before execution: ✓ / ✗
3. INSTALL.md step order followed verbatim: ✓ / ✗
4. QC rubric score: __/10 (≥ 8.5 to pass)
5. Bundled qc-*.sh exited 0: ✓ / ✗ / N/A
6. No shortcuts taken (no `--force`, etc.): ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
