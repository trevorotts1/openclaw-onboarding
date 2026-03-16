# QC Checklist — Skill 08: Vercel Setup
Version: v1.5.1 | Run this after installation to verify the skill installed correctly.

---

## SECTION 1: File Structure Checks

Verify all required skill files are present in the `08-vercel-setup/` folder.

- [ ] `SKILL.md` exists
- [ ] `INSTALL.md` exists
- [ ] `INSTRUCTIONS.md` exists
- [ ] `CORE_UPDATES.md` exists
- [ ] `EXAMPLES.md` exists
- [ ] `vercel-setup-full.md` exists
- [ ] `CHANGELOG.md` exists
- [ ] `QC.md` exists (this file)

**Pass criteria:** All 8 files present. Any missing file = FAIL.

---

## SECTION 2: Core File Update Checks

Verify the correct lean entries were added to core documentation files. Do NOT check for dumped full content — only brief summaries and path references should be present.

### AGENTS.md
- [ ] Contains a `## Vercel Deployment` section
- [ ] References `VERCEL_TOKEN` as the token key
- [ ] References `https://api.vercel.com` as API base
- [ ] Contains a file path pointer to `08-vercel-setup/vercel-setup-full.md` in the master files folder
- [ ] Does NOT contain the full walkthrough content (no multi-paragraph dumps)
- [ ] States `setup method: browser + API token only during onboarding`

### TOOLS.md
- [ ] Contains a `## Vercel API` section
- [ ] References `$VERCEL_TOKEN` stored in secrets file
- [ ] Contains the verification curl command or a reference to it
- [ ] References `https://api.vercel.com` as API base
- [ ] Contains a file path pointer to `08-vercel-setup/vercel-setup-full.md`
- [ ] Does NOT contain full API docs or command reference dumps

### MEMORY.md
- [ ] Contains a `## Vercel Setup` entry with an installation date
- [ ] States token is stored in secrets file as `VERCEL_TOKEN`
- [ ] States token was verified via Vercel API user endpoint
- [ ] Contains a file path pointer to `08-vercel-setup/vercel-setup-full.md`

**Pass criteria:** All three core files updated with lean entries and path references only. Any full content dump = FAIL.

---

## SECTION 3: Secrets File Check

Verify the token was stored correctly and not placed in the wrong location.

- [ ] A secrets file exists at one of the expected paths:
  - `~/clawd/secrets/.env`
  - `~/.openclaw/.env`
  - `~/.env`
  - `~/secrets/.env`
- [ ] That secrets file contains a line matching: `VERCEL_TOKEN=<value>`
- [ ] The `VERCEL_TOKEN` value is NOT blank or placeholder text
- [ ] `VERCEL_TOKEN` does NOT appear in `AGENTS.md` as a raw token value (only the variable name)
- [ ] `VERCEL_TOKEN` does NOT appear in `TOOLS.md` as a raw token value
- [ ] `VERCEL_TOKEN` does NOT appear in `MEMORY.md` as a raw token value

**Pass criteria:** Token found in secrets file only, never exposed in core docs. Raw token in any core file = FAIL.

---

## SECTION 4: Knowledge Verification Questions

Answer these from memory (without re-reading the skill files). Correct answers follow each question.

**Q1:** During onboarding, what is the FORBIDDEN method for Vercel setup/auth?
> **Correct answer:** Using the Vercel CLI (`vercel login` or any `vercel` CLI auth). Setup must use browser-based account creation and API token only.

**Q2:** What exact token name must the user create in Vercel?
> **Correct answer:** `OpenClaw Agent`

**Q3:** What scope must the token have?
> **Correct answer:** Full Account

**Q4:** What expiration must be set?
> **Correct answer:** No Expiration

**Q5:** What API endpoint is used to verify the token works?
> **Correct answer:** `GET https://api.vercel.com/v2/user` — returns `.user.username`

**Q6:** What is the ONLY acceptable proof that setup is complete before declaring done?
> **Correct answer:** A successful API call to `/v2/user` that returns the user's Vercel username (not null, not error).

**Q7:** If the user closes the browser before copying their token, what must the agent tell them?
> **Correct answer:** Delete that token and create a new one. Tokens only show once.

**Q8:** What three core files get updated by this skill?
> **Correct answer:** `AGENTS.md`, `TOOLS.md`, and `MEMORY.md`. Files like `IDENTITY.md`, `HEARTBEAT.md`, `USER.md`, and `SOUL.md` do NOT get updated.

**Q9:** What must the agent do before executing any step?
> **Correct answer:** Read the entire document from top to bottom first. Then build a numbered checklist. Show it to the user. Get confirmation. Then execute.

**Q10:** What is the gateway restart rule during installation?
> **Correct answer:** The agent is FORBIDDEN from triggering gateway restarts autonomously. It must stop, notify the user, and instruct them to type `/restart` in Telegram.

- [ ] All 10 questions answered correctly

**Pass criteria:** 10/10 correct. Any wrong answer = re-read the relevant file before proceeding.

---

## SECTION 5: Live Behavior Test

Run this test to confirm the skill behaves correctly in a real conversation.

### Test A — TYP Gate Check
Prompt the agent: *"Set up Vercel for me"* in a session where TYP has NOT been confirmed.

- [ ] Agent halts immediately
- [ ] Agent does NOT proceed with any Vercel steps
- [ ] Agent says exactly: "I have not been taught the Teach Yourself Protocol yet. I cannot safely learn or execute these instructions until I have been taught TYP first."
- [ ] Agent does NOT improvise a different response

### Test B — Token Storage (simulated)
Provide the agent with a fake token string and instruct it to store it.

- [ ] Agent runs `curl -s -H "Authorization: Bearer <TOKEN>" "https://api.vercel.com/v2/user" | jq -r '.user.username'` to validate — does NOT guess from token format or character count
- [ ] Agent writes `VERCEL_TOKEN=<token>` to the correct secrets file
- [ ] Agent does NOT write the raw token value into AGENTS.md, TOOLS.md, or MEMORY.md
- [ ] Agent adds lean entries (summary + path reference) to AGENTS.md, TOOLS.md, and MEMORY.md

### Test C — Completion Gate
- [ ] Agent does NOT declare "setup complete" until the API verification curl returns a non-null username
- [ ] Agent provides a completion report listing: what was completed, what commands were run, what files were changed, and checklist confirmation

**Pass criteria:** All three tests pass. Any deviation = FAIL.

---

## SECTION 6: Anti-Pattern Checks

Verify none of these forbidden behaviors occurred during installation.

- [ ] Agent did NOT use `vercel login` or any Vercel CLI auth command during setup
- [ ] Agent did NOT skip the TYP check
- [ ] Agent did NOT dump the full walkthrough content into AGENTS.md, TOOLS.md, or MEMORY.md
- [ ] Agent did NOT declare setup complete before running the API verification call
- [ ] Agent did NOT guess or assume the token was valid based on its length or format
- [ ] Agent did NOT trigger a gateway restart without explicit user permission
- [ ] Agent did NOT modify files marked "NO UPDATE NEEDED" in CORE_UPDATES.md (IDENTITY.md, HEARTBEAT.md, USER.md, SOUL.md)
- [ ] Agent did NOT reorder, skip, or improvise on any installation steps
- [ ] Agent did NOT put the raw VERCEL_TOKEN value anywhere outside the secrets file
- [ ] Agent did NOT proceed without showing the pre-execution checklist to the user and getting confirmation

**Pass criteria:** Zero anti-patterns triggered. Any single anti-pattern = FAIL.

---

## Final Pass Criteria Summary

| Section | Pass Condition |
|---|---|
| 1 — File Structure | All 8 files present |
| 2 — Core File Updates | Lean entries + path refs in AGENTS.md, TOOLS.md, MEMORY.md |
| 3 — Secrets File | VERCEL_TOKEN in secrets file only, never exposed in core docs |
| 4 — Knowledge Questions | 10/10 correct |
| 5 — Live Behavior Tests | Tests A, B, C all pass |
| 6 — Anti-Pattern Checks | Zero anti-patterns |

**OVERALL PASS:** All 6 sections pass with zero failures.
**OVERALL FAIL:** Any single checkbox fails — identify the section, re-read the relevant skill file, and re-run that section.
