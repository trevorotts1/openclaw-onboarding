# QC Checklist - Skill 16: Summarize YouTube
**Version:** v6.5.7

Run this after installation. Every section must pass before you mark summarize-youtube complete.

---

## 1. File and version checks

```bash
SKILL_DIR="$HOME/Downloads/openclaw-master-files/OpenClaw Onboarding/16-summarize-youtube"
ls -1 "$SKILL_DIR"
cat "$SKILL_DIR/skill-version.txt"
```

- [ ] Required files exist: `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`, `summarize-youtube-full.md`, `QC.md`, `skill-version.txt`
- [ ] `skill-version.txt` returns `v6.5.7`
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
