# QC.md — summarize-youtube Skill
## Post-Installation Verification Checklist

Run each section in order. All checks must pass before marking this skill installed.

---

## 1. File Structure Checks

Verify all skill source files are present in the skill folder.

```bash
ls ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/16-summarize-youtube/
```

- [ ] `SKILL.md` exists
- [ ] `INSTALL.md` exists
- [ ] `INSTRUCTIONS.md` exists
- [ ] `EXAMPLES.md` exists
- [ ] `CORE_UPDATES.md` exists
- [ ] `CHANGELOG.md` exists
- [ ] `summarize-youtube-full.md` exists

Verify the full reference copy was saved to the master files folder:

```bash
ls ~/Downloads/openclaw-master-files/ | grep -i "16-summarize-youtube"
```

- [ ] `16-summarize-youtube-full.md` (or equivalent) exists in the openclaw-master-files root

---

## 2. Binary Installation Check

```bash
which summarize
summarize --help >/dev/null && echo "OK"
```

- [ ] `which summarize` returns a path (not "not found")
- [ ] `summarize --help` exits without error

Verify it was installed via the correct tap:

```bash
brew list --formula | grep summarize
```

- [ ] `summarize` appears in Homebrew formula list (from `steipete/tap/summarize`)

---

## 3. Core File Update Checks

### AGENTS.md

```bash
grep -i "summarize" ~/clawd/AGENTS.md
```

- [ ] Contains "Summarize Skill" section header
- [ ] Lists `steipete/tap/summarize` as the install source
- [ ] States OpenAI-first key order with `GEMINI_API_KEY` as fallback
- [ ] Contains file path reference to `16-summarize-youtube-full.md`
- [ ] Does NOT contain the full INSTALL.md or INSTRUCTIONS.md content pasted in (lean format only)

### TOOLS.md

```bash
grep -i "summarize" ~/clawd/TOOLS.md
```

- [ ] Contains `summarize CLI` section
- [ ] Lists the OpenAI summary command with `OPENAI_API_KEY` prefix
- [ ] Lists the Gemini summary command with `--provider gemini` flag
- [ ] Lists the transcript-only command with `--extract-only`
- [ ] Contains `.env` discovery order: `~/clawd/secrets/.env → ~/.openclaw/.env → ~/.config/openclaw/.env`
- [ ] Contains file path reference to `16-summarize-youtube-full.md`

### MEMORY.md

```bash
grep -i "summarize" ~/clawd/MEMORY.md
```

- [ ] Contains `Installed: summarize tool` entry
- [ ] Notes OpenAI-first with Gemini fallback confirmed working
- [ ] Notes transcript extraction confirmed working
- [ ] Contains file path reference to `16-summarize-youtube-full.md`

---

## 4. Knowledge Verification Questions

Answer each question without looking at source files. If you cannot answer, the skill was not learned correctly.

**Q1.** What is the Homebrew install command for this skill's CLI?
> Expected: `brew install steipete/tap/summarize`

- [ ] Answered correctly

**Q2.** What is the key fallback order when running a summary?
> Expected: Try `OPENAI_API_KEY` first. If that fails, retry with `GEMINI_API_KEY` using `--provider gemini`. If both fail, stop and return the exact error.

- [ ] Answered correctly

**Q3.** Where are API keys loaded from, and in what order are the `.env` locations checked?
> Expected: `~/clawd/secrets/.env` → `~/.openclaw/.env` → `~/.config/openclaw/.env` → `.env` (local)

- [ ] Answered correctly

**Q4.** What is the command to extract a transcript only (no summary)?
> Expected: `summarize "https://youtu.be/VIDEO_ID" --youtube auto --extract-only`

- [ ] Answered correctly

**Q5.** What should the agent do if a gateway restart is required during install?
> Expected: STOP. Notify the user. Instruct them to type `/restart` in Telegram. Wait for confirmation. Never trigger it autonomously.

- [ ] Answered correctly

**Q6.** If both OpenAI and Gemini keys are missing, what happens?
> Expected: Print an error stating both providers were skipped and at least one API key is required. Exit with error — do not continue.

- [ ] Answered correctly

---

## 5. Live Behavior Test

> Prerequisites: At least one of `OPENAI_API_KEY` or `GEMINI_API_KEY` must be available in a `.env` file.

### 5a. Key Discovery

```bash
for env_file in \
  "$HOME/clawd/secrets/.env" \
  "$HOME/.openclaw/.env" \
  "$HOME/.config/openclaw/.env" \
  ".env"; do
  [ -f "$env_file" ] && echo "Found: $env_file" && break
done
```

- [ ] At least one `.env` file is found
- [ ] At least one of `OPENAI_API_KEY` or `GEMINI_API_KEY` is non-empty in that file

### 5b. Summary Test (OpenAI-first)

```bash
OPENAI_API_KEY=$(grep "^OPENAI_API_KEY=" ~/clawd/secrets/.env 2>/dev/null | cut -d= -f2- | tr -d '"')
OPENAI_API_KEY="$OPENAI_API_KEY" summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short
```

- [ ] Command runs without a fatal crash
- [ ] Returns a text summary or a clear provider error (not a missing-binary error)

### 5c. Gemini Fallback Test

```bash
GEMINI_API_KEY=$(grep "^GEMINI_API_KEY=" ~/clawd/secrets/.env 2>/dev/null | cut -d= -f2- | tr -d '"')
GEMINI_API_KEY="$GEMINI_API_KEY" summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short --provider gemini
```

- [ ] Command runs without a fatal crash
- [ ] Returns a text summary or a clear provider error (not a missing-binary error)

### 5d. Transcript Extraction Test

```bash
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract-only
```

- [ ] Command runs without a fatal crash
- [ ] Returns raw transcript text or a clear network/API error (not a missing-binary error)

---

## 6. Anti-Pattern Checks

These are failure conditions. Any box checked here means the install was done incorrectly.

- [ ] **FAIL** — `summarize` binary is not installed (`which summarize` returns nothing)
- [ ] **FAIL** — Full INSTALL.md or INSTRUCTIONS.md content was pasted verbatim into AGENTS.md, TOOLS.md, or MEMORY.md (violates TYP lean format rule)
- [ ] **FAIL** — Core files have no mention of `summarize` at all (snippets from CORE_UPDATES.md were skipped)
- [ ] **FAIL** — TOOLS.md entry omits `--provider gemini` from the Gemini fallback command
- [ ] **FAIL** — TOOLS.md or AGENTS.md omits the file path reference to `16-summarize-youtube-full.md`
- [ ] **FAIL** — Agent triggered a gateway restart without user permission
- [ ] **FAIL** — Both API keys were missing and the agent proceeded anyway instead of stopping with an error
- [ ] **FAIL** — Agent used hardcoded API key values instead of reading from `.env`

---

## 7. Pass Criteria

The skill is considered **fully installed and verified** when ALL of the following are true:

| Criteria | Status |
|---|---|
| All 7 skill source files present in skill folder | |
| `16-summarize-youtube-full.md` saved to openclaw-master-files root | |
| `summarize` binary installed and responds to `--help` | |
| AGENTS.md updated with lean summary + file path | |
| TOOLS.md updated with all three command variants + file path | |
| MEMORY.md updated with install confirmation + file path | |
| All 6 knowledge questions answered correctly | |
| At least one live test (5b, 5c, or 5d) returns output without a binary error | |
| Zero anti-patterns triggered | |

**Result:** `[ ] PASS` / `[ ] FAIL`

If FAIL: note which section failed and re-run only the failed steps from INSTALL.md.
