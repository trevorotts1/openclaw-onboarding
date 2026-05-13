# QC Checklist: Teach Yourself Protocol (TYP)

## 1. Purpose
Enables the agent to learn new knowledge in a structured way without bloating core workspace files.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, the full reference `.md`, and the `.skill` package.
- [ ] A master files folder is present under ~/Downloads using one of the documented naming variants, with `apis/`, `skills/`, `processes/`, and `references/` subfolders.
- [ ] The full TYP documentation has been copied into the master files folder, not pasted into core workspace files.
- [ ] Any helper files copied into `~/.openclaw/skills/01-teach-yourself-protocol` remain readable; no executable script is required in this skill folder, so executable-bit check is N/A unless a helper script was added later.
- [ ] Core files referenced by install (`AGENTS.md`, `TOOLS.md`, `MEMORY.md`, and when applicable `IDENTITY.md`) are writable.

## 3. Dependency Checks
- [ ] OpenClaw is installed and responsive: `openclaw status`.
- [ ] Workspace write access exists for `AGENTS.md`, `TOOLS.md`, `MEMORY.md`, and `IDENTITY.md`.
- [ ] The master files location under ~/Downloads is accessible and not duplicated under multiple conflicting names.
- [ ] No external API keys or CLIs are required beyond normal OpenClaw file access.

## 4. Key Detection
- [ ] No API key is required for TYP. QC should PASS only if the installer does **not** ask for any secret.
- [ ] Smart detection instead checks knowledge locations: search core files for `Teach Yourself Protocol` or `TYP`, then search the master files folder for the full protocol copy.
- [ ] Confirm no secret placeholder or fake credential was introduced while installing this skill.

## 5. Functional Checks
- [ ] Ask: “What is the Teach Yourself Protocol?” Expected answer mentions the three-layer knowledge architecture: core summaries, deep files, and folder structure.
- [ ] Ask: “Where do full documents go?” Expected answer points to the master files folder, not `AGENTS.md` or `TOOLS.md`.
- [ ] Give a short “Teach yourself this…” prompt and verify the agent announces TYP activation before doing any learning work.
- [ ] Verify the agent creates or updates a deep reference file and only adds a lean summary plus file path in core files.
- [ ] Verify the agent checks for conflicts or duplicates before creating new knowledge files.

## 6. QC Score
- Score this skill from **0 to 10** after running the checks above.
- Suggested rubric:
  - **10/10**: All installation, dependency, key-detection, and functional checks pass with no ambiguity.
  - **8-9/10**: Core behavior works, but one or two non-critical items need cleanup or documentation fixes.
  - **6-7/10**: Basic install exists, but the skill is missing a meaningful validation, dependency, or behavior requirement.
  - **0-5/10**: Missing prerequisite pieces, broken verification path, wrong secrets handling, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 7. QC Loop Rule
- Run at most **5 total QC/fix rounds** for this skill.
- After each failed round:
  1. Record exactly which checklist items failed.
  2. Apply the smallest targeted fix.
  3. Re-run only the failed checks plus any directly affected dependencies.
- If the skill still fails after the **5th round**, stop and escalate instead of continuing to loop.

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
