# Command Center Setup - Core File Updates

This document lists the exact additions to make to your core .md files after installing the Command Center.

---

## MEMORY.md Addition

Add this line to MEMORY.md (usually at the top, in the status section):

```markdown
Command Center installed [DATE], [X] departments active, dashboard at [URL], wiki enabled
```

**Example:**
```markdown
Command Center installed March 19 at 3-45 PM, 5 departments active, dashboard at http://localhost:4000, wiki enabled
```

**What to replace:**
- `[DATE]` - Use the current date in human-readable format
- `[X]` - The number of departments you activated
- `[URL]` - Either `http://localhost:4000` or your Cloudflare tunnel URL if set up

### Memory Architecture Note
The Command Center uses a 3-layer memory system:
1. **Session Memory**: Conversation context within each Telegram topic
2. **Semantic Memory**: memory-core for long-term fact retrieval across sessions
3. **Structured Memory**: Memory Wiki for coaching theories, SOPs, and persona blueprints

Each department workspace has isolated memory. Department heads use `wiki_search` and `wiki_get` for structured knowledge retrieval.

---

## TOOLS.md Addition

Add this section to TOOLS.md (in the services/tools section):

```markdown
## Command Center Dashboard

**Local URL:** http://localhost:4000
**Remote URL:** [Your Cloudflare URL if configured]
**Telegram Group:** [Your Company Name] Command Center

Departments communicate via dedicated topics in the Telegram group. Each department head responds in their assigned topic.

### Department Topics
- Marketing - Chief Marketing Officer
- Sales - Chief Sales Officer
- Operations - Chief Operating Officer
- [Add your other departments here]
- Cross-Department - For interdepartmental collaboration

### Accessing the Dashboard
- Local: http://localhost:4000
- Requires the PM2 process to be running: `pm2 list` to check
- View logs: `pm2 logs command-center`

### Managing the Dashboard
```bash
# Check if running
pm2 list

# View logs
pm2 logs command-center

# Restart if needed
pm2 restart command-center

# Stop
pm2 stop command-center
```
```

**What to customize:**
- Replace `[Your Cloudflare URL if configured]` with your actual URL or remove if not using Cloudflare
- Replace `[Your Company Name]` with your actual company name
- Update the department list to match your actual departments

### Reusable template libraries (funnel + automation)

```markdown
## Funnel + Automation Template Libraries (template-first / reuse-before-reinvent)

- **Funnel library (38):** `06-ghl-install-pages/funnel-templates/` — match with
  `funnel_matcher_cli.py --match`; runs as STEP 0 in `tools/v2_dispatcher.py` (env-gated).
- **Automation library (28):** `44-convert-and-flow-operator/automation-templates/` — match with
  `_matcher/cli.py --match` (Skill-44 Step 0.4). Shared matcher core: `_matcher/flex.py`.
- **Funnel→automation link map:** `_links/funnel-to-automation.json` (keyed by funnel_template_id).
- **Discoverable in the Command Center:** ingested into `mission-control.db` `templates` table by
  `32-command-center-setup/scripts/ingest-template-libraries.py` (LEXICAL keyword search — no
  embedding re-index; do NOT re-embed the persona corpus).
- **Build-quality gate:** FAB-QC ≥ 8.5 (`shared-utils/fab_qc.py`, rubric in universal-sops).
- Flexibility = guide-not-rule: honor explicit choice; CREATE_NEW only when nothing fits; never block.
```

**Box-side activation (run once per build / on a library update — see Event 7 of
`universal-sops/adding-capability-after-build.md`):**
```bash
# 1. (re)build + commit the lexical indexes
python3 06-ghl-install-pages/tools/funnel_matcher_cli.py --build-index
python3 44-convert-and-flow-operator/automation-templates/_matcher/cli.py --build-index
# 2. wire the matcher env vars onto the dept agent (else STEP 0 / Step 0.4 stay dark)
bash 44-convert-and-flow-operator/tools/engine/wire-ghl-env.sh
# 3. ingest the templates into the Command Center for lexical search
python3 32-command-center-setup/scripts/ingest-template-libraries.py
```

---

## HEARTBEAT.md Addition

Add this task to HEARTBEAT.md (in the regular checks section):

```markdown
### Command Center Activation Check

Check twice daily if Skill 23 is complete but Command Center not yet set up.

**How to check:**
1. Look for department folders in ~/Downloads/openclaw-master-files/ (or your master files location)
2. Check if ~/.openclaw/workspaces/command-center/ exists

**If Skill 23 is done and no command-center workspace exists:**
- Prompt user to activate Skill 32: "Your AI Workforce Blueprint is complete. Activate Skill 32 to set up your Command Center with live department agents and dashboard."

**If Command Center exists:**
- Verify dashboard is running: `pm2 list | grep command-center`
- If not running, start it: `cd ~/projects/command-center && pm2 start ecosystem.config.cjs`
```

---

## AGENTS.md - REQUIRED Addition

Add this to AGENTS.md:

```markdown
### Command Center Auto-Install Trigger

If the client says ANY of the following at ANY time — today, tomorrow, next week, whenever:
- "I finished the interview"
- "I completed the AI Workforce"
- "My departments are set up"
- "What do I do next?" (after completing Skill 23)
- "Can you install the Command Center?"
- "I'm ready for the dashboard"

Then IMMEDIATELY:
1. Verify department folders exist on disk (check ~/.openclaw/workspaces/command-center/, ~/.openclaw/workspace/departments/, ~/Downloads/openclaw-master-files/)
2. If folders exist: download and install Skill 32 from the onboarding repo (curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/update-skills.sh | bash) then follow Skill 32 INSTALL.md
3. If folders do NOT exist: ask "Where did you save your department folders?" and use their answer
4. Do NOT wait for a scheduled check. Do NOT say "I'll look into it later." Install NOW.

### Command Center Pattern

The Command Center uses a "Department Head" pattern:
- One persistent agent per department
- Each bound to a dedicated Telegram topic
- Workers spun up on-demand for specific tasks
- Personas assigned from coaching-personas library

See full documentation: ~/.openclaw/skills/32-command-center-setup/
```

This addition is REQUIRED, not optional.

---

## AGENTS.md Addition — Kanban Done-Gate Protocol (v9.6.5)

**Where:** Append at the bottom of `~/clawd/AGENTS.md` after the existing Skill 32 sections.

**Exact text to add:**
```
## 🔴🔴🔴 Kanban Done-Gate Protocol (Skill 32, v9.6.5+)

A task card cannot move from the "Review" column to the "Complete" column
until the department's Devil's Advocate has VALIDATED the measurable Done
criteria from the SOP's DEFINE section.

Workflow:
  Backlog → Ready → In Progress → REVIEW → (DA validates) → Complete

When a worker (specialist sub-agent or director) finishes a task:
  1. Move the card to Review (NOT Complete).
  2. Tag the card with `da_pending=true`.
  3. Invoke the dept's Devil's Advocate. The DA reads:
     - The task description
     - The SOP that was followed (DEFINE section — what "done" means)
     - The artifact produced (file, message, blueprint, etc.)
  4. DA returns one of:
     - PASS: card moves to Complete, log entry to dept/memory/<date>.md
     - FAIL: card stays in Review, DA writes specific failure reasons
       to the card's notes, worker iterates and re-submits.
     - INDETERMINATE: DA cannot verify (e.g. data not available yet).
       Card stays in Review with `da_indeterminate=true` and a
       follow-up date. DA re-runs on that date.

Worker rules:
  - NEVER move a card directly from In Progress to Complete (must pass
    through Review).
  - NEVER mark a card Complete on your own behalf — only the DA does.
  - If you disagree with a DA FAIL: log your disagreement in the card
    notes, escalate to the department head, do NOT override the gate.

DA rules:
  - Validate against MEASURABLE criteria only (numbers, presence of
    specific artifacts, KPI threshold). NOT against subjective taste.
  - If the SOP's DEFINE section doesn't have measurable criteria, return
    INDETERMINATE + log that the SOP needs updating.
  - One PASS per card. Do not re-PASS the same card after a failure unless
    the worker has changed the artifact.

Why: prevents "task completion theater" where workers self-mark Done
without anyone validating. The DA is the quality gate.
```

This addition is REQUIRED for v9.6.5+ Command Center installs.

---

## Verification

After making these additions, verify:

1. MEMORY.md shows your Command Center status
2. TOOLS.md has the dashboard information
3. HEARTBEAT.md has the activation check task
4. AGENTS.md has the Kanban Done-Gate Protocol section
5. All paths and URLs are correct for your setup

---

## Notes

- Keep these entries concise (as shown above)
- Full documentation stays in the skill folder
- These are pointers and status updates only
- Update the dashboard URL in TOOLS.md if you change from localhost to Cloudflare

---
<!-- BREADCRUMB: skill-32-mac | 2026-04-12 | v6.5.7 | CORE_UPDATES.md updated with memory references | Memory Surgery Playbook v3.5 -->
