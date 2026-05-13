# QC Checklist - Skill 12: OpenRouter Setup
**Version:** v6.5.9

Run this after installation. Every section must pass before you mark OpenRouter complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/12-openrouter-setup"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `openrouter-setup-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.9`
- [ ] `openrouter-setup-full.md` is non-empty

---

## 2. Backup and JSON safety checks

```bash
ls -lt ~/Downloads/openclaw-backups 2>/dev/null | head
jq empty ~/.openclaw/openclaw.json
```

- [ ] A timestamped backup of `openclaw.json` exists in `~/Downloads/openclaw-backups`
- [ ] Active config is valid JSON
- [ ] Backup file is non-empty

---

## 3. Key and model config checks

```bash
jq -r '.env.OPENROUTER_API_KEY // empty' ~/.openclaw/openclaw.json | sed 's/./*/g' | head -c 8; echo
jq -r '.agents.defaults.model.primary' ~/.openclaw/openclaw.json
jq -r '.agents.defaults.model.fallbacks[]' ~/.openclaw/openclaw.json
```

- [ ] `OPENROUTER_API_KEY` exists in config or documented env storage
- [ ] Key format starts with `sk-or-`
- [ ] Primary model is exactly `openrouter/minimax/minimax-m2.7`
- [ ] Fallback list includes at least these models:
  - `openrouter/xiaomi/mimo-v2-pro`
  - `openrouter/google/gemini-3.1-flash-lite-preview`
  - `openrouter/moonshotai/kimi-k2.5`
  - `openrouter/google/gemini-3-flash-preview`
- [ ] No fallback entry uses `openrouter/auto`

---

## 4. Model object integrity checks

```bash
jq '.agents.defaults.models | keys' ~/.openclaw/openclaw.json
```

Verify these keys exist inside `.agents.defaults.models`:

- [ ] `openrouter/minimax/minimax-m2.7`
- [ ] `openrouter/xiaomi/mimo-v2-pro`
- [ ] `openrouter/google/gemini-3-flash-preview`
- [ ] `openrouter/google/gemini-3.1-pro-preview`
- [ ] `openrouter/google/gemini-3.1-flash-lite-preview`
- [ ] `openrouter/moonshotai/kimi-k2.5`
- [ ] `openrouter/z-ai/glm-5`
- [ ] `openrouter/deepseek/deepseek-v3.2`
- [ ] `openrouter/deepseek/deepseek-r1-0528:free`
- [ ] `openrouter/xiaomi/mimo-v2-omni`
- [ ] `openrouter/nvidia/nemotron-3-super-120b-a12b:free`

Also verify each model object stays minimal.

```bash
jq '.agents.defaults.models["openrouter/minimax/minimax-m2.7"]' ~/.openclaw/openclaw.json
```

- [ ] Model entries only use allowed fields such as `params`, `alias`, or `streaming`
- [ ] No stray keys like `contextWindow`, `maxTokens`, or `context` were added

---

## 5. Functional API test

### 5A. Credits endpoint test
```bash
OPENROUTER_API_KEY=$(jq -r '.env.OPENROUTER_API_KEY // empty' ~/.openclaw/openclaw.json)
curl -s -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/credits | jq '.data'
```

- [ ] Returns JSON under `.data`
- [ ] Does not return `401`, `402`, or `invalid api key`

### 5B. Sanity check for banned auto-routing
```bash
grep -n 'openrouter/auto' ~/.openclaw/openclaw.json
```

- [ ] No results returned

**PASS:** The API key works and the config follows the skill rules.

---

## 6. Failure conditions

Fail this skill if any of these happen:

- [ ] Backup was skipped
- [ ] Config JSON is invalid
- [ ] `OPENROUTER_API_KEY` is missing or malformed
- [ ] Primary model is not `openrouter/minimax/minimax-m2.7`
- [ ] `openrouter/auto` appears anywhere in config
- [ ] Credits endpoint fails

---

## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Backup exists and config JSON is valid
- [ ] API key is stored correctly
- [ ] Primary plus required fallback models are configured
- [ ] Credits endpoint succeeds
- [ ] No banned `openrouter/auto` entry exists

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
