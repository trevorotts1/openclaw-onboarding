# QC Checklist - Skill 11: SuperDesign
**Version:** v6.5.6

Run this after installation. Every section must pass before you mark SuperDesign complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/11-superdesign"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `superdesign-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.6`
- [ ] `superdesign-full.md` is non-empty

---

## 2. Core file update checks

```bash
grep -n "SuperDesign" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```

- [ ] `AGENTS.md` says design first, build second
- [ ] `TOOLS.md` includes the CLI install command `npm install -g @superdesign/cli@latest`
- [ ] Core docs mention key commands such as `superdesign create-project` and `superdesign search-prompts`
- [ ] Full docs are referenced by file path, not pasted in full

---

## 3. Required installation checks

```bash
node --version
npm --version
which superdesign || true
superdesign --version || npx superdesign --version
ls -la ~/.agents/skills/superdesign/ 2>/dev/null
```

- [ ] Node.js is installed and version is 16+
- [ ] npm is installed
- [ ] SuperDesign CLI resolves by `superdesign` or `npx superdesign`
- [ ] `~/.agents/skills/superdesign/` exists
- [ ] Skill folder contains the expected SuperDesign files

---

## 4. Optional provider key check for IDE extension

SuperDesign can work through the web app and CLI, but the IDE extension expects one of these keys.

```bash
grep -E '^(ANTHROPIC_API_KEY|OPENAI_API_KEY|OPENROUTER_API_KEY)=' ~/clawd/secrets/.env 2>/dev/null
```

- [ ] At least one of `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY` exists if IDE mode was configured
- [ ] If IDE mode was skipped, that skip is documented

---

## 5. Functional CLI tests

### 5A. Help and login persistence
```bash
superdesign --help >/dev/null
```

- [ ] Help command exits successfully

### 5B. Prompt search test
```bash
superdesign search-prompts --keyword "landing page" --json
```

- [ ] Returns JSON, not an auth error
- [ ] Output contains at least one prompt result

### 5C. Project creation smoke test
```bash
superdesign create-project --title "QC Test Page" --json
```

- [ ] Command succeeds
- [ ] Output contains project metadata such as ID, title, or JSON result
- [ ] This confirms the CLI is installed and authenticated, not just present in PATH

---

## 6. Optional extension checks

Run these only if the user installed browser or IDE extensions.

```bash
code --list-extensions 2>/dev/null | grep -i superdesign || true
cursor --list-extensions 2>/dev/null | grep -i superdesign || true
```

- [ ] IDE extension is present if that part of install was completed
- [ ] If project initialization was performed, at least one of these exists in a test project: `.superdesign/`, `CLAUDE.md`, `.cursor/rules/design.mdc`, `.windsurfrules`

---

## 7. Failure conditions

Fail this skill if any of these happen:

- [ ] `skill-version.txt` is wrong
- [ ] CLI is not installed or `superdesign --version` fails
- [ ] Search works but project creation fails due to auth or missing setup
- [ ] Skill repo is missing from `~/.agents/skills/superdesign/`
- [ ] Core docs are bloated with full install content

---

## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Core summaries are present and lean
- [ ] Node, npm, and SuperDesign CLI work
- [ ] Skill repo is installed
- [ ] `search-prompts` and `create-project` both succeed

---

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
