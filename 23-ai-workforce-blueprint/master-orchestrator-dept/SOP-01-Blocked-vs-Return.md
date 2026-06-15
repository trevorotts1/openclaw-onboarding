# SOP-01 -- Blocked vs Return-to-Orchestrator
**Version:** 1.0.0 | 2026-06-15
**Applies to:** ALL agents at ALL levels -- worker specialists, department heads, Master Orchestrator (fleet-wide, Mac and VPS)
**Status:** CANONICAL -- cross-platform fleet standard

---

## Purpose

This SOP defines the ONLY two valid responses when a worker agent cannot complete a task:

1. **Return to Orchestrator** -- the agent hands the task back with a structured note so the orchestrator can re-route it or escalate.
2. **Blocked (human-only)** -- the orchestrator parks the task in Blocked ONLY after verifying the four-way test below.

The Blocked column is NOT a dumping ground. It is a waiting room for a specific named human performing a specific human-only action. Everything else circulates.

---

## Binding Rules (no exceptions)

| Rule | Statement |
|------|-----------|
| **W1** | A WORKER AGENT NEVER sets status=blocked directly. Workers do not have write authority over the Blocked column. |
| **W2** | When a worker cannot complete a task, it emits a structured handback to the orchestrator (see schema below) and sets status=backlog. It does NOT park the task. |
| **W3** | "The tool errored," "the API timed out," "I don't know which department," "the artifact is wrong," "I'm not sure how" are NOT blocks. They are agent-fixable or orchestrator-routable. |
| **O1** | The orchestrator is the SOLE authority that may write status=blocked on a task. |
| **O2** | Before the orchestrator sets status=blocked, it MUST verify all three of: (a) the next action is one of {decision, approval, credential/access, payment}; (b) that action can ONLY be done by a human -- no installed agent/department/tool has the authority or the secret; (c) the card names blocked_on_human + a concrete one-line ask. If any of (a)-(c) fails, it is NOT blocked. |
| **O3** | After setting status=blocked, the orchestrator immediately notifies the named human: owner via Telegram, operator via Rescue Rangers webhook (per AGENTS.md). |
| **O4** | Re-route attempt count (qc_reroute_attempts) is capped at 3. After 3 bounces with no resolution, the orchestrator escalates to the operator with a structured report -- it does NOT loop forever. |

---

## The Four-Way Classifier

Every task returned to the orchestrator is classified into exactly one of these four categories:

### Category 1: NEEDS-HUMAN (TRUE-BLOCKED)
**Result:** orchestrator sets status=blocked with required fields.

Deterministic test -- ALL three must hold:
- (a) The next action is one of: DECISION, APPROVAL, CREDENTIAL/ACCESS, PAYMENT
- (b) That action can ONLY be done by a human (owner or operator) -- no installed agent/department/tool has the authority or the secret to do it
- (c) The card names blocked_on_human + a concrete one-line ask

**The ONLY four qualifying human actions:**
1. **DECISION** -- a judgment/choice that is the owner's or operator's to make and cannot be delegated to an agent (e.g., "approve which of these 3 directions," "confirm the legal position")
2. **APPROVAL / SIGN-OFF** -- a human must give permission before work can proceed or ship
3. **CREDENTIAL or ACCESS GRANT** -- an API key, an account login, a permission, an OAuth grant, a 2FA code -- only a human controls it
4. **PAYMENT** -- a spend a human must authorize

**Examples of genuine blocks:**
- "Owner must pick brand direction A/B/C" (DECISION)
- "Operator must paste the Stripe live key" (CREDENTIAL)
- "Owner must approve the contract before it is sent" (APPROVAL)
- "Owner must authorize the $500 ad spend" (PAYMENT)

### Category 2: AGENT-FIXABLE
**Result:** orchestrator re-routes to a department/agent that CAN do it; never touches Blocked.

Deterministic test: the next action is a normal domain operation some agent CAN do (generate, write, code, research, call an API the box already has keys for, retry a transient failure, pick a department).

Includes: "I am not sure which department" (router decides) and "the first agent was wrong fit" (re-route).

### Category 3: BROKEN-BUT-AGENT-COULD
**Result:** worker emits a structured handback; orchestrator diagnoses and re-routes or drops to Backlog.

Deterministic test: an agent attempted the work and hit a concrete failure (tool error, validation fail, missing-but-obtainable input, wrong artifact, QC fail, dependency on another task) that an agent COULD resolve given the right department/context/retry.

This is also the destination for QC-fail loops instead of an infinite re-route.

### Category 4: STALE
**Result:** time/no-progress trigger auto-returns to orchestrator.

Deterministic test: now() - last_progress_at > threshold for the card's current column AND status NOT IN (done, archived).

**Per-column thresholds (defaults):**
- in_progress: 24 hours
- review: 12 hours
- to-do/backlog: 48 hours
- blocked: 72 hours before re-ping

**Sub-cases:**
1. Stale in in_progress/review/backlog/to-do -- orchestrator re-routes (broken-but-agent-could path)
2. Stale in Blocked -- re-ping the named blocked_on_human ONCE; if still no response after a second threshold (+72h), return to orchestrator to re-classify

---

## Structured Handback Schema

When a worker agent cannot complete a task, it emits this structured handback via `POST /api/tasks/{id}/return-to-orchestrator`:

```json
{
  "task_id": "<uuid>",
  "problem": "<one concise line describing exactly what failed>",
  "what_i_tried": "<brief summary of approaches attempted>",
  "what_i_think_it_needs": "<diagnosis -- what the right department or resource would be>",
  "suggested_department": "<slug or null>"
}
```

**Rules for the handback:**
- `problem` MUST be specific and actionable. "It didn't work" is not valid.
- `what_i_tried` MUST be non-empty. A worker that made no attempt has a different problem.
- The handback is routed by the orchestrator -- the worker NEVER decides the destination itself.
- The handback sets status=backlog (or a needs_routing sub-state), NOT status=blocked.

---

## Blocked Card Required Fields

When the orchestrator sets status=blocked (the ONLY entity that may do so), the task MUST carry ALL THREE of these fields:

| Field | Valid values | Meaning |
|-------|-------------|---------|
| `blocked_reason` | decision, approval, credential, payment | Which of the four human-only categories applies |
| `blocked_on_human` | "owner" or "operator" | Who is being waited on |
| `ask` | one-line string | Exactly what that human must do to unblock it |

A task missing any of these three fields is structurally rejected at the API gate (400) -- the orchestrator must supply all three.

---

## Orchestrator Re-Router Algorithm

When a task is returned (via handback, stale sweep, or Blocked-gate rejection), the orchestrator runs this deterministic sequence:

1. READ the structured handback `{problem, what_i_tried, what_i_think_it_needs, suggested_department?}` or the stale record
2. RE-CLASSIFY using the four-way test above
3. If NEEDS-HUMAN: set status=blocked WITH the required blocked_reason/blocked_on_human/ask; notify that human (owner via Telegram, operator via Rescue Rangers webhook)
4. If AGENT-FIXABLE or BROKEN-BUT-AGENT-COULD: run routeTask() across ALL departments, honoring suggested_department as a hint; assign the matching specialist; set status=in_progress; log a task_dispatched event with the diagnosis
5. If routeTask returns no confident match (score < threshold): drop to Backlog under General Task (SOP-00 R8) for human triage -- NOT Blocked
6. Cap re-route attempts at 3 (qc_reroute_attempts): after 3 bounces the orchestrator escalates to the operator with a structured report {task_id, attempts, last_problem, ask}; a card can NEVER loop forever

**The orchestrator NEVER "just fixes it" directly.** It diagnoses + routes + (only for true human-blocks) parks and pings. This is an extension of SOP-00 R2 (orchestrator does no production work) and N2 (Master Orchestrator does no work).

---

## What is NOT a Block

The following are explicitly NOT qualifying block reasons. A task citing any of these as its blocked_reason must be rejected at the gate:

| Claimed reason | Correct classification | Correct action |
|---------------|----------------------|----------------|
| "The tool errored" | BROKEN-BUT-AGENT-COULD | Return to orchestrator with handback |
| "The API timed out" | BROKEN-BUT-AGENT-COULD | Return to orchestrator; orchestrator re-routes or retries |
| "I don't know which department" | AGENT-FIXABLE | Orchestrator runs routeTask(); routes it |
| "The artifact is wrong / QC failed" | BROKEN-BUT-AGENT-COULD | Return to orchestrator with handback |
| "I'm not sure how to do this" | AGENT-FIXABLE | Orchestrator finds the right department |
| "The previous agent was the wrong fit" | AGENT-FIXABLE | Orchestrator re-routes |
| "Waiting on another task to finish" | BROKEN-BUT-AGENT-COULD | Return to orchestrator; orchestrator sequences or re-routes |

---

## STALE Task Detection

Stale detection runs via an in-process cron sweep (stale-task-sweep registered at */10 * * * * in scheduler.ts). The sweep:

1. Selects tasks WHERE archived_at IS NULL AND status NOT IN ('done') AND last_progress_at < (now - column_threshold)
2. For non-Blocked stale tasks: synthesizes a broken-but-agent-could handback and returns to the orchestrator
3. For stale Blocked tasks: re-pings the named blocked_on_human once (Telegram for owner / Rescue Rangers webhook for operator); after a second threshold (+72h), returns to the orchestrator to re-classify

`last_progress_at` is bumped on: any status change, any logged event/activity, any deliverable added, or any human action on a Blocked card.

Disable with DISABLE_STALE_TASK_SWEEP=1 (env).

---

## Enforcement

This doctrine is enforced by CODE, not just prose:

1. **API gate** (`/api/tasks/[id]` PATCH): when status=blocked is requested, requires blocked_reason IN {decision,approval,credential,payment} + blocked_on_human + ask + updated_by_agent_id matching the orchestrator/master agent. Returns 400 otherwise.
2. **Return endpoint** (`/api/tasks/[id]/return-to-orchestrator`): the only path for workers to hand back; writes task_returned event + sets status=backlog + bumps qc_reroute_attempts.
3. **Stale sweep** (`src/lib/jobs/stale-task-sweep.ts`): registered in scheduler.ts; no card rots silently.
4. **Re-router** (ceo-delegation-sweep.ts extended): sweeps needs_routing/returned tasks; honors suggested_department as a hint; enforces the attempt cap.

A rule not auto-failed at the QC gate does not exist. See BLOCKED-IS-GATED.md (sibling to DONE-IS-GATED.md).

---

## Relationship to Other Rules

| Rule | How this SOP extends it |
|------|------------------------|
| SOP-00 R2 (orchestrator does no work) | Extends: orchestrator's re-router work is classification + routing only -- still no production work |
| SOP-00 R8 (general-task fallback) | Extended: no-match tasks drop to Backlog/General Task, NOT Blocked |
| N2 (Master Orchestrator does no work) | Consistent: classifying + routing is coordinating, not working |
| N24 (no silent abandonment) | Extended: the structured handback is the required replacement for silent drop; handback is mandatory, not optional |
| DONE-IS-GATED.md | Sibling: Blocked is now gated the same way Done is gated -- specific authority + specific evidence required |

---

## CHANGELOG

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-06-15 | Initial canonical SOP. Defines four-way classifier (needs-human / agent-fixable / broken-but-agent-could / stale), three mandatory Blocked fields, structured handback schema, orchestrator re-router algorithm, and stale sweep spec. Fleet-wide: both Mac and VPS. Pairs with BLOCKED-IS-GATED.md, N36 (AGENTS.md), and Command Center gate + stale sweep (canary/command-center). |
