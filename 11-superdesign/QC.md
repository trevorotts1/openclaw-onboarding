# QC Checklist — Skill 11: SuperDesign
**Version:** v1.5.1 | Run this after completing INSTALL.md

---

## HOW TO USE THIS FILE

Work through every section in order. Mark each item `[PASS]`, `[FAIL]`, or `[SKIP]` (with reason).
Do not mark the skill installed until every check in the **Pass Criteria** section is satisfied.

---

## SECTION 1 — File Structure Checks

Verify all required files exist in the skill folder.

```
ls ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/11-superdesign/
```

- [ ] `SKILL.md` — present
- [ ] `INSTALL.md` — present
- [ ] `INSTRUCTIONS.md` — present
- [ ] `EXAMPLES.md` — present
- [ ] `CORE_UPDATES.md` — present
- [ ] `CHANGELOG.md` — present
- [ ] `superdesign-full.md` — present (2300+ lines, the canonical reference)
- [ ] `QC.md` — present (this file)

Verify the master files deep copy was saved:

```
ls ~/Downloads/openclaw-master-files/superdesign/
```

- [ ] `superdesign-instructions.md` exists at `~/Downloads/openclaw-master-files/superdesign/superdesign-instructions.md`
- [ ] File is non-empty (not a blank placeholder)

Verify the optional skill repo install:

```
ls ~/.agents/skills/superdesign/ 2>/dev/null
```

- [ ] Directory exists OR note that `npx clawhub install superdesign` was skipped with documented reason

**Section 1 result:** [ ] PASS / [ ] FAIL

---

## SECTION 2 — Core File Update Checks

Each file must contain the required section. Check content, not just presence of the file.

### 2A — AGENTS.md

```
grep -n "SuperDesign" ~/clawd/AGENTS.md 2>/dev/null || grep -n "SuperDesign" ~/.agents/AGENTS.md 2>/dev/null
```

- [ ] Contains a `## SuperDesign Web Design` section marked `[PRIORITY: HIGH]`
- [ ] Includes the rule: **NEVER create any website or UI without using SuperDesign first**
- [ ] Includes the rule: **'Create a website' = design in SuperDesign first, build from approved design**
- [ ] Includes the ref path pointing to `superdesign-instructions.md` in the master files folder
- [ ] Does NOT contain the full superdesign-full.md content dumped inline (lean summary only)

### 2B — TOOLS.md

```
grep -n "SuperDesign" ~/clawd/TOOLS.md 2>/dev/null || grep -n "SuperDesign" ~/.agents/TOOLS.md 2>/dev/null
```

- [ ] Contains a `## SuperDesign` section marked `[PRIORITY: HIGH]`
- [ ] Lists key CLI commands: `create-project`, `iterate-design-draft`, `extract-brand-guide`, `execute-flow-pages`
- [ ] Includes the rule: **Always design before building. Never skip to code.**
- [ ] Includes ref path to `superdesign-instructions.md`
- [ ] Does NOT contain thousands of lines of full documentation inline

### 2C — MEMORY.md

```
grep -n "SuperDesign" ~/clawd/MEMORY.md 2>/dev/null || grep -n "SuperDesign" ~/.agents/MEMORY.md 2>/dev/null
```

- [ ] Contains a SuperDesign installed entry with the install date
- [ ] Summarizes: AI design agent for frontend UI/UX, installed via onboarding skill 11
- [ ] Includes the rule: SuperDesign first, then build. Always.
- [ ] Includes ref path to `superdesign-instructions.md`

### 2D — IDENTITY.md

```
grep -n "SuperDesign\|Design Capability" ~/clawd/IDENTITY.md 2>/dev/null || grep -n "SuperDesign\|Design Capability" ~/.agents/IDENTITY.md 2>/dev/null
```

- [ ] Contains a `## Design Capability` section
- [ ] States: Agent uses SuperDesign for all UI/web design work — designs first, gets approval, then builds

### 2E — Files That Must NOT Have Been Touched

- [ ] `HEARTBEAT.md` — confirm NO SuperDesign entry was added
- [ ] `USER.md` — confirm NO SuperDesign entry was added
- [ ] `SOUL.md` — confirm NO SuperDesign entry was added

**Section 2 result:** [ ] PASS / [ ] FAIL

---

## SECTION 3 — CLI Install Checks

Run each command and confirm the expected output.

### 3A — Node.js prerequisite

```
node --version
```

- [ ] Returns v16.x.x or higher (v16+ required)

### 3B — SuperDesign CLI installed

```
superdesign --version
```

- [ ] Returns a version number (e.g. `1.x.x`) without error
- [ ] If "command not found": check `npx superdesign --version` as fallback and flag the issue

### 3C — CLI help menu loads

```
superdesign --help
```

- [ ] Help menu displays without authentication errors
- [ ] Commands visible: `create-project`, `iterate-design-draft`, `extract-brand-guide`, `gallery`, `search-prompts`, `execute-flow-pages`

### 3D — Login status

```
superdesign --help
```

- [ ] No "not authenticated" or "please login" error in the output
- [ ] If unauthenticated: `superdesign login` was attempted and user confirmed completion

### 3E — Test project creation (live smoke test)

```
superdesign create-project --title "QC Test Page" --json
```

- [ ] Returns JSON with a `projectId` (or `id`) field
- [ ] Returns JSON with a `draftId` field
- [ ] No error message in the response

### 3F — Search prompts smoke test

```
superdesign search-prompts --keyword "landing page" --json
```

- [ ] Returns JSON results (array of prompt suggestions)
- [ ] No error message

**Section 3 result:** [ ] PASS / [ ] FAIL

---

## SECTION 4 — Knowledge Verification Questions

Ask the agent the following questions and verify the answers match the expected responses below.
These test whether the agent actually internalized the skill — not just that files were copied.

---

**Q1: What are the three modes of SuperDesign?**

Expected: Web App (browser at app.superdesign.dev), CLI (terminal commands), IDE Extension (VS Code / Cursor / Windsurf).

- [ ] Agent names all three modes correctly

---

**Q2: What does the style.md export contain and why is it valuable?**

Expected: A written design rulebook capturing exact hex colors, font names and sizes, spacing rules, button styles, and component patterns. It is valuable because any AI tool can read it and build matching pages — so you design once and use the style.md to keep all other pages visually consistent.

- [ ] Agent mentions it is a text/design document
- [ ] Agent explains it can be handed to any AI to build matching pages
- [ ] Agent does not confuse it with the HTML/React code export

---

**Q3: A user wants to put a SuperDesign page into Go High Level (GHL). What export format do you use and what are the rules?**

Expected: Export as HTML (not React). All CSS must be inline or in a style tag. No external stylesheets. No React components. Script tags must be separate from div tags. The HTML should be pasted into a Code Element inside a GHL section set to "Allow rows to take entire width."

- [ ] Agent specifies HTML export (not React)
- [ ] Agent mentions inline CSS or style tag requirement
- [ ] Agent mentions no external stylesheets
- [ ] Agent mentions the GHL Code Element paste workflow

---

**Q4: What is the smart hybrid workflow for managing SuperDesign credits?**

Expected: Use the Web App only for cloning (the one thing only the Web App can do). Export the style.md immediately after cloning. Switch to the CLI or IDE Extension for all remaining work — variations, iterations, and additional pages. The CLI and IDE Extension use your own API key, so generation is unlimited.

- [ ] Agent explains cloning in web app, then switching to CLI/IDE
- [ ] Agent explains the credit difference (web app limited, CLI/IDE uses own API key)

---

**Q5: A user says "build me a landing page." What is the correct first step?**

Expected: Do NOT write any code first. Use SuperDesign to create the visual design first. Ask the five qualifying questions: page type, brand colors, hosting platform, primary CTA, and target audience. Then create the design, get approval, then build.

- [ ] Agent does NOT immediately write HTML or React code
- [ ] Agent invokes or references SuperDesign before any code work
- [ ] Agent asks about hosting platform (critical for export format decision)

---

**Q6: What happens to placeholder content in a SuperDesign export?**

Expected: All placeholder headlines, body text, CTA buttons, and images MUST be replaced with real content before delivery. Never deliver Lorem ipsum or "Your headline here" text as a finished product.

- [ ] Agent states placeholder replacement is mandatory
- [ ] Agent lists the items that need replacing (text, images, CTAs)

---

**Section 4 result:** [ ] PASS / [ ] FAIL

---

## SECTION 5 — Live Behavior Test

This test verifies the agent behaves correctly when given a real design task.

### Test Prompt

Give the agent exactly this prompt and observe the response:

> "I need a sales page for my $297/month coaching program. Can you build it for me?"

### Expected Behavior (in order)

1. Agent does NOT immediately produce HTML, CSS, or React code
2. Agent invokes SuperDesign or references that it will use SuperDesign first
3. Agent asks one or more qualifying questions before generating (hosting platform, colors, audience, CTA)
4. Agent does NOT say "I'll skip SuperDesign for a simple page like this"
5. Agent does NOT generate a generic AI-looking page without design-first workflow

### Scoring

- [ ] Agent responded with SuperDesign-first approach (not raw code)
- [ ] Agent asked about hosting platform before offering to export
- [ ] Agent did not skip the design step

**Section 5 result:** [ ] PASS / [ ] FAIL

---

## SECTION 6 — Anti-Pattern Checks

These are the most common failure modes. Verify NONE of these are present.

| Anti-Pattern | Check |
|---|---|
| Agent skips SuperDesign and goes straight to writing HTML/CSS | [ ] Not present |
| Agent dumps thousands of lines from superdesign-full.md into AGENTS.md or TOOLS.md | [ ] Not present |
| Agent delivers a design with Lorem ipsum text as "finished" | [ ] Not present |
| Agent exports React code for a GHL deployment | [ ] Not present |
| Agent triggers `openclaw gateway restart` without explicit user permission | [ ] Not present |
| Agent uses SuperDesign Web App credits for work that could be done in CLI/IDE | [ ] Not present |
| Agent ignores the MANDATORY TYP CHECK and executed skill instructions without TYP confirmed | [ ] Not present |
| Agent adds SuperDesign content to HEARTBEAT.md, USER.md, or SOUL.md | [ ] Not present |
| Agent executes INSTALL.md without first building and showing the full checklist to the user | [ ] Not present |
| Agent generates more than 5 design variations without user request | [ ] Not present |

**Section 6 result:** [ ] PASS / [ ] FAIL

---

## SECTION 7 — Pass Criteria

The skill is considered correctly installed ONLY when ALL of the following are true:

- [ ] Section 1 PASS: All required files exist including the master files deep copy
- [ ] Section 2 PASS: All four required core files (AGENTS.md, TOOLS.md, MEMORY.md, IDENTITY.md) updated with lean summaries; HEARTBEAT.md, USER.md, SOUL.md untouched
- [ ] Section 3 PASS: `superdesign --version` works, `superdesign --help` shows full menu, test project and search-prompts both return valid JSON
- [ ] Section 4 PASS: Agent answered all 6 knowledge questions correctly (5/6 minimum acceptable)
- [ ] Section 5 PASS: Live behavior test shows SuperDesign-first response without jumping to raw code
- [ ] Section 6 PASS: Zero anti-patterns detected

### Final Status

- [ ] **INSTALLED CORRECTLY** — All sections passed. Skill 11 is active.
- [ ] **NEEDS REMEDIATION** — One or more sections failed. List failures below and re-run after fixing.

**Failures to remediate:**

```
(list any FAIL items here before re-running)
```

---

## NOTES

- If `superdesign login` is pending user action, mark Section 3D as SKIP with note and revisit after user completes browser login.
- If Chrome Extension install is pending user action, this QC does not cover it (browser security dialogs require human interaction). Note it separately.
- IDE Extension (Part 6 of INSTALL.md) is optional. If skipped, document the reason. It does not block a PASS result.
- Re-run Sections 3E and 3F if the test project created during installation already consumed a CLI credit — those results count.

---

*QC.md authored for OpenClaw Onboarding, Skill 11 — SuperDesign v1.5.1*
