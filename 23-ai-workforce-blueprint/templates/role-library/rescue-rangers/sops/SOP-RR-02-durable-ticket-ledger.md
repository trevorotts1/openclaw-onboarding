# SOP-RR-02 — Durable Ticket Ledger (BINDING)

**SOP ID:** `SOP-RR-02-DURABLE-LEDGER`
**Owner:** Ticket Clerk
**Type:** Always-on, per-ticket
**Scope:** All ticket state written by both operator transports.
**HARD RULE:** The SQLite ledger (`~/clawd/fleet-heartbeat/rescue/tickets.db`, WAL) is
the SYSTEM OF RECORD. The n8n `workflowStaticData` queue remains only a transport
buffer. `rescue_ledger.py` is the SOLE writer — one writer, no races.

---

## 9. Standard Operating Procedures

### SOP 9.1 — Open on Ticket-In (idempotent)

**Steps:**
1. On escalate, the receiver/poller calls `rescue_ledger.py open --ticket-id <id>`
   with the nine-field context (+ `--incomplete --missing-fields …` for degraded
   tickets). `open_ticket` is INSERT-OR-IGNORE on `ticket_id` — a re-delivered
   escalation is a no-op, never a double-open — and logs one `escalate` exchange
   toward the durable 25/day counter.

**Failure mode:** never write as root (a root-owned file under the rescue dir wedges
the toolchain — the tool WARNs loudly).

---

### SOP 9.2 — Answer + Resolve (idempotent)

**Steps:**
1. On answer-out: `rescue_ledger.py answer --ticket-id <id> --answer "…"
   --fix-class <class> --fix-mode <dry-run|live>`. `record_answer` fills only an
   empty answer, so a re-pulled ticket is never re-answered.
2. On confirmed RESOLVED: `rescue_ledger.py resolve --ticket-id <id>` (stamps
   `ts_resolved`).

---

### SOP 9.3 — The 25/day Cap (durable counter)

**Steps:** The per-client daily cap is the durable replacement for the volatile n8n
counter. Answer the Dispatcher's cap question from `rescue_ledger.py count-today
--client <client> --cap 25` (exit 3 = at/over) — ground truth, never an estimate.

---

### SOP 9.4 — Schema (the row is the record)

`tickets(ticket_id, ts_open, ts_answered, ts_resolved, client, person, agent_name,
box, box_type, oc_version, problem, already_tried, return_to, answer, tier,
fix_class, fix_mode, status, return_delivered, incomplete, missing_fields, source,
cc_task_id, updated_at)`; `exchanges(...)` for the audit + cap; `meta(schema_version,
platform)`. Status vocabulary: `open | in_progress | answered | resolved | incomplete
| blocked | closed`.

---

### SOP 9.5 — Migration on Redeploy

**When to run:** Before any n8n relay redeploy (which would wipe staticData).

**Steps:** Export the workflow's staticData, then `python3
migrate-rescue-staticdata.py --export <file>` folds every historical ticket +
counter into the ledger. IDEMPOTENT — safe to re-run, never double-imports. Confirm
the export's exact shape against a REAL export before the live cutover (Open
Question 4).

**Outputs:** A durable, queryable ticket history + SLA timestamps + per-client
counters that survive any workflow re-import.
**Hand to:** SOP-RR-03 (board + aging), QC/Postmortem (weekly review).
