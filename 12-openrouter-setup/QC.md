# QC Checklist — Skill 12: OpenRouter Setup

Run this after installation to verify the skill installed correctly.
Each section lists what to check, what command to run (where applicable), and the pass condition.
Mark each item ✅ PASS or ❌ FAIL. A single ❌ FAIL means the installation is incomplete.

---

## SECTION 1: File Structure Checks

Verify all required skill files exist in the correct location.

**1.1** Skill folder exists at expected path.
```bash
ls ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/12-openrouter-setup/
```
**Pass:** Output includes: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `openrouter-setup-full.md`

---

**1.2** Config backup folder was created.
```bash
ls ~/openclaw-backup-configs/
```
**Pass:** Folder exists and contains at least one `.json` file with a timestamped name.

---

**1.3** At least one backup file is non-empty.
```bash
ls -lh ~/openclaw-backup-configs/*.json | head -5
```
**Pass:** All listed files show a file size greater than 0 bytes. No empty backups.

---

**1.4** OpenClaw config file exists and is valid JSON.
```bash
jq empty ~/.openclaw/openclaw.json && echo "Valid JSON"
```
**Pass:** Output is `Valid JSON` with no errors.

---

## SECTION 2: Core Config File Checks

Verify the config was updated correctly with no schema violations.

**2.1** API key is present in the config `env` section.
```bash
jq '.env.OPENROUTER_API_KEY' ~/.openclaw/openclaw.json
```
**Pass:** Output is a quoted string beginning with `"sk-or-`. Must not be `null` or empty.

---

**2.2** Primary model is set to MiniMax M2.5.
```bash
jq '.agents.defaults.model.primary' ~/.openclaw/openclaw.json
```
**Pass:** Output is `"openrouter/minimax/minimax-m2.5"`.

---

**2.3** Fallback array contains exactly two models.
```bash
jq '.agents.defaults.model.fallbacks' ~/.openclaw/openclaw.json
```
**Pass:** Output is:
```json
[
  "openrouter/moonshotai/kimi-k2.5",
  "openrouter/deepseek/deepseek-r1-0528:free"
]
```

---

**2.4** All 17 models are present in `agents.defaults.models`.
```bash
jq '.agents.defaults.models | keys | length' ~/.openclaw/openclaw.json
```
**Pass:** Output is `17` or greater (existing pre-install models would add to the count).

Spot-check three specific entries:
```bash
jq '.agents.defaults.models["openrouter/minimax/minimax-m2.5"]' ~/.openclaw/openclaw.json
jq '.agents.defaults.models["openrouter/moonshotai/kimi-k2.5"]' ~/.openclaw/openclaw.json
jq '.agents.defaults.models["openrouter/deepseek/deepseek-r1-0528:free"]' ~/.openclaw/openclaw.json
```
**Pass:** All three return non-null objects.

---

**2.5** MiniMax M2.5 has HIGH thinking configured.
```bash
jq '.agents.defaults.models["openrouter/minimax/minimax-m2.5"].params.reasoning.effort' ~/.openclaw/openclaw.json
```
**Pass:** Output is `"high"`.

---

**2.6** Kimi K2.5 has temperature 1.0 and NO reasoning key.
```bash
jq '.agents.defaults.models["openrouter/moonshotai/kimi-k2.5"]' ~/.openclaw/openclaw.json
```
**Pass:** Output shows `"temperature": 1` and no `"reasoning"` key present.

---

**2.7** No model entry contains forbidden keys (`contextWindow`, `maxTokens`, `cost`, `pricing`, `notes`, `description`, `tier`).
```bash
jq '[.agents.defaults.models | to_entries[] | .value | keys[]] | unique' ~/.openclaw/openclaw.json
```
**Pass:** The only keys that appear are any combination of `alias`, `params`, `streaming`. Any other key is a ❌ FAIL.

---

**2.8** No model ID uses the forbidden `openrouter/auto` value.
```bash
jq '.agents.defaults.models | keys[] | select(contains("auto"))' ~/.openclaw/openclaw.json
```
**Pass:** No output (empty result). Any match is a ❌ FAIL.

---

**2.9** No model ID is missing the `openrouter/` prefix.
```bash
jq '.agents.defaults.models | keys[] | select(startswith("openrouter/") | not)' ~/.openclaw/openclaw.json
```
**Pass:** No output (empty result). Any match means a model was added without the required prefix.

---

**2.10** Config validates cleanly.
```bash
openclaw doctor
```
**Pass:** All checks show green/pass. No red/fail lines. Warnings (yellow) are acceptable.

---

## SECTION 3: Core Workspace File Update Checks

Verify AGENTS.md, TOOLS.md, and MEMORY.md were updated correctly.

**3.1** AGENTS.md contains the model routing section.
```bash
grep -i "openrouter model routing" ~/clawd/AGENTS.md
```
**Pass:** Line found. The section includes the `[PRIORITY: CRITICAL]` label.

---

**3.2** AGENTS.md routing section points to the full reference file.
```bash
grep "openrouter-setup-full.md" ~/clawd/AGENTS.md
```
**Pass:** A line is found. The full doc path is referenced (not just a vague mention).

---

**3.3** TOOLS.md contains the OpenRouter section.
```bash
grep -i "openrouter" ~/clawd/TOOLS.md
```
**Pass:** At least two lines are found: one for the config path and one for the full reference.

---

**3.4** TOOLS.md references the correct config file path.
```bash
grep "openclaw.json" ~/clawd/TOOLS.md
```
**Pass:** Line found showing `~/.openclaw/openclaw.json`.

---

**3.5** MEMORY.md contains an OpenRouter installation entry.
```bash
grep -i "openrouter" ~/clawd/MEMORY.md
```
**Pass:** Line found with a dated entry (e.g., `OpenRouter Setup - Installed [date]`).

---

**3.6** Core files are lean — no full skill content dumped in.
```bash
wc -l ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```
**Pass:** No single file has grown by more than ~30 lines from this skill install. If AGENTS.md or TOOLS.md shows hundreds of new lines, the agent dumped the full guide instead of adding a lean summary — that is a ❌ FAIL.

---

## SECTION 4: Knowledge Verification Questions

Answer these from memory (without re-reading the skill docs). If the agent cannot answer correctly, re-read the relevant section.

**4.1** What is the recommended primary model and why?
**Expected answer:** `openrouter/minimax/minimax-m2.5` — it supports tool calls, has HIGH thinking enabled by default, and costs $0.30 per million input tokens. It is the daily workhorse.

---

**4.2** Why can Kimi K2.5 never be assigned a task that requires tool calls?
**Expected answer:** Kimi K2.5 does not support tool calls. It is for code generation and chat only. Sending it a tool-call task will fail silently.

---

**4.3** What are the only three valid keys inside a model entry in `agents.defaults.models`?
**Expected answer:** `alias`, `params`, and `streaming`. Nothing else. Adding any other key breaks the config.

---

**4.4** What happens when the OpenRouter API returns a 402 error?
**Expected answer:** The agent immediately switches to `openrouter/deepseek/deepseek-r1-0528:free`, notifies the user that credits are depleted, and continues working. It does not stop.

---

**4.5** What is the correct model ID format for OpenRouter models?
**Expected answer:** `openrouter/author/model-slug` — the `openrouter/` prefix is mandatory. Example: `openrouter/anthropic/claude-opus-4.6`.

---

**4.6** What thinking level does MiniMax M2.5 use by default, and why is it different from other models?
**Expected answer:** HIGH (`effort: "high"`). Other models default to medium. MiniMax is the daily task model and needs reliable tool execution, so it gets higher reasoning by default.

---

**4.7** What model should be used for all creative writing tasks, and why?
**Expected answer:** `openrouter/mistralai/mistral-small-creative`. It is purpose-built for writing at only $0.10 per million input tokens — the cheapest option for creative work.

---

**4.8** When must a backup be created, and what stops the install if it fails?
**Expected answer:** Before ANY edit to the config file. If the backup file is empty or does not exist after the copy command, the agent must STOP and report the failure. It must not proceed.

---

**4.9** What is the ORDER LOCK rule for this skill?
**Expected answer:** OpenRouter setup must run LAST in the onboarding sequence. No other skill installs should run after this one.

---

**4.10** What is the model switching permission protocol when the agent recommends a switch?
**Expected answer:** Agent tells user which model it recommends and why, states the cost difference, waits up to 60 seconds for a response. If approved, it switches. If declined, it stays. If no response within 60 seconds, it proceeds with its recommendation and logs the decision.

---

## SECTION 5: Live Behavior Test

These tests confirm the installed setup works end-to-end.

**5.1** Gateway is running after setup.
```bash
openclaw gateway status
```
**Pass:** Output contains `running` or `active` with a PID number and a listening port (e.g., `port 3578`).

---

**5.2** Active model responds correctly via the gateway.
Send this message to the agent:
> "What model are you currently running on?"

**Pass:** Agent identifies itself as running on MiniMax M2.5 (or the configured primary model). It does not say Claude or GPT without qualifying that it is routing through OpenRouter.

---

**5.3** Model alias switching works.
Send this command:
> `/model kimi`

**Pass:** Agent confirms the switch to Kimi K2.5 and states: "Kimi K2.5 is for code generation and chat only. It does not support tool calls."

Switch back:
> `/model minimax`

**Pass:** Agent confirms return to MiniMax M2.5.

---

**5.4** Thinking level command is recognized.
Send this command:
> `/reasoning high`

**Pass:** Agent confirms thinking level is now set to high and notes this will increase token cost.

Reset it:
> `/reasoning medium`

**Pass:** Agent confirms return to medium thinking.

---

**5.5** Agent demonstrates correct routing logic unprompted.
Send this request:
> "Write a short blog post intro about the future of AI."

**Pass:** Agent either switches to Mistral Small Creative (Creative Tier) for this writing task, or explicitly acknowledges that this task belongs to the Creative Tier and explains its model choice. It should not use Opus for a simple writing task.

---

## SECTION 6: Anti-Pattern Checks

These confirm the agent is NOT doing things it is forbidden to do.

**6.1** The config does not contain `openrouter/auto`.
```bash
grep -r "openrouter/auto" ~/.openclaw/openclaw.json
```
**Pass:** No output. Any match is a critical failure.

---

**6.2** The config was not edited without a backup being created first.
```bash
ls -lt ~/openclaw-backup-configs/ | head -3
```
**Pass:** The most recent backup timestamp is from during or just before the install session. If no backup exists, that is a ❌ FAIL.

---

**6.3** Full skill documentation was not dumped into core `.md` files.
Manually review the relevant sections in AGENTS.md and TOOLS.md.
**Pass:** The OpenRouter sections in each file are 10–30 lines of lean summaries with a file path reference. If either file contains hundreds of lines from the skill docs, that is a ❌ FAIL.

---

**6.4** The agent did not restart the gateway autonomously without user permission.
**Pass:** Confirm from the installation log or memory that the agent asked for user confirmation before running `openclaw gateway restart`. If the gateway was restarted silently, that is a ❌ FAIL.

---

**6.5** The agent did not add unknown or custom keys to model entries.
```bash
jq '[.agents.defaults.models | to_entries[] | {model: .key, keys: (.value | keys)}]' ~/.openclaw/openclaw.json
```
**Pass:** For every model, the only keys present are any subset of `["alias", "params", "streaming"]`. Any other key is a ❌ FAIL.

---

**6.6** TYP check was not skipped.
Confirm AGENTS.md or TOOLS.md existed before this install (TYP was present). The agent should have verified TYP was in context before proceeding.
**Pass:** AGENTS.md contains a TYP entry prior to the OpenRouter section. If there is no TYP section and the install proceeded anyway, that is a ❌ FAIL.

---

## Pass Criteria

**Full Pass:** All 30+ checks are ✅ PASS.

**Conditional Pass:** All Section 1–3 checks pass and all Section 4 knowledge questions answered correctly. Section 5 live tests may be deferred if the gateway is not yet accessible (e.g., API key pending).

**Fail:** Any of the following are ❌ FAIL:
- Config is not valid JSON
- `openrouter/auto` appears anywhere in the config
- Any model entry contains keys other than `alias`, `params`, `streaming`
- No backup exists in `~/openclaw-backup-configs/`
- `OPENROUTER_API_KEY` is missing or null in the config
- Primary model is not `openrouter/minimax/minimax-m2.5`
- AGENTS.md or TOOLS.md were not updated
- Full skill documentation was dumped into core files instead of lean summaries

If any FAIL condition is present, identify which installation step was missed and re-run from that step only. Do not re-run the entire install unless the config is corrupted — restore from backup and re-run from the failed step.
