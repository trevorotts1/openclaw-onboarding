# QC.md - Book-to-Persona Coaching & Leadership System
## Post-Installation Quality Control Checklist
**Version:** 1.0.0 | **Skill:** 22-book-to-persona-coaching-leadership-system

Run this checklist immediately after installation. Work top to bottom. Do not skip sections.
A skill that fails any HARD FAIL item is not installed correctly.

---

## SECTION 1 — File Structure Checks

Verify all required files and folders exist at the correct paths.

### Skill Root
- [ ] `~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/` exists
- [ ] `PIPELINE.md` present in skill root
- [ ] `CHECKLIST.md` present in skill root
- [ ] `CORE_UPDATES.md` present in skill root
- [ ] `GOOD-AND-BAD-EXAMPLES.md` present in skill root
- [ ] `PERSONA-ROUTER.md` present in skill root
- [ ] `GEMINI-RETRIEVAL-GUIDE.md` present in skill root
- [ ] `CHANGELOG.md` present in skill root

### Agent Prompts
- [ ] `agent-prompts/extraction-agent-prompt.md` exists
- [ ] `agent-prompts/analysis-agent-prompt.md` exists
- [ ] `agent-prompts/synthesis-agent-prompt.md` exists

### Pre-Built Personas Folder
- [ ] `~/Downloads/openclaw-master-files/coaching-personas/personas/` exists (or equivalent master-files path)
- [ ] At least one persona folder present with all 3 files:
  - [ ] `extraction-notes.md`
  - [ ] `analysis-notes.md`
  - [ ] `persona-blueprint.md`

### Spot-Check: 5 Required Persona Folders
Confirm these specific folders exist inside the personas directory:
- [ ] `clear-atomic-habits/`
- [ ] `hormozi-100m-offers/`
- [ ] `cialdini-influence/`
- [ ] `goggins-cant-hurt-me/`
- [ ] `miller-building-storybrand-1/` or `miller-building-storybrand-2/`

### Pipeline Orchestrator
- [ ] `pipeline/orchestrator.py` exists (or equivalent pipeline script)
- [ ] `pipeline-status.json` exists (may be empty `{}` on first install — that is acceptable)

### Secrets
- [ ] `~/clawd/secrets/.env` exists
- [ ] `MOONSHOT_API_KEY` entry present in `.env` (value does not need to be verified here)
- [ ] `OPENROUTER_API_KEY` entry present in `.env`

**HARD FAIL:** Any missing file from skill root, agent-prompts, or pre-built personas folder = installation incomplete.

---

## SECTION 2 — Core File Update Checks

Verify that AGENTS.md, TOOLS.md, MEMORY.md, SOUL.md, and HEARTBEAT.md received the correct updates per CORE_UPDATES.md.

### AGENTS.md
- [ ] Contains section heading `## Book-to-Persona Skill (Installed)`
- [ ] Section includes the phrase `Persona Reflex (DEFAULT BEHAVIOR)`
- [ ] Section includes `python3 ~/clawd/scripts/gemini-search.py "<task keywords>"` as the runtime query pattern
- [ ] Key paths block is present (skill path, personas path, router path, orchestrator path)
- [ ] Contains section `## Pending Skill Setup - Check and Remind` with `.pending-setup.md` reference
- [ ] Full PIPELINE.md content was NOT pasted into AGENTS.md (rule: reference only)

### TOOLS.md
- [ ] Contains section heading `## Book-to-Persona - Model Routing and Gemini Engine`
- [ ] Phase 1 routing entry: `moonshot/kimi-k2.5` with `MOONSHOT_API_KEY` and `https://api.moonshot.cn/v1` and `temperature MUST be 1.0`
- [ ] Phase 2 routing entry: `deepseek/deepseek-v3.2-speciale` via `OpenRouter`
- [ ] Phase 3 routing entry: `openai/gpt-5.3-codex` via `OpenClaw OAuth`
- [ ] Fallback model listed: `OpenRouter moonshotai/kimi-k2.5`
- [ ] Prompt templates were NOT pasted into TOOLS.md (rule: reference only)

### MEMORY.md
- [ ] Contains section heading `## Book-to-Persona Persona Library`
- [ ] Entry includes skill path and personas path
- [ ] Entry references `python3 ~/clawd/scripts/gemini-indexer.py --status` for live count
- [ ] Entry references Persona Reflex behavior (query Gemini Engine before professional tasks)
- [ ] "Add new book SOP" is referenced

### SOUL.md
- [ ] Contains section heading `## Persona Coaching Voice Rule`
- [ ] Rule states: author's name appears ONLY inside attribution-flagged direct quotes
- [ ] Rule includes the negative example: "Do not say 'As Mel Robbins says...'"
- [ ] Rule includes the positive example: "say 'The 5-second countdown works because...'"

### HEARTBEAT.md (if section exists in file)
- [ ] Contains `## Persona Reflex - ACTIVE`
- [ ] References `coaching-personas` collection and the Gemini Engine pre-task query pattern

**HARD FAIL:** Missing `## Book-to-Persona Skill (Installed)` in AGENTS.md = installation incomplete.
**HARD FAIL:** Persona Coaching Voice Rule missing from SOUL.md = identity confusion risk at runtime.

---

## SECTION 3 — Knowledge Verification Questions

Answer each question without looking at the files. These confirm the agent has internalized the skill, not just installed it.

**Q1: What are the three pipeline phases and which model handles each?**
- Expected: Phase 1 = Kimi K2.5 (Moonshot direct API), Phase 2 = DeepSeek V3.2-Speciale (OpenRouter), Phase 3 = GPT-5.3 Codex (OpenClaw OAuth)

**Q2: What triggers a Phase 3 fallback from GPT-5.3 Codex to Kimi K2.5?**
- Expected: Any of — API error, rate limit (429), timeout after 15 minutes, output under 5,000 characters, any error message in the response

**Q3: How many sections does a complete persona-blueprint.md have, and what are sections 3, 6, and 14?**
- Expected: 14 sections total. Section 3 = Signature Framework, Section 6 = Coaching Mode: How to Respond, Section 14 = Quick Reference Card

**Q4: What is the Persona Reflex and when does the agent skip it?**
- Expected: Before any professional task, run `python3 ~/clawd/scripts/gemini-search.py "<task keywords>"`, load the returned persona's Task Mode, and execute through that methodology. Skip ONLY if the user explicitly says so.

**Q5: What is the author name rule in Coaching Mode?**
- Expected: The author's name appears ONLY inside attribution-flagged direct quotes. Never use the author's name unprompted in the coaching voice.

**Q6: What is the maximum number of books active simultaneously in the pipeline, and how does a book flow between phases?**
- Expected: Maximum 7 simultaneous. Books flow independently — as soon as Phase 1 completes, Phase 2 starts immediately for that book (no batch waiting).

**Q7: What are the two things a persona blueprint serves?**
- Expected: Coaching Mode (guides a human through challenges) and Task Mode (governs an AI agent executing professional work to the methodology's standards)

**Q8: Which persona and department would you route to for "making offers, pricing, funnels"?**
- Expected: `hormozi-100m-offers` → `sales-dept/`

**Q9: What is the minimum character length for a complete persona-blueprint.md output?**
- Expected: Over 10,000 characters (blueprints are much larger in practice)

**Q10: After adding a new persona blueprint, what two Gemini Engine commands must be run?**
- Expected: `python3 ~/clawd/scripts/gemini-indexer.py` then `# Handled by gemini-indexer.py`

**Passing threshold:** 8/10 correct. Score below 8 = re-read PIPELINE.md, PERSONA-ROUTER.md, CORE_UPDATES.md, and GOOD-AND-BAD-EXAMPLES.md.

---

## SECTION 4 — Live Behavior Test

Run these prompts and evaluate the agent's actual output against the expected behavior.

### Test 4A — Persona Reflex (Task Mode)
**Prompt:** "Review this sales email before I send it."

**Expected behavior:**
1. Agent runs `python3 ~/clawd/scripts/gemini-search.py "sales email review outreach quality standard"` BEFORE writing any output
2. Agent loads a relevant persona (e.g., `hormozi-100m-offers`, `bly-copywriters-handbook`, or `jones-exactly-what-to-say`)
3. Agent applies that persona's execution standard and non-negotiable rules
4. Agent output includes specific rule checks with ✅ / ❌ verdicts, not generic feedback

**FAIL signal:** Agent says "This looks good! Make sure it's friendly and clear." with no persona loaded, no Gemini Engine query, no rule-based evaluation.

---

### Test 4B — Coaching Mode Voice (Identity Rule)
**Prompt:** "I keep meaning to start my workout routine but I just never do it."

**Expected behavior:**
1. Agent loads a relevant coaching persona (e.g., `clear-atomic-habits`, `goggins-cant-hurt-me`, or `robbins-five-second-rule` if present)
2. Response is written in the methodology's voice, NOT attributed to the author by name
3. Response includes a specific mechanism or framework from the methodology
4. Response ends with a specific actionable question or directive

**FAIL signals:**
- "Mel Robbins has a great technique for this called the 5 Second Rule. You should try it." (identity confusion — names the author, doesn't apply methodology)
- "You should try to be more consistent and build better habits." (generic — no methodology applied)
- Response does not ask the human a follow-up question or prompt specific action

---

### Test 4C — Gemini Engine Collection Status
**Run:** `python3 ~/clawd/scripts/gemini-indexer.py --status` or `qmd status`

**Expected output:**
- Collection named `coaching-personas` is listed
- File count is greater than 0
- No error messages about missing index or unembedded files

**FAIL signal:** "Collection not found" or "No collections registered" or zero files listed.

---

### Test 4D — Gemini Engine Query Returns Relevant Results
**Run:** `python3 ~/clawd/scripts/gemini-search.py "habit building systems behavior change consistency"`

**Expected output:**
- Returns at least one result from a persona blueprint (e.g., `clear-atomic-habits` or `duhigg-power-of-habit`)
- Results include recognizable methodology language, not blank or unrelated content

**FAIL signal:** No results returned, or results are from unrelated files.

---

### Test 4E — Persona Router Accuracy
**Prompt:** "I need help building a brand story and clarifying my messaging."

**Expected behavior:**
1. Agent identifies this as a Marketing & Content task
2. Routes to `miller-building-storybrand-1` or `miller-building-storybrand-2`
3. Applies StoryBrand framework: customer as hero, clarify the message

**FAIL signal:** Agent routes to a sales or productivity persona, or applies no persona at all.

---

## SECTION 5 — Anti-Pattern Checks

These are failure modes the skill is specifically designed to prevent. Verify none are present.

### Anti-Pattern 1: Author Impersonation
**Check:** Does the agent ever say "Hi, I'm [Author Name]" or speak as the author in first person?
- [ ] Confirmed: Agent does NOT impersonate authors
- HARD FAIL if agent introduces itself as the author (e.g., "I'm Mel Robbins...")

### Anti-Pattern 2: Author Name Used Outside Quotes
**Check:** When operating in Coaching Mode, does the agent use the author's name unprompted outside of a direct quote with attribution?
- [ ] Confirmed: Author name only appears inside attribution-flagged direct quotes
- HARD FAIL if agent says "As [Author] says..." or "[Author] would tell you..." without quoting

### Anti-Pattern 3: Generic Advice With No Methodology
**Check:** When a coaching or task prompt is given, does the agent respond with generic advice ("be consistent," "try harder," "good luck") rather than applying a specific framework?
- [ ] Confirmed: Every coaching or task response applies a named methodology
- HARD FAIL if response contains no framework, no questions, no governance rules

### Anti-Pattern 4: Skipping Persona Reflex
**Check:** When given a professional task (write, review, plan, analyze), does the agent query Gemini Engine before starting?
- [ ] Confirmed: Agent queries `python3 ~/clawd/scripts/gemini-search.py` before executing professional tasks
- HARD FAIL if agent proceeds with a task without Gemini Engine query and no explicit user instruction to skip

### Anti-Pattern 5: Pasting Full Docs Into Core Files
**Check:** Are PIPELINE.md, prompt templates, or the 14-section blueprint format pasted into AGENTS.md, TOOLS.md, or MEMORY.md?
- [ ] Confirmed: Core files contain references and summaries only — no full document pastes
- FAIL if any core file contains the full text of PIPELINE.md or any agent prompt

### Anti-Pattern 6: Thin Governance Output
**Check:** When operating in Task Mode (e.g., reviewing a document, writing outreach, building a plan), does the agent output vague approval ("looks good!") instead of applying the persona's non-negotiable rules?
- [ ] Confirmed: Task Mode output includes specific rule checks, not vague approval
- HARD FAIL if any Task Mode response contains no rule citations, no ✅ / ❌ evaluation, no specific standard applied

### Anti-Pattern 7: Missing Fallback Awareness
**Check:** Does the agent know that Phase 3 has a fallback model, and can it state the fallback trigger conditions?
- [ ] Confirmed: Agent can state the 4 fallback triggers (429, timeout, <5000 chars, any error)
- FAIL if agent believes GPT-5.3 Codex is the only option with no fallback

### Anti-Pattern 8: Gemini Engine Not Used for Retrieval
**Check:** Does the agent try to load entire persona files into context rather than using Gemini Engine surgical queries?
- [ ] Confirmed: Agent uses `qmd query` and `qmd get [path]:[line] -l [count]` for retrieval
- FAIL if agent attempts to read entire persona-blueprint.md files into context for routine tasks

---

## SECTION 6 — Pass Criteria

### Overall Pass Requirements

To declare this skill **INSTALLED AND OPERATIONAL**, ALL of the following must be true:

**File Structure (Section 1)**
- [ ] All skill root files present
- [ ] All 3 agent prompt files present
- [ ] Personas folder exists with at least 5 pre-built personas, each containing all 3 required files
- [ ] Secrets `.env` file contains both required API key entries

**Core File Updates (Section 2)**
- [ ] AGENTS.md updated with `## Book-to-Persona Skill (Installed)` and Persona Reflex
- [ ] TOOLS.md updated with model routing for all 3 phases plus fallback
- [ ] MEMORY.md updated with persona library entry
- [ ] SOUL.md updated with Persona Coaching Voice Rule
- [ ] No full document text pasted into any core file

**Knowledge (Section 3)**
- [ ] 8 out of 10 knowledge questions answered correctly

**Live Behavior (Section 4)**
- [ ] Test 4A: Task Mode applies persona execution standard with rule-based evaluation
- [ ] Test 4B: Coaching Mode applies methodology without author impersonation
- [ ] Test 4C: Gemini Vector Database `coaching-personas` is registered and shows files
- [ ] Test 4D: Gemini Engine query returns relevant persona content
- [ ] Test 4E: Persona Router correctly routes a marketing task to StoryBrand

**Anti-Patterns (Section 5)**
- [ ] Zero HARD FAIL anti-patterns present
- [ ] No generic advice substituting for methodology
- [ ] No author impersonation in any mode

---

### Status Declaration

After completing this checklist, mark one:

```
[ ] PASS — All sections complete, zero HARD FAILs, knowledge score ≥ 8/10
    Skill is operational. Persona Reflex is active.

[ ] PARTIAL — File structure complete, but Gemini Engine not yet embedded or core files not yet updated
    Action: Complete Gemini Engine setup (python3 ~/clawd/scripts/gemini-indexer.py) and apply CORE_UPDATES.md

[ ] FAIL — One or more HARD FAILs present, or knowledge score below 8/10
    Action: Re-read all 7 skill .md files and repeat failed sections
```

---

### Quick Repair Commands

If Gemini Vector Database is missing or broken:
```bash
  --name coaching-personas \
  --mask "**/*.md"
python3 ~/clawd/scripts/gemini-indexer.py
# Handled by gemini-indexer.py
```

If Gemini Engine results are stale:
```bash
qmd cleanup && python3 ~/clawd/scripts/gemini-indexer.py
```

If unsure whether core files were updated:
```bash
grep -n "Book-to-Persona" ~/.openclaw/AGENTS.md
grep -n "Persona Coaching Voice Rule" ~/.openclaw/SOUL.md
grep -n "Book-to-Persona" ~/.openclaw/TOOLS.md
```
