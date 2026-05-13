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

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `/data/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
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
