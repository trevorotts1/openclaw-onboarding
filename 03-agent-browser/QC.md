# QC Checklist: Agent Browser

## 1. Purpose
Enables precise ref-based browser automation through the `agent-browser` CLI as the preferred onboarding browser tool.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md` and `INSTALL.md`.
- [ ] If the source-of-truth operational skill exists at `~/clawd/skills/agent-browser/SKILL.md`, it is readable and treated as authoritative.
- [ ] `agent-browser` is discoverable in PATH: `command -v agent-browser`.
- [ ] If installation was needed, global npm install completed without permission errors and `agent-browser install` finished successfully.
- [ ] The `agent-browser` executable is runnable; this is the required executable for this skill.

## 3. Dependency Checks
- [ ] Node.js and npm are installed and working.
- [ ] Global npm install permissions are available, or a documented escalation path exists.
- [ ] Browser dependencies required by `agent-browser install` are present.
- [ ] No external API key is required for the basic CLI smoke test.

## 4. Key Detection
- [ ] No API key is required by this onboarding wrapper.
- [ ] Smart detection checks for binary availability, npm global path issues, and whether the authoritative skill doc path exists.
- [ ] QC fails if the installer incorrectly asks for a token just to run the local smoke test.

## 5. Functional Checks
- [ ] Run `agent-browser --help | head -20` and confirm normal help output.
- [ ] Run the documented smoke test: open `https://example.com`, take a snapshot, then close the session.
- [ ] Confirm the snapshot includes stable element refs such as `@e1` or similar ref markers.
- [ ] Verify the agent describes `agent-browser` as the preferred browser automation path, with Playwright only as fallback.
- [ ] If install initially failed due to permissions, verify the failure mode was reported clearly rather than silently skipped.
- [ ] **ASSERTED, not implied (P3-06):** the Step-4 smoke test MUST be recorded as having run **inside the guaranteed-close `trap ... EXIT` subshell with `--headed false`** — this is no longer a checkbox taken on faith. Quote, in your QC evidence, the exact command + flags that ran (`qc-agent-browser.sh` prints this verbatim under "ASSERTED evidence: exact command run (extracted from INSTALL.md Step 4)" — it re-extracts the live fenced block from INSTALL.md at run time, so what is quoted is provably the shipped doc text, not a hand-typed stand-in). A QC pass that cannot quote this block + its output is not a pass — re-run `qc-agent-browser.sh` and quote its output.
- [ ] **Bundled-archive drift gate (P3-06):** `qc-agent-browser.sh` unzips `agent-browser.skill` and diffs `INSTALL.md`/`SKILL.md`/`CHANGELOG.md`/`CORE_UPDATES.md` inside it against the on-disk copies — ANY mismatch is a hard QC FAIL naming the differing file. If it fails, run `scripts/pack-agent-browser-skill.sh` (never hand-zip) to regenerate, then re-run QC.
- [ ] **Post-smoke-test session state is ASSERTED clean (P3-06):** a Chromium process this run's own smoke test spawned and left alive after `agent-browser close` ran is a hard QC FAIL (not a warning) — `qc-agent-browser.sh`'s "zero Chromium processes spawned by this smoke test remain alive after guaranteed-close" line must read PASS. (A session that already existed *before* this QC run started is reported WARN only — that one predates this skill's own smoke test and is not this run's fault.)
- [ ] **On-box source-of-truth drift gate (GK-28/U90):** if `~/clawd/skills/agent-browser/SKILL.md` exists on this box, `qc-agent-browser.sh`'s "On-box source-of-truth drift gate" section must read PASS — either "no on-box source-of-truth copy present" (path absent) or "matches the pinned baseline" (present + pinned + unchanged). A FAIL naming "no baseline pinned yet" means the on-box copy was never reviewed/pinned — run `scripts/pin-onbox-source-of-truth.sh` after reviewing it. A FAIL naming "DRIFTED from the pinned baseline" means the on-box copy changed since it was pinned — review the change before re-pinning.
- [ ] **CLI version pin (GK-28/U90):** `qc-agent-browser.sh`'s "CLI version pin" section must read PASS on both lines — `agent-browser-cli.pin` and `CLI-VERSION-PIN.md` agree, AND the installed `agent-browser --version` matches the pin. A mismatch is a hard QC FAIL naming both versions. Never hand-edit `agent-browser-cli.pin` — bump only via `scripts/bump-agent-browser-cli-pin.sh <version> "<reason>"`, and only after the new version is proven working on the operator's own box first (see `CLI-VERSION-PIN.md`).
- [ ] **Backstop conformance battery (GK-28/U90):** `qc-agent-browser.sh`'s "Backstop conformance battery (consumer contract)" section must read PASS — all five legs (open, ref-based snapshot, snapshot-ref stability, fill-by-ref, guaranteed close) succeed against the bundled offline fixture. A FAIL names the specific leg that broke — that leg maps directly to a capability Skill 6's `browser_manager.sh` or Skill 44's Tier-4 fallback depends on; do not mark this skill done with this section failing.

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
