# QC Checklist — Skill 10: GitHub Setup
**Run this after installation to verify the skill installed correctly.**
Score each item PASS / FAIL / SKIP (SKIP only when the check is genuinely not applicable to this machine).
All items must be PASS or SKIP before declaring the install verified.

---

## 1. FILE STRUCTURE CHECKS

Verify the skill folder is intact and all expected files are present.

```
[ ] 10-github-setup/SKILL.md        exists and is non-empty
[ ] 10-github-setup/INSTALL.md      exists and is non-empty
[ ] 10-github-setup/INSTRUCTIONS.md exists and is non-empty
[ ] 10-github-setup/EXAMPLES.md     exists and is non-empty
[ ] 10-github-setup/CORE_UPDATES.md exists and is non-empty
[ ] 10-github-setup/CHANGELOG.md    exists and is non-empty
[ ] 10-github-setup/github-setup-full.md  exists and is non-empty
[ ] 10-github-setup/QC.md           exists (this file)
```

**How to check:**
```bash
ls -1 ~/Downloads/openclaw-master-files/"OpenClaw Onboarding"/10-github-setup/
```

PASS criteria: All 8 files listed above are present.

---

## 2. CORE FILE UPDATE CHECKS

Verify that AGENTS.md, TOOLS.md, and MEMORY.md were updated correctly — and that no bloat was added.

### 2a. AGENTS.md
```
[ ] Contains a "## GitHub" section with PRIORITY: HIGH
[ ] Lists setup method: GitHub browser + API token + local git config
[ ] Lists minimum PAT scopes: repo, read:org, workflow
[ ] Contains a file path reference to github-setup-full.md (not the full content pasted in)
[ ] Does NOT contain multi-page blocks of GitHub documentation pasted directly
```

**How to check:**
```bash
grep -n "GitHub" ~/clawd/AGENTS.md | head -20
grep -c "ghp_\|credential.helper\|git config" ~/clawd/AGENTS.md
```

PASS criteria: GitHub section is present and lean. The raw step-by-step install content is NOT in AGENTS.md — only a summary and file path reference.

---

### 2b. TOOLS.md
```
[ ] Contains a "## Git & GitHub" section
[ ] References $GITHUB_TOKEN and $GITHUB_USERNAME
[ ] Lists core git commands: git status, git add ., git commit, git push, git pull
[ ] References https://api.github.com
[ ] Contains a file path reference to github-setup-full.md
[ ] Does NOT contain full API documentation or multi-page examples
```

**How to check:**
```bash
grep -n "Git\|GitHub\|GITHUB_TOKEN" ~/clawd/TOOLS.md | head -20
```

PASS criteria: Section is present, concise, and references the master file path rather than duplicating content.

---

### 2c. MEMORY.md
```
[ ] Contains a "## GitHub/Git Setup" entry with an install date
[ ] Notes that Git was configured (user.name, user.email, credential.helper=store)
[ ] Notes PAT scopes: repo, read:org, workflow
[ ] Notes 90-day expiry
[ ] Contains a file path reference to github-setup-full.md
[ ] Does NOT contain the full setup walkthrough
```

**How to check:**
```bash
grep -n "GitHub\|git\|PAT" ~/clawd/MEMORY.md | head -20
```

PASS criteria: Lean timestamped entry is present with a file path reference.

---

### 2d. Files that must NOT be updated
```
[ ] IDENTITY.md — confirm no GitHub section was added
[ ] HEARTBEAT.md — confirm no GitHub section was added
[ ] USER.md      — confirm no GitHub section was added
[ ] SOUL.md      — confirm no GitHub section was added
```

**How to check:**
```bash
grep -l "GITHUB_TOKEN\|git config\|Personal Access Token" \
  ~/clawd/IDENTITY.md ~/clawd/HEARTBEAT.md ~/clawd/USER.md ~/clawd/SOUL.md 2>/dev/null
```

PASS criteria: The command returns no matches (none of those files were modified).

---

## 3. SYSTEM CONFIGURATION CHECKS

Verify the machine-level setup is in place.

### 3a. Git global config
```bash
git config --list | grep -E "user\.|credential\.|init\."
```

Expected — all four lines must be present:
```
user.name=<non-empty name>
user.email=<non-empty email>
credential.helper=store
init.defaultbranch=main
```

```
[ ] user.name is set (non-empty)
[ ] user.email is set (non-empty, matches GitHub account email)
[ ] credential.helper = store
[ ] init.defaultbranch = main
```

PASS criteria: All four values present and correct.

---

### 3b. Secrets file
```
[ ] $SECRETS_FILE resolves to one of the expected paths:
    ~/clawd/secrets/.env  OR  ~/.openclaw/.env  OR  ~/.env  OR  ~/secrets/.env
[ ] File contains GITHUB_TOKEN=ghp_...  (starts with "ghp_", ~40 chars)
[ ] File contains GITHUB_USERNAME=<non-empty string>
[ ] secrets file is NOT tracked by git (should be in .gitignore or outside any repo)
```

**How to check:**
```bash
SECRETS_FILE=""
for f in ~/clawd/secrets/.env ~/.openclaw/.env ~/.env ~/secrets/.env; do
  [ -f "$f" ] && SECRETS_FILE="$f" && break
done
echo "Secrets file: $SECRETS_FILE"
grep "GITHUB_TOKEN\|GITHUB_USERNAME" "$SECRETS_FILE"
```

PASS criteria: Both variables present in secrets file; token starts with "ghp_".

---

### 3c. Dependencies
```
[ ] git is installed: git --version  → returns a version string
[ ] curl is installed: curl --version → returns a version string
[ ] jq is installed: jq --version   → returns a version string
```

PASS criteria: All three commands return version output without error.

---

## 4. KNOWLEDGE VERIFICATION QUESTIONS

The agent must be able to answer these correctly from memory (no file lookup needed for basic questions). Ask the agent each question and evaluate the response.

| # | Question | Expected Answer |
|---|----------|-----------------|
| K1 | What is the minimum set of PAT scopes required for this skill? | `repo`, `read:org`, `workflow` |
| K2 | What is the recommended token expiration period? | 90 days |
| K3 | What does a valid GitHub PAT start with? | `ghp_` |
| K4 | What happens if the user closes the GitHub token page before copying the token? | The token is lost and cannot be recovered — they must delete it and create a new one |
| K5 | What credential helper is configured by this skill? | `store` |
| K6 | What is the default branch name configured by this skill? | `main` |
| K7 | Which core files does this skill update? | AGENTS.md, TOOLS.md, MEMORY.md |
| K8 | Which core files must NOT be updated by this skill? | IDENTITY.md, HEARTBEAT.md, USER.md, SOUL.md |
| K9 | Should the agent use `gh` CLI for setup/auth in this onboarding flow? | No — API-only execution lock. Browser-based PAT + API token + local git config only |
| K10 | Where does the full GitHub setup documentation live on disk? | In the OpenClaw master files folder under `10-github-setup/github-setup-full.md` |
| K11 | What five commit message prefixes does this skill define? | Fix, Feature, Docs, Refactor, Chore |
| K12 | Name three things that must NEVER be committed to GitHub | .env files with secrets, API tokens/passwords, node_modules/ (also acceptable: large binary files, database passwords, private certificates) |

```
[ ] K1  PASS
[ ] K2  PASS
[ ] K3  PASS
[ ] K4  PASS
[ ] K5  PASS
[ ] K6  PASS
[ ] K7  PASS
[ ] K8  PASS
[ ] K9  PASS
[ ] K10 PASS
[ ] K11 PASS
[ ] K12 PASS
```

PASS criteria: All 12 questions answered correctly without hesitation or file lookup.

---

## 5. LIVE BEHAVIOR TESTS

Run these tests to confirm the skill functions correctly end-to-end.

### Test A: GitHub API authentication
```bash
source "$SECRETS_FILE"
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/user" | jq -r '.login'
```

```
[ ] Output is a plain GitHub username string (no quotes, no "null", no error message)
[ ] HTTP response is not 401 Unauthorized
```

PASS criteria: Returns the correct GitHub username as a plain string.

---

### Test B: List repositories
```bash
source "$SECRETS_FILE"
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/user/repos" | jq -r '.[].name' | head -5
```

```
[ ] Command executes without error
[ ] Returns a list of repository names (or empty array if account is new — both acceptable)
[ ] Does NOT return an authentication error
```

PASS criteria: API call succeeds and returns valid JSON.

---

### Test C: Git commit simulation (dry run)
In a temporary directory, verify the agent can run a full git workflow:

```bash
mkdir /tmp/qc-github-test && cd /tmp/qc-github-test
git init
echo "test" > test.txt
git add .
git commit -m "Chore: QC test commit"
git log --oneline -1
cd ~ && rm -rf /tmp/qc-github-test
```

```
[ ] git init succeeds
[ ] git add . succeeds
[ ] git commit succeeds and shows correct author name and email in output
[ ] git log shows the commit with the message "Chore: QC test commit"
[ ] Commit author matches the user.name and user.email configured in Step 3a
```

PASS criteria: Full commit cycle completes without error; author identity is correct.

---

### Test D: Token format validation
Ask the agent: "What is the GitHub token stored in secrets?"

```
[ ] Agent retrieves the token from $SECRETS_FILE (not from memory or hardcoded)
[ ] Agent confirms the token starts with "ghp_"
[ ] Agent does NOT print the full token value in plain text to the user
    (it should acknowledge it exists and is valid, not expose it)
```

PASS criteria: Agent knows where the token lives, confirms format, and handles it securely.

---

## 6. ANTI-PATTERN CHECKS

These are failure modes this skill explicitly guards against. Verify none of them occurred.

```
[ ] AP1  Agent did NOT use `gh auth login` or any GitHub CLI command during setup
         Check: grep -r "gh auth\|gh repo\|gh pr" ~/clawd/ — should return nothing relevant

[ ] AP2  Agent did NOT paste multi-page GitHub documentation into AGENTS.md, TOOLS.md, or MEMORY.md
         Check: wc -l ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
         Flag if any file grew by more than ~30 lines from this install

[ ] AP3  Agent did NOT store GITHUB_TOKEN in AGENTS.md, TOOLS.md, or MEMORY.md
         Check: grep "ghp_" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
         Expected: no matches

[ ] AP4  Agent did NOT set token expiration to "No expiration"
         Verify the PAT on https://github.com/settings/tokens shows a 90-day expiry

[ ] AP5  Agent did NOT add extra scopes beyond repo, read:org, workflow without justification
         Verify on https://github.com/settings/tokens — click the token name to inspect scopes

[ ] AP6  Agent did NOT trigger a gateway restart autonomously
         No `/restart` or `openclaw gateway restart` should have been executed

[ ] AP7  Agent did NOT commit or push the secrets file to any repository
         Check: git -C "$(dirname $SECRETS_FILE)" log --all --full-history -- "$(basename $SECRETS_FILE)" 2>/dev/null
         Expected: no commits found for the secrets file

[ ] AP8  Agent did NOT skip the TYP check before executing the skill
         Core files must be lean — this is the observable evidence that TYP was followed
```

PASS criteria: All 8 anti-patterns are absent.

---

## 7. PASS CRITERIA SUMMARY

| Section | Items | Required to Pass |
|---------|-------|-----------------|
| 1. File Structure | 8 | All 8 present |
| 2. Core File Updates | 16 | All 16 correct |
| 3. System Configuration | 10 | All 10 correct |
| 4. Knowledge Questions | 12 | 12/12 correct |
| 5. Live Behavior Tests | 12 | All 12 pass |
| 6. Anti-Pattern Checks | 8 | All 8 absent |
| **Total** | **66** | **66/66** |

---

### Overall Result

```
[ ] PASS  — All 66 checks passed. GitHub setup skill is correctly installed.
[ ] FAIL  — One or more checks failed. See failed items above and remediate before use.
```

**Failed items (list any here):**
-
-
-

**QC run date:** _______________
**Run by (agent session ID or note):** _______________
