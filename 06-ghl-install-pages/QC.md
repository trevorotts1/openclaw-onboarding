# QC Checklist - ghl-install-pages (v1.5.0)

Run this after installing the `ghl-install-pages` skill. Work through every section in order. Do not mark anything PASS without actually verifying it.

---

## 1. File Structure Checks

Verify the following files exist in the skill folder:

```bash
ls ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/06-ghl-install-pages/
```

Expected files:

- [ ] `SKILL.md` — skill overview and reading order
- [ ] `INSTALL.md` — setup and prerequisites
- [ ] `INSTRUCTIONS.md` — 10-phase deployment process
- [ ] `EXAMPLES.md` — real deployment examples
- [ ] `CORE_UPDATES.md` — what to add to core .md files
- [ ] `CHANGELOG.md` — version history
- [ ] `ghl-install-pages-full.md` — full Playwright reference with all code
- [ ] `QC.md` — this file

**PASS if:** All 8 files are present.
**FAIL if:** Any file is missing — re-run the install.

---

## 2. Core File Update Checks

Verify the three required core files were updated. Check each one.

### 2a. AGENTS.md

Open AGENTS.md and confirm it contains ALL of the following:

- [ ] Section heading `## GHL Page Deployment` with `[PRIORITY: HIGH]`
- [ ] File path reference pointing to `ghl-install-pages-full.md`
- [ ] `launchPersistentContext` mentioned (NEVER `launch()`)
- [ ] Instruction to verify correct sub-account before building
- [ ] Credential location: `~/clawd/secrets/.env` with `GHL_EMAIL` and `GHL_PASSWORD`

**PASS if:** All 5 items are present. Content is a lean summary + file path reference (not thousands of lines).
**FAIL if:** Section is missing, incomplete, or the full doc was dumped directly into AGENTS.md.

### 2b. TOOLS.md

Open TOOLS.md and confirm it contains ALL of the following:

- [ ] Section heading `## GHL Page Builder (Playwright Automation)`
- [ ] File path reference pointing to `ghl-install-pages-full.md`
- [ ] Viewport minimum `1440x900` noted
- [ ] `get_builder_frame()` mentioned for iframe context switching
- [ ] Default-to-Funnels rule noted
- [ ] Deployment report requirement noted

**PASS if:** All 6 items are present as a lean summary with file path.
**FAIL if:** Section is missing or incomplete.

### 2c. MEMORY.md

Open MEMORY.md and confirm it contains:

- [ ] Entry indicating the GHL Page Deployment skill is installed, with a date
- [ ] File path reference pointing to `ghl-install-pages-full.md`
- [ ] Brief mention of what is covered (funnel creation, multi-page, updates, iframe method)

**PASS if:** Entry is present and references the correct file path.
**FAIL if:** Entry is missing or has no file path reference.

### 2d. Files That Must NOT Have Been Updated

Confirm these files were NOT modified by this install:

- [ ] `IDENTITY.md` — should be unchanged
- [ ] `HEARTBEAT.md` — should be unchanged
- [ ] `USER.md` — should be unchanged
- [ ] `SOUL.md` — should be unchanged

**PASS if:** None of these four files were touched.
**FAIL if:** Any of these files has new content added from this skill install.

---

## 3. Playwright Installation Check

Run the verification command from INSTALL.md:

```bash
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright installed successfully')"
```

- [ ] Output is: `Playwright installed successfully`

Run the Chromium check:

```bash
python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); b.close(); p.stop(); print('Chromium OK')"
```

- [ ] Output is: `Chromium OK`

**PASS if:** Both commands succeed.
**FAIL if:** Either command throws an error — re-run `pip install playwright` and `playwright install chromium`.

---

## 4. Credential Storage Check

Check whether GHL credentials are stored:

```bash
grep -E "GHL_EMAIL|GHL_PASSWORD" ~/clawd/secrets/.env 2>/dev/null
```

- [ ] `GHL_EMAIL` is present OR the agent has noted in MEMORY.md that the user will log in manually with persistent session
- [ ] `GHL_PASSWORD` is present OR the same persistent-session note applies
- [ ] No credentials appear hardcoded in any `.py` scripts

**PASS if:** Credentials are in `~/clawd/secrets/.env` OR a persistent-session approach is documented in MEMORY.md.
**FAIL if:** Credentials are hardcoded in a script file, or neither approach is configured/noted.

---

## 5. Knowledge Verification Questions

Ask the agent these questions directly. No looking up answers mid-quiz — the agent should answer from memory or session context.

| # | Question | Expected Answer |
|---|----------|-----------------|
| Q1 | What Playwright launch method is required and why? | `launchPersistentContext()` — saves login session so the user doesn't log in every time. Never use `launch()`. |
| Q2 | What is the minimum required browser viewport size for GHL? | Width 1440px, height 900px (1280x800 minimum; 1440x900 recommended). |
| Q3 | Why does the agent need to switch iframe context in GHL's builder? | GHL's page builder loads inside nested iframes. You cannot interact with builder elements from the main page. Use `get_builder_frame()`. |
| Q4 | When should the agent default to Funnels vs. Websites? | Default to Funnels 90% of the time. Use Websites only if the user explicitly requests a standalone website. |
| Q5 | What must happen before the agent publishes any page? | The agent must send a deployment report with preview screenshots and receive explicit user approval. NEVER publish without user approval. |
| Q6 | What is the iframe deployment method and when is it used? | Host the HTML externally and embed it via iframe in GHL's code block — used when GHL's styles conflict with the code and direct fixes have failed 3+ times. |
| Q7 | What are the 10 phases of a GHL page deployment (name them in order)? | 1-Navigate to Funnels, 2-Create Funnel, 3-Add Steps, 4-Open Builder, 5-Dismiss AI popup, 6-Add Blank Section + Code Element, 7-Set Full Width, 8-Paste Code, 9-Save, 10-Preview and Verify. |
| Q8 | Why must the agent verify the sub-account before deploying? | Deploying in the wrong sub-account means the client will not see the pages. Always confirm the correct sub-account is active in the top-left corner. |
| Q9 | When 2FA is detected, what should the agent do? | PAUSE the automation, notify the user, display clear instructions, and wait up to 5 minutes for the user to complete 2FA in the visible browser window. Never attempt to bypass 2FA. |
| Q10 | What is the purpose of `find_element_with_fallback()`? | GHL updates its UI frequently. This function tries multiple CSS selectors in order, so automation keeps working even when GHL changes button labels or class names. |

**PASS if:** Agent answers at least 9 of 10 correctly.
**FAIL if:** Agent misses 2 or more — re-read `ghl-install-pages-full.md` and `INSTRUCTIONS.md`.

---

## 6. Live Behavior Test

Run this simulated prompt to verify the agent behaves correctly end-to-end. Do NOT use a real GHL account for this test unless deploying a real page. Use the agent's response to assess behavior.

**Test prompt:**
> "Deploy this HTML to our Convert and Flow account as a new landing page funnel."
> _(Attach or paste any sample HTML file.)_

Evaluate the agent's response against this checklist:

**Pre-flight:**
- [ ] Agent checks for existing GHL credentials in `~/clawd/secrets/.env` before asking the user
- [ ] Agent confirms which sub-account to deploy into before starting
- [ ] Agent states it will default to Funnels (not Websites) since no type was specified
- [ ] Agent does NOT start executing without first presenting a numbered checklist and getting confirmation

**Execution (Playwright script or described steps):**
- [ ] Uses `launchPersistentContext()`, not `launch()`
- [ ] Sets viewport to at least 1440x900
- [ ] Uses `~/.openclaw/playwright-data/ghl-install-pages/` as the session data directory
- [ ] Mentions switching to builder iframe context before interacting with builder elements
- [ ] Adds a blank section, then a Code element from the Custom section
- [ ] Sets the section to full width (green border / section container, not the code element)
- [ ] Pastes the ENTIRE HTML into one code block — does not split across multiple elements
- [ ] Saves the code editor AND saves the page separately

**Post-deployment:**
- [ ] Verifies preview at all three sizes: 1440px, 768px, 375px
- [ ] Generates a deployment report matching the template in INSTRUCTIONS.md
- [ ] Report includes publish status as "Not published — awaiting your approval"
- [ ] Agent does NOT click Publish without being asked

**PASS if:** All 14 behavior items are confirmed.
**FAIL if:** 2 or more items are missing — the agent did not fully internalize the skill.

---

## 7. Anti-Pattern Checks

These are the most common failure modes. Verify NONE of them are present.

| # | Anti-Pattern | Check |
|---|--------------|-------|
| AP1 | Agent uses `p.chromium.launch()` instead of `launchPersistentContext()` | [ ] Not present |
| AP2 | Credentials hardcoded inside a `.py` script | [ ] Not present |
| AP3 | Agent publishes a page without asking for user approval | [ ] Not present |
| AP4 | Agent triggers a gateway restart without user permission | [ ] Not present |
| AP5 | Agent dumps the full `ghl-install-pages-full.md` content directly into AGENTS.md, TOOLS.md, or MEMORY.md | [ ] Not present |
| AP6 | Agent updates IDENTITY.md, HEARTBEAT.md, USER.md, or SOUL.md during installation | [ ] Not present |
| AP7 | Agent uses Websites when the user said nothing about page type | [ ] Not present |
| AP8 | Agent does not wait 5 seconds after opening the builder before clicking | [ ] Not present |
| AP9 | Agent skips the full-width toggle and pastes code into a narrow column section | [ ] Not present |
| AP10 | Agent reports "Pass" on preview verification without actually checking at 3 screen sizes | [ ] Not present |
| AP11 | Agent creates a new funnel when updating an existing page (duplication error) | [ ] Not present |
| AP12 | Agent splits HTML across multiple code elements instead of pasting it all in one block | [ ] Not present |

**PASS if:** All 12 anti-patterns are confirmed absent.
**FAIL if:** Any anti-pattern is detected — note which one and correct before proceeding.

---

## 8. Pass Criteria (Overall)

The skill install is **COMPLETE and PASSING** only when ALL of the following are true:

| Section | Status |
|---------|--------|
| 1. File Structure | All 8 files present |
| 2a. AGENTS.md | Updated correctly, lean format |
| 2b. TOOLS.md | Updated correctly, lean format |
| 2c. MEMORY.md | Updated with date and file path |
| 2d. Protected files | IDENTITY, HEARTBEAT, USER, SOUL untouched |
| 3. Playwright | Both install checks pass |
| 4. Credentials | Stored in `.env` or persistent-session noted |
| 5. Knowledge Quiz | 9/10 or better |
| 6. Live Behavior Test | 14/14 items confirmed |
| 7. Anti-Patterns | 0 anti-patterns detected |

**Final result:** [ ] PASS — Skill is fully installed and verified.

If any section is FAIL, fix it before marking the install complete. Do NOT tell the user installation is done until every row above is checked off.

---

_QC version: 1.0 — matches skill version 1.5.0_
