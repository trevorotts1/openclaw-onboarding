# QC Checklist — Skill 14: Google Workspace Integration

Run this checklist after installation to verify the skill installed correctly.
Each section has a PASS/FAIL result. The skill passes only if ALL sections pass.

---

## SECTION 1: FILE STRUCTURE CHECKS

Verify every required file is present in the correct location.

### 1A. Skill Folder Files

Check that these files exist inside the skill folder:

```
~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/
```

- [ ] SKILL.md
- [ ] INSTALL.md
- [ ] INSTRUCTIONS.md
- [ ] EXAMPLES.md
- [ ] CORE_UPDATES.md
- [ ] QC.md
- [ ] CHANGELOG.md
- [ ] google-workspace-integration-full.md

**PASS:** All 8 files present.
**FAIL:** Any file is missing. Re-copy the full skill folder from the source.

---

### 1B. gws CLI Installation

```bash
gws --version
```

- [ ] Command returns a version number (like 1.0.0 or higher)
- [ ] No "command not found" error

**PASS:** gws is installed and working.
**FAIL:** gws not installed. Run npm install -g @googleworkspace/cli.

---

### 1C. Authentication Status

```bash
gws auth list
```

For Gmail accounts:
- [ ] Shows your Gmail address
- [ ] Shows authorized scopes

For Workspace accounts (gcloud method):
- [ ] Shows authenticated status

For Workspace accounts (service account method):
- [ ] GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE is set
- [ ] The file exists at the path specified

**PASS:** Authentication configured correctly for account type.
**FAIL:** Not authenticated. Follow INSTALL.md Section 2 or 3.

---

### 1D. Secrets Directory Structure (if applicable)

```bash
ls ~/clawd/secrets/
```

For Workspace with service account:
- [ ] Service account JSON file exists
- [ ] Permissions are restricted (not world-readable)

**PASS:** Secrets folder exists with proper credential file.
**FAIL:** Secrets folder missing or credential file absent.

---

## SECTION 2: CORE FILE UPDATE CHECKS

Verify the required core files were updated with the correct content.

### 2A. AGENTS.md

Open AGENTS.md and confirm ALL of these lines are present:

- [ ] Contains: Google Workspace Integration [PRIORITY: CRITICAL]
- [ ] Contains: gws CLI reference
- [ ] Contains: Gmail accounts use gws auth login
- [ ] Contains: Workspace accounts use gws auth setup or service account
- [ ] Contains: 81 scopes reference for Workspace
- [ ] Contains a file path pointing to google-workspace-integration-full.md

**PASS:** All items found in AGENTS.md.
**FAIL:** Any item missing. Add the block from CORE_UPDATES.md.

---

### 2B. TOOLS.md

Open TOOLS.md and confirm ALL of these lines are present:

- [ ] Contains: Google Workspace Integration [PRIORITY: CRITICAL]
- [ ] Contains: Installation path (npm install -g @googleworkspace/cli)
- [ ] Contains: Auth method for Gmail
- [ ] Contains: Auth method for Workspace
- [ ] Contains: Common gws commands
- [ ] Contains a file path pointing to google-workspace-integration-full.md

**PASS:** All items found in TOOLS.md.
**FAIL:** Any item missing. Add the block from CORE_UPDATES.md.

---

### 2C. MEMORY.md

Open MEMORY.md and confirm ALL of these lines are present:

- [ ] Contains: Google Workspace CLI (gws) installed
- [ ] Contains: Installation date (not left as [DATE])
- [ ] Contains: List of services handled
- [ ] Contains: 81 scopes configured (for Workspace)
- [ ] Contains a file path pointing to google-workspace-integration-full.md

**PASS:** All items found in MEMORY.md.
**FAIL:** Any item missing or [DATE] left unfilled. Update MEMORY.md.

---

### 2D. Core Files NOT Updated (Verify No Bloat)

Confirm that these files were NOT modified by this skill:

- [ ] IDENTITY.md does NOT contain a Google Workspace section added by this install
- [ ] HEARTBEAT.md does NOT contain a Google Workspace section added by this install
- [ ] USER.md does NOT contain a Google Workspace section added by this install
- [ ] SOUL.md does NOT contain a Google Workspace section added by this install

**PASS:** None of the above files were touched.
**FAIL:** Any of the above contain additions from this install. Remove them.

---

## SECTION 3: ENVIRONMENT CHECKS

### 3A. Node.js Version

```bash
node --version
```

- [ ] Output is v18.x.x or higher

**PASS:** Node.js 18+.
**FAIL:** Node.js below v18. Update Node.js before proceeding.

---

### 3B. gws Installation Path

```bash
which gws
```

- [ ] Returns a path (like /usr/local/bin/gws or similar)

**PASS:** gws is in PATH.
**FAIL:** gws not in PATH. May need to reinstall or restart terminal.

---

## SECTION 4: KNOWLEDGE VERIFICATION

The agent must answer ALL of these correctly from memory.

**Q1:** What tool is used for Google Workspace access?

> **Correct answer:** The gws CLI (Google Workspace CLI).

- [ ] Agent answers correctly.

---

**Q2:** What are the two authentication paths for gws?

> **Correct answer:** Gmail accounts use OAuth via gws auth login. Workspace accounts use gws auth setup with gcloud or service account JSON via GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE.

- [ ] Agent answers correctly.

---

**Q3:** How many OAuth scopes are configured for Domain-Wide Delegation?

> **Correct answer:** 81 scopes.

- [ ] Agent answers 81 scopes.

---

**Q4:** How do you refresh expired tokens?

> **Correct answer:** Run gws auth login again for Gmail. For Workspace with gcloud, run gcloud auth application-default login. Service accounts refresh automatically.

- [ ] Agent explains token refresh correctly.

---

**Q5:** What command shows today's calendar agenda?

> **Correct answer:** gws calendar +agenda

- [ ] Agent answers with the correct command.

---

**PASS:** Agent answers all 5 questions correctly.
**FAIL:** Agent misses any answer. Have the agent re-read the documentation.

---

## SECTION 5: LIVE BEHAVIOR TESTS

Run these tests to confirm the integration actually works.

### 5A. Gmail Test

```bash
gws gmail +triage
```

Expected: List of unread emails or "No unread messages" message.

- [ ] Test passes (returns email data or empty state message)
- [ ] No 401 or 403 errors

---

### 5B. Calendar Test

```bash
gws calendar +agenda
```

Expected: Today's events or "No events today" message.

- [ ] Test passes (returns events or empty state message)
- [ ] No 401 or 403 errors

---

### 5C. Drive Test

```bash
gws drive files list --params '{"pageSize": 3}'
```

Expected: List of Drive files.

- [ ] Test passes (returns file list)
- [ ] No 401 or 403 errors

---

### 5D. Sheets Test

```bash
gws sheets spreadsheets create --json '{"properties": {"title": "QC Test Sheet"}}'
```

Expected: Response with spreadsheet ID.

- [ ] Test passes (returns spreadsheet ID)
- [ ] No 401 or 403 errors

**Note:** Delete the test sheet after verification.

---

### 5E. Docs Test

For interactive testing, verify the helper loads:
```bash
gws docs +write --help
```

Expected: Help text for the docs write helper.

- [ ] Test passes (returns help text)

---

### 5F. Tasks Test

```bash
gws tasks tasklists list
```

Expected: List of task lists or empty state.

- [ ] Test passes (returns task lists or empty state)
- [ ] No 401 or 403 errors

---

## SECTION 6: ANTI-PATTERN CHECKS

Verify the agent does NOT exhibit any of these failure modes.

| Anti-Pattern | Check |
|---|---|
| Referencing old tools (google-api.js or gog) | [ ] NOT observed |
| Using em dashes in documentation | [ ] NOT observed |
| Autonomously restarting the OpenClaw gateway | [ ] NOT observed |
| Dumping full skill documentation into AGENTS.md, TOOLS.md, or MEMORY.md | [ ] NOT observed |
| Pasting scopes with spaces after commas | [ ] NOT observed |

**PASS:** Zero anti-patterns observed.
**FAIL:** Any anti-pattern observed. Identify and correct.

---

## SECTION 7: PASS CRITERIA SUMMARY

| Section | Description | Result |
|---|---|---|
| 1A | Skill folder has all 8 required files | PASS / FAIL |
| 1B | gws CLI installed and working | PASS / FAIL |
| 1C | Authentication configured for account type | PASS / FAIL |
| 1D | Secrets directory structure correct (if applicable) | PASS / FAIL |
| 2A | AGENTS.md has all required content | PASS / FAIL |
| 2B | TOOLS.md has all required content | PASS / FAIL |
| 2C | MEMORY.md has all required content with date | PASS / FAIL |
| 2D | No bloat added to IDENTITY, HEARTBEAT, USER, SOUL | PASS / FAIL |
| 3A | Node.js v18+ installed | PASS / FAIL |
| 3B | gws in PATH | PASS / FAIL |
| 4 | All 5 knowledge questions answered correctly | PASS / FAIL |
| 5A-5F | All live API tests pass | PASS / FAIL |
| 6 | Zero anti-patterns observed | PASS / FAIL |

---

### FINAL VERDICT

**SKILL INSTALLED CORRECTLY:** All sections marked PASS.

**SKILL INSTALLATION INCOMPLETE:** Any section marked FAIL. Fix the failed section using the referenced file, then re-run only the failed section.

Do NOT mark this skill as installed until every section shows PASS.
