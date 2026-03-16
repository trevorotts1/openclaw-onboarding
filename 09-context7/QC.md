# QC Checklist — Skill 09: Context7
**Version:** v1.5.1 | Run this after installation to verify the skill installed correctly.

Mark each item [ ] → [x] as you verify it. All items must pass before reporting installation complete.

---

## SECTION 1: File Structure Checks

Verify the skill folder contains all required files.

- [ ] `09-context7/SKILL.md` exists
- [ ] `09-context7/INSTALL.md` exists
- [ ] `09-context7/INSTRUCTIONS.md` exists
- [ ] `09-context7/context7-full.md` exists
- [ ] `09-context7/CORE_UPDATES.md` exists
- [ ] `09-context7/EXAMPLES.md` exists
- [ ] `09-context7/CHANGELOG.md` exists
- [ ] `09-context7/QC.md` exists (this file)

**PASS CRITERIA:** All 8 files present. Missing any file = FAIL.

---

## SECTION 2: Core File Update Checks

Verify that AGENTS.md, TOOLS.md, and MEMORY.md were updated correctly.

### 2a. AGENTS.md
- [ ] AGENTS.md contains a `Context7` section
- [ ] The section references `CONTEXT7_API_KEY` stored in `secrets.env`
- [ ] The section includes the instruction to use Context7 BEFORE writing code for external APIs
- [ ] The section references the full guide path (e.g. `09-context7/context7-full.md`)
- [ ] The section is a LEAN SUMMARY — NOT a full dump of the skill documentation

### 2b. TOOLS.md
- [ ] TOOLS.md contains a `Context7` section
- [ ] The section includes the search endpoint: `https://api.context7.com/v1/search?q=<library>`
- [ ] The section includes the docs endpoint: `https://api.context7.com/v1/libraries/<id>/context`
- [ ] The section references `$CONTEXT7_API_KEY`
- [ ] The section references the full guide path
- [ ] The section is a LEAN SUMMARY — NOT a full dump

### 2c. MEMORY.md
- [ ] MEMORY.md contains a `Context7` entry
- [ ] The entry includes a reminder to check Context7 before writing code for any external library or API
- [ ] The entry references the full guide path
- [ ] The entry is brief (3–5 lines max)

### 2d. Files That Must NOT Be Updated
- [ ] `IDENTITY.md` — no Context7 content added
- [ ] `HEARTBEAT.md` — no Context7 content added
- [ ] `USER.md` — no Context7 content added
- [ ] `SOUL.md` — no Context7 content added

**PASS CRITERIA:** All three required files updated with lean summaries. Forbidden files untouched. Full documentation content NOT pasted into any core file = PASS.

---

## SECTION 3: API Key Storage Check

Verify the Context7 API key was stored correctly.

- [ ] `~/.openclaw/secrets.env` exists (or `~/clawd/secrets/.env`)
- [ ] The file contains a line starting with `CONTEXT7_API_KEY=`
- [ ] The key value starts with `ctx7sk-`
- [ ] The key matches the UUID pattern: `ctx7sk-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`
- [ ] The key was NOT hardcoded into AGENTS.md, TOOLS.md, or any other tracked file
- [ ] The key was NOT logged in plaintext in any conversation summary file

To verify format, run:
```bash
grep CONTEXT7_API_KEY ~/.openclaw/secrets.env
```
Expected output: `CONTEXT7_API_KEY=ctx7sk-...` (key present, starts with prefix)

**PASS CRITERIA:** Key present in secrets.env, correct format, not exposed elsewhere = PASS.

---

## SECTION 4: Knowledge Verification Questions

Agent must answer all of these correctly from memory (no file lookups).

**Q1:** What is Context7 and why does the agent use it?
> EXPECTED: Context7 is a real-time documentation lookup service. The agent uses it before writing code for external libraries or APIs to avoid relying on potentially outdated training data.

**Q2:** What are the two API calls needed to look up documentation for a library?
> EXPECTED:
> 1. Search: `GET https://api.context7.com/v1/search?q=<library_name>`
> 2. Get docs: `GET https://api.context7.com/v1/libraries/<library_id>/context`

**Q3:** What is the correct format for a Context7 API key?
> EXPECTED: Starts with `ctx7sk-` followed by UUID groups — e.g. `ctx7sk-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`

**Q4:** Name three libraries available in Context7 and their IDs.
> EXPECTED (any three): `n8n-io/n8n-docs`, `facebook/react`, `vercel/next.js`, `websites/marketplace_gohighlevel`, `nodejs/node`

**Q5:** When should the agent fall back to training data instead of Context7?
> EXPECTED: Only when Context7 does not have documentation for a specific library. Agent must still inform the user: "I could not find current documentation for this library in Context7. I am using my best knowledge, but you may want to double-check the code against the official docs."

**Q6:** Where is the full Context7 documentation saved, and why does it NOT go into AGENTS.md?
> EXPECTED: Full documentation is saved to the OpenClaw master files folder (e.g. `~/Downloads/openclaw-master-files/`). It does not go into core .md files because TYP requires core files to stay lean — only brief summaries and file path references belong there.

- [ ] Q1 answered correctly
- [ ] Q2 answered correctly
- [ ] Q3 answered correctly
- [ ] Q4 answered correctly
- [ ] Q5 answered correctly
- [ ] Q6 answered correctly

**PASS CRITERIA:** All 6 questions answered correctly = PASS. Any wrong answer = FAIL, re-read `context7-full.md`.

---

## SECTION 5: Live Behavior Test

Run this test to confirm the API key is functional and the agent can reach Context7.

### Test 5a — Key Available in Environment
```bash
source ~/.openclaw/secrets.env 2>/dev/null || source ~/clawd/secrets/.env 2>/dev/null || true
echo $CONTEXT7_API_KEY
```
- [ ] Key is printed and starts with `ctx7sk-`

### Test 5b — Search API Call
```bash
curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/search?q=react" | jq '.results[0].name'
```
- [ ] Response returns a library name in quotes (e.g. `"React"` or `"facebook/react"`)
- [ ] No 401 error
- [ ] No empty or null response

### Test 5c — Documentation Fetch Call
```bash
curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY" \
  "https://api.context7.com/v1/libraries/facebook/react/context" | head -c 200
```
- [ ] Response returns documentation content (not an error object)
- [ ] Content is non-empty

**PASS CRITERIA:** All three sub-tests return expected output = PASS.

**Troubleshooting if tests fail:**
- `401 Unauthorized` → Key is wrong or not loaded. Re-check secrets.env and re-source.
- `null` response on search → Try a different library name. Check internet connectivity.
- Empty content on fetch → Library ID may be wrong. Re-run the search step to get the correct ID.

---

## SECTION 6: Anti-Pattern Checks

Verify the agent did NOT do any of the following during installation.

- [ ] Did NOT use any Context7 CLI commands (e.g. `context7 login`, `context7 auth`) — API-only
- [ ] Did NOT use `gh`, `vercel`, or other service CLIs for this skill's setup
- [ ] Did NOT paste the full contents of `context7-full.md` into AGENTS.md
- [ ] Did NOT paste the full contents of `context7-full.md` into TOOLS.md or MEMORY.md
- [ ] Did NOT skip the TYP check before executing instructions
- [ ] Did NOT modify `IDENTITY.md`, `HEARTBEAT.md`, `USER.md`, or `SOUL.md`
- [ ] Did NOT attempt to restart the OpenClaw gateway without explicit user instruction
- [ ] Did NOT report completion before the verification test (Section 5) was run
- [ ] Did NOT hardcode the API key into source-controlled files or chat history
- [ ] Did NOT skip Step 5 (API verification) in the INSTALL.md flow

**PASS CRITERIA:** All 10 anti-patterns confirmed absent = PASS. Any violation = FAIL, investigate and correct.

---

## Final Pass/Fail Summary

| Section | Description | Result |
|---------|-------------|--------|
| 1 | File Structure | [ ] PASS / [ ] FAIL |
| 2 | Core File Updates | [ ] PASS / [ ] FAIL |
| 3 | API Key Storage | [ ] PASS / [ ] FAIL |
| 4 | Knowledge Verification | [ ] PASS / [ ] FAIL |
| 5 | Live Behavior Test | [ ] PASS / [ ] FAIL |
| 6 | Anti-Pattern Checks | [ ] PASS / [ ] FAIL |

**OVERALL:**
- [ ] ALL SECTIONS PASS — Context7 skill is fully installed and operational.
- [ ] ONE OR MORE SECTIONS FAIL — Do not mark installation complete. Return to the failed section(s), correct the issue, and re-run QC.

---

*QC document version: 1.0 | Skill version: v1.5.1 | Date written: 2026-03-16*
