# QC Checklist - Skill 14: Google Workspace Integration
**Version:** v6.5.6

Run this after installation. Every section must pass before you mark Google Workspace integration complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `google-workspace-integration-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.6`
- [ ] `google-workspace-integration-full.md` is non-empty

---

## 2. Core file update checks

```bash
grep -n "gws\|Google Workspace" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```

- [ ] Core docs say `gws` replaces older ad hoc Google tooling for this install path
- [ ] Docs mention both auth paths: Gmail OAuth and Workspace/service-account auth
- [ ] Docs stay short and reference the full guide by file path

---

## 3. CLI installation checks

```bash
node --version
npm --version
gws --version
```

- [ ] Node.js is installed and version is 18+
- [ ] npm is installed
- [ ] `gws --version` returns a real version number

---

## 4. Authentication checks

### 4A. Generic auth listing
```bash
gws auth list
```

- [ ] At least one account or auth profile is listed
- [ ] Output does not show `Not authenticated`

### 4B. Workspace credential path check
Run this only for Workspace/service-account installs.
```bash
printenv GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE
[ -n "$GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE" ] && ls -l "$GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"
```

- [ ] `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` is set if the install used a service account
- [ ] Referenced JSON file exists and is readable

### 4C. gcloud check
Run this only if the install used the gcloud path.
```bash
gcloud auth list 2>/dev/null
```

- [ ] Active gcloud identity exists if gcloud auth was used

---

## 5. Functional service tests

These are the exact service checks named in INSTALL.md.

### 5A. Gmail
```bash
gws gmail +triage
```
- [ ] Command succeeds

### 5B. Calendar
```bash
gws calendar +agenda
```
- [ ] Command succeeds

### 5C. Drive
```bash
gws drive files list --params '{"pageSize": 5}'
```
- [ ] Returns a file list without 401/403 errors

### 5D. Sheets
```bash
gws sheets spreadsheets create --json '{"properties": {"title": "QC Test Sheet"}}'
```
- [ ] Spreadsheet create call succeeds
- [ ] Cleanup is documented if you created a live test sheet

### 5E. Docs
```bash
gws docs +write
```
- [ ] Command succeeds

### 5F. Tasks
```bash
gws tasks tasklists list
```
- [ ] Command succeeds

---

## 6. OpenClaw skill-link checks

```bash
ls -la ~/.openclaw/skills 2>/dev/null | head -50
```

- [ ] gws-provided OpenClaw skills were copied or linked into `~/.openclaw/skills`
- [ ] Skill files are readable by the runtime user

---

## 7. Failure conditions

Fail this skill if any of these happen:

- [ ] `skill-version.txt` is wrong
- [ ] `gws --version` fails
- [ ] `gws auth list` shows no usable auth
- [ ] One of the required service tests fails with auth or API errors
- [ ] gws skill files were not linked into the OpenClaw skills folder

---

## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Core summaries are present and lean
- [ ] Node 18+, npm, and gws are installed
- [ ] Auth path is valid for Gmail or Workspace mode
- [ ] Gmail, Calendar, Drive, Sheets, Docs, and Tasks tests all pass
- [ ] OpenClaw gws skills are installed
