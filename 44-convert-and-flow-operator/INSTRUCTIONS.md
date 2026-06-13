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

> **BIDIRECTIONAL LINK (Step 9):** If at Step 9 QC catches a HALLUCINATION-class fail
> (build agent claimed X but QC-observed NOT-X), the Step 0 recommendation flips to a
> HARD REQUIREMENT — the redo MUST use a high-reasoning model with thinking=HIGH.
> See Step 9 "If QC finds a HALLUCINATION" for the full escalation path.

Read-only ops (caf contacts list, caf workflows list, etc.) do NOT trigger this check.

---

## Step 0.5 — PLAN MODE (before any workflow CREATE/BUILD)

**Trigger:** any time the intent is to build or create a new workflow, playbook, or funnel.

**NOT triggered by:** read-only ops, REVIEW/export, or a single targeted patch-email/patch-trigger
on an already-existing workflow.

**BINDING RULE: Rushing to a default build is NOT the best outcome and is a violation. Decide
the nodes, trigger, and actions deliberately, for THIS client's stated goal. The agent does NOT
touch `caf workflows build` (or the Tier 4 backstop, or skill 38 structure generation) until
the plan is presented and the gating questions are answered.**

### Step A — THINK (do not write to GHL)

Reason through the following and write them down before any other action:

**A1. DESIRED RESULT** — restate, in the client's own framing, the outcome the workflow must
produce ("when X happens, the contact should end up Y"). Pull from the conversation; do NOT
invent goals the client did not state.

**A2. CLIENT EXPECTATIONS** — capture explicit constraints, especially when the client was
hyper-specific (exact message copy, exact wait durations, exact tag names, exact channel /
SMS-vs-email, exact business-hours windows). Hyper-specific requests are honored verbatim;
the agent does NOT silently "improve" a value the client pinned.

**A3. BEST APPROACH** — design which trigger, which nodes, and which actions actually reach A1
(e.g. Contact Created vs Form Submitted vs Tag Added; SMS vs email vs both; If/Else branches;
Wait durations; Stop-on-Response). This is a reasoning step, not a template fill.

### Step B — DEPENDENCY PRE-CHECK (skill 41 dependency-first contract)

For every tag, custom field, and custom value the approach references, GET-verify it exists in
GHL FIRST. Missing items are listed in the plan as "must create first (will surface for
approval)". ZHC-/ZHC_ objects carry standing approval. The plan MUST NOT propose a build on
non-existent dependencies.

### Step C — OUTLINE

Produce a concrete, ordered node outline:
Trigger (type + filters) → each action/step in sequence (with its config: template/copy,
recipient, channel, wait duration, branch conditions) → exit.
This is the human-readable blueprint of what will be built.

### Step D — CHECKLIST

Instantiate the canonical checklist template
(`references/workflow-build-checklist-template.md`) for THIS workflow — fill the workflow name,
trigger type, each expected node, each tag/field/value, the intended re-entry setting, the
intended publish state, and (if any SMS node) the intended SMS From-number. This is the artifact
QC and the client will both verify against.

### Step E — IMPROVEMENTS + RECOMMENDATIONS

Surface concrete upgrades the client did not ask for but that serve the goal (e.g. "add a
Stop-on-Response so contacts who reply are not re-texted", "add a 3-day re-nudge branch",
"guard the SMS behind business-hours"). Each recommendation is OPTIONAL and clearly labeled as
a suggestion. When the client was hyper-specific, recommendations are offered ALONGSIDE (never
instead of) their exact spec, and the agent states it will build their spec unless they accept
the suggestion.

### Step F — PRESENT THE PLAN + ASK THE GATING QUESTIONS

Send the client: the restated result + expectations, the outline, the checklist, and the
recommendations — then ask the two mandatory gating questions and WAIT for answers:

**GATING QUESTION 1 — PUBLISH:**
"Do you want me to publish this and make it live, or build it as a draft for you to review first?"
(Default if unanswered = DRAFT, matching CAF_DRAFT_ONLY=true.)

**GATING QUESTION 2 — RE-ENTRY:**
"Should a contact be able to come through this workflow more than once (re-entry / allow
multiple), or only once?"
(Default if unanswered = once / re-entry OFF — the safer default; recorded explicitly in the
checklist either way.)

The publish answer maps to the build's status/trigger-active intent; the re-entry answer maps to
the workflow's allow-multiple / re-entry setting. NEITHER is guessed — both are recorded on the
checklist with the client's answer.

**Only after the gating questions are answered may the agent proceed to TRINITY routing / the
Per-operation decision rule.**

---

## Natural-language intents -> CLI commands

Operators never memorize CLI syntax. Say what you want in Telegram; the agent routes to the right command.

| Intent | Command |
|---|---|
| "Who are my new leads?" | `caf contacts list --tag ZHC-new-lead` |
| "Show me open opportunities in the Sales pipeline" | `caf opportunities list --stage open` |
| "What appointments do I have this week?" | `caf calendars appointments --this-week` |
| "Build a follow-up workflow for new leads" | PLAN MODE (Step 0.5) first, then TRINITY |
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
2.0 NEW workflow build/create? → run PLAN MODE (Step 0.5) and get the gating answers
    BEFORE choosing the token/tier path. Do not proceed to 2a/2b until plan is done.
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

## Step 9 — QC GATE (before declaring done)

**Trigger:** immediately after the build agent finishes constructing a new workflow.

**BINDING RULE: The build agent MUST NOT say "done" until QC passes and the filled checklist
is handed to the client. Done is never declared before a clean QC pass + checklist handover.**

### Step 9.1 — Announce to client (MANDATORY, send before spawning QC)

Send via the client's own gateway (`openclaw message send --channel telegram`):

> "I've built the workflow. Before I call it done, I'm running an independent QC agent to
> verify it against the checklist item-by-item. One moment."

### Step 9.2 — Spawn an independent QC sub-agent on MiniMax

Dispatch a fresh sub-agent via OpenClaw's agent-to-agent dispatch (`sessions_send` — same
mechanism as skill 38's subagent-delegation-pattern.md), in a fresh session, on an
INDEPENDENT MiniMax model (independent = a DIFFERENT model than the build agent, so QC cannot
inherit the builder's own hallucinations).

**Model resolution (in order):**
1. Prefer `minimax/minimax-2.7` via OpenRouter (the repo's established MiniMax extraction model,
   per skill 38 Step 9.24).
2. Or `minimax-m3:cloud` if an Ollama-Cloud MiniMax slug is configured.
3. VERIFY the MiniMax model is actually configured + reachable before spawning (per
   subagent-delegation-pattern.md: "Verify the chosen model exists in the OpenClaw config and
   has an API key available"; per MEMORY ollama-cloud-baseurl-trap). If no MiniMax model is
   available, fall back to the next independent high-reasoning model and RECORD which model QC'd.

The QC sub-agent receives: the filled checklist artifact, the workflow id, and read-only `caf`
access.

### Step 9.3 — QC runs item-by-item

The QC sub-agent independently inspects the BUILT workflow:
- Primary: `caf workflows export <id>` (read-only, Tier 0).
- Escalation per skill 36 ONLY for what export cannot show (e.g. trigger-bucket state — the
  exact gap that bit Sheila and is the v12.3.6 deferred follow-up).

The sub-agent runs `qc-built-workflow.sh <workflow-id>` (in the skill folder) which
machine-asserts the mechanically-checkable items and returns per-item PASS/FAIL JSON.

For EACH checklist item (WF-1..WF-21) the QC sub-agent returns an explicit PASS / FAIL with
the observed value vs expected value.

### Step 9.4 — QC verdict routing

- All-PASS → proceed to Step 9.6.
- Any FAIL → Step 9.5.

### Step 9.5 — On FAIL: fix and re-run QC

The build agent fixes the failing items (re-using the snapshot/restore if needed) and RE-RUNS
QC from Step 9.2. Do NOT declare done on a partial pass.

Exception: if the FAIL is class=HALLUCINATION, follow the "If QC finds a HALLUCINATION"
escalation below instead of the normal fix path.

### Step 9.6 — Declare done + hand over checklist

Only after all-PASS: tell the client "QC passed — here is the verified workflow" and HAND THE
CLIENT THE FILLED CHECKLIST (every item with its PASS + observed value) so the client can
independently verify every setting themselves.

### Step 9.7 — Logging (build-events ledger)

Append to the build-events ledger at:
`~/.openclaw/tools/convert-and-flow-cli/data/build-events.jsonl`

Each QC run logs: model used, per-item verdicts, pass/fail result, any escalation, workflow id,
timestamp. This makes a crash/limit mid-QC recoverable (per MEMORY persistent-ledger rule).

---

### If QC finds a HALLUCINATION

QC distinguishes a HALLUCINATION from a REAL GAP by the evidence shape:

**REAL GAP:** the build agent did NOT claim the item, and QC's independent read shows it absent
or misconfigured. Response: normal fix + re-run QC (Step 9.5). No model escalation required.

**HALLUCINATION:** the build agent CLAIMED the item is set/done, but QC's independent
ground-truth read contradicts the claim. Discriminator: (build-agent-claimed == TRUE) AND
(QC-observed == FALSE/absent/different). Fingerprints:
- A LINK the build agent reported that returns 404 / does not exist.
- A phone or SMS From-NUMBER the agent said it set that is not on the node (WF-12/WF-20).
- A TRIGGER the agent said it activated that export shows active:false (WF-4).
- A tag/field/value/workflow-id the agent cited that GET-verification cannot find.
WF-20 ("NO HALLUCINATED ARTIFACTS") is the dedicated detector.

**Escalation on HALLUCINATION-class FAIL (Step 0 recommendation FLIPPED TO REQUIREMENT):**

1. **HARD STOP** — do NOT let the same build agent "fix and continue." A hallucination means
   the build agent's self-report cannot be trusted; silent retry compounds the lie.

2. **REQUIRE a high-reasoning model at thinking HIGH for the redo.** This is the v12.3.5
   Step 0 recommendation FLIPPED FROM RECOMMENDATION TO REQUIREMENT for this case. The redo
   MUST run on a high-reasoning model (e.g. deepseek-v4-pro / Opus-tier) with thinking=HIGH;
   if the current build session is on a lighter model, the build does NOT proceed until
   switched (cross-references and strengthens INSTRUCTIONS.md Step 0).

3. **RE-DO** the affected build steps on the reasoning model at thinking HIGH, restoring from
   the pre-build snapshot if the workflow state is suspect.

4. **RE-RUN QC** (fresh independent MiniMax sub-agent) from scratch against the FULL checklist
   — a hallucination invalidates the whole build agent's report, so QC re-verifies ALL items,
   not just the flagged one.

5. **DISCLOSE to the client:** "QC caught that I reported something that wasn't actually true
   (<the specific item>). I've switched to a high-reasoning model with deep thinking and
   rebuilt + re-verified." Honest disclosure, per the no-lies rule.

6. **LOG the hallucination event** to the build-events ledger: item, claimed value, observed
   value, model that hallucinated, model used for redo.

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
