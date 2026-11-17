# SOP-RR-01 — Triage & Dispatch (BINDING)

**SOP ID:** `SOP-RR-01-TRIAGE-DISPATCH`
**Owner:** Director of Rescue Rangers (Dispatcher)
**Type:** Always-on, per-inbound-ticket
**Scope:** Every escalation the Relay Brain hands the rescue runtime.
**HARD RULE:** No distress call is ever dropped. Every inbound escalation gets a
ledger row, a board card, and either an answer or a clear operator page.

> **RR-017 CORRECTION (2026-09-08):** "ledger row" means the live **RR-04 n8n
> Data Tables** ledger (current-v2 pipeline). The Python SQLite ledger is
> compatibility-only drill tooling; its `count-today` command in SOP 9.1 applies
> to DRILLS ONLY — the live cap lives in the intake pipeline's `rr_cap_counters`
> table. Contract: `blackceo-fleet-ops:rescue/contract-manifest.json`.

---

## 9. Standard Operating Procedures

### SOP 9.1 — Read + Cap-Check FIRST

**When to run:** On every inbound ticket.

**Steps:**
1. Read the nine fields (`person`, `clientName`, `agentName`, `boxName`, `boxType`,
   `openclawVersion`, `problem`, `alreadyTried`, `returnTo`). The `alreadyTried`
   list tells you what NOT to repeat. INCOMPLETE tickets carry `missing_fields` —
   work them with degraded context; never drop them.
2. **Cap check before anything else:** read the live `rr_cap_counters` table and
   record the reading as step 2 of the case (`rr_step_gate.py record --step 2`,
   SOP-RR-06). The drill ledger is never used for a live ticket. At cap → do NOT loop: deliver
   outcome (b) — instruct the client's agent to have its owner escalate through the Rescue Rangers escalation section (never a personal chat) — and page the Operator. The client-instruction IS the
   outcome (b); it is delivered by the client's own agent and is a complete
   dispatch, never a silent drop. The cap is a furnace guard, not a courtesy.

**Failure mode:** ledger unreachable → treat as "cannot confirm cap," page the
Operator rather than risk a furnace loop.

---

### SOP 9.2 — Tier the Ticket (FIX-RESCUE-05)

**Steps:**
1. Default tier **MEDIUM**. Assign **FAST** for a known single-symptom,
   low-blast-radius class (offset rewind, orphan-gateway clear, cron park); **LONG**
   for multi-step diagnosis or a config-touching fix; **HIGH** priority for anything
   client-visible-down (gateway down, billing furnace, box unreachable).
2. The tier sets the fix budget the Structured-Fix Operator may spend: **FAST 180s /
   LONG 1,320s / default 300s.** Record tier + budget in the ledger.

---

### SOP 9.3 — Dispatch + Board

**Steps:**
1. Route to the **Diagnostician** when the root cause is unknown; straight to the
   **Structured-Fix Operator** when the class is already identified and has a
   sanctioned `remediate.sh` card.
2. Confirm the ledger row exists. The Command Center copies the ticket onto the
   Kanban board by itself (department `rescue-rangers`). **The board is a view, never
   a gate: do not wait for a card before working a ticket.**

---

### SOP 9.4 — Page the Operator (a first-class outcome, LAST resort)

**The three-tier order is BINDING.** (1) Instruct the client's agent (outcome b) —
the PRIMARY route for coaching/how-to classes and client-account actions (OAuth
dashboard steps, billing top-up, owner confirmation); never a page. (2) The rescue
AI self-fixes reachable-box infrastructure using our access — the box's `rescue-*`
SSH alias from the operator's `~/.ssh/config` plus the provider env var NAME from
`~/.openclaw/secrets/.env` (names only, never a value; values live in the secrets
env). Check the credential exists BEFORE escalating; a missing credential is itself
a finding to report. (3) Page the Operator ONLY after tiers 1-2 ran and the ticket
can document why neither worked, or on a one-way-door class that pages on the class
alone.

**Page the Operator when any of:** no-reply/timeout on a HIGH ticket; anything
touching credential-ACTION (rotate/regenerate/revoke)/DNS/deletion/model-
sovereignty (never auto-fixed — pages on the class alone); a client at the daily
cap still unresolved; a Diagnostician marks "cannot proceed without a one-way-door
decision"; a P1 or a 3rd consecutive same-defect fail; a box UNREACHABLE after the
rescue AI's own SSH attempts. The page carries WHAT THE RESCUE AI ALREADY TRIED AND
WHY IT FAILED. Paging the human is success, not failure. One-way doors are the
Operator's — never authorize an irreversible action.

---

### SOP 9.5 — Enforce the Outcome Contract

**Steps:** A dispatch is not complete until the answer is in the outbox WITH the
words the owner will read (`owner_message`), the client's box has collected and
acknowledged it, and the owner-message receipt is recorded. The owner hears one of:
(a) we solved it and checked it, (b) here is the one thing only you can do,
(c) here is the answer, (d) a person on the team now has it. A ticket answered in
the operator group but never acknowledged by the client's box is an **incomplete
dispatch** — chase the return leg. There is no box-side `status` poll.

**Outputs:** Triaged, tiered, boarded, dispatched ticket with a durable ledger row.
**Hand to:** Diagnostician / Structured-Fix Operator / Operator (per SOP 9.4).
