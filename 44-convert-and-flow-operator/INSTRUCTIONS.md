# Skill 44 — Convert and Flow Operator: Runtime Instructions

## Step 0 — Model Check Pre-flight (READ BEFORE ANY BUILD OR MODIFY ACTION)

**Trigger:** any time you are about to BUILD or MODIFY a GHL workflow (caf workflows build,
patch-email, patch-trigger, restore, or Tier 4 agent-browser build).

**Check:** look at your current session's active model name and thinking level.

**If the active model is a lighter/faster model** (e.g. deepseek-flash, haiku, mini, flash,
or any model NOT identified as a high-reasoning model) **OR thinking is not set to HIGH**:

Surface this recommendation to the owner BEFORE proceeding:

> ⚠️ **GHL workflow builds are complex and error-prone on lighter models.**
> It is HIGHLY RECOMMENDED to switch to a high-reasoning model (e.g. deepseek-v4-pro,
> or an Opus-tier model) with thinking set to HIGH before proceeding — for the best
> possible output and to avoid hard-to-catch hallucinations in workflow logic.
> *(A lighter model previously turned a 2-minute fix into a 12-hour loop by
> hallucinating a failure cause, a fake link, and a wrong number.)*
> Say "proceed anyway" to continue on the current model, or switch first and re-run.

**Then proceed** once surfaced — this is a recommendation, not a hard block. Do NOT
repeat the warning on the same build session after the owner has acknowledged it.

Read-only ops (caf contacts list, caf workflows list, etc.) do NOT trigger this check.

---

## Natural-language intents -> CLI commands

Operators never memorize CLI syntax. Say what you want in Telegram; the agent routes to the right command.

| Intent | Command |
|---|---|
| "Who are my new leads?" | `caf contacts list --tag ZHC-new-lead` |
| "Show me open opportunities in the Sales pipeline" | `caf opportunities list --stage open` |
| "What appointments do I have this week?" | `caf calendars appointments --this-week` |
| "Build a follow-up workflow for new leads" | Triggers TRINITY (see below) |
| "Update the welcome email in the onboarding workflow" | `caf workflows patch-email <workflow-id> --subject "..." --body "..."` |
| "List my active invoices" | `caf payments invoices list --status active` |
| "Schedule this social post for tomorrow at 9am" | `caf social post schedule --time "tomorrow 9am" --content "..."` |
| "What workflows do I have?" | `caf workflows list` |
| "Review/audit this workflow" / "check this workflow" / "inspect this workflow" | `caf workflows export <id>` (Tier 0 first), then escalate per skill 36 for what export cannot show (e.g. trigger-bucket state) |

---

## TRINITY routing (conversational workflow builds)

When the operator asks to "build a workflow / playbook / funnel" AND the workflow contains
a conversational node:

1. Skill 44 builds the GHL automation structure (the HANDS)
2. Skill 44 AUTO-INVOKES skill 38 for the brain (communications playbook + Build-with-AI prompt)
3. All three TRINITY legs ship together, or the build is NOT registered

For a purely mechanical workflow (no conversational node): skill 41 builds standalone (12-point checklist).

**Token-aware build path:**
- Firebase token present + healthy → `caf workflows build` via internal API
- Firebase token missing or expired → fall through for reads; BUILD falls to Tier 4 (agent-browser); owner
  nudge: "I need you to grab the Convert and Flow token to build workflows directly."

---

## Per-operation decision rule (runtime)

```
1. Is this a media upload? → ALWAYS Tier 3 (POST /medias/upload-file). Skip Tier 0.
2. Is this a workflow BUILD? → Check Firebase token:
   a. Present + healthy → caf workflows build
   b. Absent / expired → Tier 4 backstop (agent-browser) + owner nudge
2.5 Is this a workflow REVIEW / inspect / audit / "check this workflow"?
   → Tier 0 FIRST: caf workflows export <id>
   → Escalate per skill 36 ONLY for pieces export cannot show (e.g. trigger-bucket state).
   → NEVER open-ended-pick the 834-tool Community MCP for a workflow review.
3. Is this any other op in the CLI surface? → caf <command>
4. CLI returns 404 / unknown command? → Fall to Tier 1/2/3 per skill 36
5. Rate limit (429)? → STOP. Surface reset time. NEVER fall through tiers.
```

---

## Workflow-Write Data Rollback

Every `workflows update`, `patch-email`, or `patch-trigger` writes a timestamped snapshot BEFORE mutating:

```
~/.openclaw/tools/convert-and-flow-cli/data/snapshots/<location>/<workflow-id>/<timestamp>.json
```

To revert a workflow to a previous state:
```bash
caf workflows restore ~/.openclaw/tools/convert-and-flow-cli/data/snapshots/<location>/<workflow-id>/<timestamp>.json
```

---

## Rate-limit protocol (inherited from skill 36)

All tiers share one GHL daily bucket (200k req/day). On a 429 from ANY tier:
1. Parse `X-RateLimit-Daily-Reset`
2. Surface to owner: "Rate limited — back at HH:MM ET (in X hours)."
3. DO NOT retry. DO NOT fall through tiers.

---

## Dependency-first contract (from skill 41)

Before building any workflow, skill 44 checks that every referenced tag, custom field,
and custom value exists in GHL (GET-back verification). Missing items are surfaced to the
owner before touching the workflow builder. ZHC- / ZHC_ objects carry standing approval.

---

## Disclosure header format

Every GHL response from Tier 0 must begin with:
```
[GHL tier used: 0 — convertandflow <command>]
```

On fall-through:
```
[GHL tier used: 4 (Tier 0 build blocked: no Firebase token) — agent-browser]
```
