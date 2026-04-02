# QC Checklist - Skill 17: Self-Improving Agent
**Version:** v6.5.6

Run this after installation. Every section must pass before you mark self-improving-agent complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/17-self-improving-agent"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `self-improving-agent-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.6`
- [ ] `self-improving-agent-full.md` is non-empty

---

## 2. Installed skill folder checks

```bash
ls -la ~/.openclaw/skills/self-improving-agent
ls -la ~/.openclaw/skills/self-improving-agent/.learnings
```

- [ ] Installed skill folder exists at `~/.openclaw/skills/self-improving-agent`
- [ ] `SKILL.md`, `INSTALL.md`, and `CORE_UPDATES.md` exist there
- [ ] `.learnings/` exists inside the installed skill folder
- [ ] `.learnings/LEARNINGS.md`, `.learnings/ERRORS.md`, and `.learnings/FEATURE_REQUESTS.md` all exist

---

## 3. Upstream asset and hook checks

```bash
for f in   assets/LEARNINGS.md   assets/SKILL-TEMPLATE.md   hooks/openclaw/HOOK.md   references/examples.md   references/hooks-setup.md   references/openclaw-integration.md; do
  [ -f "$HOME/.openclaw/skills/self-improving-agent/$f" ] && echo "PASS $f" || echo "FAIL $f"
done
ls -la ~/.openclaw/hooks/self-improvement 2>/dev/null || true
```

- [ ] All upstream reference assets listed above exist
- [ ] Hook directory exists if the install copied hooks into runtime location
- [ ] No expected upstream subfolder is missing

---

## 4. Writability and smoke tests

### 4A. Writable learnings folder
```bash
LDIR="$HOME/.openclaw/skills/self-improving-agent/.learnings"
touch "$LDIR/.qc-write-test" && rm "$LDIR/.qc-write-test"
```

- [ ] `.learnings/` is writable

### 4B. Workspace learnings location
```bash
mkdir -p ~/.openclaw/workspace/.learnings
ls -ld ~/.openclaw/workspace/.learnings
```

- [ ] Workspace learnings directory exists if the install created it

### 4C. Installer smoke test
```bash
echo "--- Self-Improving Agent Smoke Test ---"
SKILL_FILE=~/.openclaw/skills/self-improving-agent/SKILL.md
[ -s "$SKILL_FILE" ] && echo "PASS: SKILL.md present and non-empty" || echo "FAIL: SKILL.md"
for f in SKILL.md INSTALL.md CORE_UPDATES.md; do
  [ -f "$HOME/.openclaw/skills/self-improving-agent/$f" ] && echo "PASS: $f present" || echo "FAIL: $f missing"
done
```

- [ ] Smoke test prints PASS for the installed core files

---

## 5. Core file policy checks

```bash
grep -n "self-improving\|self-improvement" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md 2>/dev/null
```

- [ ] Core files reference the skill briefly if CORE_UPDATES required it
- [ ] Full imported upstream documentation was **not** pasted into core files
- [ ] TYP-first behavior is preserved in docs and usage notes

---

## 6. Failure conditions

Fail this skill if any of these happen:

- [ ] `skill-version.txt` is wrong
- [ ] Installed skill folder is missing
- [ ] `.learnings/` is missing or not writable
- [ ] Upstream assets or references are missing
- [ ] Smoke test fails on installed files

---

## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Installed skill folder exists in the runtime skill path
- [ ] `.learnings/` exists and is writable
- [ ] Upstream assets and references are present
- [ ] Smoke test passes
