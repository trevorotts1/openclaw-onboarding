# QC.md — Agent Browser (Vercel) — Post-Install Verification Checklist

**Skill:** `agent-browser` (Vercel)
**Version:** v1.5.0
**Run this after completing INSTALL.md to confirm the skill installed correctly.**

---

## SECTION 1 — File Structure Checks

Verify the expected files are present on disk.

### 1.1 Onboarding package files
Run:
```bash
ls ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/03-agent-browser/
```
Expected files present:
- [ ] `SKILL.md`
- [ ] `INSTALL.md`
- [ ] `CORE_UPDATES.md`
- [ ] `CHANGELOG.md`
- [ ] `QC.md` (this file)

**PASS:** All 5 files listed.
**FAIL:** Any file missing — re-download the onboarding package.

---

### 1.2 Master files folder copy
Run:
```bash
ls ~/Downloads/ | grep -i "openclaw"
```
Expected: An `OpenClaw Master Files` folder (or variation) exists.

Then check the skill doc was saved inside it:
```bash
find ~/Downloads -ipath "*openclaw*master*" -name "*agent-browser*" 2>/dev/null
```
Expected: At least one `.md` file found referencing `agent-browser`.

- [ ] Master files folder exists
- [ ] agent-browser skill doc saved inside master files folder

**PASS:** Both items confirmed.
**FAIL:** If the doc was never saved — re-run INSTALL.md and save the full SKILL.md content to the master files folder.

---

### 1.3 Clawd skills directory (optional but preferred)
Run:
```bash
ls ~/clawd/skills/agent-browser/SKILL.md 2>/dev/null && echo "EXISTS" || echo "NOT FOUND"
```
- [ ] `~/clawd/skills/agent-browser/SKILL.md` exists

**PASS:** File exists and is treated as source of truth.
**NOTE:** If not present, the onboarding folder copy is the fallback. Not a hard failure, but flag it.

---

## SECTION 2 — Core File Update Checks

This skill intentionally makes **no** changes to core `.md` files. Verify that no unwanted content was added.

### 2.1 AGENTS.md — no changes expected
Run:
```bash
grep -i "agent-browser" ~/AGENTS.md 2>/dev/null && echo "FOUND — INVESTIGATE" || echo "CLEAN — OK"
```
- [ ] No `agent-browser` entries in AGENTS.md

**PASS:** Output is `CLEAN — OK`.
**FAIL:** If `agent-browser` content was added — this is incorrect. CORE_UPDATES.md explicitly says no AGENTS.md changes are required. Remove the entry.

---

### 2.2 TOOLS.md — no changes expected
Run:
```bash
grep -i "agent-browser" ~/TOOLS.md 2>/dev/null && echo "FOUND — INVESTIGATE" || echo "CLEAN — OK"
```
- [ ] No `agent-browser` entries in TOOLS.md

**PASS:** Output is `CLEAN — OK`.
**FAIL:** agent-browser is a CLI tool with no API keys or config — no TOOLS.md entry is needed. Remove any added content.

---

### 2.3 MEMORY.md — no changes expected
Run:
```bash
grep -i "agent-browser" ~/MEMORY.md 2>/dev/null && echo "FOUND — INVESTIGATE" || echo "CLEAN — OK"
```
- [ ] No `agent-browser` entries in MEMORY.md

**PASS:** Output is `CLEAN — OK`.
**FAIL:** Installation status is verified by running `agent-browser --help`, not stored in MEMORY.md. Remove any added content.

---

## SECTION 3 — Knowledge Verification Questions

Answer these questions to confirm you understood and retained the skill correctly. No tools needed — answer from memory.

**Q1:** What is `agent-browser` and why is it preferred over ad-hoc browser clicking?
> Correct answer: It produces accessibility snapshots with stable element refs (`@e1`, `@e2`, etc.), allowing the agent to click/fill by ref for high-precision, reliable automation.

- [ ] Can explain what agent-browser does
- [ ] Can explain why ref-based automation is preferred

---

**Q2:** Where does the full operational skill documentation live on the machine?
> Correct answer: `~/clawd/skills/agent-browser/SKILL.md` — treat it as source of truth if it exists.

- [ ] Can state the full path

---

**Q3:** What should the agent do if a gateway restart is needed during installation?
> Correct answer: STOP. Do NOT execute the restart. Notify the user: "This installation requires an OpenClaw gateway restart." Instruct them to type `/restart` in Telegram. Wait for confirmation before proceeding.

- [ ] Knows it is FORBIDDEN to trigger gateway restarts autonomously
- [ ] Knows the correct user notification message
- [ ] Knows the user must type `/restart` in Telegram

---

**Q4:** What happens if `npm install -g agent-browser` fails with a permissions error?
> Correct answer: Try `sudo npm install -g agent-browser`. If sudo is unavailable or still fails, tell the user they need npm global permissions (system admin, or run as Administrator/sudo).

- [ ] Knows the sudo fallback
- [ ] Knows to stop and notify the user if permissions cannot be resolved

---

**Q5:** What does a successful snapshot from `agent-browser snapshot -i` look like?
> Correct answer: Interactive elements with stable refs like `@e1`, `@e2` in the output.

- [ ] Can describe what a valid snapshot output contains

---

## SECTION 4 — Live Behavior Test

Run these commands in order. Do not skip steps.

### 4.1 Binary check
```bash
command -v agent-browser >/dev/null 2>&1 && echo "agent-browser: INSTALLED" || echo "agent-browser: NOT INSTALLED"
```
- [ ] Output: `agent-browser: INSTALLED`

**FAIL:** If `NOT INSTALLED` — return to INSTALL.md Step 2 and complete the npm install.

---

### 4.2 Help output check
```bash
agent-browser --help | head -20
```
- [ ] Command exits without error
- [ ] Help text is displayed (not empty, not an error message)

---

### 4.3 Smoke test — open, snapshot, close
```bash
agent-browser open https://example.com
agent-browser snapshot -i
agent-browser close
```
- [ ] `agent-browser open` completes without error
- [ ] `agent-browser snapshot -i` returns output containing element refs (e.g. `@e1`, `@e2`)
- [ ] `agent-browser close` completes without error

**PASS:** All three commands succeed and snapshot contains `@e` refs.
**FAIL:** If snapshot contains no refs — browser may have opened but accessibility tree is empty. Check if a browser is correctly installed and retry.

---

## SECTION 5 — Anti-Pattern Checks

Confirm none of the following mistakes were made during installation.

- [ ] Agent did NOT dump full INSTALL.md or SKILL.md content into AGENTS.md, TOOLS.md, or MEMORY.md
- [ ] Agent did NOT skip the TYP check before beginning installation
- [ ] Agent did NOT attempt to restart the OpenClaw gateway on its own
- [ ] Agent did NOT proceed past Step 2 of INSTALL.md before confirming npm install completed without error
- [ ] Agent did NOT fall back to Playwright or another browser tool without first attempting agent-browser install
- [ ] Agent did NOT mark this skill as complete without running the smoke test (Section 4.3)

**PASS:** All boxes checked (none of these mistakes occurred).
**FAIL:** If any box cannot be checked — note which anti-pattern occurred and correct it before marking the skill installed.

---

## SECTION 6 — Pass Criteria

The skill is correctly installed when ALL of the following are true:

| Check | Status |
|---|---|
| All 5 onboarding package files present | |
| Skill doc saved to master files folder | |
| `agent-browser` binary found on PATH | |
| `agent-browser --help` runs without error | |
| Smoke test completes with `@e` refs in snapshot | |
| AGENTS.md, TOOLS.md, MEMORY.md unchanged | |
| All knowledge questions answerable from memory | |
| No anti-patterns triggered | |

**OVERALL RESULT:**
- [ ] **PASS** — All checks above confirmed. Skill 03 (agent-browser) is fully installed.
- [ ] **FAIL** — One or more checks failed. Do not mark as complete. Return to the failed section and resolve before re-running QC.

---

*QC version: 1.0 | Matches skill version: v1.5.0*
