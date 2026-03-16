# QC Checklist: Teach Yourself Protocol (TYP)

Run these checks after installation to verify TYP is correctly installed and operational.

---

## 1. File Structure Checks

- [ ] `~/Downloads/openclaw-master-files/` exists (or equivalent named folder)
- [ ] Subfolder `apis/` exists inside master files folder
- [ ] Subfolder `skills/` exists inside master files folder
- [ ] Subfolder `processes/` exists inside master files folder
- [ ] Subfolder `references/` exists inside master files folder
- [ ] `01-teach-yourself-protocol/` folder is present inside master files folder
- [ ] All 7 skill files are present in that folder:
  - [ ] `SKILL.md`
  - [ ] `INSTALL.md`
  - [ ] `INSTRUCTIONS.md`
  - [ ] `EXAMPLES.md`
  - [ ] `CORE_UPDATES.md`
  - [ ] `teach-yourself-protocol-full.md`
  - [ ] `teach-yourself-protocol.skill`

---

## 2. Core Workspace File Checks

Verify the following core files were updated per `CORE_UPDATES.md`:

- [ ] `AGENTS.md` contains a TYP entry (lightweight summary, 10–25 lines, with path reference)
- [ ] `TOOLS.md` contains a TYP entry describing when and how to invoke it
- [ ] `MEMORY.md` records that TYP was installed (date, file path, source)
- [ ] No core file contains the full protocol text (it must remain a pointer, not the content)

---

## 3. Knowledge Verification — Ask the Agent

Ask the agent each question below and verify the expected answer:

**Q1: "What is the Teach Yourself Protocol?"**
- [ ] Answer mentions three layers: core summaries, deep files, folder structures
- [ ] Answer does NOT describe it as simply "saving files"

**Q2: "Where do full documents go when you learn something new?"**
- [ ] Answer: master files folder (e.g. `~/Downloads/openclaw-master-files/`)
- [ ] Answer confirms they do NOT go into `AGENTS.md`, `TOOLS.md`, or `MEMORY.md`

**Q3: "What goes in AGENTS.md or TOOLS.md when you learn something?"**
- [ ] Answer: a lightweight summary (10–25 lines) with a pointer to the deep file
- [ ] Answer mentions the Five Question Test

**Q4: "What triggers TYP?"**
- [ ] Answer covers explicit triggers: "teach yourself this", "learn this", "memorize this"
- [ ] Answer covers implicit triggers: large documents (50+ lines), corrections, credentials, system architecture

**Q5: "What must you do before creating any new knowledge files?"**
- [ ] Answer: search existing core files AND the master files folder for existing knowledge first
- [ ] Answer mentions checking for conflicts and avoiding duplicates

**Q6: "What do you do after TYP completes?"**
- [ ] Answer: confirm to the user — what was learned, where it was stored, which core files were updated, and a summary of key points

**Q7: "Can you restart the OpenClaw gateway yourself?"**
- [ ] Answer: No — must notify the user and wait for them to type `/restart` in Telegram

---

## 4. Behavior Check — Run a Live Test

Give the agent this prompt:

> "Teach yourself this: Our Stripe account uses live mode only. Never use test keys in production. The publishable key prefix is `pk_live_` and the secret key must never be logged."

Verify the agent:

- [ ] Announces TYP is activating before doing any work
- [ ] Does NOT dump the full content into a core file
- [ ] Creates or updates a file in the master files folder (e.g. `references/stripe-keys.md`)
- [ ] Adds a lightweight summary entry to the appropriate core file(s)
- [ ] Confirms to the user what was stored and where
- [ ] Assigns a priority tag (CRITICAL, HIGH, STANDARD, or REFERENCE)

---

## 5. Anti-Pattern Checks

Confirm none of these failure modes are present:

- [ ] Core files are not bloated (no single TYP entry exceeds ~25 lines)
- [ ] No duplicate TYP entries exist across core files
- [ ] The full protocol text (`teach-yourself-protocol-full.md`) is not pasted into any core file
- [ ] No knowledge files were created without a corresponding core file summary

---

## Pass Criteria

All items in Sections 1–3 must pass. Section 4 live test must pass. Section 5 must show zero anti-patterns.

If any item fails, re-read `teach-yourself-protocol-full.md` and re-run `CORE_UPDATES.md` for the affected files, then re-run this checklist.
