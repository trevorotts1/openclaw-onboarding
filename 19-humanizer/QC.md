# QC Checklist — Humanizer (Skill 19)

Run this after installation to verify the skill is correctly installed and operational.
Each check has a clear pass/fail criterion. Work through all sections in order.

---

## 1. File Structure Checks

Verify the install target directory and required files exist.

- [ ] `~/.openclaw/skills/humanizer/` directory exists
- [ ] `~/.openclaw/skills/humanizer/SKILL.md` exists
- [ ] `~/.openclaw/skills/humanizer/README.md` exists

**How to check:**
```bash
ls ~/.openclaw/skills/humanizer/
```

**Pass:** Both `SKILL.md` and `README.md` are present in the directory.
**Fail:** Directory missing, or either file is absent — reinstall from `upstream-original/`.

---

## 2. Core File Update Checks

Verify the correct core files were updated and the forbidden files were left untouched.

### 2a. Files that MUST have been updated
- [ ] `AGENTS.md` — contains a humanizer entry (skill trigger/use statement + TYP gate rule)
- [ ] `TOOLS.md` — contains any tool commands or endpoints the humanizer skill needs

### 2b. Optional file (only if explicitly required)
- [ ] `MEMORY.md` — if updated, contains only persistent facts/constraints from this skill

### 2c. Files that MUST NOT have been touched
- [ ] `USER.md` — confirm no humanizer content was added
- [ ] `SOUL.md` — confirm no humanizer content was added
- [ ] `IDENTITY.md` — confirm no humanizer content was added
- [ ] `HEARTBEAT.md` — confirm no humanizer content was added

**Pass:** AGENTS.md and TOOLS.md have humanizer entries. USER.md, SOUL.md, IDENTITY.md, HEARTBEAT.md are unchanged.
**Fail:** Any forbidden file was modified, or AGENTS.md/TOOLS.md have no humanizer entry.

---

## 3. Knowledge Verification Questions

Answer each question from memory (without re-reading the skill files). These confirm the agent has internalized the skill content.

### 3a. Pattern count and categories
- [ ] Q: How many AI writing patterns does the humanizer detect?
  - **Expected answer:** 24
- [ ] Q: What are the four pattern categories?
  - **Expected answer:** Content Patterns (1–6), Language and Grammar Patterns (7–12), Style Patterns (13–18), Communication Patterns (19–21), and Filler and Hedging (22–24)
  - *(Note: README groups 19–21 as Communication and 22–24 as Filler/Hedging — both groupings acceptable)*

### 3b. Specific pattern recall
- [ ] Q: What is pattern 8 called and what does it fix?
  - **Expected answer:** Copula avoidance — replacing elaborate constructions like "serves as / stands as / boasts" with simple "is / are / has"
- [ ] Q: What is pattern 11?
  - **Expected answer:** Elegant variation (synonym cycling) — AI's repetition-penalty causes excessive synonym substitution; fix by using consistent terms
- [ ] Q: Name three words on the high-frequency AI vocabulary list (pattern 7).
  - **Expected answer:** Any three from: Additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight, interplay, intricate/intricacies, key (adj), landscape (abstract), pivotal, showcase, tapestry (abstract), testament, underscore, valuable, vibrant

### 3c. Skill behavior rules
- [ ] Q: What is the agent required to do beyond just removing AI patterns?
  - **Expected answer:** Add soul / voice — inject personality, vary rhythm, have opinions, use first person when appropriate, acknowledge complexity
- [ ] Q: What tools is this skill allowed to use?
  - **Expected answer:** Read, Write, Edit, Grep, Glob, AskUserQuestion
- [ ] Q: What is the skill version in the upstream SKILL.md?
  - **Expected answer:** 2.1.1
- [ ] Q: What source is this skill's pattern list based on?
  - **Expected answer:** Wikipedia's "Signs of AI writing" page, maintained by WikiProject AI Cleanup

### 3d. TYP and install protocol
- [ ] Q: What must be confirmed before installing or running this skill?
  - **Expected answer:** Teach Yourself Protocol (TYP) must be completed first
- [ ] Q: If a gateway restart is needed during install, what should the agent do?
  - **Expected answer:** Stop, notify the user, instruct them to type `/restart` in Telegram, and wait — never trigger the restart autonomously

**Pass:** All answers match expected values.
**Fail:** Any incorrect answer — re-read the relevant section of `humanizer-full.md` or `upstream-original/SKILL.md`.

---

## 4. Live Behavior Test

Submit the following AI-sounding paragraph and verify the humanized output removes the flagged patterns.

**Input:**
> The new platform serves as a testament to the company's commitment to innovation. Moreover, it provides a seamless, intuitive, and powerful user experience—ensuring that users can accomplish their goals efficiently. It's not just a product, it's a pivotal moment in the evolving technological landscape. Experts believe this will have a lasting impact on the sector. The future looks bright.

**Patterns present (the agent should catch all of these):**
- "serves as a testament" → pattern 1 (significance inflation) + pattern 8 (copula avoidance)
- "Moreover" → pattern 7 (AI vocabulary)
- "seamless, intuitive, and powerful" → pattern 10 (rule of three) + pattern 4 (promotional language)
- em dash + "-ensuring" phrase → pattern 13 (em dash overuse) + pattern 3 (superficial -ing analysis)
- "It's not just...it's..." → pattern 9 (negative parallelism)
- "pivotal moment" + "evolving technological landscape" → pattern 1 + pattern 7 (AI vocabulary)
- "Experts believe" → pattern 5 (vague attribution)
- "The future looks bright" → pattern 24 (generic positive conclusion)

**Pass criteria for the output:**
- [ ] None of the flagged phrases appear in the rewritten text
- [ ] Output contains specific, concrete details rather than vague claims
- [ ] Output uses "is/are/has" instead of "serves as / stands as"
- [ ] No em dashes used where a comma or period works
- [ ] No rule-of-three list preserved intact
- [ ] Output reads naturally aloud — varied sentence length, not robotic
- [ ] Agent identifies at least 5 of the 8 flagged patterns in a changes summary

**Pass:** All criteria above are met.
**Fail:** Flagged phrases survive in output, or output retains the same AI structure — the skill is not applying the pattern list correctly.

---

## 5. Anti-Pattern Checks

Verify the agent is NOT doing any of the following after install.

- [ ] Agent did NOT edit USER.md, SOUL.md, IDENTITY.md, or HEARTBEAT.md
- [ ] Agent did NOT dump the full SKILL.md content into AGENTS.md or TOOLS.md (core files stay lean — brief summary + file path only)
- [ ] Agent did NOT trigger a gateway restart without explicit user permission
- [ ] Agent did NOT attempt to install or run the skill without first confirming TYP
- [ ] Agent did NOT skip reading the upstream markdown files (`README.md`, `SKILL.md`) before installing
- [ ] Agent did NOT copy files from anywhere other than `upstream-original/` into `~/.openclaw/skills/humanizer/`
- [ ] When humanizing text, agent did NOT produce "clean but soulless" output (technically free of AI words but still monotone and voiceless)
- [ ] Agent did NOT apply the rule-of-three fix by simply removing one item — it should rewrite the sentence structurally

**Pass:** None of the anti-patterns occurred.
**Fail:** Any anti-pattern triggered — review the relevant section of INSTALL.md or CORE_UPDATES.md and correct.

---

## 6. Pass Criteria Summary

| Section | Requirement | Status |
|---|---|---|
| 1. File structure | `~/.openclaw/skills/humanizer/SKILL.md` and `README.md` exist | [ ] Pass / [ ] Fail |
| 2. Core file updates | AGENTS.md + TOOLS.md updated; USER/SOUL/IDENTITY/HEARTBEAT untouched | [ ] Pass / [ ] Fail |
| 3. Knowledge verification | All 10 knowledge questions answered correctly | [ ] Pass / [ ] Fail |
| 4. Live behavior test | All 8 patterns caught; output is specific, varied, and readable | [ ] Pass / [ ] Fail |
| 5. Anti-pattern checks | All 8 anti-patterns absent | [ ] Pass / [ ] Fail |

**Overall pass:** All 5 sections must pass.
**If any section fails:** Do not consider the skill installed. Re-run the failing section after correcting the issue.

---

*QC version: 1.0.0 | Skill version checked: 2.1.1 | Written: 2026-03-16*

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
