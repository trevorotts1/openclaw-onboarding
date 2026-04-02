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
