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
