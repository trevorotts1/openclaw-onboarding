# ZHC Bugs Department -- Standard Operating Procedures (B-9.1 to B-9.5)

**Department:** Bugs
**Version:** 1.0
**Authority:** THE_HEALER_AND_BUGS_DEPARTMENT.md PART 2.4
**SOP count:** 5

These SOPs are the operational backbone of the ZHC Bugs Department. They are transplanted verbatim from the build authority document and govern every function from ticket intake through closure and knowledge capture. All five SOPs are also embedded within the relevant specialist role files (bug-intake-clerk.md, triage-dedup-analyst.md, bug-librarian.md) per the standard role template.

---

## SOP B-9.1 -- Bug Ticket Intake

**Owned by:** Bug Intake Clerk (Registrar)

Validate schema, assign id, open Kanban card in REPORTED, acknowledge reporter, write to the ledger. Failure mode: malformed ticket = return to reporter with the exact missing fields, never silently discard.

---

## SOP B-9.2 -- Triage, Severity, and Dedup

**Owned by:** Triage and Dedup Analyst

Confirm severity (P0 run-dead: SLA heal-start < 30 min; P1: < 4 h; P2: next business cycle; P3: backlog), signature-match against the knowledge base, set dedup_of/recurrence, flag healed-bug recurrences CRITICAL, move card to TRIAGED.

---

## SOP B-9.3 -- Kanban Lifecycle

**Owned by:** Bug Librarian (board hygiene); card moves shared across all three specialists and Healers per the column ownership rules below.

The board columns and who moves cards: REPORTED (Intake Clerk) -> TRIAGED (Analyst) -> HEALING (the assigned Healer owns the card) -> VERIFYING (Healer: fix applied, regression running) -> HEALED (report sent, regression green) -> REGRESSION WATCH (Librarian, time-boxed) -> CLOSED. Every transition stamps the ticket. SLA timers per severity; breaches auto-flag to the Chief Healer and appear in the weekly report.

---

## SOP B-9.4 -- Healer Handoff and Status Sync

**Owned by:** Triage and Dedup Analyst (initiates handoff); Bug Librarian (monitors status sync)

Package the ticket + evidence to the assigned Healer, keep ticket status and Kanban card in lockstep with the Healer's incident ledger (single source of truth: the ticket id links the Healer's incident record), surface blockers.

---

## SOP B-9.5 -- Closure, Knowledge Capture, and Metrics

**Owned by:** Bug Librarian (Pattern Keeper)

On HEALED: capture root cause, fix summary, SOP/core-file patches, teaching link into the knowledge base; move through REGRESSION WATCH to CLOSED on schedule; publish weekly metrics to the operator: new bugs, healed, mean time to heal, SLA breaches, and the same-bug-twice count, which must read 0.

---

*All five SOPs are also embedded in the relevant specialist role files (bug-intake-clerk.md carries B-9.1; triage-dedup-analyst.md carries B-9.2; bug-librarian.md carries B-9.3 and B-9.5) with full expanded step-by-step detail. This file is the SOP library reference index for the Bugs Department.*
