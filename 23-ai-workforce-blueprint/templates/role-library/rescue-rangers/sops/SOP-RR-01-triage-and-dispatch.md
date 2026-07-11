# SOP-RR-01 — Triage & Dispatch (BINDING)

**SOP ID:** `SOP-RR-01-TRIAGE-DISPATCH`
**Owner:** Director of Rescue Rangers (Dispatcher)
**Type:** Always-on, per-inbound-ticket
**Scope:** Every escalation the Relay Brain hands the rescue runtime.
**HARD RULE:** No distress call is ever dropped. Every inbound escalation gets a
ledger row, a board card, and either an answer or a clear operator page.

---

## 9. Standard Operating Procedures

### SOP 9.1 — Read + Cap-Check FIRST

**When to run:** On every inbound ticket.

**Steps:**
1. Read the nine fields (`person`, `clientName`, `agentName`, `boxName`, `boxType`,
   `openclawVersion`, `problem`, `alreadyTried`, `returnTo`). The `alreadyTried`
   list tells you what NOT to repeat. INCOMPLETE tickets carry `missing_fields` —
   work them with degraded context; never drop them.
2. **Cap check before anything else:** `python3 rescue_ledger.py count-today
   --client <client> --cap 25` (exit 3 = at/over). At cap → do NOT loop: instruct
   the client agent to ping the Operator (`5252140759`) directly, and page the
   Operator. The cap is a furnace guard, not a courtesy.

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
2. Confirm the **Ticket Clerk** has opened the ledger row and boarded the ticket on
   the Command Center Kanban (a card in `backlog`). **No ticket is worked that is not
   on the board.**

---

### SOP 9.4 — Page the Operator (a first-class outcome)

**Page `5252140759` when any of:** no-reply/timeout on a HIGH ticket; anything
touching billing/credentials/DNS/model-sovereignty (never auto-fixed); a client at
the daily cap still unresolved; a Diagnostician marks "cannot proceed without a
one-way-door decision"; a P1 or a 3rd consecutive same-defect fail. Paging the human
is success, not failure. One-way doors are the Operator's — never authorize an
irreversible action.

---

### SOP 9.5 — Enforce the Outcome Contract

**Steps:** A dispatch is not complete until an answer (or a clear escalation) is
posted back through the relay's `answer` action so the CLIENT's own agent can tell
its owner one of: (a) we solved it, (b) here is what you should do, (c) here is the
answer. A ticket answered in the operator group but never returned to the client
agent is an **incomplete dispatch** — chase the return leg (the VPS `status`-poll
return leg exists for exactly this).

**Outputs:** Triaged, tiered, boarded, dispatched ticket with a durable ledger row.
**Hand to:** Diagnostician / Structured-Fix Operator / Operator (per SOP 9.4).
