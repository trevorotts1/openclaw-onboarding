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
