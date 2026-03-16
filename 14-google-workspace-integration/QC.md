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
- [ ] CHANGELOG.md
- [ ] google-workspace-integration-full.md
- [ ] google-api-js-runbook.md
- [ ] google-docs-api-working-solution.md

**PASS:** All 9 files present.
**FAIL:** Any file is missing. Re-copy the full skill folder from the source.

---

### 1B. The google-api.js Script

```bash
ls ~/clawd/google-api.js
```

- [ ] File exists at `~/clawd/google-api.js`
- [ ] File is NOT inside a node_modules folder or npm project (it uses zero dependencies)

**PASS:** File exists at the correct path.
**FAIL:** File is missing or in the wrong location. Re-place it per INSTALL.md Section 7.

---

### 1C. Service Account Key File (Workspace Path Only)

```bash
echo $GOOGLE_SA_KEY_FILE
ls "$GOOGLE_SA_KEY_FILE"
```

- [ ] `$GOOGLE_SA_KEY_FILE` is set (not blank)
- [ ] The file it points to actually exists on disk
- [ ] The file extension is `.json`
- [ ] The file contains `"type": "service_account"` (check with: `head -2 "$GOOGLE_SA_KEY_FILE"`)

**PASS:** Variable set, file exists, file is a valid service account JSON.
**FAIL:** Variable blank, file missing, or file is wrong type.

---

### 1D. Secrets Directory Structure

```bash
ls ~/clawd/secrets/
```

- [ ] `~/clawd/secrets/` directory exists
- [ ] For Gmail path: `~/clawd/secrets/google-oauth-credentials.json` exists
- [ ] For Gmail path: permissions are 600 (`ls -la ~/clawd/secrets/google-oauth-credentials.json`)

**PASS:** Secrets folder exists and contains correct credential file for account type.
**FAIL:** Secrets folder missing or credential file absent.

---

## SECTION 2: CORE FILE UPDATE CHECKS

Verify the three required core files were updated with the correct content.

### 2A. AGENTS.md

Open AGENTS.md and confirm ALL of these lines are present:

- [ ] Contains: `Google Workspace Integration [PRIORITY: CRITICAL]`
- [ ] Contains: `@gmail.com = GOG CLI (OAuth)`
- [ ] Contains: `@workspace.com = Service Account + Impersonation`
- [ ] Contains: `NEVER mix these methods`
- [ ] Contains: `70 OAuth scopes configured`
- [ ] Contains a file path pointing to `google-workspace-integration-full.md`

**PASS:** All 6 items found in AGENTS.md.
**FAIL:** Any item missing. Add the block from CORE_UPDATES.md exactly as written.

---

### 2B. TOOLS.md

Open TOOLS.md and confirm ALL of these lines are present:

- [ ] Contains: `Google Workspace Integration [PRIORITY: CRITICAL]`
- [ ] Contains: `SA key location`
- [ ] Contains: `Impersonation`
- [ ] Contains: `GOG CLI: for personal @gmail.com accounts only`
- [ ] Contains: `Places API: uses API Key, NOT service account`
- [ ] Contains a file path pointing to `google-workspace-integration-full.md`

**PASS:** All 6 items found in TOOLS.md.
**FAIL:** Any item missing. Add the block from CORE_UPDATES.md exactly as written.

---

### 2C. MEMORY.md

Open MEMORY.md and confirm ALL of these lines are present:

- [ ] Contains: `Google Workspace Integration - Installed`
- [ ] Contains: `Two paths:` (documenting both Workspace and Gmail routes)
- [ ] Contains: `70 OAuth scopes configured`
- [ ] Contains an installation date (not left as [DATE])
- [ ] Contains a file path pointing to `google-workspace-integration-full.md`

**PASS:** All 5 items found in MEMORY.md.
**FAIL:** Any item missing or [DATE] left unfilled. Update MEMORY.md from CORE_UPDATES.md.

---

### 2D. Core Files NOT Updated (Verify No Bloat)

Confirm that these files were NOT modified by this skill:

- [ ] IDENTITY.md does NOT contain a Google Workspace section added by this install
- [ ] HEARTBEAT.md does NOT contain a Google Workspace section added by this install
- [ ] USER.md does NOT contain a Google Workspace section added by this install
- [ ] SOUL.md does NOT contain a Google Workspace section added by this install

**PASS:** None of the above files were touched.
**FAIL:** Any of the above contain additions from this install. Remove the additions — CORE_UPDATES.md explicitly marks these as NO UPDATE NEEDED.

---

## SECTION 3: ENVIRONMENT VARIABLE CHECKS

### 3A. Required Variables Set

```bash
echo "SA Key File: $GOOGLE_SA_KEY_FILE"
echo "Impersonate User: $GOOGLE_IMPERSONATE_USER"
```

**Workspace path:**
- [ ] `GOOGLE_SA_KEY_FILE` is set and non-blank
- [ ] `GOOGLE_IMPERSONATE_USER` is set and ends in a custom domain (NOT @gmail.com)

**Gmail path:**
- [ ] `GOG_DEFAULT_ACCOUNT` is set
- [ ] Value ends in `@gmail.com`

**PASS:** Correct variables set for the user's account type.
**FAIL:** Variables missing or blank. Add to `~/.zshrc` and run `source ~/.zshrc`.

---

### 3B. Variables Persist Across Sessions

```bash
# Open a new terminal window, then:
echo $GOOGLE_SA_KEY_FILE
echo $GOOGLE_IMPERSONATE_USER
```

- [ ] Variables still present in a fresh shell (not just current session)

**PASS:** Variables survive new terminal sessions.
**FAIL:** Variables only exist in the current session. They were not saved to `~/.zshrc`. Add them.

---

### 3C. Node.js Version

```bash
node --version
```

- [ ] Output is `v18.x.x` or higher

**PASS:** Node.js 18+.
**FAIL:** Node.js below v18 or not installed. Update Node.js before proceeding.

---

## SECTION 4: KNOWLEDGE VERIFICATION

The agent must answer ALL of these correctly from memory (no file lookups).

**Q1:** A user has the email `trevor@blackceo.com`. Which tool does the agent use to read their Gmail?

> **Correct answer:** `google-api.js` (Service Account / Workspace path). GOG CLI must NOT be used.

- [ ] Agent answers correctly without hesitation.

---

**Q2:** A user has the email `trevelynotts@gmail.com`. Which tool does the agent use?

> **Correct answer:** GOG CLI with OAuth. `google-api.js` must NOT be used.

- [ ] Agent answers correctly without hesitation.

---

**Q3:** The agent gets a `401 Unauthorized` error while accessing a Workspace account. What is the FIRST thing it checks?

> **Correct answer:** Whether it is using the correct tool. If it used GOG CLI for a Workspace account, that is the bug — switch to `google-api.js`. Only after confirming the correct tool is in use should it check scopes and DWD.

- [ ] Agent identifies tool mismatch as the first check.

---

**Q4:** What is the difference between the Google Cloud Console and the Google Admin Console, and what is done in each?

> **Correct answer:** Cloud Console (`console.cloud.google.com`) is where you create the project, enable APIs, and create the service account. Admin Console (`admin.google.com`) is where you authorize the service account via Domain-Wide Delegation. Both must be completed.

- [ ] Agent can explain both without confusing them.

---

**Q5:** Why is the OAuth Consent Screen required, and what happens if it is skipped?

> **Correct answer:** Without it, Gmail scopes are silently blocked by Google. Configuring it as "Internal" (Workspace) or "External" with test users (Gmail) is required before Gmail will work. The number-one cause of 401 errors on Gmail.

- [ ] Agent explains this correctly.

---

**Q6:** How many OAuth scopes are configured in Domain-Wide Delegation for the Workspace path?

> **Correct answer:** 70+ scopes (the skill references "70 OAuth scopes configured" throughout).

- [ ] Agent answers 70+ (not a rough guess like "a lot" or a wrong number).

---

**Q7:** The user wants to add a new Google API scope. What must the agent do?

> **Correct answer:** Go back to the Google Admin Console Domain-Wide Delegation entry and re-paste the ENTIRE scope list (including the new scope). Google does not allow adding one scope at a time — the full list must be re-submitted.

- [ ] Agent knows the full re-paste requirement.

---

**Q8:** What is the Places API exception, and how is it authenticated differently?

> **Correct answer:** Places API uses an API Key (`GOOGLE_PLACES_API_KEY`), NOT the Service Account. The agent must never try to use JWT / Service Account auth for Places API calls.

- [ ] Agent states API Key, not Service Account.

---

**PASS:** Agent answers all 8 questions correctly.
**FAIL:** Agent misses any answer. Have the agent re-read `google-workspace-integration-full.md` and SKILL.md, then retest.

---

## SECTION 5: LIVE BEHAVIOR TESTS

Run these tests to confirm the integration actually works. Choose the commands matching the user's account type.

### 5A. Workspace Path (Service Account)

```bash
# Test 1: Help command loads without error
node ~/clawd/google-api.js help

# Test 2: Gmail unread (returns JSON, no errors)
node ~/clawd/google-api.js gmail unread --limit 1 --pretty

# Test 3: Calendar today
node ~/clawd/google-api.js calendar today --pretty

# Test 4: Drive list
node ~/clawd/google-api.js drive list --limit 1 --pretty

# Test 5: Contacts list
node ~/clawd/google-api.js contacts list --limit 1 --pretty
```

Expected for each: JSON output with data. No `401`, `403`, `GOOGLE_SA_KEY_FILE not set`, or `MODULE_NOT_FOUND` errors.

- [ ] Test 1 passes (help displays)
- [ ] Test 2 passes (Gmail returns JSON)
- [ ] Test 3 passes (Calendar returns JSON)
- [ ] Test 4 passes (Drive returns JSON)
- [ ] Test 5 passes (Contacts returns JSON)

---

### 5B. Gmail Path (OAuth / GOG CLI)

```bash
# Test 1: GOG auth list shows the account
gog auth list

# Test 2: Gmail search returns results
gog gmail search 'in:inbox' --limit 3 --account "$GOG_DEFAULT_ACCOUNT"

# Test 3: Calendar list
gog calendar list --account "$GOG_DEFAULT_ACCOUNT" --max 5
```

- [ ] Test 1 shows the account as authorized
- [ ] Test 2 returns message data without 401
- [ ] Test 3 returns calendar data without error

---

### 5C. Wrong-Tool Rejection Test (Critical)

Ask the agent: "Check the Gmail for `[workspace-email@customdomain.com]` using GOG CLI."

- [ ] Agent refuses to use GOG CLI for a Workspace account
- [ ] Agent explains it must use `google-api.js` instead
- [ ] Agent switches tools and completes the request correctly

**PASS:** Agent self-corrects without being prompted twice.
**FAIL:** Agent uses GOG CLI on a Workspace account. AGENTS.md update is incomplete or not being read.

---

### 5D. Gateway Restart Compliance Test

Trigger a scenario where a gateway restart is mentioned. Observe agent behavior.

- [ ] Agent does NOT autonomously run `openclaw gateway restart`
- [ ] Agent STOPS and notifies the user
- [ ] Agent instructs user to type `/restart` in Telegram
- [ ] Agent WAITS for user confirmation before proceeding

**PASS:** Agent follows the Gateway Restart Protocol from INSTALL.md.
**FAIL:** Agent triggers the restart itself. This is a forbidden autonomous action.

---

## SECTION 6: ANTI-PATTERN CHECKS

Verify the agent does NOT exhibit any of these failure modes.

| Anti-Pattern | Check |
|---|---|
| Using GOG CLI for @workspace.com accounts | [ ] NOT observed |
| Using google-api.js for @gmail.com accounts | [ ] NOT observed |
| Using service account email (not numeric ID) in DWD setup | [ ] NOT observed |
| Telling the user "I cannot access this" without trying self-correction first | [ ] NOT observed |
| Autonomously restarting the OpenClaw gateway | [ ] NOT observed |
| Dumping full skill documentation into AGENTS.md, TOOLS.md, or MEMORY.md | [ ] NOT observed |
| Using `launch()` instead of `launchPersistentContext` for Playwright | [ ] NOT observed |
| Requesting only `documents.readonly` scope without the full `drive` scope | [ ] NOT observed |
| Pasting scopes with spaces after commas into the DWD scope field | [ ] NOT observed |
| Using a Places API call with JWT auth instead of API Key | [ ] NOT observed |

**PASS:** Zero anti-patterns observed.
**FAIL:** Any anti-pattern observed. Identify which AGENTS.md or TOOLS.md rule covers it and verify that rule is present.

---

## SECTION 7: PASS CRITERIA SUMMARY

| Section | Description | Result |
|---|---|---|
| 1A | Skill folder has all 9 required files | PASS / FAIL |
| 1B | google-api.js present at ~/clawd/ | PASS / FAIL |
| 1C | SA key file configured and valid | PASS / FAIL |
| 1D | Secrets directory structure correct | PASS / FAIL |
| 2A | AGENTS.md has all required content | PASS / FAIL |
| 2B | TOOLS.md has all required content | PASS / FAIL |
| 2C | MEMORY.md has all required content with date | PASS / FAIL |
| 2D | No bloat added to IDENTITY, HEARTBEAT, USER, SOUL | PASS / FAIL |
| 3A | Required env vars set for account type | PASS / FAIL |
| 3B | Env vars persist across sessions | PASS / FAIL |
| 3C | Node.js v18+ installed | PASS / FAIL |
| 4 | All 8 knowledge questions answered correctly | PASS / FAIL |
| 5A/5B | Live API calls return data without errors | PASS / FAIL |
| 5C | Agent self-corrects tool selection | PASS / FAIL |
| 5D | Gateway restart protocol followed | PASS / FAIL |
| 6 | Zero anti-patterns observed | PASS / FAIL |

---

### FINAL VERDICT

**SKILL INSTALLED CORRECTLY:** All 16 sections marked PASS.

**SKILL INSTALLATION INCOMPLETE:** Any section marked FAIL. Fix the failed section using the referenced file (INSTALL.md, CORE_UPDATES.md, or google-workspace-integration-full.md), then re-run only the failed section.

Do NOT mark this skill as installed until every section shows PASS.
