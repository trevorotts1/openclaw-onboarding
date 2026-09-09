# SOP-RR-02 — Durable Ticket Ledger (BINDING)

**SOP ID:** `SOP-RR-02-DURABLE-LEDGER`
**Owner:** Ticket Clerk
**Type:** Always-on, per-ticket
**Scope:** All ticket state written by both operator transports.

> **RR-017 CORRECTION (2026-09-08, BINDING):** the LIVE system of record for the
> current-v2 pipeline is the **RR-04 n8n Data Tables ledger** (subworkflow
> `RR-04-ledger` — the sole ticket-state writer, fail-closed status gate). The
> SQLite ledger this SOP originally described is **compatibility-only**: use it
> for offline drills and historical migration, NEVER against production ticket
> state. Starting it beside the live pipeline would be a competing writer —
> prohibited. Authoritative contract: `blackceo-fleet-ops:rescue/contract-manifest.json`.

**HARD RULE:** RR-04 Data Tables are the SYSTEM OF RECORD. The legacy SQLite
ledger (`~/clawd/fleet-heartbeat/rescue/tickets.db`) is compatibility-only.
`RR-04-ledger` is the SOLE production writer — one writer, no races.

---

## 9. Standard Operating Procedures

### SOP 9.1 — Open on Ticket-In (idempotent)

**Steps:**
1. On escalate, the current-v2 pipeline mints/folds the ticket through the
   `RR-04-ledger` subworkflow (`op: mint-or-recur`, dedup_key identity). For
   OFFLINE DRILLS only, the legacy path is `rescue_ledger.py open --ticket-id <id>`:
   with the nine-field context (+ `--incomplete --missing-fields …` for degraded
   tickets). `open_ticket` is INSERT-OR-IGNORE on `ticket_id` — a re-delivered
   escalation is a no-op, never a double-open — and logs one `escalate` exchange
   toward the durable 25/day counter.

**Failure mode:** never write as root (a root-owned file under the rescue dir wedges
the toolchain — the tool WARNs loudly).

---

### SOP 9.2 — Answer + Resolve (idempotent) — OFFLINE DRILLS ONLY

**Steps (drill tooling; live answers close through `RR-04-ledger op: close`):**
1. On answer-out: `rescue_ledger.py answer --ticket-id <id> --answer "…"
   --fix-class <class> --fix-mode <dry-run|live>`. `record_answer` fills only an
   empty answer, so a re-pulled ticket is never re-answered.
2. On confirmed RESOLVED: `rescue_ledger.py resolve --ticket-id <id>` (stamps
   `ts_resolved`).

---

### SOP 9.3 — The 25/day Cap (drill counter; live cap is `rr_cap_counters`)

**Steps:** For OFFLINE DRILLS, the per-client daily cap is answered from
`rescue_ledger.py count-today --client <client> --cap 25` (exit 3 = at/over).
The LIVE current-v2 cap lives in the intake pipeline's `rr_cap_counters` table —
never answer a live cap question from the drill ledger.

---

### SOP 9.4 — Schema (drill ledger; the row is the record)

`tickets(ticket_id, ts_open, ts_answered, ts_resolved, client, person, agent_name,
box, box_type, oc_version, problem, already_tried, return_to, answer, tier,
fix_class, fix_mode, status, return_delivered, incomplete, missing_fields, source,
cc_task_id, updated_at)`; `exchanges(...)` for the audit + cap; `meta(schema_version,
platform)`. Status vocabulary: `open | in_progress | answered | resolved | incomplete
| blocked | closed`.

---

### SOP 9.5 — Migration on Redeploy (historical migration tooling)

**When to run:** Before any n8n relay redeploy (which would wipe staticData).

**Steps:** Export the workflow's staticData, then `python3
migrate-rescue-staticdata.py --export <file>` folds every historical ticket +
counter into the ledger. IDEMPOTENT — safe to re-run, never double-imports. Confirm
the export's exact shape against a REAL export before the live cutover (Open
Question 4).

**Outputs:** A durable, queryable ticket history + SLA timestamps + per-client
counters that survive any workflow re-import.
**Hand to:** SOP-RR-03 (board + aging), QC/Postmortem (weekly review).
