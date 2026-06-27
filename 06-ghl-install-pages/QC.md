# QC Checklist: GHL Install Pages

## 1. Purpose
Enables browser-based deployment of finished HTML pages into Convert and Flow / GHL funnels or websites using Playwright.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, the full reference `.md`, and the `.skill` package.
- [ ] Playwright is installed and Chromium has been downloaded successfully.
- [ ] The credential store or persistent-session path exists at the documented location for this repo.
- [ ] The Playwright configuration uses persistent context with the documented session directory and minimum viewport requirements.
- [ ] No standalone script in the skill folder is required; if a local deployment helper was created, confirm it is executable.

## 3. Dependency Checks
- [ ] TYP, BYUP, and GHL setup (skill 05) are already complete.
- [ ] Python 3 and Playwright are installed: `python3 -c "from playwright.sync_api import sync_playwright"` succeeds.
- [ ] Chromium is installed for Playwright: `playwright install chromium` completed successfully.
- [ ] Stored GHL login credentials exist in `~/clawd/secrets/.env` or a persistent browser session exists at `~/.openclaw/playwright-data/ghl-install-pages`.
- [ ] Finished HTML is available, self-contained, and ready to paste.

## 4. Key Detection
- [ ] Search all standard locations for `GHL_EMAIL` and `GHL_PASSWORD`, while also allowing the documented skip path if SSO or manual login is used.
- [ ] Also search for existing persistent session data at `~/.openclaw/playwright-data/ghl-install-pages` before declaring credentials missing.
- [ ] Recognize broader GHL credential aliases from setup skill if needed for account context: `GHL_API_KEY`, `GHL_PIT`, `GOHIGHLEVEL_API_KEY`, and `GHL_LOCATION_ID`.
- [ ] QC fails if the agent hardcodes credentials into a script or ignores an existing reusable session.

## 5. Functional Checks
- [ ] Run the Playwright import verification command and confirm success output.
- [ ] Verify the launch configuration uses `launch_persistent_context()` and **not** `launch()`.
- [ ] Open the GHL dashboard and confirm the agent checks the current sub-account before editing any page.
- [ ] Verify the agent can describe the nested iframe requirement and that code insertion happens inside the correct builder context.
- [ ] Confirm the agent ends with preview/report behavior and does **not** publish without explicit user approval.

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

---

## Per-build quality gate (FAB-QC ≥ 8.5) — distinct from install QC above

The checklist above is **install-level QC** (is the skill set up correctly?). Every
**built funnel** is ALSO held to the standing, library-aware **FAB-QC** build-quality
gate — the Skill-6 parallel of Skill-44's `qc-built-workflow.sh`:

- **Script:** `06-ghl-install-pages/qc-built-funnel.sh <evidence_root|slug>`
- **Shared scorer:** `shared-utils/fab_qc.py` · **Rubric:** `universal-sops/funnel-automation-build-quality-rubric.md`
- **SUPERSET overlay** on top of the canonical `ghl_verify` render gate (HTTP 200 + marker stays the hard D3 floor).
- **Six dimensions** (weights 22/20/18/15/13/12): template fidelity, copy substance (no surviving
  placeholders), render/soundness, persona grounding (fail-closed), flexibility honored, funnel↔automation link integrity.
- **Binding:** `v2_dispatcher.py` refuses to mark a task `verified` when the build emits FAB
  evidence and scores < 8.5 (`v2-autonomous-build-sop.md §9` BUILD-QC GATE).
- [ ] Built funnel passes `qc-built-funnel.sh` with FAB-QC score ≥ 8.5 and no hard miss.
