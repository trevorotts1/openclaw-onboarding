# QC Checklist - Skill 09: Context7
**Version:** v6.5.6

Run this after installation. Every section must pass before you mark Context7 complete.

---

## 1. File and version checks

Confirm the onboarding folder is intact and the version file matches this checklist.

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/09-context7"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `context7-full.md`, `QC.md`, and `skill-version.txt` all exist
- [ ] `skill-version.txt` returns `v6.5.6`
- [ ] `context7-full.md` is non-empty

**PASS:** All files exist and the version matches.

---

## 2. Core file update checks

Verify the lean summaries were added without dumping the whole skill into core files.

```bash
grep -n "Context7" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```

- [ ] `AGENTS.md` mentions Context7 as a docs lookup tool and says to use it before coding against external APIs
- [ ] `TOOLS.md` includes both endpoints below:
  - `https://api.context7.com/v1/search?q=<library>`
  - `https://api.context7.com/v1/libraries/<id>/context`
- [ ] `MEMORY.md` contains a short reminder, not a pasted copy of the full skill
- [ ] Forbidden files such as `IDENTITY.md`, `SOUL.md`, and `USER.md` were not edited for this skill

**PASS:** All three core files contain short, correct references only.

---

## 3. Secret storage checks

Context7 is API-only. There is no CLI install for this skill.

```bash
printenv CONTEXT7_API_KEY | sed 's/./*/g' | head -c 8; echo
grep -n '^CONTEXT7_API_KEY=' ~/clawd/secrets/.env 2>/dev/null
```

- [ ] A `CONTEXT7_API_KEY` exists in environment or secrets storage
- [ ] Stored key starts with `ctx7sk-`
- [ ] Key is not committed into repo files or pasted into core docs
- [ ] No one installed or relied on a fake `context7` CLI for setup

**PASS:** A valid-looking key exists and the skill stays API-only.

---

## 4. Functional API tests

Run the real lookup flow the skill depends on.

### 4A. Search test
```bash
source ~/clawd/secrets/.env 2>/dev/null || true
curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY"   "https://api.context7.com/v1/search?q=react" | jq '.results[0]'
```

- [ ] Returns JSON, not HTML or an auth error
- [ ] `.results[0].id` is non-null
- [ ] `.results[0].name` is non-empty

### 4B. Fetch docs test
Use the ID from the search result above.
```bash
LIB_ID="<paste-library-id-here>"
curl -s -H "Authorization: Bearer $CONTEXT7_API_KEY"   "https://api.context7.com/v1/libraries/$LIB_ID/context" | jq 'keys'
```

- [ ] Request succeeds with HTTP 200 behavior
- [ ] Response contains documentation content, not `401`, `403`, or empty output
- [ ] This confirms the full search -> fetch-docs flow works

**PASS:** Both API calls succeed.

---

## 5. Failure conditions

Mark this skill FAIL if any of these are true:

- [ ] `skill-version.txt` does not match `v6.5.6`
- [ ] `CONTEXT7_API_KEY` is missing or malformed
- [ ] Search works but docs fetch fails
- [ ] Core files are bloated with copied full-doc content
- [ ] Installer relied on a Context7 CLI even though this skill is API-only

---

## Final pass rule

Pass this skill only if all of the following are true:

- [ ] File set is complete
- [ ] Version matches `v6.5.6`
- [ ] Core file summaries are lean and correct
- [ ] `CONTEXT7_API_KEY` is stored correctly
- [ ] Search and docs fetch both work with the real API

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
