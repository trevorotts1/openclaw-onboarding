# Sub-Agent Handoff and Mandatory QC Protocol

This protocol governs how agents in the openclaw-onboarding repo
delegate work to sub-agents, and how they verify the work is correct
before declaring done. It applies to ALL skills in this repo, with
special emphasis on skill 38 (Conversational AI System) which has
9 install scripts, 27 protocols, and 8 journey templates that must
all land correctly.

## PART 1 — SUB-AGENT HANDOFF RULES

### Rule 1: Sub-agents receive full instructions, never summaries

When a main agent delegates work to a sub-agent (via sub-agent
spawning, the Task tool, or any other delegation mechanism), the
sub-agent MUST receive ONE of the following:

  (a) The literal file path to the instructions document, AND
      a directive to read the ENTIRE file before starting work, OR

  (b) The verbatim text of the instructions, copied character-for-
      character with no summarization, no "for brevity" cuts, no
      "I'll skip the prerequisites since you know them" shortcuts.

The main agent NEVER:
  - Summarizes instructions to save context window space
  - Paraphrases instructions in its "own words"
  - Skips sections it judges as "redundant" or "obvious"
  - Removes examples to make the prompt shorter
  - Strips out edge cases it thinks won't come up
  - Reduces the number of checks, protocols, or quality criteria
  - Reformats lists into prose or vice-versa "for readability"

If the instructions are too long for the main agent's context window,
the main agent passes the FILE PATH and directs the sub-agent to
read the file itself. The sub-agent has its own context window.

### Rule 2: Instruction modifications require a documented, valid reason

The main agent MAY modify instructions before passing them to a sub-
agent ONLY when ALL of these conditions are met:

  1. The modification is based on NEW INFORMATION not available
     when the instructions were originally written. Examples of valid
     new information:
       - A version number changed (web research confirmed user's
         OpenClaw is now v2026.5 and instructions referenced v2026.4)
       - An API endpoint deprecated (provider published deprecation
         notice the operator must follow)
       - The operator's environment differs from what instructions
         assume (e.g., they're on Linux but instructions assume Mac)
       - A required dependency changed (skill name changed,
         repository moved, command syntax updated)

  2. The modification is LOGGED in a visible place the operator can
     review. The log must include:
       - WHAT was changed (original text → new text)
       - WHY it was changed (cite the source: URL, command output,
         file content)
       - WHEN the change was made (timestamp)

  3. The modification is announced to the operator BEFORE proceeding,
     not buried at the end of the run.

Invalid reasons to modify instructions (the main agent must REFUSE
its own urge to modify in these cases):
  - "The instructions seemed too verbose"
  - "I thought this step was unnecessary"
  - "The operator probably already knows this"
  - "I can be more concise"
  - "I prefer a different ordering"
  - "Modern best practice is different" (without a cited source)
  - "I'm confident the result will be the same"

### Rule 3: Sub-agents acknowledge before starting

Before doing ANY work, the sub-agent must respond with:
  - Confirmation it received the full instructions (file path read
    in full, OR verbatim text confirmed received)
  - Word count or section count to prove it has the complete set
  - Any clarifying questions BEFORE acting
  - Its planned approach so the main agent can confirm

The main agent must wait for this acknowledgment before assuming
the sub-agent has what it needs.

### Rule 4: When in doubt, the sub-agent asks

If the sub-agent receives instructions it suspects have been trimmed
or modified, it MUST stop and ask:
  - "I noticed [specific gap]. Is that intentional or were these
    instructions abbreviated?"
  - "These instructions seem shorter than I'd expect for this task.
    Can I see the full version at [path]?"
  - "I see no [QC step / verification / checklist]. Was that
    intentional or should I follow the QC protocol?"

The main agent's job is to ANSWER these questions honestly, not
dismiss them.

## PART 2 — MANDATORY QC PROTOCOL

### Rule 5: QC is non-negotiable

Every skill install, every PR creation, every multi-file change MUST
run QC before being declared complete. Skipping QC is the same as
failing the task.

QC has two phases:
  - Phase A: Self-rating by the agent on a 10-point scale
  - Phase B: Evidence verification of the rating

If Phase A's score is below 8.5, the agent MUST go back and fix the
gap. It does NOT proceed. It does NOT declare done. It does NOT open
the PR. It loops until the score is 8.5 or higher.

If Phase B reveals the Phase A rating was inflated (evidence doesn't
support it), the rating is reset to whatever Phase B determined and
the agent loops back to fix.

### Rule 6: The 10-point scoring rubric

Each category scores 0-10. The skill's overall QC score is the
AVERAGE of all categories.

For skill 38 (Conversational AI System), the categories and their
0-10 definitions are:

**Category 1 — Protocol files present and verbatim**
  0  = no protocol files exist
  3  = some protocol files exist but content is summarized
  5  = all 27 protocol files exist but content doesn't match playbook
  7  = all 27 protocol files exist, most content matches playbook
  9  = all 27 protocol files exist, content is verbatim from playbook
       except for minor formatting
  10 = all 27 protocol files exist, content is byte-for-byte
       identical to the playbook's relevant section

**Category 2 — Journey templates present**
  0  = no templates exist
  5  = some templates exist but not all 8
  7  = all 8 templates exist but coach is not fully detailed
  9  = all 8 templates exist, coach is fully detailed, stubs have
       6-phase skeleton with at least 1 workflow per phase
  10 = all 8 templates exist, coach is fully detailed with all 12
       workflows, stubs have 6-phase skeleton + 1 workflow per
       phase verbatim from playbook §9.28-D, plus registry.md

**Category 3 — Install scripts present and verified**
  0  = no scripts exist
  3  = some scripts exist but not all 9
  5  = all 9 scripts exist but not executable or not OS-aware
  7  = all 9 scripts exist, are executable, but not idempotent
  9  = all 9 scripts exist, executable, idempotent, OS-aware, but
       not bash-syntax-verified
  10 = all 9 scripts exist, chmod +x verified, bash -n syntax-clean,
       idempotent (verified by mental dry-run of re-execution),
       OS-aware via uname detection, log actions to a file

**Category 4 — Reference documents present**
  0  = no references exist
  5  = some references exist but not all 6 (plus playbook + roadmap)
  7  = all 6 deep-dives plus full playbook plus roadmap exist
  9  = same as 7 plus references are cross-linked from the protocols
       that depend on them
  10 = all references exist, cross-linked, AND the full v5.14 source
       playbook + strategic roadmap are shipped intact

**Category 5 — Top-level skill files**
  0  = SKILL.md missing
  3  = SKILL.md exists but malformed frontmatter
  5  = SKILL.md, INSTALL.md, INSTRUCTIONS.md present, others missing
  7  = all 7 files present but one or more contains client-specific
       data (tags, names, IDs)
  9  = all 7 files present, no client-specific data, but some
       sections summarized rather than verbatim from playbook
  10 = all 7 files (SKILL.md, INSTALL.md, INSTRUCTIONS.md,
       EXAMPLES.md, CORE_UPDATES.md, CHANGELOG.md, skill-version.txt
       or .skill descriptor) present, all content verbatim, no
       client-specific data, frontmatter validates

**Category 6 — Root-file updates**
  0  = none updated
  5  = some updated but README inventory table wrong format
  7  = all 5 updated correctly (README, CHANGELOG, Start Here.md,
       version file, install.sh) but not all bumped per existing
       convention
  9  = all 5 updated, format matches existing entries, version bumped
       per semver convention
  10 = all 5 updated correctly, version bumped properly, AND
       CONTRIBUTING.md checklist run through if it exists

**Category 7 — Git workflow correctness**
  0  = committed to main directly
  3  = feature branch created but only one giant commit
  5  = feature branch with multiple commits but messages don't follow
       repo convention
  7  = feature branch, conventional commits, pushed to remote, but
       no PR opened
  9  = feature branch, conventional commits, pushed, PR opened, but
       PR body doesn't follow template or no cross-link to sibling
       repo
  10 = feature branch named correctly, 12 conventional commits in
       a-l sequence, pushed, PR opened against main with full body
       template, cross-linked to sibling repo PR, NOT merged, no
       tags created

**Category 8 — Independence rules respected**
  0  = modified skills the rules said not to touch
  5  = some untouched but accidentally added duplicates of features
       owned by other skills
  7  = all untouched skills truly untouched, but no duplicate-detection
       verification was run
  9  = all untouched skills verified untouched via git diff, but no
       written confirmation that humanizer-protocol.md is NOT in the
       new skill's protocols/ folder
  10 = skills 17, 18, 19, 29, 31 untouched verified by git diff;
       humanizer-protocol.md confirmed absent from new skill;
       skill 10 verified at latest version but not modified;
       skill 29 verified as prerequisite but not modified

**Category 9 — Pending features NOT implemented**
  0  = one or more of F14, F15, F16, F17, F18, F21 was implemented
  5  = no pending features implemented but some references to them
       in code or comments
  7  = no pending features implemented, no references in code
  9  = no pending features implemented, structure leaves room for
       them but doesn't mention them
  10 = no pending features implemented, structure leaves room for
       them, NO references to them anywhere in the shipped skill,
       AND no architectural assumptions that would block future
       implementation

**Category 10 — Prerequisite verification at install time**
  0  = no prerequisite check exists
  3  = check exists but only verifies presence, not version
  5  = checks skills 05, 10, 19, 29 presence but doesn't validate
       skill 10 is latest version
  7  = checks presence + latest version for skill 10, but doesn't
       check skills 19 + 29 are actually functional
  9  = checks all 4 prerequisites: presence, version, functional
       state (e.g., is GHL actually connected for skill 29)
  10 = all of 9, PLUS the check halts install with a clear error
       message naming the missing/outdated prerequisite, PLUS
       skill 10 is verified at LATEST version without being modified
       by skill 38

### Rule 7: Score calculation and pass/fail

  Overall QC Score = (sum of all 10 category scores) / 10

  Pass threshold = 8.5

  If overall score < 8.5:
    - Identify the lowest-scoring categories (any below 8.5)
    - Fix each one to at least 9 or 10
    - Re-run the rubric
    - Loop until overall score >= 8.5

  If overall score >= 8.5:
    - Proceed to Phase B: Evidence verification

### Rule 8: Phase B — Evidence verification

For each category scored 8 or higher, the agent MUST cite evidence:

  - File paths and line counts (e.g., "protocols/ has 27 files,
    confirmed by `ls protocols/ | wc -l`")
  - Diff outputs (e.g., "git diff main --stat shows only
    38-conversational-ai-system/ and root files modified")
  - Command outputs (e.g., "bash -n verified clean on all 9 scripts")
  - Hash comparisons (e.g., "protocols/sales-best-practices-protocol.md
    matches playbook §9.23 lines 5023-5187 verbatim")

If evidence cannot be cited for a 8+ score, that score is INFLATED.
Reset it to whatever can be evidenced, and loop back to Rule 7.

### Rule 9: QC report is delivered with every completion

When the agent declares done, the QC report MUST be in the output.
Format:

  QC Report — <task name>
  Date: <timestamp>

  Category scores:
    1. Protocol files:           X/10  (evidence: ...)
    2. Journey templates:        X/10  (evidence: ...)
    3. Install scripts:          X/10  (evidence: ...)
    4. Reference documents:      X/10  (evidence: ...)
    5. Top-level skill files:    X/10  (evidence: ...)
    6. Root-file updates:        X/10  (evidence: ...)
    7. Git workflow:             X/10  (evidence: ...)
    8. Independence rules:       X/10  (evidence: ...)
    9. No pending features:      X/10  (evidence: ...)
    10. Prerequisite checks:     X/10  (evidence: ...)

  Overall: X.X / 10
  Pass threshold: 8.5
  Status: PASS / FAIL

  Loops needed to reach pass: N
  Items fixed during QC: <list>

## PART 2b — WIRING CORRECTNESS: 3-LAYER REQUIREMENT (PRD 1.11)

### Rule 9b: "Wiring correctness" requires all THREE layers verified

The QC rubric dimension "Wiring correctness" (weight 30%) is scored 10/10
ONLY when all three of the following layers are confirmed, not just one:

**Layer 1 — MERGED (GitHub ground truth)**
  The fix or feature exists on the `main` branch of the onboarding repo.
  Evidence: the SHA on `main` in GitHub, not a local clone.
  A local commit that hasn't been pushed and merged = NOT merged.

**Layer 2 — DEPLOYED (version on the client box)**
  The merged version has been pulled and is present on the client box.
  Evidence: `.onboarding-version` on the box matches the expected tag,
  AND the Command Center version satisfies `cc-compat.json` `minVersion`.
  A fix that was pushed to GitHub but never pulled to the box = NOT deployed.

**Layer 3 — LOADED (marker present in the INJECTED system prompt)**
  The deployed files have been read by the OpenClaw gateway and injected
  into the active session's system prompt.
  Evidence: the gateway's `sessions.systemPromptReport` call returns a
  prompt body that contains the `CEO_ORCHESTRATOR_RULE_V2` marker.
  A file that is on disk but in a resumed session with `systemSent=true` =
  NOT loaded (the gateway caches the old prompt until the session resets).

  Fallback (proxy confidence, weaker): `workspace/SOUL.md` contains the
  marker AND the session's `lastSystemPromptTs` post-dates the last
  `sessions.reset` call. This proves Layer 3 by disk+session state rather
  than live prompt inspection; labeled `loaded_confidence: "proxy"` in
  the fleet-refresh output.

**Scoring for "Wiring correctness" in the PRD 1.11 rubric:**
  10 = All 3 layers verified with authoritative evidence (SHA + version + live prompt)
   8 = Layer 1 + Layer 2 confirmed; Layer 3 proxy-only (marker on disk, session rebuilt)
   5 = Layer 1 + Layer 2 only (not known if session loaded the new content)
   3 = Layer 1 only (merged but undeployed)
   0 = Layer 1 not confirmed (assumed but not checked)

**Tool:** `scripts/fleet-refresh.sh --verify-only` generates the per-box
evidence for all three layers without making any changes.

## PART 3 — CLOUDFLARE API KEY CHECK AT INSTALL

### Rule 10: Cloudflare API key is verified before install proceeds

When skill 38 (Conversational AI System) starts, the very first action
is the prerequisite check (00-verify-prerequisites.sh). That check
now also includes Cloudflare API key verification.

### Rule 11: Where to look for the key

The 00-verify-prerequisites.sh script must check the following
locations in order, stopping at the first one that contains a valid
Cloudflare API key:

  1. ~/.openclaw/.env
  2. ~/.openclaw/secrets.env
  3. ~/.openclaw/openclaw.env
  4. <MASTER_FILES_DIR>/.env
  5. <MASTER_FILES_DIR>/secrets.env
  6. ~/.cloudflared/.env
  7. ~/.zshrc (look for export CLOUDFLARE_API_TOKEN or
     export CF_API_TOKEN lines)
  8. ~/.bashrc (same)
  9. ~/.bash_profile (same)
  10. Current shell environment ($CLOUDFLARE_API_TOKEN or
      $CF_API_TOKEN)

Variable names to look for (any of these):
  - CLOUDFLARE_API_TOKEN
  - CF_API_TOKEN
  - CLOUDFLARE_API_KEY
  - CF_API_KEY

Valid token format: starts with a known Cloudflare token prefix or
is a 40+ character alphanumeric string. The script validates format
but does NOT make a network call to verify the token works (that
happens later in the install when the tunnel is actually created).

### Rule 12: If the key is found

Log to install log:
  "Cloudflare API key found at <location>. Proceeding."

Continue to next prerequisite check (skills 05, 10, 19, 29).

### Rule 13: If the key is NOT found

STOP install. Output this exact message to the operator:

  =====================================================
  CLOUDFLARE API KEY NOT FOUND
  =====================================================

  Skill 38 (Conversational AI System) requires a Cloudflare API
  key to set up the public tunnel for receiving webhooks from GHL.

  I checked these locations and found no Cloudflare API key:
    - ~/.openclaw/.env
    - ~/.openclaw/secrets.env
    - ~/.openclaw/openclaw.env
    - <MASTER_FILES_DIR>/.env
    - <MASTER_FILES_DIR>/secrets.env
    - ~/.cloudflared/.env
    - ~/.zshrc, ~/.bashrc, ~/.bash_profile
    - Current shell environment

  To proceed, follow these instructions to get your credentials:

    https://docs.google.com/document/d/1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo/edit?usp=sharing

  Once you have your Cloudflare API key:

    1. Save it to your OpenClaw environment file at:
       ~/.openclaw/.env (or whichever env file you already use)

       Add the line:
         CLOUDFLARE_API_TOKEN=<your-token-here>

    2. Tell me you're done, and I'll restart the skill 38 install
       from the beginning. The check will find your key and
       proceed automatically.

  =====================================================

Then HALT install. Do not skip. Do not work around. Do not try to
generate a placeholder key. Wait for the operator's "I'm done"
signal.

### Rule 14: Restart flow

When the operator returns and says they have the key (signals like
"I'm done", "got it", "ready", "added the key"), the agent:

  1. Re-runs the entire 00-verify-prerequisites.sh script from the
     start (not just the Cloudflare check — full prereq sweep)

  2. If Cloudflare check now passes: continue to next prereqs
     (skills 05, 10, 19, 29), then begin install Phase 0 (Step O.1)

  3. If Cloudflare check still fails: re-display the message from
     Rule 13. Do not assume the operator made an error elsewhere.

  4. Once install begins, the agent reads the key from wherever
     00-verify-prerequisites.sh found it, sets it as an environment
     variable for the install session, and uses it for the
     Cloudflare Tunnel creation step.

### Rule 15: The Google Doc is the canonical source for credentials

The Google Doc at the link in Rule 13 contains:
  - How to create a Cloudflare account (if needed)
  - How to generate an API token with the right scopes
  - What other credentials the operator needs (GHL API key,
    OpenRouter key, etc.)
  - Common gotchas

The operator maintains the doc. The agent does NOT recreate this
information in its own words or duplicate it elsewhere. The link is
the single source of truth.

If the operator asks "what scopes do I need" or similar, the agent
points them to the Google Doc rather than answering from memory.
The doc may have been updated since the skill was built.

## PART 3.5 — THE ONBOARDING VERIFICATION GATE (binding definition of "installed/done")

**Added v10.15.48 (FIX 1: ONBOARDING HONESTY).** The #1 reported failure was
agents reporting a skill "installed / done / onboarded" when it had only been
DOWNLOADED to disk — install.sh copies files + pastes activation PROSE into
AGENTS.md (never executed), and the old "complete" Telegram fired
unconditionally. There is now a real STATE MACHINE + GATE.

### Rule 16: A skill is INSTALLED only when the gate passes

State file: `~/.openclaw/workspace/.onboarding-state.json` — every non-archived
skill is seeded `pending` and advances:

```
pending → downloaded → wired → qc-passed | qc-failed     (+ park: interview-pending)
```

Gate library: `~/.openclaw/scripts/onboarding-state.sh` (also at
`~/.openclaw/onboarding/scripts/onboarding-state.sh`). A skill counts INSTALLED
only when **all applicable checks pass**:

  (a) `openclaw skills info <name>` returns the skill as Ready/visible (the
      `name` is the SKILL.md frontmatter `name:` field), AND
  (b) its CORE_UPDATES sentinel `<!-- skill:<folder>:core-update-applied -->`
      is present in the workspace core files — only required if the skill ships
      a `CORE_UPDATES.md`, AND
  (c) its `qc-*.sh` exits 0 — only required if it ships one.

Usage:

```bash
source ~/.openclaw/scripts/onboarding-state.sh
obs_verify_skill 36-ghl-mcp-setup      # sets qc-passed | qc-failed, echoes reason
obs_gate_summary                       # "X/Y verified-installed, Z NOT verified: <list>"; rc=0 only when all pass
```

### Rule 17: "Onboarding complete" is gate + closeout, never a flag

Onboarding/update is **complete** ONLY when `obs_gate_summary` returns success
(every non-archived skill is `qc-passed` OR an explicit `interview-pending`
park) AND closeout (Skill 37) has fired where applicable. A `✅ complete` /
"Skills updated successfully" message is now CONDITIONAL on this gate in both
`install.sh` and `update-skills.sh`, and the `qc-completeness.sh` exit code is
HONORED (was ignored). If the gate is not met, report the TRUTH — "wave N: X/Y
verified-installed, Z failed: <list>" — never "done".

### Rule 18: INTERVIEW_PENDING is a park, not "done"

A skill that legitimately awaits owner input may be parked
`interview-pending` (`obs_set_status <folder> interview-pending`). The
`onboarding-resume` cron re-pings the owner on backoff. It is NOT a terminal
"done" and must never be reported to the owner as installed.

### Rule 19: The onboarding-resume cron is the retry engine

`onboarding-resume` (every 15 min) runs the gate and, while any skill is
`pending|downloaded|wired|qc-failed`, self-pings the agent to activate + verify.
It NEVER stops on a self-declared "done" — only on a real gate-pass (shell guard
`scripts/resume-onboarding.sh`), with max-runs + Rescue-Rangers escalation
identical to the workforce-build-resume cron.

## PART 4 — APPLICATION TO ALL SKILLS

These rules apply to:
  - All current skills (01 through 38)
  - All future skills added to either openclaw-onboarding repo
  - Any work delegated to sub-agents in either repo

When adding a new skill:
  - Reference this protocol in the new skill's SKILL.md or INSTALL.md
  - The new skill's QC rubric may extend this 10-category rubric
    with skill-specific categories, but cannot remove or weaken any
    existing category
  - Sub-agent handoff rules apply automatically; no per-skill
    customization needed

## PART 5 — WHAT TO DO WHEN YOU'RE THE SUB-AGENT READING THIS

If you (as a sub-agent) are reading this protocol because your parent
agent passed it to you, here's your contract:

  1. Read Part 1 fully. Confirm to your parent that you got the full
     instructions (cite section names and approximate word count).

  2. Ask any clarifying questions BEFORE starting work.

  3. Do the work without summarizing or shortcutting.

  4. Run the Part 2 QC against your own work BEFORE declaring done.

  5. Report your QC scores with evidence. If overall < 8.5, loop and
     fix without being asked.

  6. When you declare done, include the QC report.

  7. If at any point your parent tells you to skip QC, refuse and cite
     this protocol. QC is non-negotiable.

  8. If at any point your parent tells you to summarize or trim work
     "to save time," refuse and cite this protocol. The work was
     specified at the level of detail it was specified for a reason.
