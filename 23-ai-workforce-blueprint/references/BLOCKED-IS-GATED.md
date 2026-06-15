# BLOCKED-IS-GATED -- Blocked Column Status Contract

**Sibling doc to DONE-IS-GATED.md. Same gating principle: a status requires a specific authority + specific evidence before it is accepted.**

---

## A task is `status:blocked` ONLY when ALL of the following are true:

1. **blocked_reason is set** to exactly one of: `decision`, `approval`, `credential`, `payment` -- these are the ONLY four qualifying human-only categories.
2. **blocked_on_human is set** to "owner" or "operator" -- the task names who is being waited on.
3. **ask is set** to a one-line string describing exactly what that human must do to unblock it.
4. **Authority check passes**: the request was made by the Master Orchestrator / master agent (`is_master = 1`). Worker agents do not have write authority over the Blocked column.

**Missing any of these four: the Blocked gate rejects the request (HTTP 400).** The Blocked column is structurally impossible to misuse at the API layer -- not just a matter of trust.

---

## The Authority Model

| Who can set blocked? | How? |
|----------------------|------|
| Master Orchestrator / master agent | PATCH /api/tasks/{id} with status=blocked + all three required fields. Must pass the four-way classifier in SOP-01 first. |
| Worker agents | NEVER. Workers call POST /api/tasks/{id}/return-to-orchestrator with a structured handback instead. |
| Human operators (UI drag-drop) | The drag-into-Blocked path opens a required-fields modal; the drop is blocked if the three fields are not filled. The UI enforces the same contract as the API. |

---

## The Four Qualifying Human-Only Categories

A task is blocked ONLY when the next action requires a human to perform exactly one of these:

| blocked_reason | What it means | Example ask |
|---------------|--------------|-------------|
| `decision` | A judgment/choice only the owner or operator can make | "Owner: please select one of the three brand directions attached" |
| `approval` | Human must give permission before work proceeds or ships | "Owner: please approve the draft contract at [link] before we send" |
| `credential` | An API key, login, OAuth grant, 2FA code only a human controls | "Operator: please paste the Stripe live API key into the env" |
| `payment` | A spend the human must authorize | "Owner: please authorize the $500 Facebook ad spend" |

---

## What Blocked is NOT

The Blocked column is NOT for:
- Tasks where the tool errored (return to orchestrator)
- Tasks that are waiting on a dependency (return to orchestrator)
- Tasks the agent does not know how to complete (agent-fixable; re-route)
- Tasks with a wrong artifact or QC failure (broken-but-agent-could; return to orchestrator)
- Transient API failures (return to orchestrator; retry)
- "I don't know which department" (agent-fixable; orchestrator routes)

None of these are Blocked. They are returned to the orchestrator for re-routing or re-classification.

---

## Writers of these fields and the gate each must call

| Write | Writer | Gate required before write |
|-------|--------|--------------------------|
| `status = 'blocked'` | Master Orchestrator only | Four-way test (SOP-01) + authority check |
| `blocked_reason` | Master Orchestrator only | One of {decision,approval,credential,payment} |
| `blocked_on_human` | Master Orchestrator only | "owner" or "operator" |
| `ask` | Master Orchestrator only | Non-empty string; one-line human-readable ask |
| `last_progress_at` (reset) | Any human action on the Blocked card | Stale sweep reads this to determine re-ping timing |

---

## Stale-Blocked Lifecycle

A Blocked card that sits past its stale threshold (default 72h with no progress) is NOT silently rotting -- the stale-task-sweep detects it and:

1. Re-pings the named blocked_on_human (Telegram for owner / Rescue Rangers webhook for operator) with the one-line ask
2. If still stale after a second threshold (+72h additional), returns to the orchestrator for re-classification -- sometimes the human-need has evaporated and an agent can now proceed

No card sits in Blocked indefinitely without detection and action.

---

## Enforcement Memory

This document is doctrine propagated into the repo. The enforcement is in the CODE, not in this doc alone:
- API gate in `src/app/api/tasks/[id]/route.ts` PATCH handler (parallel to the Triad gate and QC-authority gate)
- Migration `071_blocked_fields` adds `blocked_reason`, `blocked_on_human`, `ask` columns to the `tasks` table
- UI drag-into-Blocked path in `MissionQueue.tsx` opens a required-fields modal and blocks the drop if fields are empty
- Stale sweep in `src/lib/jobs/stale-task-sweep.ts` registered in scheduler.ts
- QC.md rubric row asserts migration + gate + sweep exist (auto-fail if missing)

**A rule not auto-failed at a QC gate does not exist.**
