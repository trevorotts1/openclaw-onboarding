# QC Checklist — tavily-search

Run this after installation to verify the skill is installed correctly.
Each item is a command or check the agent can execute autonomously.
Mark each item ✅ PASS or ❌ FAIL. A single ❌ FAIL blocks the skill from use.

---

## 1. File Structure Checks

Verify the install target contains all required files.

```bash
ls ~/.openclaw/skills/tavily-search/
```

| # | Check | Expected |
|---|-------|----------|
| 1.1 | `~/.openclaw/skills/tavily-search/` directory exists | Directory present |
| 1.2 | `~/.openclaw/skills/tavily-search/SKILL.md` exists | File present |
| 1.3 | `~/.openclaw/skills/tavily-search/scripts/search.mjs` exists | File present |
| 1.4 | `~/.openclaw/skills/tavily-search/scripts/extract.mjs` exists | File present |
| 1.5 | No extra unexpected files were created outside `~/.openclaw/skills/tavily-search/` | Clean install boundary |

**Commands to run:**
```bash
test -f ~/.openclaw/skills/tavily-search/SKILL.md && echo "PASS: SKILL.md" || echo "FAIL: SKILL.md missing"
test -f ~/.openclaw/skills/tavily-search/scripts/search.mjs && echo "PASS: search.mjs" || echo "FAIL: search.mjs missing"
test -f ~/.openclaw/skills/tavily-search/scripts/extract.mjs && echo "PASS: extract.mjs" || echo "FAIL: extract.mjs missing"
```

---

## 2. Core File Update Checks

Verify only the permitted core files were updated, and only with lean summaries (not full content dumps).

| # | Check | Expected |
|---|-------|----------|
| 2.1 | `AGENTS.md` contains a trigger/use statement for Tavily web search tasks | Present, lean (not full doc dump) |
| 2.2 | `TOOLS.md` contains env requirement (`TAVILY_API_KEY`) and usage pattern for Tavily | Present, lean |
| 2.3 | `MEMORY.md` contains persistent routing/constraints entry for Tavily | Present, lean |
| 2.4 | `SOUL.md` was NOT modified | Unchanged |
| 2.5 | `IDENTITY.md` was NOT modified | Unchanged |
| 2.6 | `HEARTBEAT.md` was NOT modified | Unchanged |
| 2.7 | Full documentation was saved to `~/Downloads/openclaw-master-files/` (not dumped into core files) | Full doc in master files folder |

**Commands to run:**
```bash
grep -i "tavily" ~/.openclaw/AGENTS.md && echo "PASS: AGENTS.md updated" || echo "FAIL: AGENTS.md missing Tavily entry"
grep -i "TAVILY_API_KEY" ~/.openclaw/TOOLS.md && echo "PASS: TOOLS.md has API key ref" || echo "FAIL: TOOLS.md missing Tavily entry"
grep -i "tavily" ~/.openclaw/MEMORY.md && echo "PASS: MEMORY.md updated" || echo "FAIL: MEMORY.md missing Tavily entry"
```

---

## 3. Knowledge Verification Questions

The agent must be able to answer these correctly from installed docs. No web search allowed for these answers.

| # | Question | Correct Answer |
|---|----------|----------------|
| 3.1 | What env variable does tavily-search require? | `TAVILY_API_KEY` |
| 3.2 | What binary does this skill require? | `node` |
| 3.3 | What is the default number of results returned by search.mjs? | 5 |
| 3.4 | What is the maximum number of results supported via `-n`? | 20 |
| 3.5 | Which flag enables advanced/deeper research mode? | `--deep` |
| 3.6 | Which `--topic` value is used for current events? | `news` |
| 3.7 | Which flag limits news results to a recent time window? | `--days <n>` |
| 3.8 | Which script handles URL content extraction? | `extract.mjs` |
| 3.9 | Which core files are explicitly forbidden from modification by this skill? | `SOUL.md`, `IDENTITY.md`, `HEARTBEAT.md` |
| 3.10 | What must the agent do before triggering a gateway restart? | STOP, notify user, instruct them to type `/restart` in Telegram, and wait for confirmation |

---

## 4. Live Behavior Test

Run a real Tavily search to confirm the skill executes end-to-end.

**Pre-condition:** `TAVILY_API_KEY` must be set in the environment.

```bash
echo "Checking for TAVILY_API_KEY..."
test -n "$TAVILY_API_KEY" && echo "PASS: TAVILY_API_KEY is set" || echo "FAIL: TAVILY_API_KEY not found in env"
```

**Basic search test:**
```bash
node ~/.openclaw/skills/tavily-search/scripts/search.mjs "OpenClaw AI agent framework" -n 3
```

| # | Check | Expected |
|---|-------|----------|
| 4.1 | Command exits without error (exit code 0) | Exit code: 0 |
| 4.2 | Output contains at least one result URL | URL present in output |
| 4.3 | Output contains a snippet or summary text | Non-empty result body |
| 4.4 | `-n 3` flag is respected (returns ~3 results, not default 5) | ~3 results returned |

**Extract test (dry run — verifies script loads correctly):**
```bash
node ~/.openclaw/skills/tavily-search/scripts/extract.mjs --help 2>&1 || node ~/.openclaw/skills/tavily-search/scripts/extract.mjs "" 2>&1 | head -5
```

| # | Check | Expected |
|---|-------|----------|
| 4.5 | `extract.mjs` loads without a Node.js syntax/parse error | No `SyntaxError` in output |

---

## 5. Anti-Pattern Checks

These checks catch incorrect or dangerous install behaviors.

| # | Anti-Pattern | How to Check | Pass Condition |
|---|-------------|--------------|----------------|
| 5.1 | Full SKILL.md or script content pasted directly into AGENTS.md | `wc -l ~/.openclaw/AGENTS.md` and review Tavily section | Tavily section in AGENTS.md is ≤ 10 lines (summary + path ref only) |
| 5.2 | Full SKILL.md or script content pasted directly into TOOLS.md | Review Tavily section in TOOLS.md | Tavily section in TOOLS.md is ≤ 10 lines |
| 5.3 | Full SKILL.md or script content pasted directly into MEMORY.md | Review Tavily section in MEMORY.md | Tavily section in MEMORY.md is ≤ 10 lines |
| 5.4 | Agent autonomously ran a gateway restart during install | Check session logs / agent transcript | No `openclaw gateway restart` was executed without explicit user confirmation |
| 5.5 | Install was partially completed then abandoned (scripts folder exists but SKILL.md is missing, or vice versa) | Run file structure checks from Section 1 | All files present or none present (no partial state) |
| 5.6 | SOUL.md, IDENTITY.md, or HEARTBEAT.md were modified | `git diff` or manual review of those files | Zero changes to these files |
| 5.7 | Files were installed to a path other than `~/.openclaw/skills/tavily-search/` | Check for stray files in `/tmp`, `~/`, or project folder | Skill files exist only at canonical path |
| 5.8 | TYP was not confirmed before install proceeded | Review agent transcript for TYP check | TYP confirmation appears before any install step |

---

## 6. Pass Criteria

The skill is considered **fully installed and verified** only when ALL of the following are true:

| Criteria | Status |
|----------|--------|
| All Section 1 file structure checks pass | ☐ |
| All Section 2 core file update checks pass | ☐ |
| All Section 3 knowledge questions answered correctly | ☐ |
| All Section 4 live behavior tests pass (requires valid `TAVILY_API_KEY`) | ☐ |
| All Section 5 anti-pattern checks pass (no violations found) | ☐ |

**If `TAVILY_API_KEY` is not yet set:** Sections 1, 2, 3, and 5 can still be verified. Section 4 requires the key. Mark Section 4 as DEFERRED and note that live test must be run before the skill is used in production.

**Overall result:**
- ✅ ALL PASS → Skill is verified and ready to use
- ❌ ANY FAIL → Do not use the skill. Identify the failing check, remediate, and re-run this QC from the top.

---

*QC version: 1.0.0 — skill version: 1.5.0 (CHANGELOG March 7, 2026)*

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
