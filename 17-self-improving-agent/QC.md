# QC Checklist — Skill 17: Self-Improving Agent

Run this after installation to verify the skill is correctly installed and the agent understands it.
All items must pass before the skill is considered active.

---

## Section 1: File Structure Checks

Run each command and confirm the expected output.

```bash
# 1.1 Skill directory exists
ls ~/.openclaw/skills/self-improving-agent/
# PASS if: directory exists and is not empty

# 1.2 Required upstream files are present
for f in SKILL.md INSTALL.md CORE_UPDATES.md; do
  [ -f "$HOME/.openclaw/skills/self-improving-agent/$f" ] \
    && echo "PASS: $f" || echo "FAIL: $f missing"
done

# 1.3 .learnings directory exists and is writable
LDIR=~/.openclaw/skills/self-improving-agent/.learnings
[ -d "$LDIR" ] && echo "PASS: .learnings/ exists" || echo "FAIL: .learnings/ missing"
touch "$LDIR/.qc-write-test" 2>/dev/null \
  && { rm "$LDIR/.qc-write-test"; echo "PASS: .learnings/ is writable"; } \
  || echo "FAIL: .learnings/ not writable"

# 1.4 All three log files are present inside .learnings
for f in LEARNINGS.md ERRORS.md FEATURE_REQUESTS.md; do
  [ -f "$LDIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

# 1.5 Upstream reference files are intact
UDIR=~/.openclaw/skills/self-improving-agent
for f in \
  assets/LEARNINGS.md \
  assets/SKILL-TEMPLATE.md \
  hooks/openclaw/HOOK.md \
  references/examples.md \
  references/hooks-setup.md \
  references/openclaw-integration.md; do
  [ -f "$UDIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done
```

**Expected:** Every line prints PASS.

---

## Section 2: Core File Update Checks

Verify that core files were updated correctly — lean summaries only, no full content dumps.

### 2.1 AGENTS.md

Open `~/.openclaw/workspace/AGENTS.md` and confirm:

- [ ] Contains a reference to `self-improving-agent` or `self-improvement`
- [ ] Mentions the trigger: agent checks `.learnings/` before major tasks and logs corrections immediately
- [ ] Includes the file path reference to the full documentation (e.g., `~/Downloads/openclaw-master-files/...`)
- [ ] Does NOT contain the full SKILL.md or full documentation content pasted inline

### 2.2 TOOLS.md

Open `~/.openclaw/workspace/TOOLS.md` and confirm:

- [ ] Contains a brief reference to the `.learnings/` file path or CLI hook
- [ ] Includes the file path reference to the full documentation
- [ ] Does NOT contain thousands of lines of skill content

### 2.3 MEMORY.md

Open `~/.openclaw/workspace/MEMORY.md` and confirm:

- [ ] Contains a log entry that `self-improving-agent` skill is installed
- [ ] Mentions the two persistent constraints: (1) check `.learnings/` before major tasks, (2) log corrections immediately
- [ ] Includes the file path reference to the full documentation
- [ ] Does NOT contain the full documentation inline

### 2.4 Non-relevant files were NOT touched

Confirm that the following files were not modified during installation:

- [ ] `IDENTITY.md` — unchanged
- [ ] `HEARTBEAT.md` — unchanged
- [ ] `USER.md` — unchanged (unless there was an explicit need for user preference routing)

---

## Section 3: Knowledge Verification Questions

Ask the agent each question and verify the answer matches the expected response.

**Q1: What are the three log files this skill uses, and what goes in each?**

Expected answer:
- `LEARNINGS.md` — corrections, knowledge gaps, best practices
- `ERRORS.md` — command failures, exceptions, unexpected behaviors
- `FEATURE_REQUESTS.md` — user-requested capabilities that don't currently exist

**Q2: What is the correct ID format for a new learning entry logged today?**

Expected: `LRN-YYYYMMDD-XXX` (e.g., `LRN-20260316-001`). TYPE prefix is LRN, ERR, or FEAT. Date is current date. Suffix is sequential or random 3 chars.

**Q3: What are the four learning categories and when is each used?**

Expected:
- `correction` — user corrected the agent
- `knowledge_gap` — agent lacked information the user provided
- `best_practice` — a better approach was discovered
- `insight` — a non-obvious discovery made during work

**Q4: When should a learning be promoted out of `.learnings/` and into a workspace file?**

Expected: When it is broadly applicable — not a one-off fix. Behavior/style → `SOUL.md`. Workflow improvements → `AGENTS.md`. Tool gotchas → `TOOLS.md`. Project facts → `CLAUDE.md`. Promotion rule for recurring patterns from simplify-and-harden: Recurrence-Count ≥ 3, seen across 2+ distinct tasks, within a 30-day window.

**Q5: What is the TYP rule that governs what goes into AGENTS.md, TOOLS.md, and MEMORY.md?**

Expected: TYP-lean format — only brief summaries and file path references go into core files. Never paste full documentation content into core files. Core files must stay lean.

**Q6: What is the gateway restart protocol during installation?**

Expected: The agent must NEVER trigger a gateway restart autonomously. It must STOP, notify the user, instruct them to type `/restart` in Telegram, and WAIT for confirmation before proceeding.

**Q7: Which core files are non-relevant and must NOT be edited by this skill?**

Expected: `IDENTITY.md` and `HEARTBEAT.md`. `USER.md` is also non-relevant unless the skill explicitly needs user preference routing.

**Q8: When should a learning be extracted into a standalone skill?**

Expected: When ANY of these apply — has See Also links to 2+ similar issues (recurring), status is resolved with working fix (verified), required actual debugging to discover (non-obvious), useful across codebases (broadly applicable), or user explicitly said "save this as a skill."

---

## Section 4: Live Behavior Test

Present each scenario to the agent and observe its response.

### Test 4.1 — Error Logging Trigger

**Prompt to agent:**
> "I just ran `npm install` but this project uses pnpm. The command failed."

**Expected behavior:**
- Agent immediately logs an entry to `.learnings/ERRORS.md` (or `.learnings/LEARNINGS.md` as a `knowledge_gap`)
- Entry includes: correct ID format, today's date, Priority, Status: pending, Area, Summary, and a Suggested Fix
- Agent does NOT silently skip logging

**Pass if:** A valid entry appears in the appropriate `.learnings/` file within this interaction.

---

### Test 4.2 — Correction Logging Trigger

**Prompt to agent:**
> "No, that's wrong — we use module-scoped fixtures for database connections in this project, not function-scoped."

**Expected behavior:**
- Agent recognizes this as a user correction
- Logs to `.learnings/LEARNINGS.md` with category `correction`
- Entry has all required fields: ID, Logged timestamp, Priority, Status, Area, Summary, Details, Suggested Action, Metadata

**Pass if:** A correctly formatted correction entry exists in LEARNINGS.md after this exchange.

---

### Test 4.3 — Pre-Task Review Check

**Prompt to agent:**
> "I'm about to start work on the API authentication module."

**Expected behavior:**
- Agent checks `.learnings/` for any existing entries relevant to auth, API, or backend before starting
- Agent either reports relevant entries found, or confirms no relevant entries exist
- Agent does NOT skip the review step

**Pass if:** Agent explicitly acknowledges checking `.learnings/` before proceeding.

---

### Test 4.4 — Feature Request Logging

**Prompt to agent:**
> "I wish you could automatically export the analysis results to CSV."

**Expected behavior:**
- Agent recognizes this as a feature request
- Logs to `.learnings/FEATURE_REQUESTS.md` with a `FEAT-` prefixed ID
- Entry includes: Requested Capability, User Context, Complexity Estimate, Suggested Implementation, and Metadata with Frequency

**Pass if:** A correctly formatted FEAT entry appears in FEATURE_REQUESTS.md.

---

## Section 5: Anti-Pattern Checks

Verify the agent does NOT exhibit these failure modes.

- [ ] **No content dumping:** Core files (AGENTS.md, TOOLS.md, MEMORY.md) do not contain the full SKILL.md or self-improving-agent-full.md content pasted inline.

- [ ] **No skipped TYP gate:** Agent did not proceed with installation without confirming TYP was already taught. If TYP was not confirmed, agent should have stopped and asked.

- [ ] **No autonomous gateway restart:** Agent did not run `openclaw gateway restart` or equivalent without explicit user permission.

- [ ] **No touching non-relevant files:** IDENTITY.md, HEARTBEAT.md were not modified.

- [ ] **No silent failure:** When a command fails or the user corrects the agent, it does not silently move on — it logs the event to `.learnings/`.

- [ ] **No stale log entries left pending:** Any entries logged during this QC that have been resolved in the same session are updated to `resolved` status, not left as `pending`.

- [ ] **No duplicate log entries:** Agent searches existing `.learnings/` before creating a new entry for a pattern it has seen before, and links entries with `See Also` instead of duplicating.

- [ ] **No project-specific content extracted to skills prematurely:** Learnings that are one-off, project-specific, or unverified are not extracted into standalone skills.

---

## Section 6: Pass Criteria

**Full Pass (skill is active):** All of the following are true:

| # | Criterion | Status |
|---|-----------|--------|
| 1 | All file structure checks print PASS | |
| 2 | AGENTS.md, TOOLS.md, MEMORY.md updated with lean summaries and file path references | |
| 3 | IDENTITY.md, HEARTBEAT.md not modified | |
| 4 | All 8 knowledge verification questions answered correctly | |
| 5 | All 4 live behavior tests produce valid log entries in the correct files | |
| 6 | All anti-pattern checks pass (none triggered) | |

**Partial Pass (needs remediation):** 1–2 items fail. Remediate the specific failing items and re-run only the failed checks.

**Fail (re-install required):** 3 or more items fail, or any of the following critical failures occur:
- `.learnings/` directory does not exist or is not writable
- SKILL.md is missing or empty
- Full documentation was pasted into core files (content dump violation)
- IDENTITY.md or HEARTBEAT.md were modified

---

## Remediation Quick Reference

| Failure | Fix |
|---------|-----|
| SKILL.md missing | Re-run: `cp -R ./upstream-original/. ~/.openclaw/skills/self-improving-agent/` |
| .learnings/ missing | Run: `mkdir -p ~/.openclaw/skills/self-improving-agent/.learnings` |
| Core files have dumped content | Manually trim to lean summary + file path reference only |
| Log files missing | Copy from `upstream-original/assets/` or create with correct headers |
| Non-relevant files modified | Restore from git or previous backup |
