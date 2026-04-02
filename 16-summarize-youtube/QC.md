# QC Checklist - Skill 16: Summarize YouTube
**Version:** v6.5.6

Run this after installation. Every section must pass before you mark summarize-youtube complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/16-summarize-youtube"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `summarize-youtube-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.6`
- [ ] `summarize-youtube-full.md` is non-empty

---

## 2. Core file update checks

```bash
grep -n "summarize\|YouTube" ~/clawd/AGENTS.md ~/clawd/TOOLS.md ~/clawd/MEMORY.md
```

- [ ] Core docs mention the summarize CLI
- [ ] Core docs mention provider order: OpenAI first, Gemini fallback
- [ ] Full guide is referenced by path, not pasted in full

---

## 3. Binary and install-path checks

```bash
which summarize
summarize --help >/dev/null && echo OK
```

- [ ] `summarize` resolves in PATH
- [ ] `summarize --help` exits successfully
- [ ] Installed using the command path documented in INSTALL.md: `brew install steipete/tap/summarize`

---

## 4. Provider key checks

```bash
grep -E '^(OPENAI_API_KEY|GEMINI_API_KEY)=' ~/clawd/secrets/.env 2>/dev/null
```

- [ ] At least one of `OPENAI_API_KEY` or `GEMINI_API_KEY` exists
- [ ] If both are present, OpenAI remains the first-choice provider
- [ ] If one is missing, the skip is intentional and documented

---

## 5. Functional summary tests

Use the exact test video from INSTALL.md.

### 5A. OpenAI-first test
Run only if `OPENAI_API_KEY` is available.
```bash
source ~/clawd/secrets/.env 2>/dev/null || true
OPENAI_API_KEY="$OPENAI_API_KEY" summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short
```

- [ ] Command succeeds or produces a usable short summary
- [ ] Output is not a provider-auth error

### 5B. Gemini fallback test
Run this if OpenAI was skipped or failed.
```bash
GEMINI_API_KEY="$GEMINI_API_KEY" summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short --provider gemini
```

- [ ] Gemini fallback succeeds when used
- [ ] This proves the documented fallback path works

### 5C. Transcript extraction test
```bash
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract-only
```

- [ ] Transcript extraction succeeds
- [ ] Output is transcript text only, not another summary

---

## 6. Failure conditions

Fail this skill if any of these happen:

- [ ] `skill-version.txt` is wrong
- [ ] `summarize --help` fails
- [ ] Neither `OPENAI_API_KEY` nor `GEMINI_API_KEY` is available
- [ ] OpenAI-first path fails and Gemini fallback was not tested
- [ ] Transcript extraction fails even though a provider path works

---

## Final pass rule

Pass only if all of the following are true:

- [ ] Files and version are correct
- [ ] Core summaries are present and lean
- [ ] `summarize` binary is installed and callable
- [ ] At least one provider key is configured
- [ ] Summary test passes through OpenAI or Gemini
- [ ] `--extract-only` transcript test passes
