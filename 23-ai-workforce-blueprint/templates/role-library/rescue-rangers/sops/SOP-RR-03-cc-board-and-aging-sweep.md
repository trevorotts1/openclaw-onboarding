# SOP-RR-03 — Command Center Board & Aging Sweep (BINDING)

**SOP ID:** `SOP-RR-03-CC-BOARD-AGING`
**Owner:** Ticket Clerk
**Type:** Always-on (board) + scheduled (aging sweep)
**Scope:** Every ticket's visibility on the Command Center Kanban + the SLA sweep.
**HARD RULE:** Boarding is a VIEW, never a gate. A board outage must NEVER block
answering a distress call — `rescue_cc_board.py` is fail-soft and always returns.

---

## 9. Standard Operating Procedures

### SOP 9.1 — Board on Ticket-Open

**Steps:**
1. On ticket-open, `rescue_cc_board.ingest_ticket(...)` → `POST /api/tasks/ingest`
   with `department_slug:"rescue-rangers"`, `persona:"Director of Rescue Rangers"`,
   and `idempotency_key = ticket_id` (a re-delivered escalation dedupes to the SAME
   card server-side).
2. Stamp the returned `task_id` back onto the ledger row (`stamp_cc_task`) so the
   card and the durable record are joined.

**Failure mode:** CC unreachable → the movement receipt records the miss
(`cc-board/<ticket_id>.json`), the ticket proceeds ungrouped, the rescue is NOT
blocked.

---

### SOP 9.2 — Advance the Card Through the Lifecycle

**Status → CC column mapping:** `open`/`incomplete` → `backlog`, `in_progress` →
`in_progress`, `answered` → `review`, `resolved`/`closed` → `done`, `blocked` →
`blocked`. Only values in the authoritative CC `TaskStatus` enum are sent (a bogus
status is refused offline, before any network call). Every advance attempt writes a
movement receipt so a failed advance is VISIBLE on disk, never silent.

---

### SOP 9.3 — The Aging / SLA Sweep

**When to run:** On a cron beside the Command Center's stale-task sweep (e.g. hourly).

**Steps:**
1. `rescue_ledger.py aging --older-than-minutes N` (or
   `rescue_cc_board.aging_sweep(ledger, N)`) reads the durable ledger for
   open/in-progress/answered/blocked tickets past the cutoff.
2. Hand the aged list to the Dispatcher (who decides re-dispatch, tier bump, or an
   Operator page).
3. Page the Fixer topic **ONCE per aged ticket (deduped)** — the aging alarm must
   never become its own furnace.

**Why this exists (kills R6):** the old design swept nothing; a ticket could sit
stale forever if both transports were down but the relay was up.

---

### SOP 9.4 — Weekly Digest

**Steps:** `rescue_ledger.py digest --since <ISO>` → post the Operator a compact SLA
scoreboard (total, by-status, per-client volume, answered vs still-open). This is the
department's honest, query-backed SLA record — never a self-report.

**Outputs:** Full open-ticket + aging + SLA visibility on the Command Center.
**Hand to:** Dispatcher (aging decisions), QC/Postmortem (weekly review).
