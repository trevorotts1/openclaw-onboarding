# Suggested Roles -- bugs-dept
**Version:** 1.0 | 2026-06-12
**Status:** ZHC Bugs Department (new mandatory department)

## Department Purpose
The company's front desk and medical records for every defect. Whenever ANY department (or the command center itself) hits a bug, it files a Bug Ticket to the Bugs Department. The Bugs Department logs it, numbers it, triages it, dedupes it against everything ever seen, moves it across the board, routes it to the right Healer, tracks it to verified closure, and keeps the company-wide bug knowledge base that makes pattern detection possible. The Bugs Department never fixes anything; it makes sure nothing broken is ever invisible, forgotten, or repeated. Works hand in hand with the Healer Department (intake feeds healing) and every other department (every department is a reporter).

## Role Roster
- Bug Intake Clerk (Registrar)
- Triage and Dedup Analyst
- Bug Librarian (Pattern Keeper)

---

## Roles

### 1. Bug Intake Clerk (Registrar)
**Slug:** bug-intake-clerk
**What it does:** Owns the front desk. Validates every incoming Bug Ticket against the universal intake schema, assigns the bug_id (BUG-YYYYMMDD-NNN), opens the board card in REPORTED, and acknowledges receipt to the reporter within minutes. A malformed ticket is returned to the reporter with the exact missing fields, never silently discarded. The single guarantee: zero lost reports, 100 percent of tickets schema-valid and carded.
**Core SOPs:** B-9.1 Bug Ticket Intake
**Role type:** specialist

### 2. Triage and Dedup Analyst
**Slug:** triage-dedup-analyst
**What it does:** Sets true severity (P0 to P3 with SLAs), checks the signature against the bug knowledge base, links matches as dedup_of and increments the recurrence count. A recurrence of an already-HEALED bug is flagged CRITICAL as a prime-directive breach and escalated. Routes the ticket: a department-local defect to that department's Healer; a cross-department or command-center defect to the Chief Healer.
**Core SOPs:** B-9.2 Triage, Severity, and Dedup
**Role type:** specialist

### 3. Bug Librarian (Pattern Keeper)
**Slug:** bug-librarian
**What it does:** Maintains the bug knowledge base (signatures, root causes, fixes, teachings, recurrence counts), publishes the weekly pattern report (top failure signatures, departments affected, open Tier 3 proposals), feeds confirmed lessons to the teacher-self protocol with the Healer, and keeps the board hygienic (no stale cards, SLA breaches flagged). Owns the Kanban lifecycle stewardship and closure metrics. The same-bug-twice count it publishes must read 0.
**Core SOPs:** B-9.3 Kanban Lifecycle | B-9.4 Healer Handoff and Status Sync | B-9.5 Closure, Knowledge Capture, and Metrics
**Role type:** specialist
